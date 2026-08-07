"""Aggregate PUCSL API responses into a daily clean record.

Fuel attribution joins through powerPlantComplex.energyType (the plant-level
fuelUsed/technology fields are empty for 67 of 82 plants — audit 2026-08-08;
the complex→energyType join measured Unknown 55.8% → 0.0%).
"""

import re


def _sanitize(name) -> str:
    # metadata contains a literal XSS probe as one complex name; never pass through markup
    return re.sub(r"<[^>]*>", "", str(name or "")).strip()


def build_fuel_map(plants: list[dict], complexes: list[dict]) -> dict[int, dict]:
    """plant id → {fuel, category, is_renewable}; complexes are the authority."""
    by_slug = {c.get("slug"): c for c in complexes if c.get("slug")}
    fuel_map: dict[int, dict] = {}
    for p in plants:
        pid = p.get("id")
        if pid is None or pid in fuel_map:  # metadata carries duplicate ids (38, 68)
            continue
        complex_obj = p.get("powerPlantComplex") or by_slug.get(p.get("powerPlantComplexSlug")) or {}
        etype = complex_obj.get("energyType") or {}
        fuel = _sanitize(etype.get("name")) or _sanitize(complex_obj.get("energyTypeSlug")) or "Unknown"
        category = _sanitize((etype.get("energyTypeCategory") or {}).get("name"))
        fuel_map[pid] = {
            "fuel": fuel,
            "category": category or None,
            "is_renewable": etype.get("isRenewable"),
            "plant_name": _sanitize(p.get("name")),
        }
    return fuel_map


def build_clean(
    day: str,
    generation: dict,
    reservoir: dict,
    plants: list[dict],
    complexes: list[dict] | None = None,
) -> dict | None:
    # Pin to the single reportDate bucket belonging to `day` (local midnight is
    # stamped T18:30Z of the PREVIOUS calendar date) — a naive date-span fetch
    # returns two buckets and silently doubles totals once the next day lands.
    gen_rows = [r for r in generation.get("data", []) if r.get("dailyTotalEnergyInMwh") is not None]
    report_dates = sorted({r.get("reportDate") for r in gen_rows if r.get("reportDate")})
    if not report_dates:
        return None
    target = report_dates[0]
    gen_rows = [r for r in gen_rows if r.get("reportDate") == target]
    res_rows = [r for r in reservoir.get("data", []) if r.get("reportDate") == target] or reservoir.get("data", [])

    fuel_map = build_fuel_map(plants, complexes or [])
    by_fuel: dict[str, float] = {}
    renewable_mwh = 0.0
    total = 0.0
    plants_out = []
    for row in gen_rows:
        mwh = row.get("dailyTotalEnergyInMwh") or 0
        info = fuel_map.get(row.get("powerPlantId"), {})
        fuel = info.get("fuel", "Unknown")
        by_fuel[fuel] = by_fuel.get(fuel, 0.0) + mwh
        total += mwh
        if info.get("is_renewable"):
            renewable_mwh += mwh
        plants_out.append(
            {
                "plant_id": row.get("powerPlantId"),
                "plant_name": info.get("plant_name"),
                "mwh": mwh,
                "available_capacity_mwh": row.get("availableCapacityInMwh"),
                "fuel": fuel,
                "is_renewable": info.get("is_renewable"),
            }
        )

    reservoirs = [
        {
            "name": _sanitize(r.get("reservoirName")),
            "storage_gwh": r.get("storageInGwh"),
            "rainfall_mm": r.get("rainfallInMm"),
            "mol_below_spill_m": r.get("molBelowSpillInM"),
        }
        for r in res_rows
        if r.get("reservoirName")
    ]
    return {
        "date": day,
        "report_date": target,
        "total_generation_mwh": round(total, 1),
        "renewable_share_pct": round(renewable_mwh / total * 100, 1) if total else None,
        "generation_by_fuel_mwh": {k: round(v, 1) for k, v in sorted(by_fuel.items(), key=lambda kv: -kv[1])},
        "plants": plants_out,
        "reservoirs": reservoirs,
        "total_storage_gwh": round(sum(r["storage_gwh"] or 0 for r in reservoirs), 1),
    }

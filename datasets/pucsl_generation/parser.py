"""Aggregate PUCSL API responses into a daily clean record."""


def build_clean(
    day: str, generation: dict, reservoir: dict, plants: list[dict]
) -> dict | None:
    gen_rows = generation.get("data", [])
    res_rows = reservoir.get("data", [])
    if not gen_rows:
        return None
    fuel_by_plant = {p["id"]: (p.get("fuelUsed") or p.get("technology") or "Unknown") for p in plants}
    by_fuel: dict[str, float] = {}
    total = 0.0
    for row in gen_rows:
        mwh = row.get("dailyTotalEnergyInMwh") or 0
        fuel = fuel_by_plant.get(row.get("powerPlantId"), "Unknown")
        by_fuel[fuel] = by_fuel.get(fuel, 0.0) + mwh
        total += mwh
    reservoirs = [
        {
            "name": r.get("reservoirName"),
            "storage_gwh": r.get("storageInGwh"),
            "rainfall_mm": r.get("rainfallInMm"),
        }
        for r in res_rows
        if r.get("reservoirName")
    ]
    return {
        "date": day,
        "total_generation_mwh": round(total, 1),
        "generation_by_fuel_mwh": {k: round(v, 1) for k, v in sorted(by_fuel.items(), key=lambda kv: -kv[1])},
        "reservoirs": reservoirs,
        "total_storage_gwh": round(sum(r["storage_gwh"] or 0 for r in reservoirs), 1),
    }

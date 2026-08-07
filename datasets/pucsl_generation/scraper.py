"""PUCSL generation & reservoirs via the gendata.pucsl.gov.lk JSON API
(the daily PDFs were discontinued 2025-03; the dashboard API replaced them)."""

import json
import sys
from datetime import date, timedelta

from pipeline.doc import Doc
from pipeline.http import get
from pipeline.runner import TimeBudget
from pipeline.store import Store

from .parser import build_clean

DATASET = "pucsl_generation"
API = "https://gendata.pucsl.gov.lk/api"


def fetch_day(day: date) -> dict:
    frm = f"{day.isoformat()}T00:00:00.000Z"
    to = f"{(day + timedelta(days=1)).isoformat()}T00:00:00.000Z"
    span = f"dateAggregation=day&from={frm}&to={to}"
    return {
        "generation": get(f"{API}/daily-generation-statistics?{span}").json(),
        "reservoir": get(f"{API}/reservoir/storage-rainfall?{span}").json(),
    }


def run(days_back: int = 7, budget_seconds: float = 300) -> int:
    store = Store()
    budget = TimeBudget(budget_seconds)
    plants = get(f"{API}/metadata/power-plants").json().get("data", [])
    complexes = get(f"{API}/metadata/power-plant-complexes").json().get("data", [])
    new_docs = 0
    for offset in range(1, days_back + 1):  # data lags ~1 day
        if budget.expired:
            break
        day = date.today() - timedelta(days=offset)
        doc_id = day.strftime("%Y%m%d")
        probe = Doc(DATASET, doc_id, day.isoformat(), API, sha256="")
        if store.exists(probe):
            continue
        raw = fetch_day(day)
        clean = build_clean(day.isoformat(), raw["generation"], raw["reservoir"], plants, complexes)
        if clean is None:
            print(f"{day}: no data yet")
            continue
        payload = json.dumps(raw, ensure_ascii=False).encode()
        store.write_doc(
            Doc(DATASET, doc_id, day.isoformat(), f"{API}/daily-generation-statistics", Doc.sha256_of(payload)),
            payload,
            "original.json",
            clean,
        )
        print(f"{day}: total {clean['total_generation_mwh']:.0f} MWh, storage {clean['total_storage_gwh']:.0f} GWh")
        new_docs += 1
    store.regenerate_indexes(DATASET)
    print(f"done: {new_docs} new docs")
    return new_docs


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 7)

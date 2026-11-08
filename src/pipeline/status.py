"""Run a scraper, persist its outcome even on failure, and report overdue data."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

from .store import Store

# Publication cadence plus normal release lag; independent of polling frequency.
MAX_AGE_DAYS = {
    "cbsl_daily": 4, "cbsl_price_report": 4, "pucsl_generation": 4,
    "cbsl_weekly": 21, "tbill_auctions": 21, "wer": 21, "forbes_tea": 21,
    "sltda_arrivals": 65, "nmra_registrations": 45, "edb_indicators": 730,
    "cbsl_prices": 60, "cbsl_activity": 60, "cbsl_monetary": 60,
    "cbsl_external": 60, "cbsl_fiscal": 430, "cbsl_financial": 240,
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def make_status(dataset: str, previous: dict, before: dict, latest: dict,
                error: str | None, now: datetime) -> dict:
    published = latest.get("date")
    try:
        age = (now.date() - datetime.fromisoformat(published).date()).days
        overdue = age > MAX_AGE_DAYS[dataset] or age < -1
    except (TypeError, ValueError):
        overdue = True
    state = "error" if error else ("overdue" if overdue else "ok")
    changed = (before.get("doc_id"), before.get("data")) != (latest.get("doc_id"), latest.get("data"))
    return {
        "dataset": dataset, "checked_at": now.isoformat(),
        "last_successful_check_at": previous.get("last_successful_check_at") if error else now.isoformat(),
        "publication_date": published, "max_age_days": MAX_AGE_DAYS[dataset],
        "status": state, "outcome": "failed" if error else ("updated" if changed else "unchanged"),
        "error": error,
        "message": error or ("Latest publication is overdue or unavailable" if overdue else "Source checked successfully"),
    }


def run(dataset: str) -> int:
    if dataset not in MAX_AGE_DAYS:
        raise ValueError(f"Unknown dataset: {dataset}")
    directory = Store().dataset_dir(dataset)
    previous = read_json(directory / "status.json")
    before = read_json(directory / "latest.json")
    error = None
    try:
        result = subprocess.run([sys.executable, "-m", f"datasets.{dataset}.scraper"],
                                capture_output=True, text=True, timeout=480)
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        if result.returncode:
            lines = (result.stderr or result.stdout).strip().splitlines()
            error = lines[-1][:1500] if lines else f"Scraper exited {result.returncode}"
    except subprocess.TimeoutExpired:
        error = "Scraper exceeded its 480 second time budget"
    status = make_status(dataset, previous, before, read_json(directory / "latest.json"), error,
                         datetime.now(timezone.utc))
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "status.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(status, indent=2) + "\n")
    temporary.replace(target)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as stream:
            stream.write(f"### {dataset}\n\n| Publication | Check | Outcome | Status |\n|---|---|---|---|\n"
                         f"| {status['publication_date'] or 'none'} | {status['checked_at']} | {status['outcome']} | {status['status']} |\n\n")
            stream.write(status["message"].replace("<", "&lt;") + "\n")
    print(json.dumps(status))
    return 0 if status["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))

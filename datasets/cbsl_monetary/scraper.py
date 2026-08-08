"""CBSL monetary sector — interest rates, reserve money, monetary survey."""

import sys

from pipeline.cbsl_tables import Source, harvest

from .parser import (
    parse_bank_balance_sheet,
    parse_cbsl_balance_sheet,
    parse_interest_rates,
    parse_monetary_survey,
    parse_reserve_money,
    parse_sectoral_credit,
)

DATASET = "cbsl_monetary"
LISTING = "https://www.cbsl.gov.lk/en/statistics/statistical-tables/monetary-sector"

SOURCES = [
    Source("rates", LISTING, ("interest rates - monthly",)),
    Source("reserve_money", LISTING, ("reserve money", "monthly")),
    Source("survey", LISTING, ("monetary survey - monthly",)),
    Source("cbsl_bs", LISTING, ("assets and liabilities of cbsl - monthly",)),
    Source("bank_bs", LISTING, ("assets and liabilities of commercial banks - monthly",)),
]


def _last(points: list[dict]) -> dict:
    return points[-1] if points else {}


def build(wb: dict) -> dict:
    rates = parse_interest_rates(wb["rates"])
    reserve = parse_reserve_money(wb["reserve_money"])
    survey = parse_monetary_survey(wb["survey"])
    credit = parse_sectoral_credit(wb["survey"])
    cbsl_bs = parse_cbsl_balance_sheet(wb["cbsl_bs"])
    bank_bs = parse_bank_balance_sheet(wb["bank_bs"])
    return {
        "interest_rates": rates,
        "reserve_money": reserve,
        "survey": survey,
        "sectoral_credit": credit,
        "cbsl_balance_sheet": cbsl_bs,
        "bank_balance_sheet": bank_bs,
        "latest": {
            "month": _last(reserve.get("reservemoneyrsmillion_total", [])).get("t"),
            "opr_pct": _last(rates.get("overnightpolicyrateoprb", [])).get("v"),
            "sdfr_pct": _last(rates.get("standingdepositfacilityratesdfrb", [])).get("v"),
            "slfr_pct": _last(rates.get("standinglendingfacilityrateslfrb", [])).get("v"),
            "bank_rate_pct": _last(rates.get("bankratec", [])).get("v"),
            "reserve_money_rs_mn": _last(reserve.get("reservemoneyrsmillion_total", [])).get("v"),
            "money_multiplier_m2b": _last(reserve.get("moneymultiplier_m2b", [])).get("v"),
            "broad_money_m2b_rs_mn": _last(survey.get("broadmoneym2b", [])).get("v"),
        },
    }


def run(_budget_seconds: float = 300) -> int:
    return harvest(DATASET, SOURCES, build, LISTING)


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)

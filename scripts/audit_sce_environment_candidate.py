#!/usr/bin/env python3
"""Offline acceptance of an isolated E candidate; no simulation or API calls.

Requires complete independent HTML/PDF component agreement. Date checks do not
certify gas/news vintages, and current-CPI-day inputs are not B cutoff inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from socioverse.schemas import EnvironmentBundle


def audit(folder: Path) -> dict:
    def read(name):
        return json.loads((folder / name).read_text())

    summary = read("summary.json")
    assert summary["candidate_written"] and not summary["issues"]
    assert summary["component_handoff_count"] == 0
    assert summary["component_html_unchecked_count"] == 0
    checks = read("component_html_checks.json")
    assert len(checks) == summary["components_extracted"]
    assert all(r["status"] == "agree" for r in checks)
    headline_checks = read("headline_html_checks.json")
    assert summary["headline_html_unchecked_count"] == 0
    assert all(r["status"] == "agree" for r in headline_checks)
    bundle = read("environment_candidate.json")
    EnvironmentBundle.model_validate(bundle)
    external = read("external_events_candidate.json")
    assert bundle["provider_args"]["signals_by_step"] == external["records_by_step"]
    assert bundle["provider_args"]["events_by_step"] == external["events_by_step"]
    month_checks = []
    for step, target in enumerate(summary["targets"]):
        rows = external["records_by_step"][str(step)]
        news = external["events_by_step"][str(step)]
        cutoff = datetime.fromisoformat(external["as_of"][str(step)])
        assert len(rows) == 77 and len(news) >= 30
        # Existing selection deliberately leaves A1+strong news uncapped.
        if len(news) > 30:
            assert all(r["tier"] == "front_page+strong" for r in news)
        assert len({r["signal_id"] for r in rows}) == len(rows)
        assert all(datetime.fromisoformat(r["published_at"]) <= cutoff for r in rows)
        assert all(r["pub_date"] <= cutoff.date().isoformat() for r in news)
        assert all(r["selection_cutoff"] == cutoff.date().isoformat() for r in news)
        assert all(r["eligibility"] in ("eligible", "vintage_unverified") for r in rows)
        gas_rows = [r for r in rows if r["eligibility"] == "vintage_unverified"]
        assert all(r["signal_id"].startswith("eia_gasoline_retail_") for r in gas_rows)
        gas = len(gas_rows)
        assert gas == 13
        month_checks.append({"target_month": target, "as_of": cutoff.isoformat(),
                             "numeric_signals": len(rows), "news": len(news),
                             "gasoline_vintage_unverified": gas})
    return {"schema_valid": True, "target_months": len(month_checks),
            "signal_count": sum(r["numeric_signals"] for r in month_checks),
            "selected_step_news_count": sum(r["news"] for r in month_checks),
            "independent_component_agreements": len(checks), "month_checks": month_checks,
            "independent_cpi_headline_agreements": len(headline_checks),
            "date_filter_valid": True, "strict_pit_certified": False,
            "remaining_boundaries": ["gasoline current snapshot vintage/date assumption",
                                     "NYT current archive text vintage",
                                     "current-month CPI-day cutoff is not B previous-month-end"],
            "real_llm_calls": 0, "paid_mcp_calls": 0, "source_config_modified": False}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("candidate_dir", type=Path)
    args = ap.parse_args()
    result = audit(args.candidate_dir)
    with (args.candidate_dir / "acceptance.json").open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    files = sorted(p for p in args.candidate_dir.iterdir() if p.is_file())
    with (args.candidate_dir / "manifest.sha256").open("x") as handle:
        for path in files:
            handle.write(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    print(json.dumps({k: v for k, v in result.items() if k != "month_checks"}))


if __name__ == "__main__":
    main()

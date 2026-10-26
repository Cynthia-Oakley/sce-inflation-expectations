#!/usr/bin/env python3
"""Refresh original English Fox leads for the two manual-sample months."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.experiments.fox_mechanism_preparation import refresh_existing_english
from studies.sce_inflation_expectations.fox_news_archive import UrlLibFetcher


def main():
    result = refresh_existing_english(ROOT, UrlLibFetcher(min_interval=2.0, timeout=30.0, max_retries=2))
    print({month: len(entries) for month, entries in result.items()})


if __name__ == "__main__":
    main()

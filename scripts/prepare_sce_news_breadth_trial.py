#!/usr/bin/env python3
"""Freeze varied news-count inputs for the shared engine; no API calls."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.experiments.news_breadth import prepare

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    print(json.dumps(prepare(p.parse_args().out),ensure_ascii=False,indent=2))

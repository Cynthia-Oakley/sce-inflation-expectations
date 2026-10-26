#!/usr/bin/env python3
"""Publish cached news-mechanism figures, HTML and interactive canvas."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.reports.media_mechanism_report import main

if __name__=='__main__':main()

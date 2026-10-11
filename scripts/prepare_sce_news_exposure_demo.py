#!/usr/bin/env python3
"""Thin, offline entry point for the news exposure demonstration."""
import runpy
from pathlib import Path

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'studies/sce_inflation_expectations/news_exposure_demo.py'), run_name='__main__')

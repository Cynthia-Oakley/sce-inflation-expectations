"""Offline verification of news trial; no classifier or simulation calls."""
import importlib.util
from pathlib import Path

path=Path(__file__).resolve().parents[1]/'studies/sce_inflation_expectations/news_selection_analysis.py'
spec=importlib.util.spec_from_file_location('sce_news_selection_analysis',path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if __name__=='__main__':module.main()

"""Offline entry point; import the study without optional simulation packages."""
import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'studies/sce_inflation_expectations/news_selection_trial.py'
spec = importlib.util.spec_from_file_location('sce_news_selection_trial', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if __name__ == '__main__':
    module.main()

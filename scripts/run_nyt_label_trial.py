"""Classification runner; offline validation unless --execute is explicit."""
import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'studies/sce_inflation_expectations/news_label_trial.py'
spec = importlib.util.spec_from_file_location('sce_news_label_trial',path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if __name__=='__main__':
    module.main()

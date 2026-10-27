"""Resume the approved weekly run after its API-key limit was raised."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.weekly_key_limit_resume import main
if __name__=='__main__':main()

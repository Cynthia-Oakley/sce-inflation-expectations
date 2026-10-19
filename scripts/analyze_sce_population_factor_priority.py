"""Compare existing ten trait blocks using cached monthly SCE regressions."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'studies/sce_inflation_expectations/evaluation'))
from population_factor_priority import run

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    result=run(p.parse_args().out)
    for period, models in result['periods'].items():
        for outcome, model in models.items():
            print(period, outcome, model['n_person_months'], model['r2_within_month'],
                  [(r['factor'], round(r['drop_from_full_r2_points'], 3))
                   for r in model['ranked_factors']])

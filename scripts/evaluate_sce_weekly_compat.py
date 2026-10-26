"""Zero-API final evaluator for the actual compact weekly execution schema.

The frozen evaluator and the run's bound files remain unchanged. This adapter
only supplies redundant date metadata during evaluation, after all 47 actual
checkpoints exist. Original evaluator validity checks and scoring stay intact.
"""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments import weekly_evaluation as ev
from studies.sce_inflation_expectations.experiments.weekly_partial_readout import normalized_point
from studies.sce_inflation_expectations.experiments.weekly_terminal import checked
from studies.sce_inflation_expectations.submission_tools.reproduce import no_network
from studies.sce_inflation_expectations.experiments.frozen_batch import dump, sha


def evaluate_compatible(folder):
    folder=Path(folder).resolve()
    protocol,_=checked(folder)
    target=(ROOT/protocol['inputs']/'weekly_plan.json').resolve()
    original=ev.read_json
    def adapted(path):
        value=original(path)
        return [normalized_point(p) for p in value] if Path(path).resolve()==target else value
    ev.read_json=adapted
    try:
        with no_network():result=ev.evaluate(folder)
        dump(folder/'evaluation/compatibility_receipt.json',dict(
            schema='sce_weekly_compact_plan_evaluation_adapter/v1',new_API_calls=0,
            execution_plan_sha256=sha(target),adapter_sha256=sha(Path(__file__)),
            normalization_source_sha256=sha(ROOT/'studies/sce_inflation_expectations/experiments/weekly_partial_readout.py'),
            normalized_fields=['target_reference_period','anchor_published_date'],
            method='New York cutoff calendar month; frozen cycle_key publication date',
            original_plan_and_frozen_evaluator_unchanged=True))
        return result
    finally:ev.read_json=original


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True)
    print(evaluate_compatible(p.parse_args().run_dir))

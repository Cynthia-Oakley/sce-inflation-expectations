# Portable A macro calibration replay

Status: implemented and locally verified as an offline wrapper around the original calibration source. The original evaluator and its feature definitions are copied byte for byte into the bundle. The wrapper stages data in a temporary source workspace so neither the exported bundle nor the archived calibration output is modified.

## API and commands

`studies/sce_inflation_expectations/submission_tools/portable_calibration.py` exposes:

```python
from studies.sce_inflation_expectations.submission_tools.portable_calibration import export, replay

export("workspace/portable/calibration", root="/path/to/source/workspace")
replay("workspace/portable/calibration", "outputs/calibration_replay")
replay("workspace/portable/calibration", "outputs/fresh_A_recalibration",
       fresh_evaluation="outputs/fresh_answer_evaluation")
```

CLI from the source workspace or exported source tree:

```bash
python studies/sce_inflation_expectations/submission_tools/portable_calibration.py \
  export --root /path/to/source/workspace --out workspace/portable/calibration

python studies/sce_inflation_expectations/submission_tools/portable_calibration.py \
  replay --data workspace/portable/calibration --out outputs/calibration_replay

python studies/sce_inflation_expectations/submission_tools/portable_calibration.py \
  replay --data workspace/portable/calibration --out outputs/fresh_A_recalibration \
  --fresh-evaluation outputs/fresh_answer_evaluation
```

Each destination must be new. Runtime packages are Python 3.10+, NumPy, pandas, SciPy, and openpyxl. There are no network or model calls.

## What the bundle includes

The manifest assigns a role and SHA-256 to each copied file. Original relative paths remain intact so the original script can run without path rewrites:

- Frozen A Core and Core+Normal monthly aggregate, its complete manifest, and yearly summary.
- The A T0 summary containing fixed national truth/anchor values and common-score measurement bridge.
- All 82 monthly `environment.json` files used to select as-of eligible first-release CPI features.
- The frozen calibration protocol, original calibration script and dependency modules, and all archived calibration outputs for replay comparison.
- The frozen B Core+Normal monthly aggregate and its manifest/summary as a separate downstream input. The A calibration itself is trained on A; it does not fit parameters on B.

The export excludes unrelated simulator package initializers and does not include private raw respondents or the 367 MB materialized environment tree. Only the public macro/date features consumed by this calibration are included.

## Refit behavior

Default replay executes the original `scripts/analyze_sce_full_a_macro_calibration.py` and `evaluation/full_a_macro_calibration.py`. It refits the original MAE and MSE blend weights on A’s first 48 months with `evaluation/aggregate_blend.py::fit_weight`. It also refits the predeclared macro/ridge families: fit the first 36 months, choose ridge alpha on the next 12 by MAE (ties prefer the larger alpha), refit on all 48 months, and score the later 34. Original CPI cutoff handling, regimes, transforms, metrics, and paired block interval are unchanged.

Default replay compares all original outputs with the archived calibration tables at `rtol=1e-10`, `atol=1e-12`. It checks source hashes, recalculated fit/prediction contents, and the generated output manifest. The run writes the original output files plus `portable_calibration_receipt.json`; the receipt records input mode, comparison status, and the zero-call boundary.

Fresh mode accepts a completed `portable_evaluate` output directory. It requires model-backed results and complete coverage for exactly the 82 A months in both direct A and A_Normal. It reads direct medians from `monthly_series.csv`, A_Normal medians from `normal_summary.json`, checks that the Normal downstream CSV agrees, and verifies frozen truth/anchors still match. It replaces only `before_model_pp` and `expanded_model_pp` in a staged copy of the A aggregate. The frozen targets, anchors, monthly `as_of`, public CPI releases, and protocol stay fixed. Then the original early-48 fit and later-34 scoring run again with those new centers. Fresh results are not compared to archived score values, and the fixed-weight default in `portable_evaluate` is unaffected.

The resulting `monthly_predictions_public.csv` can be passed to the existing portable downstream regression replay along with a B aggregate. That replay refits its original expanding-window A models and frozen-A B transfer; see [downstream_notes.md](downstream_notes.md). The calibration adapter does not invent a new B fit or alter the downstream protocol.

## Validation

```bash
python -m pytest tests/test_sce_portable_calibration.py -q
```

Two tests cover full archived replay and an independent fresh-input run with deliberately shifted A/A_Normal centers. The local archived replay matched canonical results at the declared numeric tolerance, retained exact source hashes, and made zero API calls or new Q9 fits. The fresh-input test confirms the early-48 blend is actually refitted and that no archived value assertion is applied to the changed series.

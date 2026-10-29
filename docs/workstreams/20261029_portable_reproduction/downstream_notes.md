# Offline downstream regression reconstruction

Status: implemented as a portable wrapper around the frozen downstream builder and evaluator. This adds no model, feature, outcome, horizon, hyperparameter search, or changed validation rule.

## API and package layout

`studies/sce_inflation_expectations/submission_tools/portable_downstream.py` provides:

- `export(out, root=...)`: copies a fixed list of original source files, the complete public-series input set, the frozen A/B monthly aggregate inputs, and the complete archived table outputs. It writes `portable_downstream_manifest.json` with SHA-256 hashes and each file's role.
- `replay(data, out, source_root=...)`: invokes the original `scripts/prepare_sce_downstream_data.py` to rebuild the panel from raw series, then invokes the original `scripts/analyze_sce_downstream_regression.py` with the original evaluation module and protocol. A clean subprocess is used so imports resolve inside the exported source tree. Rebuilt panel artifacts are preserved at `out/reconstructed_data/`.

The bundle preserves paths expected by the old scripts:

- `scripts/prepare_sce_downstream_data.py`
- `scripts/analyze_sce_downstream_regression.py`
- `studies/sce_inflation_expectations/evaluation/downstream_regression.py`
- `docs/workstreams/20261026_downstream/regression_protocol.json`
- `studies/sce_inflation_expectations/submission_tools/portable_downstream.py`

The simulation package initializer is intentionally not copied into this narrow bundle. The evaluator import uses Python namespace-package resolution and needs only the exact evaluator module above; registration of unrelated simulation components is not part of the downstream calculation. The copied analysis script and evaluator themselves are byte-identical to the source workspace and are SHA-256 recorded.

## Inputs and dependencies

`data/raw/` contains all 14 input files: the original Atlanta Fed wage workbook, its extracted monthly CSV, and 12 public FRED series CSVs. It also includes the category manifests the original builder uses for source-hash verification. `data/frozen_inputs/` contains the exact A and B aggregate inputs:

- A: `monthly_predictions_public.csv` from `outputs/sce_full_a_macro_calibration_20261026_v1/`.
- B: `monthly_national.csv` from `outputs/sce_recent_b_core_normal_evaluation_20261026_v1/`.

`data/expected/` contains archived `predictions.csv`, `model_metrics.csv`, `in_sample_metrics.csv`, `contrasts.csv`, `coverage.csv`, and `key_contrasts.csv`. Comparing the complete prediction and contrast tables keeps every favorable and unfavorable result in scope.

Runtime requirements are Python 3, NumPy, pandas, and Matplotlib. The bundle manifest records versions present at export. There is no network or paid call in export or replay.

## Reviewer command

From the exported bundle root:

```bash
python studies/sce_inflation_expectations/submission_tools/portable_downstream.py \
  replay --data data --out outputs/downstream_replay
```

This rebuilds the 117-month panel, runs all 4 outcomes × 3 horizons × 8 models and A/B evaluation, and compares six complete output tables with the archived result using `rtol=1e-10`, `atol=1e-12`. The per-run `portable_verification.json` records input hashes, source hashes, counts, comparisons and output hashes. Existing outputs are not overwritten.

New monthly A/B aggregate inputs can be explored by passing both `--a path/to/a.csv --b path/to/b.csv --no-verify`. The API similarly requires both `a_input`/`b_input` and `verify_reference=False`. Such a run is explicitly marked `completed_unverified_new_analysis`; it is not represented as verification of the frozen scores.

## Integration references for the outer package builder

Call `export(target, root=repository_root)` to place a self-contained reproduction bundle at a chosen package path. Preserve the directory as a unit because the original scripts depend on their relative layout. For a single-request reviewer package, include that directory's entire `data/`, `scripts/`, `studies/`, `docs/`, `REPRODUCTION.json`, and `portable_downstream_manifest.json`. Do not replace the archived reference tables with summary excerpts.

The frozen scientific protocol remains `docs/workstreams/20261026_downstream/regression_protocol.json`; the underlying downstream documentation and all positive/negative findings remain in `docs/workstreams/20261026_downstream/README.md` and the archived complete CSVs. This wrapper does not revise that protocol or reinterpret results.

## Fresh-answer offline evaluation

`studies/sce_inflation_expectations/submission_tools/portable_evaluate.py` accepts a new runner `answers.jsonl` plus the runtime export's `data/evaluation/` files. Its Python API is:

```python
from studies.sce_inflation_expectations.submission_tools.portable_evaluate import evaluate

summary = evaluate(answers, data, out, source_root=source_workspace)
```

The corresponding offline CLI is:

```bash
python studies/sce_inflation_expectations/submission_tools/portable_evaluate.py \
  --answers outputs/answers.jsonl --data data --out outputs/evaluation
```

Each input row identifies `task`, `period`, original `agent_id`, exported `household` alias, positive `weight`, `q8`, `q9_bins`, per-field `field_sources`, and the explicit `actual_model_results` flag. Optional `before_q8` and `before_q9_bins` fields record the prior state used by the original A operational fallback. The alias must resolve to the same original ID in the exported `code_map.json`.

The evaluator scores Q9 with an exact-vector frozen score when available and the original frozen scorer for genuinely new vectors. A updated answer whose density fit fails retains its declared prior operational value for the direct A evaluation, while that failed model output is excluded from the fresh Normal donor bank. The Normal population frame and selected Core roster come from the outcome-free mechanism export; archived answer values are never used as replacement donors. A Normal rows are emitted only when every period's Core roster is present and fresh answers can support the original tau-8 `JointExpansion`.

`national_metrics.json` applies the original `headline_errors` function to A (82 periods), B (11), recursive monthly (10, excluding the reused 202511 root), and weekly (11 frozen `main_score_point=True` targets). It reports fresh raw, frozen anchor, and fixed A-early-48-MSE blend metrics for each supported series, plus analogous A_Normal/B_Normal metrics when complete fresh Normal banks exist. Missing periods remain explicit in coverage and prevent a complete-series metric; retained/update/fallback counts are recorded per field and period. The blend weight remains the frozen `0.1339762571517809`; it is never fitted on fresh B, monthly, or weekly results. The adapter does not calculate human micro accuracy for B, monthly, or weekly because the runtime package contains no corresponding human micro targets.

## Validation

Run the targeted tests with:

```bash
python -m pytest tests/test_sce_portable_downstream.py -q
```

The end-to-end test exports a package into a temporary directory, rebuilds the panel from the included public series, reruns the original evaluator, and checks all six archived tables plus the established row counts (4,896 predictions, 192 model metrics, 408 contrasts). It also confirms both positive and negative RMSE comparisons remain present.

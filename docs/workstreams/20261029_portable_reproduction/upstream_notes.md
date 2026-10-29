# Portable generation sources and raw preparation

Updated 2026-10-29.

## Source data bundle

`studies/sce_inflation_expectations/submission_tools/portable_workspace.py export` creates a ZIP data supplement with original repository-relative paths. Every file has a SHA-256 digest, byte count, role, and source lineage in `portable_source_manifest.json`. The Python study source tree is supplied separately by the portable launcher.

The current bundle is `outputs/sce_portable_workspace_20261029_v4/source_data.zip` (731,967,644 bytes compressed; 4,200,740,773 bytes uncompressed; 1,800 files). Its SHA-256 is `5f5f7a5d45ee9dade862cf6519626b58e056e87a7494522fbcba117664e0456a`. Export reopens the ZIP and verifies every member against its manifest before publishing it.

The bundle retains the raw public SCE workbooks, anonymous respondent IDs, source registries, candidate pools and labels, deterministic scoring caches, original donor/weight tables, A assembly states, B and monthly PE/state templates, and all weekly templates and priors. It contains all 300 public BLS archive files and 6 EIA support files used by P/E materialization. The B date protocol, weekly old joint-donor pool, and weekly Q9 score cache are included as explicit dependencies discovered by exercising the original preparation functions.

Answer-bearing SCE microdata workbooks remain included as public raw source material, separately role-tagged from generation projections. The original functions keep their pre-answer and publication-date filters. Current target Q8/Q9 values do not enter generated A prompts. The weekly anchor table is included as `dated_public_anchor_table`; weekly preparation reads its dated headline releases and applies the original release-by-cutoff rule. Individual current truth and model responses are excluded.

Archived final A prompt payloads are not in the source bundle. A digest-only registry at `data/portable_metadata/a_prompt_message_hashes.json` records SHA-256 hashes of each of the 41,970 exact message lists across 82 months, after validating each source file against the frozen manifest. It supports a per-person reproduction check without shipping the archived prompt text. The B date sampler receives only the `month,cpi_published_at` projection at `data/portable_metadata/cpi_release_schedule.csv`.

## Rebuild commands

Materialize the data bundle into an empty workspace, then install the original study source tree and use the installed SocioVerse SDK:

```sh
python studies/sce_inflation_expectations/submission_tools/portable_workspace.py materialize \
  --package-data /path/to/source_data.zip \
  --workspace /path/to/reviewer_workspace

python studies/sce_inflation_expectations/submission_tools/portable_prepare.py \
  --workspace /path/to/reviewer_workspace \
  --out outputs/sce_portable_rebuild_20261029_v1
```

The default `--task all` runs A, B, and weekly preparation. `--task a`, `--task b`, or `--task weekly` selects one path. These stages are offline and record zero new API calls.

The A chain calls the original public Q9 extraction, prior labeling, full-period materialization, monthly fine grid and donor preparation, household projection, prompt assembly/Core check, and personal-completion cutoff functions. The B chain rebuilds the response-date distribution, sampled dates, candidate match, and prompt inputs. Weekly preparation rebuilds the roster preflight, all 12 release-cycle priors, weekly news matching, and message templates.

The output has a `preparation_index.json` with fresh A final prompts and assembly, B period prompt roots, and weekly input roots. `portable_adopt.py` consumes these paths and rejects any A/B message mismatch or weekly structural mismatch before the rebuilt inputs can replace the runtime cache.

## Reproduction checks and limits

The offline original-function run completed all A, B, and weekly preparation stages:

- A rebuilt 41,984 person-month rows over 82 months; 14 rows were excluded by the original personal completion cutoffs. All 41,970 eligible final message lists matched their digest-only references. The 82 serialized `prompts.json` byte hashes differ because the outer row dictionaries have a different insertion order; the message payloads and respondent sets match exactly.
- B rebuilt 5,632 sampled person-date rows and 5,632 prompt records. Of 79 generation input files, 68 matched byte-for-byte and 11 timing-context JSON files compared equal after parsing; the only other manifest-listed item is a generated summary report and is not a generation input. A local `portable_adopt` check reproduced all 5,632 rendered B messages.
- Weekly rebuilt 47 points for 300 households each and all 12 release-cycle priors. Of 344 generation input files, 297 matched byte-for-byte and 47 timing-context JSON files compared equal after parsing. Summary reports are excluded from generation-input comparison. The local adopt check validated 14,100 weekly positions and exact prior/template structures.

The historical full-period materializer still uses its registered 93-month coverage ledger, the 201906 environment schema seed, and three original persona rows for 201906, 202303, and 202606. Those historical seeds are listed and hashed separately; target truth sidecars are excluded. The rebuilt method covers the public-source-to-prior/reference-to-grid/matching/prompt chain over that registered scope, not independent recovery of the coverage ledger or the three seed personas.

The weekly prior step uses the original deterministic Q9 density-score cache and the registered old joint-donor pool. These are method inputs, not model outcomes. The B date diagnostic records a 2026-01 archive-coverage screen blocker and 297 missing basic-topic labels in its wider inventory; the original 11-month B generation assembly still completes and its prompt inputs pass the original reference comparison. These diagnostics remain visible in the generated report.

This package is for reproducing generation inputs. It does not create forecasts, authorize paid dispatch, certify evaluation performance, or replace current truth data.

"""Evaluation-side projection of frozen scores to model-generated bins only.

The historical score cache mixes human and model questionnaire vectors. It is
only parsed in this isolated projection stage. Prediction receives just the
vectors found in the verified T0 model-output overlay and their fixed scores.
"""
from pathlib import Path
import argparse
import json

from ..experiments.full_a_core_normal import (
    ROOT, GENERATION, T0_INPUTS, EVALUATION, read, sha, write, fresh, checked,
)
from ..scoring.sce_q9_frozen import provenance
from ..submission_tools.reproduce import no_network


def export(out):
    from .full_a_personal import validate_completed_view, _validate_production_origin
    receipt, _ = validate_completed_view(GENERATION)
    _validate_production_origin(T0_INPUTS, GENERATION, receipt)
    em = read(EVALUATION / 'manifest.json')
    cache_file = EVALUATION / 'scoring_cache_private.json'
    checked(EVALUATION, {'scoring_cache_private.json': em['files_sha256'][cache_file.name]})
    vectors = set()
    for line in (GENERATION / 'logical_actions_private.jsonl').open():
        action = json.loads(line)
        if action['field_updated']['q9']:
            vectors.add(tuple(action['effective_q9_bins']))
    # Mixed cache is read only here, never by the prepare/predict stages.
    cache = {tuple(r['bins']): r['score'] for r in read(cache_file)}
    if not vectors <= cache.keys():
        raise ValueError('Verified model vectors missing from frozen score cache')
    out = fresh(out)
    write(out / 'model_scores_private.json', [dict(bins=list(v), score=cache[v]) for v in sorted(vectors)])
    result = dict(status='exported_frozen_scores_for_verified_model_vectors_only',
        origin_validation_performed=True, model_vector_count=len(vectors),
        new_api_calls=0, new_q9_fits=0, scorer=provenance(),
        mixed_cache_read_only_in_this_evaluation_stage=True,
        human_only_vectors_exported=False,
        generation_manifest_sha256=sha(GENERATION / 'manifest.json'),
        input_manifest_sha256=sha(T0_INPUTS / 'manifest.json'),
        projection_rule='Exact set of Q9 vectors actually updated by verified main/repair model replies; shared human/model vectors are included only by model membership.')
    write(out / 'summary.json', result)
    write(out / 'manifest.json', dict(
        source_sha256={str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__),
            GENERATION / 'manifest.json', GENERATION / 'logical_actions_private.jsonl',
            T0_INPUTS / 'manifest.json', cache_file, EVALUATION / 'manifest.json',
            ROOT / 'studies/sce_inflation_expectations/evaluation/full_a_personal.py']},
        files_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()}))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    with no_network():
        print(json.dumps(export(args.out), ensure_ascii=False))


if __name__ == '__main__': main()

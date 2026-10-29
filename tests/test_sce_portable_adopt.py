import json
from pathlib import Path

import pytest

from studies.sce_inflation_expectations.submission_tools import portable_run as p
from studies.sce_inflation_expectations.submission_tools.portable_adopt import adopt


def setup(root, *, changed=False):
    runtime = root / "portable/runtime"
    row = dict(messages=[dict(role="user", content="original source-derived prompt")],
        initial={"public_prior": 3.0}, cutoff="2019-01-02T23:59:59-05:00", weight=2,
        household="A_000001", agent_id="person-1")
    relative = "inputs/A/201901.json.gz"
    p.write(runtime / relative, dict(task="A", period="201901", rows={"person-1": row}))
    p.write(runtime / "index.json", dict(schema="sce_portable_runtime/v1", model=p.MODEL,
        waves={"A": [dict(period="201901", file=relative, people=1)]},
        files_sha256={relative: p.sha(runtime / relative)}))
    prepared = root / "outputs/prepared"
    final = prepared / "A/201901"
    assembly = prepared / "assembly"
    messages = [dict(role="user", content="different" if changed else "original source-derived prompt")]
    p.write(final / "prompts.json", dict(rows={"person-1": dict(messages=messages)}))
    p.write(final / "contexts_private.json", {"person-1": {"as_of": row["cutoff"]}})
    p.write(final / "weights_private.json", {"person-1": {"analysis_weight": 2}})
    p.write(assembly / "prompts/201901/initial_states_private.json", {"person-1": row["initial"]})
    p.write(prepared / "preparation_index.json", dict(fresh_inputs=dict(
        a_personal_cutoff=str((prepared / "A").relative_to(root)),
        a_assembly=str(assembly.relative_to(root)))))
    return runtime, prepared


def test_rebuilt_inputs_are_adopted_without_modifying_the_original_cache(tmp_path):
    runtime, prepared = setup(tmp_path)
    original = p.sha(runtime / "index.json")
    result = adopt(tmp_path, prepared)
    assert result["positions"]["A"] == 1
    assert p.sha(runtime / "index.json") == original
    assert (tmp_path / result["runtime"] / "index.json").exists()
    assert p.read(tmp_path / "portable/active_runtime.json") == result


def test_changed_reconstructed_prompt_is_not_quietly_accepted(tmp_path):
    _runtime, prepared = setup(tmp_path, changed=True)
    with pytest.raises(ValueError, match="Rebuilt A prompt differs"):
        adopt(tmp_path, prepared)
    assert not (tmp_path / "portable/active_runtime.json").exists()


def test_preparation_may_not_redirect_to_an_author_external_path(tmp_path):
    _runtime, prepared = setup(tmp_path)
    p.write(prepared / "preparation_index.json", dict(fresh_inputs=dict(a_personal_cutoff="../../outside")))
    with pytest.raises(ValueError, match="escaped"):
        adopt(tmp_path, prepared)

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
from zipfile import ZipFile, ZipInfo

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


portable_workspace = _load(
    "sce_portable_workspace_test",
    "studies/sce_inflation_expectations/submission_tools/portable_workspace.py",
)
portable_prepare = _load(
    "sce_portable_prepare_test",
    "studies/sce_inflation_expectations/submission_tools/portable_prepare.py",
)


def _write_zip(path: Path, files: dict[str, bytes], *, declared: dict | None = None) -> None:
    records = declared or {
        name: {
            "role": "test_input",
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
            "source_lineage": ["unit test"],
        }
        for name, content in files.items()
    }
    manifest = {"schema_version": 1, "files": records}
    with ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr(portable_workspace.MANIFEST_NAME,
                         json.dumps(manifest, sort_keys=True).encode("utf-8"))


def test_materialize_preserves_original_paths_and_verifies_hashes(tmp_path: Path) -> None:
    content = b"public source bytes\n"
    archive = tmp_path / "sources.zip"
    _write_zip(archive, {"data/raw/example.csv": content})
    destination = tmp_path / "review_workspace"

    receipt = portable_workspace.materialize(archive, destination)

    assert (destination / "data/raw/example.csv").read_bytes() == content
    assert receipt["file_count"] == 1
    assert receipt["role_counts"] == {"test_input": 1}
    assert (destination / portable_workspace.MANIFEST_NAME).is_file()


def test_materialize_refuses_nonempty_destination(tmp_path: Path) -> None:
    archive = tmp_path / "sources.zip"
    _write_zip(archive, {"data/raw/example.csv": b"x"})
    destination = tmp_path / "review_workspace"
    destination.mkdir()
    (destination / "keep.txt").write_text("do not overwrite")

    with pytest.raises(FileExistsError):
        portable_workspace.materialize(archive, destination)
    assert (destination / "keep.txt").read_text() == "do not overwrite"


def test_materialize_rejects_path_traversal_and_hash_drift(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.zip"
    _write_zip(traversal, {"../escape.txt": b"outside"})
    with pytest.raises(ValueError, match="Unsafe repository-relative path"):
        portable_workspace.materialize(traversal, tmp_path / "bad_workspace")

    bad_hash = tmp_path / "bad_hash.zip"
    _write_zip(
        bad_hash,
        {"data/raw/example.csv": b"actual"},
        declared={"data/raw/example.csv": {
            "role": "test_input", "sha256": "0" * 64, "bytes": 6,
            "source_lineage": ["unit test"],
        }},
    )
    with pytest.raises(ValueError, match="ZIP hash differs from manifest"):
        portable_workspace.materialize(bad_hash, tmp_path / "hash_workspace")


def test_materialize_rejects_zip_symlink(tmp_path: Path) -> None:
    path = tmp_path / "symlink.zip"
    with ZipFile(path, "w") as archive:
        info = ZipInfo("data/raw/link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, b"target")
        archive.writestr(portable_workspace.MANIFEST_NAME,
                         json.dumps({"schema_version": 1, "files": {}}))

    with pytest.raises(ValueError, match="Non-regular ZIP member"):
        portable_workspace.materialize(path, tmp_path / "symlink_workspace")


def test_prompt_comparison_hashes_each_message_and_reports_file_order_separately(tmp_path: Path) -> None:
    output = tmp_path / "rebuilt"
    (output / "201901").mkdir(parents=True)
    (output / "201902").mkdir(parents=True)
    messages_a = [{"role": "user", "content": "a"}]
    messages_b = [{"role": "user", "content": "b"}]
    messages_c = [{"role": "user", "content": "c"}]
    frozen_201901 = {"rows": {
        "agent_a": {"messages": messages_a},
        "agent_b": {"messages": messages_b},
    }}
    # Same per-agent payloads, different outer mapping insertion order.
    (output / "201901/prompts.json").write_text(json.dumps({"rows": {
        "agent_b": {"messages": messages_b},
        "agent_a": {"messages": messages_a},
    }}), encoding="utf-8")
    (output / "201902/prompts.json").write_text(json.dumps({"rows": {
        "agent_c": {"messages": messages_c},
    }}), encoding="utf-8")
    expected = {"files_sha256": {
        "201901/prompts.json": hashlib.sha256(json.dumps(frozen_201901).encode()).hexdigest(),
        "201902/prompts.json": "f" * 64,
        "201903/prompts.json": "e" * 64,
    }}
    message_hash = portable_prepare._message_sha256
    expected_message_hashes = {"months": {
        "201901": {"agent_a": message_hash(messages_a), "agent_b": message_hash(messages_b)},
        "201902": {"agent_c": message_hash([{"role": "user", "content": "expected"}])},
        "201903": {"agent_d": message_hash([{ "role": "user", "content": "missing"}])},
    }}

    result = portable_prepare._compare_expected_prompts(expected, output, expected_message_hashes)

    assert result["exact_file_hash_match_count"] == 0
    assert result["file_hash_difference_count"] == 2
    assert result["missing_prompt_file_count"] == 1
    assert result["matched_message_count"] == 2
    assert result["mismatched_message_count"] == 1
    assert result["missing_message_count"] == 1
    assert not result["all_match"]


def test_prompt_message_hash_match_survives_outer_json_row_reordering(tmp_path: Path) -> None:
    output = tmp_path / "rebuilt"
    (output / "201901").mkdir(parents=True)
    messages_a = [{"role": "user", "content": "a"}]
    messages_b = [{"role": "user", "content": "b"}]
    frozen = {"rows": {
        "agent_a": {"messages": messages_a},
        "agent_b": {"messages": messages_b},
    }}
    regenerated = {"rows": {
        "agent_b": {"messages": messages_b},
        "agent_a": {"messages": messages_a},
    }}
    (output / "201901/prompts.json").write_text(json.dumps(regenerated), encoding="utf-8")
    expected = {"files_sha256": {
        "201901/prompts.json": hashlib.sha256(json.dumps(frozen).encode()).hexdigest(),
    }}
    message_hash = portable_prepare._message_sha256
    registry = {"months": {"201901": {
        "agent_a": message_hash(messages_a),
        "agent_b": message_hash(messages_b),
    }}}

    result = portable_prepare._compare_expected_prompts(expected, output, registry)

    assert result["all_match"]
    assert result["matched_message_count"] == 2
    assert result["exact_file_hash_match_count"] == 0
    assert result["file_hash_difference_count"] == 1


def test_sce_raw_sources_are_role_separated_from_prompt_projection() -> None:
    assert portable_workspace._role("data/raw/sce_p_sources/micro_2017_2019.xlsx") == (
        "public_raw_sce_snapshot_answers_separate_from_generation_projection"
    )
    assert not portable_workspace._is_separate_evaluation_or_outcome(
        "data/evaluation/sce_recent_b_evaluation_20261025_v1/aggregate_inputs.json"
    )
    assert portable_workspace._is_separate_evaluation_or_outcome(
        "data/evaluation/sce_recent_b_evaluation_20261025_v1/micro_truth.json"
    )
    assert portable_workspace._role(
        "data/evaluation/sce_recent_b_evaluation_20261025_v1/aggregate_inputs.json"
    ) == "evaluation_metadata_not_generation_truth"
    assert not portable_workspace._is_separate_evaluation_or_outcome(
        "data/evaluation/sce_baselines_latest_20261007/micro_reference_sources.json"
    )

#!/usr/bin/env python3
"""SCE LLM probe — explicit, counted, tiny paid interactions with the configured endpoint.

    python scripts/sce_llm_probe.py --list-models                 # free catalog read (no tokens)
    python scripts/sce_llm_probe.py --sample 2 --model deepseek-flash \
        --extra-body '{"thinking": {"type": "disabled"}}' --confirm-spend

--list-models only queries the service catalog (ID/display names + fetch time); it
proves connectivity and catalog state, not that a specific model will answer.
--sample N runs the SCE decision model on the first N agents of conceptual step 0
(2021-05) with at most N paid calls (retry_max=0), writing the same audit sidecar
as a full run under outputs/local_runs/<run_id>/. Two passing samples show access
and format only — not stability, not accuracy.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_ROOT = REPO_ROOT.parent / "socioverse2_repo"
STUDY_ID = "sce_inflation_expectations"


def _load_client():
    from socioverse.external_events import _load_dotenv
    _load_dotenv()
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit('needs the openai client: pip install -e ".[llm]" in the socioverse env')
    key = os.environ.get("SV_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("SV_LLM_API_KEY is not set (env or official clone .env); ask the user to place it.")
    return OpenAI(api_key=key,
                  base_url=os.environ.get("SV_LLM_BASE_URL", "https://api.openai.com/v1"),
                  max_retries=0, timeout=30.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--sample", type=int, default=0, help="N agents x 1 step, exactly N paid calls")
    ap.add_argument("--model", default=None)
    ap.add_argument("--extra-body", default=None)
    ap.add_argument("--price-in", type=float, default=None)
    ap.add_argument("--price-out", type=float, default=None)
    ap.add_argument("--confirm-spend", action="store_true")
    args = ap.parse_args(argv)

    if not args.list_models and not args.sample:
        ap.error("choose --list-models and/or --sample N")

    out_dir = REPO_ROOT / "outputs" / "local_runs" / f"probe-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    out_dir.mkdir(parents=True, exist_ok=False)

    if str(OFFICIAL_ROOT) not in sys.path:
        sys.path.insert(0, str(OFFICIAL_ROOT))

    if args.list_models:
        client = _load_client()
        catalog = client.models.list()
        payload = {
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "base_url": str(client.base_url),
            "models": sorted(m.id for m in catalog.data),
            "note": "Service catalog state only; a listed ID does not guarantee the account "
                    "can call it, and a returned model string does not prove weight identity.",
        }
        (out_dir / "models_catalog.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"catalog saved: {out_dir / 'models_catalog.json'} "
              f"({len(payload['models'])} ids)")

    if args.sample:
        if not args.confirm_spend:
            sys.exit("--sample spends real API budget; re-run with --confirm-spend after approval.")
        if not args.model:
            sys.exit("--sample needs --model (pin the requested model explicitly).")
        export = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "export_study_runtime.py")],
                                capture_output=True, text=True)
        if export.returncode != 0:
            sys.stderr.write(export.stdout + export.stderr)
            sys.exit("export failed; resolve the runtime-copy conflict first.")
        import studies.sce_inflation_expectations  # noqa: F401
        from skills.sv_workspace import study_paths
        from socioverse.engine import build_providers
        from socioverse.schemas import EnvironmentBundle, PopulationBundle
        from socioverse.validation import validate_handoff
        from studies.sce_inflation_expectations.model import SCEDecision

        p = study_paths(OFFICIAL_ROOT / "studies" / STUDY_ID)
        env_b = validate_handoff(p["environment"], EnvironmentBundle)
        pop_b = validate_handoff(p["population"], PopulationBundle)
        run_id = out_dir.name
        env_b.provider_args["audit_dir"] = str(out_dir)
        env_b.provider_args["run_id"] = run_id
        env, population = build_providers(env_b, pop_b)
        personas = population.build(42)
        env.reset(42)
        env.advance_to(1)  # runtime t=1 = conceptual step 0 (2021-05)
        agent_ids = [p_.agent_id for p_ in personas[: args.sample]]
        obs = env.observe_batch(agent_ids, 1)

        decision = SCEDecision(
            llm_kind="openai", prompt_version="sce-q8-q9-llm-en-v1", model=args.model,
            temperature=0.0, max_tokens=1024, max_calls=args.sample, retry_max=0,
            extra_body=json.loads(args.extra_body) if args.extra_body else None,
            price_input_per_mtok=args.price_in, price_output_per_mtok=args.price_out,
            run_id=run_id, audit_dir=str(out_dir))
        actions = decision.decide_batch(obs, {})
        for a in actions:
            pl = a.payload
            print(f"{a.agent_id}: status={pl['validation_status']} point={pl['point_pct']} "
                  f"q9_sum={pl['q9_sum']} source={a.source} llm={pl.get('llm')}")
        print(f"ledger: {decision.cost_summary()}")
        (out_dir / "probe_summary.json").write_text(json.dumps({
            "run_id": run_id, "model": args.model, "n_samples": len(actions),
            "statuses": [a.payload["validation_status"] for a in actions],
            "ledger": decision.cost_summary(),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"audit dir: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""SCE inflation-expectations study model on the SocioVerse2 Core.

Two decision modes share one payload schema:

- ``llm_kind="scripted"``: the deterministic stylized rule, byte-compatible with
  the cloud v3 process-validation run (2026-10-01 archive). Not an estimator.
- ``llm_kind="openai"``: a real LLM over any OpenAI-compatible endpoint
  (``SV_LLM_API_KEY`` / ``SV_LLM_BASE_URL``; model pinned in decision_args).
  Every attempt is fully audited: prompt text + sha256, raw response + sha256,
  requested/returned model, request_id, system_fingerprint, usage, finish_reason,
  latency, timestamps, retries and errors. Q9 is validated (each bin 0-100,
  sum 100 within tolerance) and NEVER silently normalized; there is no fallback
  to the scripted rule on LLM failure. The openai client is created with
  ``max_retries=0`` so every billed attempt appears in our own call ledger.

Audit sidecar (written only when ``audit_dir`` and ``run_id`` are injected by the
runner, e.g. scripts/run_sce_local.py):

- ``observations.jsonl``  one row per Observation, with observation_sha256
- ``llm_calls.jsonl``     one row per LLM attempt (openai mode only)

Historical note: the cloud v3 archive wrote a literal "\\n" sequence in
observations.jsonl (the platform's exported state used real LF; the conversion
layer is recorded in docs/CLOUD_V3_AUDIT_RECEIPT.md). This local source writes
real newlines; local runs get fresh run_ids, so no archive comparability breaks.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from statistics import median
from typing import Any

from socioverse.abc import DecisionModel, EnvironmentProvider, MetricCollector, PopulationProvider
from socioverse.engine import register
from socioverse.schemas import (
    Action, EnvironmentBundle, Observation, Persona, PopulationBundle,
    SimulationConfig, StudySpec,
)

Q9_KEYS = [f"q9_bin{i}" for i in range(1, 11)]
TARGETS = {
    0: {"target_month": "2021-05", "as_of": "2021-04-30T23:59:59-04:00"},
    1: {"target_month": "2021-06", "as_of": "2021-05-31T23:59:59-04:00"},
}
# Dev-window default; longer windows pass provider_args.targets (same dict shape,
# indexed by conceptual step). The Core records t=0 as initialization, so runtime
# decision t=k maps to conceptual step k-1.
DEFAULT_TARGETS = [TARGETS[0], TARGETS[1]]

# Q9 acceptance gate for LLM replies: each bin within [0, 100] and the sum equal
# to 100 within this tolerance. Out-of-gate replies are kept raw and marked
# invalid; they are never renormalized.
Q9_SUM_TOL = 0.5

# Q9 bin labels in questionnaire order (bin1 .. bin10), matching scoring/sce_q9.py.
Q9_BIN_LABELS = [
    "12% or more",
    "between 8% and 12%",
    "between 4% and 8%",
    "between 2% and 4%",
    "between 0% and 2%",
    "between -2% and 0%",
    "between -4% and -2%",
    "between -8% and -4%",
    "between -12% and -8%",
    "-12% or less (deflation of 12% or more)",
]

# Persona profile text. Keys cover BOTH the 20-persona synthetic pilot (codes
# like "under_35k") and the real SCE micro-data sampling labels produced by
# scripts/build_sce_population.py (codes like "under_50k", mapped from the real
# _EDU_CAT/_HH_INC_CAT categories, and Q10/Q43 employment/housing codes).
# Old keys must stay: the pilot population.json still uses them.
_PROFILE_TEXT = {
    "household_income_band": {
        # synthetic pilot (4 bands)
        "under_35k": "under $35,000",
        "35k_to_75k": "between $35,000 and $75,000",
        "75k_to_125k": "between $75,000 and $125,000",
        "125k_plus": "over $125,000",
        # real SCE _HH_INC_CAT (3 bands)
        "under_50k": "under $50,000",
        "50k_to_100k": "between $50,000 and $100,000",
        "over_100k": "over $100,000",
    },
    "education_group": {
        # synthetic pilot
        "high_school_or_less": "high school or less",
        "some_college": "some college",
        "bachelors": "a bachelor's degree",
        "postgraduate": "a postgraduate degree",
        # real SCE _EDU_CAT (3 categories; "College" = college graduate, no
        # postgraduate split exists in the real derived column)
        "high_school": "a high school diploma or less",
        "college": "a college degree",
    },
    "housing_tenure": {
        "renter": "renting your home",
        "owner": "owning your home",
        # real SCE Q43 code 3 ("Other", e.g. living with family rent-free)
        "other": "in other housing arrangements",
    },
    "employment_status": {
        # synthetic pilot
        "employed": "currently employed",
        "unemployed": "currently unemployed",
        "retired": "retired",
        # real SCE Q10 codes (questionnaire p.11-12); "unemployed" above covers
        # codes 3 (not working, would like to work) and 4 (temporarily laid off)
        "on_leave": "on sick or other leave from work",
        "disabled": "permanently disabled or unable to work",
        "student": "a student",
        "homemaker": "a homemaker",
        "other": "in some other employment situation",
    },
    # _NUM_CAT is the SCE numeracy category (High/Low), NOT household size;
    # the real whitelist columns contain no household-size variable.
    "numeracy": {"high": "high", "low": "low"},
}


def _stable_int(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)


def _target_for_runtime_step(step: int) -> dict[str, str]:
    # The Core records t=0 as initialization. Runtime decision t=1 is conceptual step 0.
    return TARGETS[max(0, min(1, step - 1))]


def _target_from_observation(ob: Observation) -> dict[str, str]:
    """Target month/as_of as the environment actually served them (window-length
    agnostic); falls back to the dev-window constant only if absent."""
    info = ob.macro_information or {}
    month = info.get("target_month")
    as_of = info.get("as_of")
    if month and as_of:
        return {"target_month": month, "as_of": as_of}
    return _target_for_runtime_step(ob.step)


def self_reported_code_sha256() -> str:
    """SHA-256 of this source file, self-reported (RESEARCH_PROTOCOL §6 addendum)."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


# =============================================================================
# P — population (uploaded fixture; personas arrive materialized in the bundle)
# =============================================================================
@register("population", "sce_inflation_expectations.population")
class SCEPopulationProvider(PopulationProvider):
    def __init__(self, bundle: PopulationBundle):
        self.bundle = bundle

    def build(self, seed: int) -> list[Persona]:
        return list(self.bundle.personas)


# =============================================================================
# E — environment (BLS initial-release signals materialized at build time)
# =============================================================================
@register("environment", "sce_inflation_expectations.environment")
class SCEEnvironmentProvider(EnvironmentProvider):
    def __init__(self, bundle: EnvironmentBundle):
        self.bundle = bundle
        self.signals_by_step = bundle.provider_args.get("signals_by_step", {})
        self.events_by_step = bundle.provider_args.get("events_by_step", {})
        self.persona_by_id = bundle.provider_args.get("persona_by_id", {})
        self.targets: list[dict[str, str]] = list(
            bundle.provider_args.get("targets") or DEFAULT_TARGETS)
        self.answers: dict[str, dict[str, Any]] = {}
        self.current_signals: list[dict[str, Any]] = []
        self.current_events: list[dict[str, Any]] = []
        self.current_step = 0
        self._active_broadcasts: list[dict[str, Any]] = []
        self.audit_dir = Path(bundle.provider_args["audit_dir"]) if bundle.provider_args.get("audit_dir") else None
        self.run_id = bundle.provider_args.get("run_id", "")

    def _audit_observations(self, observations: list[Observation]) -> None:
        if not self.audit_dir or not self.run_id:
            return
        for ob in observations:
            raw = json.dumps(ob.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            row = {"run_id": self.run_id, "agent_id": ob.agent_id, "runtime_step": ob.step,
                   "observation": ob.model_dump(), "observation_sha256": _sha256_text(raw)}
            _append_jsonl(self.audit_dir / "observations.jsonl", row)

    def reset(self, seed: int) -> None:
        self.answers = {}
        self.current_step = 0
        self.current_signals = list(self.signals_by_step.get("0", []))
        self.current_events = list(self.events_by_step.get("0", []))
        self._active_broadcasts = []

    def advance_to(self, t: int) -> list[Any]:
        conceptual = max(0, min(len(self.targets) - 1, t - 1))
        self.current_step = conceptual
        self.current_signals = list(self.signals_by_step.get(str(conceptual), []))
        self.current_events = list(self.events_by_step.get(str(conceptual), []))
        self._active_broadcasts = [
            {"message_id": b.message_id, "content": b.content, "channel": b.channel,
             "target_month": (self.targets[b.at_step] if b.at_step < len(self.targets)
                              else self.targets[-1])["target_month"]}
            for b in self.bundle.information_program.broadcasts
            if b.is_macro and b.at_step == conceptual and b.ttl == 1
        ]
        return []

    def apply(self, actions: list[Action]) -> None:
        for action in actions:
            payload = dict(action.payload)
            self.answers[action.agent_id] = payload

    def observe_batch(self, agent_ids: list[str], t: int, round_idx: int = 0) -> list[Observation]:
        target = self.targets[self.current_step]
        info = {
            "target_month": target["target_month"],
            "as_of": target["as_of"],
            "signals": list(self.current_signals),
            "events": list(self.current_events),
            "broadcasts": list(self._active_broadcasts),
            "evidence_class": self.bundle.provider_args.get(
                "evidence_class", "historical_official_release_evidence"),
            "source_status": self.bundle.provider_args.get("source_status", {}),
            "excluded_fred": "fred" in self.bundle.provider_args.get(
                "excluded_sources", ["fred"]),
        }
        out = []
        for aid in agent_ids:
            profile = dict(self.persona_by_id.get(aid, {}))
            prior = dict(self.answers.get(aid, {}))
            out.append(Observation(
                agent_id=aid,
                step=t,
                macro_physical={"target_month": target["target_month"], "as_of": target["as_of"]},
                local_physical={"profile": profile, "prior_answer": prior},
                macro_information=info,
                local_information={},
            ))
        self._audit_observations(out)
        return out

    def agent_state(self, agent_id: str) -> dict[str, Any]:
        answer = self.answers.get(agent_id, {})
        state = {
            "target_month": answer.get("target_month", ""),
            "direction": answer.get("direction", ""),
            "magnitude_pct": answer.get("magnitude_pct", 0.0),
            "point_pct": answer.get("point_pct", 0.0),
            "q9_valid": bool(answer.get("validation_status") == "valid"),
            "validation_status": answer.get("validation_status", "not_answered"),
            "q9_sum": answer.get("q9_sum", 0.0),
            "e_snapshot_id": answer.get("e_snapshot_id", ""),
            "reason": answer.get("reason", ""),
        }
        for key in Q9_KEYS:
            state[key] = answer.get(key, 0.0)
        return state

    def snapshot(self) -> dict[str, Any]:
        return {
            "conceptual_step": self.current_step,
            "target_month": self.targets[self.current_step]["target_month"],
            "signals": list(self.current_signals),
            "answered_agents": len(self.answers),
        }


# =============================================================================
# B helpers — prompt construction and response parsing (openai mode)
# =============================================================================
def _persona_sentence(profile: dict[str, Any]) -> str:
    inc = _PROFILE_TEXT["household_income_band"].get(
        str(profile.get("household_income_band", "")), "unknown income")
    edu = _PROFILE_TEXT["education_group"].get(
        str(profile.get("education_group", "")), "unknown education")
    ten = _PROFILE_TEXT["housing_tenure"].get(
        str(profile.get("housing_tenure", "")), "unknown housing situation")
    emp = _PROFILE_TEXT["employment_status"].get(
        str(profile.get("employment_status", "")), "unknown employment status")
    sentence = (f"You are a U.S. household head, age group {profile.get('age_group', 'unknown')}, "
                f"with {edu}, household income {inc}, living in the {profile.get('region', 'unknown')} "
                f"region, {ten}, {emp}.")
    num = _PROFILE_TEXT["numeracy"].get(str(profile.get("numeracy", "")))
    if num:
        sentence += (f" Your score on the survey's numeracy assessment was {num}.")
    return sentence


def _signal_lines(signals: list[dict[str, Any]]) -> str:
    lines = []
    for s in signals:
        lines.append(
            f"- {s.get('measure', '')} for {s.get('reference_period', '')}: "
            f"{s.get('value', '')}{'%' if s.get('unit') == 'percent' else ''} "
            f"(initial release published {str(s.get('published_at', ''))[:10]}, "
            f"source {s.get('source_version', '')})")
    return "\n".join(lines)


def build_sce_messages(ob: Observation, *, prior_note: str | None = None) -> list[dict[str, str]]:
    """English Q8/Q9 prompt: persona + whitelisted E (BLS initial releases) only.

    Whitelist: persona profile fields, target_month/as_of, the materialized BLS
    signals and broadcast text, and the agent's OWN prior simulated answer.
    SCE results, survey weights and any later-vintage data never enter the prompt.
    """
    info = ob.macro_information
    profile = ob.local_physical.get("profile", {})
    prior = ob.local_physical.get("prior_answer", {})
    bin_lines = "\n".join(f'  "bin{i + 1}": probability that inflation will be {label}'
                          for i, label in enumerate(Q9_BIN_LABELS))
    prior_block = ""
    if prior_note is None and prior.get("validation_status") in ("valid", "invalid"):
        prior_block = (f"\nLast month you gave a point estimate of {prior.get('point_pct', 0.0)}% "
                       f"for the then-current 12-month-ahead period. You may revise it freely.\n")
    elif prior_note:
        prior_block = prior_note
    user = f"""{_persona_sentence(profile)}

It is {info.get('target_month', '')}. You only know information that was publicly available by {info.get('as_of', '')}.
The most recent official U.S. Bureau of Labor Statistics releases available to you:
{_signal_lines(info.get('signals', []))}

Question 1 (point estimate): Over the next 12 months, what do you expect the rate of inflation to be,
in percent? Give a single signed number (negative means deflation).

Question 2 (density): What is the percent chance that the 12-month-ahead inflation rate will fall in
each of the following ten ranges? Give each a probability from 0 to 100; the ten probabilities must
sum to exactly 100.
{bin_lines}
{prior_block}
Reply with ONLY a JSON object of the form:
{{"point_pct": <number>, "q9": {{"bin1": <0-100>, "bin2": <0-100>, ..., "bin10": <0-100>}},
 "reason": "<one or two short sentences>"}}"""
    return [{"role": "user", "content": user}]


# ---------------------------------------------------------------------------
# Prompt v2 (D049a/c/d + D050 + D051): compact natural-language rendering of
# the full E v2 environment - latest releases, 6 rolling trend lines, NYT
# salient headlines. Per D049b the agent's own prior answer is NOT injected;
# cross-month persistence comes from the trend sequences themselves.
# ---------------------------------------------------------------------------
_MONTH_FULL = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]

# (title, signal prefix, value style). History refs R-11..R-1 plus the latest
# release appended = 12 monthly points, oldest to newest.
_TREND_LINES = [
    ("CPI inflation (12-month %)", "bls_cpi_u_all_items_yoy_nsa", "pct"),
    ("Unemployment rate (%)", "bls_unemployment_rate_sa", "pct"),
    ("Regular gasoline price ($/gallon)", "eia_gasoline_retail_regular_mean", "usd"),
    ("Food prices (12-month %)", "bls_cpi_food_yoy_nsa", "pct"),
    ("Energy prices (12-month %)", "bls_cpi_energy_yoy_nsa", "pct"),
    ("Rent/shelter prices (12-month %)", "bls_cpi_shelter_yoy_nsa", "pct"),
]


def _month_label(ref: str) -> str:
    y, m = ref.split("-")
    return f"{_MONTH_FULL[int(m) - 1]} {y}"


def _news_date_label(iso_date: str) -> str:
    y, m, d = (int(x) for x in iso_date[:10].split("-"))
    return f"{_MONTH_FULL[m - 1][:3]} {d}"


def _full_date_label(iso: str) -> str:
    y, m, d = (int(x) for x in iso[:10].split("-"))
    return f"{_MONTH_FULL[m - 1]} {d}, {y}"


def _find_signal(signals: list[dict[str, Any]], prefix: str) -> dict[str, Any] | None:
    return next((s for s in signals
                 if s.get("signal_id", "").startswith(prefix)), None)


def _fmt_signed_pct(v: Any) -> str:
    v = float(v)
    return f"{v:+.1f}"


def _fmt_trend_value(v: Any, style: str) -> str:
    v = float(v)
    if style == "usd":
        return f"{v:.2f}"
    return f"{v:.1f}"


def _trend_line(title: str, prefix: str, style: str,
                latest: list[dict[str, Any]],
                history: list[dict[str, Any]]) -> str | None:
    hist = sorted((s for s in history
                   if s.get("signal_id", "").startswith(prefix)),
                  key=lambda s: s["reference_period"])
    if not hist:
        return None  # a trend line needs actual history, not one point
    last = _find_signal(latest, prefix)
    values = [_fmt_trend_value(s["value"], style) for s in hist]
    if last is not None:
        values.append(_fmt_trend_value(last["value"], style))
    if not values:
        return None
    return f"- {title}: {', '.join(values)}"


def build_sce_messages_v2(ob: Observation,
                          include_event_abstracts: bool = False,
                          ) -> list[dict[str, str]]:
    """English Q8/Q9 prompt v2: persona + compact E v2 rendering.

    Same whitelist and the same Q8/Q9 JSON contract as v1; only the
    presentation of the environment changes. The agent's own prior answer
    is deliberately absent (D049b). With include_event_abstracts, each
    headline is followed by its NYT abstract when present.
    """
    info = ob.macro_information
    profile = ob.local_physical.get("profile", {})
    signals = info.get("signals", [])
    latest = [s for s in signals if s.get("role") != "history"]
    history = [s for s in signals if s.get("role") == "history"]

    cpi_y = _find_signal(latest, "bls_cpi_u_all_items_yoy")
    cpi_m = _find_signal(latest, "bls_cpi_u_all_items_mom")
    ue = _find_signal(latest, "bls_unemployment_rate")
    nf = _find_signal(latest, "bls_nonfarm_payroll")
    gas = _find_signal(latest, "eia_gasoline_retail_regular_mean")
    ref_label = _month_label(cpi_y["reference_period"]) if cpi_y else ""
    ref_month_short = ref_label.split()[0] if ref_label else ""

    release_lines = []
    if cpi_y:
        seg = (f"- Consumer Price Index ({ref_label}): "
               f"{_fmt_signed_pct(cpi_y['value'])}% compared with a year earlier")
        if cpi_m:
            seg += (f"; {_fmt_signed_pct(cpi_m['value'])}% in "
                    f"{ref_month_short} alone")
        release_lines.append(seg)
    if ue:
        seg = f"- Unemployment rate ({ref_label}): {float(ue['value']):g}%"
        if nf:
            n = int(round(float(nf["value"]) * 1000))
            seg += (f"; U.S. employers added {n:,} jobs" if n >= 0
                    else f"; U.S. employers cut {abs(n):,} jobs")
        release_lines.append(seg)
    comp_parts = []
    for prefix, label in (("bls_cpi_gasoline_yoy", "gasoline"),
                          ("bls_cpi_energy_yoy", "energy"),
                          ("bls_cpi_food_yoy", "food"),
                          ("bls_cpi_food_at_home_yoy", "groceries (food at home)"),
                          ("bls_cpi_shelter_yoy", "rent and shelter")):
        c = _find_signal(latest, prefix)
        if c:
            comp_parts.append(f"{label} {_fmt_signed_pct(c['value'])}%")
    if comp_parts:
        seg = ("- Prices you may notice compared with a year ago: "
               + ", ".join(comp_parts) + ".")
        if gas:
            seg += (f" A gallon of regular gasoline costs about "
                    f"${float(gas['value']):.2f}.")
        release_lines.append(seg)

    trends = [line for line in
              (_trend_line(t, p, st, latest, history) for t, p, st in _TREND_LINES)
              if line]
    news = []
    for e in info.get("events", []):
        line = f"- {_news_date_label(e['pub_date'])}: \"{e['headline']}\""
        abstract = (e.get("abstract") or "").strip()
        if include_event_abstracts and abstract:
            line += f" — {abstract}"
        news.append(line)

    blocks = []
    if release_lines:
        blocks.append("Recent official statistics:\n" + "\n".join(release_lines))
    if trends:
        blocks.append("Recent trends (each lists the past 12 monthly releases, "
                      "oldest to newest):\n" + "\n".join(trends))
    if news:
        header = ("Recent news headlines (with brief summaries):"
                  if include_event_abstracts else "Recent news headlines:")
        blocks.append(header + "\n" + "\n".join(news))
    env_block = "\n\n".join(blocks)

    bin_lines = "\n".join(f'  "bin{i + 1}": probability that inflation will be {label}'
                          for i, label in enumerate(Q9_BIN_LABELS))
    user = f"""{_persona_sentence(profile)}

You are answering a monthly survey in {_month_label(info.get('target_month', ''))}. \
You only know information that was publicly available by {_full_date_label(info.get('as_of', ''))}.

{env_block}

Question 1 (point estimate): Over the next 12 months, what do you expect the rate of inflation to be,
in percent? Give a single signed number (negative means deflation).

Question 2 (density): What is the percent chance that the 12-month-ahead inflation rate will fall in
each of the following ten ranges? Give each a probability from 0 to 100; the ten probabilities must
sum to exactly 100.
{bin_lines}

Reply with ONLY a JSON object of the form:
{{"point_pct": <number>, "q9": {{"bin1": <0-100>, "bin2": <0-100>, ..., "bin10": <0-100>}},
 "reason": "<one or two short sentences>"}}"""
    return [{"role": "user", "content": user}]


def parse_sce_response(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse the LLM reply. Returns (parsed, error). Never raises, never normalizes."""
    candidate = text.strip()
    if not candidate:
        return None, "empty_response"
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate[:5].lower() == "json":
            candidate = candidate[5:]
        candidate = candidate.strip()
    try:
        obj = json.loads(candidate)
    except ValueError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            return None, "not_json"
        try:
            obj = json.loads(candidate[start:end + 1])
        except ValueError as exc:
            return None, f"not_json: {exc}"
    if not isinstance(obj, dict):
        return None, "json_not_object"
    try:
        point = float(obj["point_pct"])
    except (KeyError, TypeError, ValueError):
        return None, "missing_or_bad_point_pct"
    q9 = obj.get("q9")
    if not isinstance(q9, dict):
        return None, "missing_q9_object"
    bins: list[float] = []
    for i in range(1, 11):
        try:
            bins.append(float(q9[f"bin{i}"]))
        except (KeyError, TypeError, ValueError):
            return None, f"missing_or_bad_q9_bin{i}"
    return {"point_pct": point, "bins": bins,
            "reason": str(obj.get("reason", ""))[:500]}, None


def validate_sce_bins(bins: list[float]) -> tuple[bool, str | None, float]:
    """Q9 syntactic gate: bins in [0, 100], sum 100 within Q9_SUM_TOL. No normalization."""
    q9_sum = round(sum(bins), 6)
    if any(not (0.0 <= b <= 100.0) for b in bins):
        return False, "bin_out_of_range", q9_sum
    if abs(q9_sum - 100.0) > Q9_SUM_TOL:
        return False, f"q9_sum_{q9_sum}", q9_sum
    return True, None, q9_sum


# =============================================================================
# B — decision model (scripted rule or audited real LLM)
# =============================================================================
class SCEOpenAILLM:
    """Thin OpenAI-compatible chat wrapper. SDK retries are OFF (max_retries=0):
    every billed attempt is counted in our own ledger instead."""

    def __init__(self, *, model: str, temperature: float, max_tokens: int,
                 extra_body: dict[str, Any] | None = None,
                 response_format: str | None = "json_object", timeout_s: float = 60.0):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_body = dict(extra_body) if extra_body else None
        self.response_format = response_format
        self.timeout_s = timeout_s
        self._client = None

    def _get_client(self):
        if self._client is None:
            from socioverse.external_events import _load_dotenv
            _load_dotenv()
            from openai import OpenAI  # local import: the llm extra is optional
            key = os.environ.get("SV_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
            if not key:
                raise RuntimeError("SV_LLM_API_KEY is not set (env or .env); refusing to call.")
            self._client = OpenAI(
                api_key=key,
                base_url=os.environ.get("SV_LLM_BASE_URL", "https://api.openai.com/v1"),
                max_retries=0, timeout=self.timeout_s)
        return self._client

    def chat(self, messages: list[dict[str, str]]) -> tuple[Any, float]:
        kwargs: dict[str, Any] = {
            "model": self.model, "temperature": self.temperature,
            "max_tokens": self.max_tokens, "messages": messages,
        }
        if self.response_format:
            kwargs["response_format"] = {"type": self.response_format}
        if self.extra_body:
            kwargs["extra_body"] = dict(self.extra_body)
        t0 = time.perf_counter()
        resp = self._get_client().chat.completions.create(**kwargs)
        return resp, (time.perf_counter() - t0) * 1000.0


@register("decision", "sce_inflation_expectations.decision")
class SCEDecision(DecisionModel):
    def __init__(self, **decision_args: Any):
        self.llm_kind = decision_args.get("llm_kind", "scripted")
        self.prompt_version = decision_args.get("prompt_version", "sce-q8-q9-scripted-v1")
        self.model_version = decision_args.get("model_version", "deterministic-scripted-v1")
        self.seed = int(decision_args.get("seed", 42))
        # openai-mode configuration
        self.model = decision_args.get("model")  # requested model, pinned per run
        self.temperature = float(decision_args.get("temperature", 0.0))
        self.max_tokens = int(decision_args.get("max_tokens", 1024))
        self.max_calls = int(decision_args.get("max_calls", 0))  # 0 = unlimited (scripted only)
        self.max_prompt_chars = int(decision_args.get("max_prompt_chars", 16000))
        self.retry_max = int(decision_args.get("retry_max", 1))  # extra attempts per answer
        self.extra_body = decision_args.get("extra_body")
        self.response_format = decision_args.get("response_format", "json_object")
        self.timeout_s = float(decision_args.get("timeout_s", 60.0))
        self.price_input_per_mtok = decision_args.get("price_input_per_mtok")
        self.price_output_per_mtok = decision_args.get("price_output_per_mtok")
        self.cost_cap_usd = decision_args.get("cost_cap_usd")
        self.audit_dir = Path(decision_args["audit_dir"]) if decision_args.get("audit_dir") else None
        self.run_id = decision_args.get("run_id", "")
        # ledger state
        self.call_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.reserved_cost_usd = 0.0
        self.llm: SCEOpenAILLM | None = None
        if self.llm_kind == "openai":
            if not self.model:
                raise ValueError("llm_kind=openai requires decision_args.model to pin the model.")
            if self.max_calls < 1:
                raise ValueError("llm_kind=openai requires an explicit max_calls >= 1 budget.")
            if self.cost_cap_usd is not None:
                rates = (self.price_input_per_mtok, self.price_output_per_mtok)
                if (not isfinite(float(self.cost_cap_usd)) or float(self.cost_cap_usd) < 0
                        or any(r is None or not isfinite(float(r)) or float(r) < 0 for r in rates)):
                    raise ValueError("cost cap requires finite nonnegative cap and both token prices")
            self.llm = SCEOpenAILLM(
                model=self.model, temperature=self.temperature, max_tokens=self.max_tokens,
                extra_body=self.extra_body, response_format=self.response_format,
                timeout_s=self.timeout_s)
        elif self.llm_kind != "scripted":
            raise ValueError(f"unknown llm_kind: {self.llm_kind!r}")

    # ---- ledger -----------------------------------------------------------
    def estimated_cost_usd(self) -> float | None:
        if self.price_input_per_mtok is None or self.price_output_per_mtok is None:
            return None
        billed = (self.total_prompt_tokens * float(self.price_input_per_mtok)
                  + self.total_completion_tokens * float(self.price_output_per_mtok)) / 1_000_000.0
        return billed + self.reserved_cost_usd

    def cost_summary(self) -> dict[str, Any]:
        return {
            "call_count": self.call_count,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "reserved_cost_usd": round(self.reserved_cost_usd, 6),
            "estimated_cost_usd": (None if self.estimated_cost_usd() is None
                                   else round(self.estimated_cost_usd(), 6)),
            "price_input_per_mtok": self.price_input_per_mtok,
            "price_output_per_mtok": self.price_output_per_mtok,
            "request_reserve_rule": "prompt UTF-8 bytes + 256 input tokens, plus max_tokens output",
            "note": "Self-kept ledger from API usage fields; conservative reserve added for "
                    "calls that errored without usage. Not a vendor bill.",
        }

    def _request_cost_bound(self, prompt_text: str) -> float | None:
        """Planning bound for our plain text requests, at supplied token prices.

        UTF-8 byte count avoids the earlier characters/4 underestimate. The 256
        token allowance covers role framing. It is a local conservative budget
        guard, not a provider quote or guarantee about changed billing rules.
        """
        if self.price_input_per_mtok is None or self.price_output_per_mtok is None:
            return None
        input_bound = len(prompt_text.encode("utf-8")) + 256
        return (input_bound * float(self.price_input_per_mtok)
                + self.max_tokens * float(self.price_output_per_mtok)) / 1_000_000.0

    def _reserve_failed_call(self, prompt_text: str) -> None:
        """Conservative cost reservation for a call that errored without usage data."""
        if self.price_input_per_mtok is None or self.price_output_per_mtok is None:
            return
        self.reserved_cost_usd += self._request_cost_bound(prompt_text) or 0.0

    def _audit_llm_call(self, row: dict[str, Any]) -> None:
        if not self.audit_dir or not self.run_id:
            return
        _append_jsonl(self.audit_dir / "llm_calls.jsonl", row)

    # ---- scripted mode (identical to cloud v3) -----------------------------
    def _decide_scripted(self, obs: list[Observation]) -> list[Action]:
        actions: list[Action] = []
        for ob in obs:
            target = _target_from_observation(ob)
            signals = ob.macro_information.get("signals", [])
            profile = ob.local_physical.get("profile", {})
            inflation = next((float(s["value"]) for s in signals if "12-month" in s.get("measure", "")), 2.0)
            unemployment = next((float(s["value"]) for s in signals if "unemployment rate" in s.get("measure", "").lower()), 6.0)
            # Deterministic, transparent stylized rule; values are not calibrated predictions.
            adjustment = (_stable_int(f"{self.seed}|{ob.agent_id}|{target['target_month']}") % 7 - 3) * 0.05
            income = str(profile.get("household_income_band", ""))
            income_adjustment = 0.10 if income == "125k_plus" else (-0.05 if income == "under_35k" else 0.0)
            magnitude = round(max(0.0, inflation * 0.55 + (unemployment - 6.0) * -0.03 + adjustment + income_adjustment), 2)
            direction = "inflation" if magnitude > 0 else "deflation"
            point = round(magnitude if direction == "inflation" else -magnitude, 2)
            # Three adjacent middle bins: valid for the project's syntactic Q9 gate;
            # no official generalized-beta headline is computed here.
            shift = _stable_int(f"q9|{self.seed}|{ob.agent_id}|{target['target_month']}") % 5
            bins = [0.0, 0.0, 0.0, 25.0 + shift, 55.0 - shift, 20.0, 0.0, 0.0, 0.0, 0.0]
            q9_sum = round(sum(bins), 6)
            valid = all(0.0 <= x <= 100.0 for x in bins) and abs(q9_sum - 100.0) < 1e-9
            payload: dict[str, Any] = {
                "agent_id": ob.agent_id,
                "target_month": target["target_month"],
                "as_of": target["as_of"],
                "p_snapshot_id": "p_pilot_20260929_v1",
                "e_snapshot_id": f"bls_initial_release_e_{target['target_month']}",
                "direction": direction,
                "magnitude_pct": magnitude,
                "point_pct": point,
                "validation_status": "valid" if valid else "invalid",
                "q9_sum": q9_sum,
                "prompt_version": self.prompt_version,
                "model_version": self.model_version,
                "seed": self.seed,
                "reason": "我根据已发布的当月价格和就业信号形成这个判断。",
            }
            payload.update(dict(zip(Q9_KEYS, bins)))
            actions.append(Action(agent_id=ob.agent_id, step=ob.step, kind="sce_answer", payload=payload,
                                  rationale=[payload["reason"]], source="rule"))
        return actions

    # ---- openai mode ---------------------------------------------------------
    def _call_with_audit(self, ob: Observation, target: dict[str, str],
                         messages: list[dict[str, str]], attempt_idx: int) -> dict[str, Any]:
        """One audited LLM attempt. Never raises; the row records the outcome."""
        prompt_text = json.dumps(messages, ensure_ascii=False)
        row: dict[str, Any] = {
            "run_id": self.run_id,
            "call_seq": self.call_count,
            "agent_id": ob.agent_id,
            "runtime_step": ob.step,
            "target_month": target["target_month"],
            "attempt_idx": attempt_idx,
            "timestamp_utc": _utc_now(),
            "code_sha256": self_reported_code_sha256(),
            "prompt_version": self.prompt_version,
            "requested_model": self.model,
            "returned_model": None,
            "request_id": None,
            "system_fingerprint": None,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "extra_body": self.extra_body,
            "response_format": self.response_format,
            "prompt_chars": len(prompt_text),
            "prompt_sha256": _sha256_text(prompt_text),
            "prompt_text": prompt_text,
            "raw_response_text": None,
            "raw_response_sha256": None,
            "finish_reason": None,
            "usage": None,
            "latency_ms": None,
            "error": None,
        }
        try:
            resp, latency = self.llm.chat(messages)  # type: ignore[union-attr]
            row["latency_ms"] = round(latency, 1)
            choice = resp.choices[0]
            content = choice.message.content or ""
            row["raw_response_text"] = content
            row["raw_response_sha256"] = _sha256_text(content)
            row["finish_reason"] = getattr(choice, "finish_reason", None)
            row["returned_model"] = getattr(resp, "model", None)
            row["request_id"] = getattr(resp, "id", None)
            row["system_fingerprint"] = getattr(resp, "system_fingerprint", None)
            usage = getattr(resp, "usage", None)
            if usage is not None:
                row["usage"] = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }
                self.total_prompt_tokens += int(usage.prompt_tokens or 0)
                self.total_completion_tokens += int(usage.completion_tokens or 0)
            else:
                self._reserve_failed_call(prompt_text)
        except Exception as exc:  # noqa: BLE001 - every failure is evidence, not a crash
            row["error"] = f"{type(exc).__name__}: {exc}"
            self._reserve_failed_call(prompt_text)
        self._audit_llm_call(row)
        return row

    def _decide_openai_one(self, ob: Observation) -> Action:
        target = _target_from_observation(ob)
        if self.prompt_version.startswith("sce-q8-q9-v2"):
            messages = build_sce_messages_v2(
                ob,
                include_event_abstracts=self.prompt_version.startswith(
                    "sce-q8-q9-v2-abstract"),
            )
        else:
            messages = build_sce_messages(ob)
        base_payload: dict[str, Any] = {
            "agent_id": ob.agent_id,
            "target_month": target["target_month"],
            "as_of": target["as_of"],
            "p_snapshot_id": "p_pilot_20260929_v1",
            "e_snapshot_id": f"bls_initial_release_e_{target['target_month']}",
            "prompt_version": self.prompt_version,
            "model_version": self.model,
            "seed": self.seed,
        }
        prompt_text = json.dumps(messages, ensure_ascii=False)
        if len(prompt_text) > self.max_prompt_chars:
            payload = {**base_payload, "direction": "", "magnitude_pct": 0.0, "point_pct": 0.0,
                       "validation_status": "error", "q9_sum": 0.0,
                       "reason": f"prompt_too_long:{len(prompt_text)}>{self.max_prompt_chars}",
                       "llm": {"requested_model": self.model, "attempts": 0,
                               "outcome": "error", "error": "prompt_too_long"}}
            payload.update(dict.fromkeys(Q9_KEYS, 0.0))
            return Action(agent_id=ob.agent_id, step=ob.step, kind="sce_answer", payload=payload,
                          rationale=[payload["reason"]], source="llm")

        accepted: dict[str, Any] | None = None
        last_bins: list[float] = [0.0] * 10
        last_point = 0.0
        last_reason = ""
        last_error = "not_attempted"
        attempts = 0
        last_row: dict[str, Any] | None = None
        while attempts <= self.retry_max:
            if self.max_calls and self.call_count >= self.max_calls:
                last_error = "max_calls_exceeded"
                break
            cap = self.cost_cap_usd
            est = self.estimated_cost_usd()
            next_cost = self._request_cost_bound(json.dumps(messages, ensure_ascii=False))
            if cap is not None and est is not None and (est >= float(cap) or est + (next_cost or 0) > float(cap)):
                last_error = "cost_cap_exceeded"
                break
            self.call_count += 1
            row = self._call_with_audit(ob, target, messages, attempts)
            attempts += 1
            last_row = row
            if row["error"]:
                last_error = row["error"]
                continue
            parsed, perr = parse_sce_response(row["raw_response_text"] or "")
            if perr:
                last_error = perr
                messages = messages + [{"role": "user", "content": (
                    f"Your previous reply was invalid ({perr}). Reply again with ONLY the JSON "
                    "object, with point_pct, all ten q9 bins as numbers, and reason.")}]
                continue
            ok, verr, q9_sum = validate_sce_bins(parsed["bins"])
            last_bins = list(parsed["bins"])
            last_point = parsed["point_pct"]
            last_reason = parsed["reason"]
            if not ok:
                last_error = verr or "invalid"
                messages = messages + [{"role": "user", "content": (
                    f"Your previous reply was invalid ({verr}). Each bin must be 0-100 and the "
                    "ten bins must sum to exactly 100. Reply again with ONLY the JSON object.")}]
                continue
            accepted = parsed
            break

        if accepted:
            outcome = "valid"
        else:
            outcome = "error" if last_row is None or (last_row or {}).get("error") else "invalid"
        llm_meta = {
            "requested_model": self.model,
            "returned_model": (last_row or {}).get("returned_model"),
            "request_id": (last_row or {}).get("request_id"),
            "system_fingerprint": (last_row or {}).get("system_fingerprint"),
            "attempts": attempts,
            "finish_reason": (last_row or {}).get("finish_reason"),
            "outcome": outcome,
            "error": None if accepted else last_error,
        }
        if accepted:
            point = round(accepted["point_pct"], 4)
            direction = "inflation" if point > 0 else ("deflation" if point < 0 else "zero")
            payload = {**base_payload, "direction": direction,
                       "magnitude_pct": round(abs(point), 4), "point_pct": point,
                       "validation_status": "valid",
                       "q9_sum": round(sum(accepted["bins"]), 6),
                       "reason": accepted["reason"], "llm": llm_meta}
            payload.update(dict(zip(Q9_KEYS, accepted["bins"])))
        else:
            point = round(last_point, 4)
            payload = {**base_payload, "direction": "",
                       "magnitude_pct": round(abs(point), 4), "point_pct": point,
                       "validation_status": outcome,
                       "q9_sum": round(sum(last_bins), 6),
                       "reason": last_reason or last_error, "llm": llm_meta}
            payload.update(dict(zip(Q9_KEYS, last_bins)))
        # Action.source is a schema Literal ('llm'/'rule'/'fallback'/'replay'); the
        # valid/invalid/error distinction lives in payload.validation_status and llm.outcome.
        return Action(agent_id=ob.agent_id, step=ob.step, kind="sce_answer", payload=payload,
                      rationale=[payload["reason"]], source="llm")

    def decide_batch(self, obs: list[Observation], memories: dict[str, Any]) -> list[Action]:
        if self.llm_kind == "scripted":
            return self._decide_scripted(obs)
        return [self._decide_openai_one(ob) for ob in obs]


# =============================================================================
# metrics
# =============================================================================
@register("collector", "sce_inflation_expectations.collector")
class SCEMetricCollector(MetricCollector):
    def collect(self, env: SCEEnvironmentProvider, actions: list[Action], t: int) -> dict[str, Any]:
        vals = [float(a.payload["point_pct"]) for a in actions if a.kind == "sce_answer"]
        valid = [a for a in actions if a.payload.get("validation_status") == "valid"]
        med = float(median(vals)) if vals else 0.0
        return {
            "q8_point_median_demo": round(med, 4),
            "q9_valid_fraction": round(len(valid) / len(actions), 4) if actions else 0.0,
            "q9_density_eligible_count": len(valid),
            "panel_size": len(actions),
        }

    def columns(self) -> list[str]:
        return ["q8_point_median_demo", "q9_valid_fraction", "q9_density_eligible_count", "panel_size"]


def make_sce_inflation_bundles(**kwargs: Any) -> tuple[StudySpec, EnvironmentBundle, PopulationBundle, SimulationConfig]:
    raise NotImplementedError("Artifacts are authored in this repository and exported one-way; "
                              "run via socioverse_challenge/scripts/run_sce_local.py.")

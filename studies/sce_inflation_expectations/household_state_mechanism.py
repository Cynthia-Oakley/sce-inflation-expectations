"""Opt-in Q1-only A reconstruction treatment; no target-conditioned offsets."""
from copy import deepcopy
from .price_experience import canonical_hash, profile_hash

PROMPT_VERSION = "sce-q8-q9-household-state-v1"
SCHEMA = "sce-household-state-v1"
LABELS = {1: "much worse", 2: "somewhat worse", 3: "about the same",
          4: "somewhat better", 5: "much better"}
FIELDS = {"agent_id", "target_month", "financial_change_12m_code", "profile_sha256"}


def validate_bundle(bundle, personas, target_month):
    """Reject target columns, B use, stale profiles and partial ID coverage."""
    keys = {"schema_version", "research_line", "source", "target_month", "state_by_id"}
    if set(bundle) != keys or bundle["schema_version"] != SCHEMA:
        raise ValueError("invalid household-state bundle schema/keys")
    if bundle["research_line"] != "A_historical_reconstruction":
        raise ValueError("contemporaneous observed Q1 is only allowed for A reconstruction")
    if bundle["source"] != "SCE_Q1_current_microdata" or bundle["target_month"] != target_month:
        raise ValueError("Q1 source or target month mismatch")
    states = bundle["state_by_id"]
    if set(states) != {p.agent_id for p in personas}:
        raise ValueError("Q1 IDs must exactly match population")
    for p in personas:
        row = states[p.agent_id]
        if set(row) != FIELDS or row["agent_id"] != p.agent_id or row["target_month"] != target_month:
            raise ValueError("Q1 fields or routing mismatch")
        code = row["financial_change_12m_code"]
        if type(code) is not int or code not in LABELS:
            raise ValueError("Q1 must be integer code 1..5; no missing-value imputation")
        if row["profile_sha256"] != profile_hash(p.attributes):
            raise ValueError("Q1 profile hash mismatch")
    return deepcopy(bundle)


def build_state(row, profile, target_month):
    if set(row) != FIELDS or row["target_month"] != target_month:
        raise ValueError("Q1 row schema or month mismatch")
    if row["profile_sha256"] != profile_hash(profile):
        raise ValueError("Q1 profile mismatch in observation")
    if type(row["financial_change_12m_code"]) is not int or row["financial_change_12m_code"] not in LABELS:
        raise ValueError("invalid Q1 code")
    return {"financial_change_12m_code": row["financial_change_12m_code"],
            "source": "SCE_Q1_current_microdata", "research_line": "A_historical_reconstruction",
            "state_sha256": canonical_hash(row)}


def build_household_state_messages(ob, base_messages):
    state = ob.local_information.get("household_state")
    if not state or state.get("research_line") != "A_historical_reconstruction":
        raise ValueError("Q1 prompt requires explicit A observed-state input")
    code = state["financial_change_12m_code"]
    if type(code) is not int or code not in LABELS:
        raise ValueError("invalid Q1 code")
    messages = deepcopy(base_messages)
    marker = "Question 1 (point estimate):"
    content = messages[0]["content"]
    if content.count(marker) != 1:
        raise ValueError("Q1 insertion requires an unchanged v2 questionnaire")
    block = ("Household experience reported in this survey month:\n"
             f"- Compared with 12 months ago, your household's financial situation is {LABELS[code]}.\n"
             "- This describes your own financial situation; it is not a recorded answer about future inflation.\n\n")
    pos = content.index(marker)
    messages[0]["content"] = content[:pos] + block + content[pos:]
    return messages

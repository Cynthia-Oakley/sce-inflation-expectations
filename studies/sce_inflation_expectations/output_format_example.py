"""Value-free, fully expanded answer shapes for newly prepared SCE prompts."""
from copy import deepcopy

FORMAT_VERSION = "sce-output-structure-example-v1"


def structure_example(*, include_point=True, include_reason=True):
    """Return a complete shape example, with no illustrative numerical answers."""
    fields = []
    if include_point:
        fields.append('  "point_pct": <signed_number>')
    bins = ",\n".join(f'    "bin{i}": <probability>' for i in range(1, 11))
    fields.append('  "q9": {\n' + bins + '\n  }')
    if include_reason:
        fields.append('  "reason": "<brief_reason>"')
    return "{\n" + ",\n".join(fields) + "\n}"


def format_instruction(*, include_point=True, include_reason=True):
    example = structure_example(include_point=include_point, include_reason=include_reason)
    return (
        "Output structure example (placeholders only):\n"
        "Use the exact field names and nesting shown below. The q9 field contains an object "
        "with all ten keys, bin1 through bin10. Replace every angle-bracket placeholder with "
        "your own answer. Emit probabilities as JSON numbers, without quotation marks; "
        "use a signed JSON number for point_pct when that field is shown. "
        "Each probability must be between 0 and 100 and the ten probabilities must sum to 100. "
        "Emit the completed JSON object only, with no markdown fences, literal placeholders, "
        "ellipses, or flat keys such as q9.bin1.\n"
        + example
    )


def append_format_example(messages, *, include_point=True, include_reason=True):
    """Copy and append to the final user message; never rewrite frozen inputs."""
    result = deepcopy(messages)
    if not result or result[-1].get("role") != "user" or not isinstance(result[-1].get("content"), str):
        raise ValueError("A final text user message is required")
    result[-1]["content"] += "\n\n" + format_instruction(
        include_point=include_point, include_reason=include_reason)
    return result

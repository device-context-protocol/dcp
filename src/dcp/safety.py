"""Safety: validate intent calls against the manifest before they hit the wire.

The Bridge is the trust boundary. The LLM's params come in here untrusted; what
comes out is either ``SafetyError`` (refused) or a normalized param dict.
"""
from __future__ import annotations

import re

from dcp.manifest import Intent

_NUMERIC_TYPES = {"float", "int", "duration"}

# Compiled patterns are cached by source string so check_call stays cheap
# in tight loops (LLM Bridge invocations).
_PATTERN_CACHE: dict[str, re.Pattern] = {}


def _get_pattern(src: str) -> re.Pattern:
    p = _PATTERN_CACHE.get(src)
    if p is None:
        p = re.compile(src)
        _PATTERN_CACHE[src] = p
    return p


class SafetyError(Exception):
    """Raised when an intent call violates the manifest.

    ``status`` maps directly to a DCP reply status code:
    ``denied``, ``range``, ``unknown_intent``, ``capability_required``.
    """

    def __init__(self, status: str, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


def check_call(
    intent: Intent,
    params: dict,
    *,
    granted_capabilities: set[str],
) -> dict:
    """Validate and normalize params against an intent. Raises SafetyError on violation."""
    if intent.capability and intent.capability not in granted_capabilities:
        raise SafetyError("capability_required", f"missing capability '{intent.capability}'")

    extra = set(params) - set(intent.params)
    if extra:
        raise SafetyError("range", f"unknown parameters: {sorted(extra)}")

    normalized: dict = {}
    for name, param in intent.params.items():
        if name in params:
            value = params[name]
        elif param.default is not None:
            value = param.default
        else:
            raise SafetyError("range", f"missing required parameter '{name}'")

        value = _coerce(value, param.type, name)

        if param.range is not None and param.type in _NUMERIC_TYPES:
            lo, hi = param.range
            if value < lo or value > hi:
                raise SafetyError("range", f"'{name}'={value} outside [{lo}, {hi}]")

        # String-typed constraints: max_length + regex pattern. Both are
        # opt-in per the manifest; absent constraints mean "anything goes".
        if param.type == "string" and isinstance(value, str):
            if param.max_length is not None and len(value) > param.max_length:
                raise SafetyError(
                    "range",
                    f"'{name}' length {len(value)} exceeds max_length {param.max_length}")
            if param.pattern is not None:
                if not _get_pattern(param.pattern).fullmatch(value):
                    raise SafetyError(
                        "range",
                        f"'{name}' does not match pattern {param.pattern!r}")

        normalized[name] = value

    return normalized


def _coerce(value, type_: str, name: str):
    try:
        if type_ in ("float", "duration"):
            return float(value)
        if type_ == "int":
            return int(value)
        if type_ == "bool":
            return bool(value)
        if type_ == "string":
            return str(value)
    except (TypeError, ValueError) as e:
        raise SafetyError("range", f"'{name}' cannot be coerced to {type_}: {e}") from e
    return value  # unknown type — pass through

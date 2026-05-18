"""Safety: validate intent calls against the manifest before they hit the wire.

The Bridge is the trust boundary. The LLM's params come in here untrusted; what
comes out is either ``SafetyError`` (refused) or a normalized param dict.
"""
from __future__ import annotations

from dcp.manifest import Intent

_NUMERIC_TYPES = {"float", "int", "duration"}


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

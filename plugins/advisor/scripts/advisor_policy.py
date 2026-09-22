"""Fixed Astra consultation policy shared by the skill and local transport.

This module intentionally has no Codex, network, shell, or repository side
effects.  It is the small policy boundary that prevents legacy tier/model
selection from leaking into the active consultation path.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Iterable, Mapping


MODEL = "gpt-6-astra"
LEVELS = ("low", "medium", "high", "extra_high")
RUNTIME_EFFORTS = {"low": "low", "medium": "medium", "high": "high", "extra_high": "xhigh"}
NEXT_LEVEL = {level: LEVELS[index + 1] if index + 1 < len(LEVELS) else None for index, level in enumerate(LEVELS)}


class PolicyError(ValueError):
    """The caller attempted to bypass the bounded Astra policy."""


class PolicyUnavailable(PolicyError):
    """The requested policy level is not advertised by the local runtime."""


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def should_consult(
    *,
    approved_plan: bool = False,
    standalone: bool = False,
    explicit_advisor: bool = False,
    uncertainty: bool = False,
    material_impact: bool = False,
    routine: bool = False,
    cheap_check_resolved: bool = False,
    implementation_started: bool = False,
    completion_check: bool = False,
    checkpoint_consulted: bool = False,
    no_delegation: bool = False,
) -> bool:
    """Return whether one checkpoint has earned an advisor opportunity.

    The negative gates deliberately run first: a completion check, a routine
    operation, or an already-consumed opportunity never becomes a new token
    spend merely because the task is large or the caller wants reassurance.
    """

    if (
        routine
        or cheap_check_resolved
        or implementation_started
        or completion_check
        or checkpoint_consulted
        or no_delegation
    ):
        return False
    if not uncertainty or not material_impact:
        return False
    return approved_plan or (standalone and explicit_advisor)


def resolve_selection(
    level: str | None = None,
    *,
    chain_authorized: bool = False,
    supported_efforts: Iterable[str] | None = None,
) -> dict[str, str]:
    """Resolve one explicit policy level to Astra and its runtime effort.

    Only the first level may be selected without a verified chain transition.
    ``extra_high`` is a skill-level label and maps transparently to Codex's
    current ``xhigh`` runtime value; lack of that runtime capability is a
    typed unavailable result, never a fallback to another level/model.
    """

    level = level or "low"
    if level not in LEVELS:
        raise PolicyError("unsupported advisor level")
    if level != "low" and not chain_authorized:
        raise PolicyError("higher advisor levels require a verified escalation")
    effort = RUNTIME_EFFORTS[level]
    if supported_efforts is not None and effort not in set(supported_efforts):
        raise PolicyUnavailable(f"runtime does not advertise {effort} for {level}")
    return {"level": level, "model": MODEL, "effort": effort}


def validate_escalation(current_level: str, escalation: Mapping[str, Any]) -> str | None:
    """Validate one advisor response's adjacent escalation request."""

    if current_level not in LEVELS:
        raise PolicyError("unsupported current advisor level")
    required = {"next_level", "reason", "unresolved_difficulty", "required_resolution"}
    if not isinstance(escalation, Mapping) or set(escalation) != required:
        raise PolicyError("invalid escalation object")
    next_level = escalation["next_level"]
    if next_level is None:
        return None
    if next_level != NEXT_LEVEL[current_level]:
        raise PolicyError("escalation must request the immediate next level")
    if not all(_nonblank(escalation[name]) for name in required - {"next_level"}):
        raise PolicyError("escalation request must explain the unresolved difficulty")
    return next_level


def validate_response(current_level: str, response: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the typed response boundary without consulting external state."""

    if not isinstance(response, Mapping):
        raise PolicyError("advisor response must be an object")
    expected = {
        "recommendation",
        "why",
        "strongest_objection",
        "change_my_mind",
        "acceptance_checks",
        "risks",
        "follow_up_areas",
        "escalation",
    }
    if set(response) != expected:
        raise PolicyError("advisor response fields do not match the contract")
    for name in (
        "recommendation",
        "why",
        "strongest_objection",
        "change_my_mind",
        "risks",
        "follow_up_areas",
    ):
        if not _nonblank(response[name]):
            raise PolicyError(f"advisor response field is blank: {name}")
    checks = response["acceptance_checks"]
    if not isinstance(checks, list) or not checks or not all(_nonblank(item) for item in checks):
        raise PolicyError("advisor acceptance_checks must be nonempty and nonblank")
    escalation = dict(response["escalation"]) if isinstance(response["escalation"], Mapping) else response["escalation"]
    next_level = validate_escalation(current_level, escalation)
    return {"next_level": next_level}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the fixed Astra advisor policy.")
    parser.add_argument("command", choices=("resolve", "validate-escalation", "validate-response"))
    parser.add_argument("--level", default="low")
    parser.add_argument("--chain-authorized", action="store_true")
    parser.add_argument("--supported-effort", action="append", default=None)
    parser.add_argument("--response")
    args = parser.parse_args(argv)
    try:
        if args.command == "resolve":
            result: Any = resolve_selection(
                args.level,
                chain_authorized=args.chain_authorized,
                supported_efforts=args.supported_effort,
            )
        else:
            if not args.response:
                raise PolicyError("--response is required")
            response = json.loads(args.response)
            if args.command == "validate-response":
                result = validate_response(args.level, response)
            else:
                result = {"next_level": validate_escalation(args.level, response)}
    except (PolicyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "unavailable", "error": str(exc)}, separators=(",", ":")))
        return 2
    print(json.dumps({"status": "ok", **result}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

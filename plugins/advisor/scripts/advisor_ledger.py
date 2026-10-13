"""Durable issue admission, consumption and conservative recovery CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path

from advisor_admission import authorize, bounded_file, parent_evidence
from advisor_acceptance import verify_acceptance
from advisor_ledger_store import MAX_ISSUES, Store, digest, process_identity
from advisor_settings import normalize_level
from advisor_state import (
    ConfigError,
    TRANSPORT_CONTRACT_VERSION,
    _duplicate_key,
    validate_response,
)

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
HEX = re.compile(r"[0-9a-f]{64}")


def project_identity(root):
    root = Path(root).resolve(strict=True)
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    if proc.returncode:
        raise ConfigError("ledger project must be a Git checkout")
    common = Path(proc.stdout.strip()).resolve(strict=True)
    canonical = str(common)
    # Windows drive mounts can spell one physical repository in different cases.
    # Preserve case on ordinary Linux paths; conservatively fold mapped drives.
    if re.match(r"^/mnt/[A-Za-z]/", canonical):
        canonical = canonical.casefold()
    return hashlib.sha256(canonical.encode()).hexdigest()


def canonical_packet(packet):
    text = unicodedata.normalize("NFC", bounded_file(Path(packet)).decode("utf-8"))
    # Formatting/observation timestamps alone are not materially new evidence.
    text = re.sub(
        r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b",
        "<timestamp>",
        text,
    )
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return hashlib.sha256(
        "\n".join(line for line in lines if line).encode()
    ).hexdigest()


def identity(args):
    if not args.issue or not ID.fullmatch(args.issue):
        raise ConfigError("ledger requires stable --issue-id")
    project = project_identity(args.project_root)
    return project, digest([project, args.issue])


def receipt_file(path):
    value = json.loads(bounded_file(Path(path)), object_pairs_hook=_duplicate_key)
    if not isinstance(value, dict):
        raise ConfigError("ledger receipt must be an object")
    verify_acceptance(value)
    return value


def require_binding(body, issue, receipt, execution=None):
    binding = receipt.get("ledger")
    if (
        receipt.get("schema_version") != 4
        or not isinstance(binding, dict)
        or set(binding)
        != {
            "version",
            "namespace",
            "project",
            "issue",
            "execution",
            "level",
            "canonical",
            "policy",
        }
        or binding["version"] != 1
        or binding["namespace"] != body["namespace"]
        or binding["project"] != issue["project"]
        or binding["issue"] != issue["id"]
        or binding["canonical"] != issue["canonical"]
        or binding["policy"] != issue["policy"]
    ):
        raise ConfigError(
            "ledger receipt binding mismatch; A receipts cannot authorize B"
        )
    level = binding["level"]
    record = issue["executions"].get(level)
    if (
        not isinstance(record, dict)
        or record["id"] != binding["execution"]
        or execution is not None
        and execution != record["id"]
        or receipt.get("packet_identity", {}).get("sha256") != record["raw_packet"]
        or receipt.get("runtime_source") != record["source"]
        or receipt.get("runtime", {}).get("parent_thread_id") != record["parent"]
        or receipt.get("selection", {}).get("level") != level
        or receipt["selection"].get("source_revision") != issue["policy"]
    ):
        raise ConfigError("ledger execution/packet/source/parent mismatch")
    return record


def reserve(store, args):
    project, key = identity(args)
    level = normalize_level(args.level)
    if not ID.fullmatch(args.execution) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", args.policy
    ):
        raise ConfigError("invalid ledger execution/policy")
    canonical = canonical_packet(args.packet)
    raw = hashlib.sha256(bounded_file(Path(args.packet))).hexdigest()
    source = json.loads(args.source, object_pairs_hook=_duplicate_key)
    owner = process_identity(args.launcher_pid or os.getppid())
    if not owner or not isinstance(source, dict):
        raise ConfigError("launcher ownership/source unavailable")
    prior = receipt_file(args.receipt) if args.receipt else None
    binding = None
    with store.transaction(mutate=True) as body:
        canonical_key = digest([project, canonical])
        registered = body["canonical"].get(canonical_key)
        if registered is not None and registered != key:
            raise ConfigError(
                "canonical packet already consumed under another issue ID"
            )
        issue = body["issues"].get(key)
        if issue is None:
            if level != "low" or prior is not None:
                raise ConfigError("new issue must begin low without legacy receipt")
            if len(body["issues"]) >= MAX_ISSUES:
                raise ConfigError(
                    "ledger registry full; consumed identities cannot be pruned"
                )
            revision = None
            if args.supersedes:
                old = body["issues"].get(digest([project, args.supersedes]))
                if (
                    old is None
                    or old["canonical"] == canonical
                    or not args.reason.strip()
                    or not HEX.fullmatch(args.evidence)
                    or args.evidence in (canonical, old.get("evidence"))
                ):
                    raise ConfigError(
                        "material revision needs linked old issue, new packet, reason and new evidence digest"
                    )
                revision = {
                    "supersedes": args.supersedes,
                    "reason_digest": digest(args.reason),
                    "evidence": args.evidence,
                }
            issue = {
                "key": key,
                "id": args.issue,
                "project": project,
                "canonical": canonical,
                "canonical_key": canonical_key,
                "policy": args.policy,
                "parent": args.parent,
                "closed": False,
                "executions": {},
                "transfer": None,
                "revision_proof": revision,
                "evidence": args.evidence or None,
            }
            body["issues"][key] = issue
            body["canonical"][canonical_key] = key
        if issue["canonical"] != canonical or issue["policy"] != args.policy:
            raise ConfigError(
                "issue packet/policy mismatch; explicit material revision required"
            )
        if level in issue["executions"] or issue["closed"]:
            raise ConfigError("issue/level already consumed or closed; no replay/retry")
        if issue["parent"] != args.parent:
            raise ConfigError(
                "parent changed; explicit transfer/reconcile proof required"
            )
        if level != "low":
            if prior is None:
                raise ConfigError("ledger previous receipt required")
            record = require_binding(body, issue, prior)
            if (
                record["state"] != "accepted"
                or record.get("consumed")
                or record.get("next") != level
                or record.get("receipt_digest") != digest(prior)
            ):
                raise ConfigError(
                    "previous receipt already consumed or not the adjacent accepted execution"
                )
            record["consumed"] = True
        elif issue["executions"]:
            raise ConfigError("low already consumed")
        issue["executions"][level] = {
            "id": args.execution,
            "state": "reserved",
            "owner": owner,
            "parent": args.parent,
            "raw_packet": raw,
            "source": source,
            "consumed": False,
        }
        binding = {
            "version": 1,
            "namespace": body["namespace"],
            "project": project,
            "issue": args.issue,
            "execution": args.execution,
            "level": level,
            "canonical": canonical,
            "policy": args.policy,
        }
    return {"status": "ok", "ledger": binding}


def execution_for(body, args):
    _, key = identity(args)
    issue = body["issues"].get(key)
    if not issue:
        raise ConfigError("ledger issue unavailable")
    matches = [r for r in issue["executions"].values() if r["id"] == args.execution]
    if len(matches) != 1:
        raise ConfigError("ledger execution unavailable or ambiguous")
    return issue, matches[0]


def update_execution(store, args):
    receipt = receipt_file(args.receipt) if args.receipt else None
    with store.transaction(mutate=True) as body:
        issue, record = execution_for(body, args)
        if args.action != "reconcile" and record["owner"] != process_identity(
            args.launcher_pid or os.getppid()
        ):
            raise ConfigError("ledger launcher process ownership mismatch")
        if args.action == "start":
            if record["state"] != "reserved":
                raise ConfigError("reservation already started/consumed")
            record["state"] = "started"
        elif args.action == "fail":
            if record["state"] not in ("reserved", "started"):
                raise ConfigError("ledger execution already terminal")
            record["state"] = args.outcome
        else:
            if (
                args.action == "reconcile"
                and process_identity(record["owner"]["pid"]) == record["owner"]
            ):
                raise ConfigError("cannot reconcile an active owned launcher")
            if record["state"] == "accepted":
                if receipt is not None and record["receipt_digest"] != digest(receipt):
                    raise ConfigError(
                        "reconcile receipt differs from committed execution"
                    )
                return {"status": "ok", "execution": record["id"], "state": "accepted"}
            if record["state"] not in ("reserved", "started", "unknown"):
                raise ConfigError("ledger execution terminal; no recovery launch")
            if receipt is None:
                if args.action != "reconcile":
                    raise ConfigError(
                        "accepted persistence requires authenticated receipt"
                    )
                record["state"] = "unknown"
            else:
                require_binding(body, issue, receipt, args.execution)
                # Reconcile independently repeats the persisted runtime acceptance.
                if args.action == "reconcile":
                    authorize(
                        receipt["selection"]["level"],
                        Path(args.receipt),
                        Path(args.packet),
                        record["parent"],
                        args.sessions_dir,
                        issue["policy"],
                        verify_only=True,
                    )
                if (
                    receipt.get("status") != "completed"
                    or receipt.get("outcome") != "accepted"
                ):
                    raise ConfigError("ledger receipt is not accepted")
                validate_response(
                    receipt["selection"]["level"], receipt["advisor_response"]
                )
                if receipt["escalation"] != receipt["advisor_response"]["escalation"]:
                    raise ConfigError(
                        "ledger escalation differs from validated response"
                    )
                record.update(
                    state="accepted",
                    receipt_digest=digest(receipt),
                    next=receipt["escalation"]["next_level"],
                    runtime_digest=digest(receipt["runtime"]),
                )
                if record["next"] is None:
                    issue["closed"] = True
        result = {"status": "ok", "execution": record["id"], "state": record["state"]}
    return result


def verify_transfer(store, args):
    receipt = receipt_file(args.receipt)
    with store.transaction() as body:
        _, key = identity(args)
        issue = body["issues"].get(key)
        if not issue:
            raise ConfigError("ledger issue unavailable")
        record = require_binding(body, issue, receipt)
        if args.parent != record["parent"]:
            proof = issue.get("transfer")
            if (
                not proof
                or proof["from"] != record["parent"]
                or proof["to"] != args.parent
                or proof["receipt"] != digest(receipt)
            ):
                raise ConfigError(
                    "previous parent guard requires explicit ledger transfer"
                )
        return {"status": "ok", "receipt_parent": record["parent"]}


def transfer(store, args):
    receipt = receipt_file(args.receipt)
    parent_evidence(args.parent, args.sessions_dir)
    old_parent = receipt.get("runtime", {}).get("parent_thread_id")
    # parent inspector still requires the environment's actual parent, also for old evidence.
    prior_env = os.environ.get("CODEX_THREAD_ID")
    try:
        os.environ["CODEX_THREAD_ID"] = old_parent
        authorize(
            receipt["selection"]["level"],
            Path(args.receipt),
            Path(args.packet),
            old_parent,
            args.sessions_dir,
            receipt["selection"]["source_revision"],
            verify_only=True,
        )
    finally:
        if prior_env is None:
            os.environ.pop("CODEX_THREAD_ID", None)
        else:
            os.environ["CODEX_THREAD_ID"] = prior_env
    with store.transaction(mutate=True) as body:
        _, key = identity(args)
        issue = body["issues"].get(key)
        if not issue:
            raise ConfigError("ledger issue unavailable")
        record = require_binding(body, issue, receipt)
        if (
            issue["closed"]
            or record["state"] != "accepted"
            or record.get("consumed")
            or record.get("receipt_digest") != digest(receipt)
            or issue["parent"] != old_parent
            or any(
                r["state"] in ("reserved", "started", "unknown")
                for r in issue["executions"].values()
            )
        ):
            raise ConfigError(
                "transfer requires inactive accepted chain and complete proof"
            )
        issue["transfer"] = {
            "from": old_parent,
            "to": args.parent,
            "receipt": digest(receipt),
        }
        issue["parent"] = args.parent
    return {"status": "ok", "parent": args.parent}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger-dir", default=os.environ.get("ADVISOR_LEDGER_DIR"))
    parser.add_argument(
        "--project-root", default=os.environ.get("ADVISOR_PROJECT_ROOT", os.getcwd())
    )
    parser.add_argument(
        "--issue-id", dest="issue", default=os.environ.get("ADVISOR_ISSUE_ID")
    )
    parser.add_argument(
        "action",
        choices=(
            "init",
            "status",
            "reserve",
            "start",
            "accept",
            "fail",
            "reconcile",
            "transfer",
            "verify-transfer",
            "prune",
            "import-a",
        ),
    )
    parser.add_argument("--launcher-pid", type=int)
    parser.add_argument("--level", default="low")
    parser.add_argument("--execution", default="")
    parser.add_argument("--packet", default="")
    parser.add_argument("--parent", default="")
    parser.add_argument("--policy", default="")
    parser.add_argument("--source", default="{}")
    parser.add_argument("--receipt")
    parser.add_argument("--sessions-dir", default="")
    parser.add_argument(
        "--outcome",
        choices=("failed", "cancelled", "timed_out", "unknown"),
        default="unknown",
    )
    parser.add_argument("--supersedes", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--evidence", default="")
    args = parser.parse_args()
    try:
        if not args.ledger_dir:
            raise ConfigError("ledger namespace unavailable; explicit init required")
        store = Store(args.ledger_dir)
        if args.action == "init":
            result = {"status": "ok", **store.initialize()}
        elif args.action == "reserve":
            result = reserve(store, args)
        elif args.action in ("start", "accept", "fail", "reconcile"):
            result = update_execution(store, args)
        elif args.action == "transfer":
            result = transfer(store, args)
        elif args.action == "verify-transfer":
            result = verify_transfer(store, args)
        elif args.action == "import-a":
            result = import_a(store, args)
        else:
            with store.transaction(mutate=args.action == "prune") as body:
                if args.action == "prune":
                    for issue in body["issues"].values():
                        if issue["closed"]:
                            for record in issue["executions"].values():
                                record.pop("runtime_digest", None)
                result = {"status": "ok", "registry": body}
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except (
        ConfigError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
        RecursionError,
    ) as exc:
        print(
            json.dumps(
                {"status": "unavailable", "error": str(exc)}, separators=(",", ":")
            )
        )
        return 2


def import_a(store, args):
    """Conservative legacy import closes the packet, never grants a B continuation."""
    receipt = receipt_file(args.receipt)
    if (
        receipt.get("schema_version") != 3
        or receipt.get("selection", {}).get("transport_contract_version") != "1.5"
    ):
        raise ConfigError("legacy import requires authenticated A receipt")
    project, key = identity(args)
    raw = hashlib.sha256(bounded_file(Path(args.packet))).hexdigest()
    if receipt.get("packet_identity") != {"sha256": raw}:
        raise ConfigError("legacy import packet mismatch")
    prior_parent = os.environ.get("CODEX_THREAD_ID")
    try:
        os.environ["CODEX_THREAD_ID"] = receipt["runtime"]["parent_thread_id"]
        authorize(
            receipt["selection"]["level"],
            Path(args.receipt),
            Path(args.packet),
            receipt["runtime"]["parent_thread_id"],
            args.sessions_dir,
            receipt["selection"]["source_revision"],
            verify_only=True,
            allow_legacy=True,
        )
    finally:
        if prior_parent is None:
            os.environ.pop("CODEX_THREAD_ID", None)
        else:
            os.environ["CODEX_THREAD_ID"] = prior_parent
    canonical = canonical_packet(args.packet)
    with store.transaction(mutate=True) as body:
        canonical_key = digest([project, canonical])
        if (
            key in body["issues"]
            or canonical_key in body["canonical"]
            or len(body["issues"]) >= MAX_ISSUES
        ):
            raise ConfigError("legacy issue already consumed or registry full")
        body["canonical"][canonical_key] = key
        body["issues"][key] = {
            "key": key,
            "id": args.issue,
            "project": project,
            "canonical": canonical,
            "canonical_key": canonical_key,
            "policy": receipt["selection"]["source_revision"],
            "parent": receipt["runtime"]["parent_thread_id"],
            "closed": True,
            "executions": {},
            "legacy_receipt_digest": digest(receipt),
            "transfer": None,
        }
    return {
        "status": "ok",
        "legacy": "closed-tombstone",
        "transport_contract_version": TRANSPORT_CONTRACT_VERSION,
    }


if __name__ == "__main__":
    raise SystemExit(main())

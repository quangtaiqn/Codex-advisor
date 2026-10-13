"""Production launcher proof for policy transitions; fixtures are not live inference."""
from __future__ import annotations
import json
import hashlib
import subprocess
import unittest

if __package__:
    from .advisor_transport_support import AdvisorTransportTestCase, PARENT
else:
    from advisor_transport_support import AdvisorTransportTestCase, PARENT


class AdvisorEscalationTests(AdvisorTransportTestCase):
    def receipt(self, result, name="previous.json"):
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.root / name
        path.write_text(result.stdout)
        path.chmod(0o600)
        return path

    def test_adjacent_ladder_uses_actual_runtime_efforts_and_role_aliases(self):
        previous = self.receipt(self.run_transport("--tier","standard",case="adjacent"))
        for level, option, alias in (("medium","--tier","specialist"),
                                     ("high","--role","advisor-terra"),
                                     ("extra_high","--role","advisor-sol")):
            result = self.run_transport("--level",level,option,alias,"--previous-result",str(previous),"--authorize-escalation",case="adjacent")
            previous = self.receipt(result,level+".json")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["selection"]["level"],level)
            self.assertEqual(len(payload["attempts"]),1)
        self.assertEqual([(r["model"],r["effort"]) for r in self.rows()],
                         [("gpt-6-astra","low"),("gpt-6-astra","medium"),("gpt-6-astra","high"),("gpt-6-astra","xhigh")])
        for row, allowed in zip(self.rows(), ([None,"medium"], [None,"high"], [None,"extra_high"], [None]), strict=True):
            observed = row["output_schema"]["properties"]["escalation"]["properties"]["next_level"]
            self.assertEqual(observed["type"], ["string", "null"])
            self.assertEqual(observed["enum"], allowed)
        final = json.loads(previous.read_text())
        self.assertIsNone(final["escalation"]["next_level"])
        terminal = self.run_transport("--level","extra_high","--previous-result",str(previous),"--authorize-escalation")
        self.assertNotEqual(terminal.returncode,0)
        self.assertIn("terminal previous level",terminal.stderr)
        self.assertEqual(len(self.rows()),4)

    def test_sufficient_result_stops_and_receipt_cannot_forge_escalation(self):
        previous = self.receipt(self.run_transport("--level","low"))
        result = self.run_transport("--level","medium","--previous-result",str(previous),"--authorize-escalation")
        self.assertNotEqual(result.returncode,0)
        self.assertIn("stop when sufficient",result.stderr)
        receipt = json.loads(previous.read_text())
        escalation = {"next_level":"medium","reason":"ambiguous","unresolved_difficulty":"material","required_resolution":"compare"}
        receipt["advisor_response"]["escalation"] = escalation
        receipt["escalation"] = escalation
        previous.write_text(json.dumps(receipt))
        forged = self.run_transport("--level","medium","--previous-result",str(previous),"--authorize-escalation")
        self.assertNotEqual(forged.returncode,0)
        self.assertIn("persisted response",forged.stderr)
        self.assertEqual(len(self.rows()),1)

    def test_receipt_identity_and_adjacent_admission_negatives_spawn_nothing(self):
        previous = self.receipt(self.run_transport("--role","advisor-astra",case="adjacent"))
        original = previous.read_text()
        changes = (
            ("schema_version",2),
            ("outcome","failed"),
            ("packet_identity",{"sha256":"0"*64}),
            ("runtime_source",{"source":"forged"}),
        )
        for key, value in changes:
            payload = json.loads(original)
            payload[key] = value
            previous.write_text(json.dumps(payload))
            result = self.run_transport("--level","medium","--previous-result",str(previous),"--authorize-escalation")
            self.assertNotEqual(result.returncode,0,key)
            self.assertEqual(len(self.rows()),1,key)
        for key, value in (("model","other/model"),("effort","high"),("transport_contract_version","1.4"),("role","other-role")):
            payload = json.loads(original)
            payload["selection"][key]=value
            previous.write_text(json.dumps(payload))
            result=self.run_transport("--level","medium","--previous-result",str(previous),"--authorize-escalation")
            self.assertNotEqual(result.returncode,0,key)
            self.assertEqual(len(self.rows()),1,key)
        payload=json.loads(original)
        payload["runtime"]["parent_thread_id"]="00000000-0000-7000-8000-000000000000"
        previous.write_text(json.dumps(payload))
        wrong_parent=self.run_transport("--level","medium","--previous-result",str(previous),"--authorize-escalation")
        self.assertNotEqual(wrong_parent.returncode,0)
        self.assertIn("parent/child/role mismatch",wrong_parent.stderr)
        previous.write_text(original)
        for level in ("low","high","extra_high"):
            result=self.run_transport("--level",level,"--tier","specialist","--previous-result",str(previous),"--authorize-escalation")
            self.assertNotEqual(result.returncode,0,level)
            self.assertEqual(len(self.rows()),1,level)
        no_authorization=self.run_transport("--level","medium","--previous-result",str(previous))
        self.assertNotEqual(no_authorization.returncode,0)
        boolean=self.run_transport("--level","medium","--chain-authorized")
        self.assertNotEqual(boolean.returncode,0)
        self.assertIn("cannot authorize",boolean.stderr)
        self.assertEqual(len(self.rows()),1)

    def test_wrong_receipt_container_types_return_terminal_envelope(self):
        previous = self.receipt(self.run_transport("--level", "low", case="adjacent"))
        original = previous.read_text()
        for key, value in (("selection", []), ("attempts", [None]), ("runtime", [])):
            payload = json.loads(original)
            payload[key] = value
            previous.write_text(json.dumps(payload))
            result = self.run_transport("--level", "medium", "--previous-result", str(previous), "--authorize-escalation")
            self.assertNotEqual(result.returncode, 0, key)
            self.assertEqual(len(result.stdout.splitlines()), 1, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "unavailable")
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(len(self.rows()), 1, key)

    def test_invalid_responses_and_runtime_guards_are_one_attempt_terminal(self):
        for case in ("skip","blank","malformed","duplicate-response","wrong-model","wrong-effort","wrong-sandbox","wrong-permission","wrong-provenance","duplicate-child","reroute","tool",
                     "blank-escalation-reason", "blank-escalation-unresolved_difficulty", "blank-escalation-required_resolution"):
            self.invocations.unlink(missing_ok=True)
            result=self.run_transport("--level","low",case=case)
            self.assertNotEqual(result.returncode,0,case)
            self.assertEqual(len(self.rows()),1,case)
            self.assertEqual(len(json.loads(result.stdout)["attempts"]),1,case)
            if case.startswith("blank-escalation-"):
                self.assertEqual(json.loads(result.stdout)["attempts"][0]["outcome"], "rejected_response")
                self.assertIn("escalation request must explain the unresolved difficulty", result.stderr)
        self.assertEqual(self.rows()[0]["effort"],"low")

    def test_local_response_semantics_remain_strict_with_flat_provider_schema(self):
        response = {"recommendation":"path", "why":"reason", "strongest_objection":"risk",
                    "change_my_mind":"evidence", "acceptance_checks":["check"], "risks":"none",
                    "follow_up_areas":"none"}
        path = self.root / "local-response.json"
        cases = [("low", None, None, None), ("low", "medium", None, None),
                 ("extra_high", None, None, None),
                 ("low", "high", None, "immediate next level"),
                 ("medium", "medium", None, "immediate next level"),
                 ("extra_high", "high", None, "extra_high is terminal")]
        cases += [("low", "medium", field, "must explain the unresolved difficulty")
                  for field in ("reason", "unresolved_difficulty", "required_resolution")]
        for level, next_level, blank, error in cases:
            with self.subTest(level=level, next_level=next_level, blank=blank):
                escalation = {"next_level":next_level, "reason":"ambiguity" if next_level else "",
                              "unresolved_difficulty":"ordering" if next_level else "",
                              "required_resolution":"compare" if next_level else ""}
                if blank:
                    escalation[blank] = " \t "
                path.write_text(json.dumps({**response, "escalation":escalation}))
                result = subprocess.run(
                    [str(self.config_wrapper), "--json", "_validate-response", "--level", level, "--file", str(path)],
                    env=self.env, text=True, capture_output=True, check=False, timeout=10,
                )
                self.assertEqual(result.returncode, 2 if error else 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["status"], "unavailable" if error else "ok")
                if error:
                    self.assertIn(error, payload["error"])
                else:
                    self.assertEqual(payload["response"]["escalation"], escalation)
        self.assertEqual(self.rows(), [])

    def test_rejected_launch_cannot_forge_accepted_receipt_for_next_spawn(self):
        accepted = json.loads(self.run_transport("--level", "low", case="adjacent").stdout)
        rejected = self.run_transport("--level", "low", case="ambiguous-adjacent")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("ambiguous child thread", rejected.stderr)
        forged = json.loads(rejected.stdout)
        child = "00000002-1111-7111-8111-000000000002"
        runtime = subprocess.run(
            ["sh", str(self.plugin_root / "scripts/inspect-agent-runtime.sh"),
             "--sessions-dir", str(self.home / "sessions"), "--expected-role", "advisor-astra",
             "--expected-model", "gpt-6-astra", "--expected-effort", "low",
             "--expected-parent", PARENT, child],
            env=self.env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(runtime.returncode, 0, runtime.stderr)
        rollout = next((self.home / "sessions").rglob("*" + child + ".jsonl"))
        rows = [json.loads(line) for line in rollout.read_text().splitlines()]
        response = json.loads(rows[-1]["payload"]["content"][0]["text"])
        forged.update(status="completed", outcome="accepted", runtime=json.loads(runtime.stdout),
                      advisor_response=response, escalation=response["escalation"],
                      packet_identity={"sha256": hashlib.sha256(self.fixture_packets[self.last_issue].encode()).hexdigest()},
                      runtime_source=accepted["runtime_source"])
        forged["attempts"][0]["outcome"] = "accepted"
        # A token from a genuinely accepted consultation cannot attest this rejected child.
        if "acceptance_proof" in accepted:
            forged["acceptance_proof"] = accepted["acceptance_proof"]
        previous = self.root / "forged-rejected.json"
        previous.write_text(json.dumps(forged))
        result = self.run_transport("--level", "medium", "--previous-result", str(previous), "--authorize-escalation")
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn("launcher acceptance proof", result.stderr)
        self.assertEqual(len(self.rows()), 2)
        # An authentic receipt still needs its private, unchanged launcher key.
        previous.write_text(json.dumps(accepted))
        key = self.home / ".tmp/advisor-acceptance/key"
        key.chmod(0o644)
        unsafe = self.run_transport("--level", "medium", "--previous-result", str(previous), "--authorize-escalation")
        self.assertNotEqual(unsafe.returncode, 0)
        self.assertEqual(len(self.rows()), 2)
        key.chmod(0o600)
        preserved = key.with_name("preserved")
        key.rename(preserved)
        try:
            for symlink in (False, True):
                if symlink:
                    key.symlink_to(preserved)
                missing_or_linked = self.run_transport("--level", "medium", "--previous-result", str(previous), "--authorize-escalation")
                self.assertNotEqual(missing_or_linked.returncode, 0)
                self.assertEqual(len(self.rows()), 2)
                if symlink:
                    self.assertTrue(key.is_symlink())
                else:
                    self.assertFalse(key.exists())
                key.unlink(missing_ok=True)
        finally:
            preserved.rename(key)

    def test_next_level_rejects_reused_previous_child(self):
        previous=self.receipt(self.run_transport("--level","low",case="adjacent"))
        child=json.loads(previous.read_text())["runtime"]["thread_id"]
        result=self.run_transport("--level","medium","--previous-result",str(previous),"--authorize-escalation",
                                  env={"FAKE_REUSED_CHILD":child})
        self.assertNotEqual(result.returncode,0)
        self.assertIn("reused previous child",result.stderr)
        self.assertEqual(len(self.rows()),2)

    def test_valid_explicit_override_precedes_invalid_installed_configuration(self):
        result=self.run_transport("--level","low",env={"ADVISOR_TRANSPORT_CONFIG":"relative/invalid.json"})
        self.assertEqual(result.returncode,0,result.stderr)
        source=json.loads(result.stdout)["runtime_source"]
        self.assertEqual(source["source"],"explicit")
        self.assertEqual(source["executable"],str(self.fake))
        self.assertEqual(len(self.rows()),1)

    def test_invalid_explicit_transport_never_falls_back_to_path(self):
        result=self.run_transport("--level","low",env={"ADVISOR_CODEX_BIN":str(self.root/"missing")})
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.rows(),[])

    def test_unavailable_parent_and_current_parent_mismatch_prevent_spawn(self):
        result=self.run_transport("--level","low",env={"CODEX_THREAD_ID":"00000000-0000-7000-8000-000000000000"})
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.rows(),[])
        rollout=next((self.home/"sessions").rglob("*"+PARENT+".jsonl"))
        rollout.write_text("invalid")
        result=self.run_transport("--level","low")
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.rows(),[])


if __name__ == "__main__":
    unittest.main()

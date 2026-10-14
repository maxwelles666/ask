"""Behavioral safety checks. All adapters below are local fakes; no model calls."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone

SPEC = importlib.util.spec_from_file_location("trial", Path(__file__).resolve().parents[1] / "scripts" / "trial.py")
trial = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trial)


def bundle():
    return {"schema_version": 1, "sources": [{
        "id": "S1", "title": "Test fixture", "url": "https://example.org/fixture",
        "published_at": "unknown", "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "text": "Sample size limits the conclusion. This fixture is not scientific evidence.",
    }], "questions": [{"id": "q1", "topic": "生物", "question": "证据有何边界？", "source_ids": ["S1"]}]}


def card():
    claim = {"text": "样本量限制结论范围。", "kind": "fact", "source_ids": ["S1"]}
    return {"question_id": "q1", "title": "样本量与证据边界", "answer": claim,
            "reasoning": [copy.deepcopy(claim) for _ in range(3)],
            "evidence": [{"source_id": "S1", "quote": "Sample size limits the conclusion.",
                          "supports": ["answer", "reasoning.0", "reasoning.1", "reasoning.2"]}],
            "limitations": ["不能据此推及其他总体。"], "indicators": ["样本量与置信区间。"],
            "uncertainty": "原始样本尚不明确。"}


HELPER = r'''
import json, sys, time
from pathlib import Path
from datetime import datetime,timezone,timedelta
mode, base = sys.argv[1], Path(sys.argv[2])
request = json.load(sys.stdin)
now = datetime.now(timezone.utc)
if mode == 'verify':
    output = dict(schema_version=1,status='ok',app_id=request['app_id'],billing_channel='chatgpt_subscription',
      provider_enforced=True,extra_credits_enabled=False,can_generate=True,limit_fraction=0.1,
      checked_at=now.isoformat(),valid_until=(now+timedelta(minutes=2)).isoformat(),
      evidence=dict(method='provider_api',request_id='fixture-not-real'))
    if (base/'invalid_verifier').exists(): output['provider_enforced']=False
elif mode == 'usage':
    counter=base/'usage_count'
    count=int(counter.read_text())+1 if counter.exists() else 1
    counter.write_text(str(count))
    output=dict(schema_version=1,status='ok',billing_channel='chatgpt_subscription',source='provider_usage',
      checked_at=now.isoformat(),windows=[dict(id='weekly',used_percent=10 if count==1 or (base/'usage_flat').exists() else 14,
      resets_at=2000000000)])
else:
    with (base/'model_calls').open('a') as f: f.write('call\n')
    if (base/'sleep').exists(): time.sleep(30)
    output=dict(status='ok',app_id=request['app_id'],billing_channel='chatgpt_subscription',
      card=json.loads((base/'card.json').read_text(encoding='utf-8')))
    output['card']['question_id']=request['question']['id']
    if (base/'quota').exists(): output['status']='quota_exhausted'
    if (base/'bad_quote').exists(): output['card']['evidence'][0]['quote']='An invented quote'
print(json.dumps(output))
if (base/'adapter_nonzero').exists(): sys.exit(2)
'''


class TrialBehaviorTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / ".local"
        scratch.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=scratch)
        self.base = Path(self.directory.name)
        (self.base / "tasks.json").write_text(json.dumps(bundle()), encoding="utf-8")
        (self.base / "card.json").write_text(json.dumps(card()), encoding="utf-8")
        (self.base / "helper.py").write_text(HELPER, encoding="utf-8")
        for name in ("verify", "model", "usage"):
            (self.base / (name + ".json")).write_text(json.dumps([
                sys.executable, str(self.base / "helper.py"), name, str(self.base)
            ]), encoding="utf-8")

    def tearDown(self):
        self.directory.cleanup()

    def args(self, live=True):
        arguments = ["--tasks", str(self.base / "tasks.json"), "--output", str(self.base / "output"),
                     "--duration-seconds", "20", "--interval-seconds", "0", "--max-cards", "8"]
        if live:
            arguments += ["--mode", "live", "--app-id", "test-app", "--max-limit-fraction", "0.2",
                          "--model-command", str(self.base / "model.json"),
                          "--limit-check-command", str(self.base / "verify.json")]
        return trial.parser().parse_args(arguments)

    def calls(self):
        path = self.base / "model_calls"
        return len(path.read_text().splitlines()) if path.exists() else 0

    def test_default_dry_run_never_invokes_provided_commands(self):
        args = self.args()
        args.mode = "dry-run"
        result = trial.run(args)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(self.calls(), 0)
        self.assertFalse((self.base / "output/cards").exists())
        self.assertTrue((self.base / "output/prompt-preview.json").exists())

    def test_no_proof_stops_before_any_model_call(self):
        (self.base / "invalid_verifier").touch()
        state = trial.run(self.args())
        self.assertEqual(state["stop_reason"], "limit_not_provider_enforced")
        self.assertEqual(self.calls(), 0)

    def test_missing_command_cannot_fall_back_to_model_login(self):
        args = self.args()
        args.limit_check_command = None
        with self.assertRaisesRegex(trial.TrialError, "missing_trusted_command"):
            trial.run(args)
        self.assertEqual(self.calls(), 0)

    def test_public_seed_requiring_fetch_cannot_start_live_generation(self):
        data = bundle()
        data["requires_refetch_before_live"] = True
        (self.base / "tasks.json").write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(trial.TrialError, "sources_require_refetch"):
            trial.run(self.args())
        self.assertEqual(self.calls(), 0)

    def test_valid_card_persists_and_relaunch_does_not_duplicate(self):
        state = trial.run(self.args())
        self.assertEqual(state["completed"], ["q1"])
        self.assertTrue((self.base / "output/cards/q1.md").exists())
        with self.assertRaisesRegex(trial.TrialError, "run_already_finished"):
            trial.run(self.args())
        self.assertEqual(self.calls(), 1)

    def test_unseen_evidence_is_rejected_and_retries_are_bounded(self):
        (self.base / "bad_quote").touch()
        state = trial.run(self.args())
        self.assertEqual(state["completed"], [])
        self.assertEqual(self.calls(), 2)
        self.assertEqual(state["failures"][-1]["code"], "evidence_quote_not_in_source")
        self.assertFalse((self.base / "output/cards/q1.json").exists())

    def test_provider_quota_denial_is_not_retried(self):
        (self.base / "quota").touch()
        state = trial.run(self.args())
        self.assertEqual(state["stop_reason"], "quota_exhausted")
        self.assertEqual(self.calls(), 1)

    def test_adapter_nonzero_quota_response_is_preserved_without_retry(self):
        # Match codex_adapter.main: error envelopes are accompanied by exit 2.
        args = self.args()
        (self.base / "quota").touch()
        original = self.base / "helper.py"
        original.write_text(HELPER.replace("if (base/'adapter_nonzero').exists(): sys.exit(2)",
                                           "if mode == 'model': sys.exit(2)"), encoding="utf-8")
        state = trial.run(args)
        self.assertEqual(state["stop_reason"], "quota_exhausted")
        self.assertEqual(self.calls(), 1)

    def test_usage_adapter_nonzero_stops_before_model(self):
        args = self.args()
        args.observed_trial_risk_accepted = True
        args.usage_check_command = str(self.base / "usage.json")
        (self.base / "adapter_nonzero").touch()
        state = trial.run(args)
        self.assertEqual(state["stop_reason"], "command_failed")
        self.assertEqual(self.calls(), 0)

    def test_deadline_kills_slow_adapter_without_retry(self):
        (self.base / "sleep").touch()
        args = self.args()
        args.duration_seconds = 0.8
        start = time.monotonic()
        state = trial.run(args)
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(state["stop_reason"], "command_timeout")
        self.assertEqual(self.calls(), 1)

    def test_observed_usage_increase_stops_further_calls(self):
        data = bundle()
        data["questions"].append({"id": "q2", "topic": "生物", "question": "还缺什么？", "source_ids": ["S1"]})
        (self.base / "tasks.json").write_text(json.dumps(data), encoding="utf-8")
        args = self.args()
        args.observed_trial_risk_accepted = True
        args.usage_check_command = str(self.base / "usage.json")
        state = trial.run(args)
        self.assertEqual(state["stop_reason"], "observed_usage_budget_reached")
        self.assertEqual(self.calls(), 1)
        self.assertEqual(len(state["usage_observations"]), 2)
        self.assertEqual(state["completed"], ["q1"])
        self.assertTrue((self.base / "output/cards/q1.md").exists())

    def test_observed_eight_call_cap_includes_invalid_card_retries(self):
        data = bundle()
        for index in range(2, 5):
            data["questions"].append({"id": f"q{index}", "topic": "生物", "question": "还缺什么？", "source_ids": ["S1"]})
        (self.base / "tasks.json").write_text(json.dumps(data), encoding="utf-8")
        (self.base / "bad_quote").touch()
        (self.base / "usage_flat").touch()
        args = self.args()
        args.max_attempts = 3
        args.observed_trial_risk_accepted = True
        args.usage_check_command = str(self.base / "usage.json")
        state = trial.run(args)
        self.assertEqual(state["stop_reason"], "observed_trial_call_limit")
        self.assertEqual(self.calls(), 8)

    def test_unknown_source_ids_and_unsupported_claims_are_rejected(self):
        data = bundle()
        value = card()
        value["answer"]["source_ids"] = ["unseen"]
        with self.assertRaisesRegex(trial.TrialError, "unbound_claim_source"):
            trial.validate_card(value, data["questions"][0], {"S1": data["sources"][0]})
        value = card()
        value["evidence"][0]["supports"].remove("reasoning.2")
        with self.assertRaisesRegex(trial.TrialError, "unsupported_claim"):
            trial.validate_card(value, data["questions"][0], {"S1": data["sources"][0]})

    def test_usage_reset_and_expired_verifier_are_not_accepted(self):
        before = {"windows": [{"id": "weekly", "used_percent": 20, "resets_at": 2000000000}]}
        after = {"windows": [{"id": "weekly", "used_percent": 1, "resets_at": 2000000001}]}
        with self.assertRaisesRegex(trial.TrialError, "usage_window_reset_or_decreased"):
            trial.check_usage_delta(before, after, 3)
        receipt = trial.command_json(trial.read_command(str(self.base / "verify.json")), {"app_id": "test-app"}, 5)
        receipt["valid_until"] = "2000-01-01T00:00:00+00:00"
        with self.assertRaisesRegex(trial.TrialError, "stale_limit_receipt"):
            trial.validate_receipt(receipt, "test-app", 0.2, time.time())


if __name__ == "__main__":
    unittest.main()

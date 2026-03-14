from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sts2_agent.bridge import MockGameBridge
from sts2_agent.models import ActionResult, ActionStatus, ActionSubmission, CardView, DecisionSnapshot, EnemyState, LegalAction, PlayerState, PolicyDecision
from sts2_agent.orchestrator import AutoplayOrchestrator, OrchestratorConfig
from sts2_agent.policy import FirstLegalActionPolicy, PolicyError


class InvalidActionPolicy:
    def decide(self, snapshot, legal_actions):
        return PolicyDecision(action_id="act-invalid", reason="invalid action")


class FailingPolicyError(PolicyError):
    error_code = "llm_parse_error"


class FailingPolicy:
    def decide(self, snapshot, legal_actions):
        raise FailingPolicyError("invalid llm response")


class CapturingBridge:
    def __init__(self) -> None:
        self.submissions: list[ActionSubmission] = []

    def attach_or_start(self, scenario: str = "live") -> object:
        from sts2_agent.bridge import BridgeSession

        return BridgeSession(session_id="sess-test1234", scenario=scenario)

    def get_snapshot(self, session_id: str) -> DecisionSnapshot:
        return DecisionSnapshot(
            session_id=session_id,
            decision_id="dec-test1234",
            state_version=3,
            phase="combat",
            player=PlayerState(
                hp=80,
                max_hp=80,
                block=0,
                energy=3,
                gold=99,
                hand=[CardView(card_id="card-1", name="打击", cost=1, playable=True)],
            ),
            enemies=[EnemyState(enemy_id="1", name="小啃兽", hp=20, max_hp=20, block=0, intent="unknown")],
            terminal=False,
        )

    def get_legal_actions(self, session_id: str) -> list[LegalAction]:
        return [
            LegalAction(
                action_id="act-targeted",
                type="play_card",
                label="Play 打击",
                params={"card_id": "card-1", "target_type": "AnyEnemy"},
                target_constraints=["1"],
                metadata={},
            )
        ]

    def submit_action(self, submission: ActionSubmission) -> ActionResult:
        self.submissions.append(submission)
        return ActionResult(
            status=ActionStatus.ACCEPTED,
            session_id=submission.session_id,
            decision_id=submission.decision_id,
            state_version=submission.state_version + 1,
            accepted_action_id=submission.action_id,
            message="ok",
            terminal=True,
            metadata={"phase": "terminal"},
        )

    def stop(self, session_id: str):
        raise NotImplementedError

    def reset(self, session_id: str):
        raise NotImplementedError


class OrchestratorTests(unittest.TestCase):
    def test_autoplay_reaches_terminal_and_persists_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=MockGameBridge(),
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run()

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertEqual(summary.decisions, 3)
            self.assertTrue(summary.trace_path)
            trace_path = Path(summary.trace_path)
            self.assertTrue(trace_path.exists())
            records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 3)
            self.assertEqual(records[0]["phase"], "combat")
            self.assertEqual(records[-1]["bridge_result"]["metadata"]["phase"], "terminal")

    def test_invalid_policy_action_interrupts_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=MockGameBridge(),
                policy=InvalidActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run()

            self.assertFalse(summary.completed)
            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.reason, "invalid_payload")
            trace_lines = Path(summary.trace_path).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(trace_lines), 1)
            record = json.loads(trace_lines[0])
            self.assertTrue(record["interrupted"])
            self.assertEqual(record["bridge_result"]["error_code"], "invalid_payload")

    def test_manual_stop_interrupts_before_action_submission(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=MockGameBridge(),
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            orchestrator.request_stop()
            summary = orchestrator.run()

            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.reason, "manual_stop")

    def test_dry_run_records_planned_action_without_submission(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=MockGameBridge(),
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, dry_run=True),
            )
            summary = orchestrator.run()

            self.assertFalse(summary.completed)
            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.reason, "dry_run")
            record = json.loads(Path(summary.trace_path).read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["bridge_result"]["status"], "dry_run")
            self.assertEqual(record["bridge_result"]["planned_action_id"], record["policy_output"]["action_id"])

    def test_policy_error_interrupts_and_persists_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=MockGameBridge(),
                policy=FailingPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run()

            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.reason, "llm_parse_error")
            record = json.loads(Path(summary.trace_path).read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["bridge_result"]["error_code"], "llm_parse_error")

    def test_orchestrator_infers_single_target_id_from_legal_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = CapturingBridge()
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertEqual(len(bridge.submissions), 1)
            self.assertEqual(bridge.submissions[0].args["target_id"], "1")
            self.assertEqual(bridge.submissions[0].args["card_id"], "card-1")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sts2_agent.bridge import BridgeSession, InvalidPayloadError, MockGameBridge, StaleActionError
from sts2_agent.models import (
    ActionResult,
    ActionStatus,
    ActionSubmission,
    BattleContext,
    CardView,
    DecisionSnapshot,
    EnemyState,
    LegalAction,
    PlayerState,
    PolicyDecision,
)
from sts2_agent.orchestrator import AutoplayOrchestrator, OrchestratorConfig
from sts2_agent.policy import FirstLegalActionPolicy, PolicyError


class InvalidActionPolicy:
    def decide(self, snapshot, legal_actions):
        return PolicyDecision(action_id="act-invalid", reason="invalid action")


class CapturingBattleContextPolicy:
    def __init__(self, action_id: str = "act-0-0-play_card") -> None:
        self.action_id = action_id
        self.battle_contexts: list[BattleContext | None] = []

    def decide(self, snapshot, legal_actions, battle_context: BattleContext | None = None):
        self.battle_contexts.append(battle_context)
        action_id = next((action.action_id for action in legal_actions if action.type != "end_turn"), legal_actions[0].action_id)
        return PolicyDecision(action_id=action_id, reason="capture battle context", confidence="medium")


class LegacyPolicy:
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, snapshot, legal_actions):
        self.calls += 1
        return PolicyDecision(action_id=legal_actions[0].action_id, reason="legacy policy")


class RetryInvalidThenValidPolicy:
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, snapshot, legal_actions, battle_context: BattleContext | None = None):
        self.calls += 1
        if self.calls == 1:
            return PolicyDecision(action_id="act-invalid-stale", reason="first try invalid action", confidence="low")
        return PolicyDecision(action_id=legal_actions[0].action_id, reason="retry with legal action", confidence="high")


class RetryPolicyErrorThenValid:
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, snapshot, legal_actions, battle_context: BattleContext | None = None):
        self.calls += 1
        if self.calls == 1:
            raise FailingPolicyError("invalid llm response")
        return PolicyDecision(action_id=legal_actions[0].action_id, reason="retry after policy error", confidence="high")


class MultiTargetPolicy:
    def __init__(self, target_id: str | None) -> None:
        self.target_id = target_id

    def decide(self, snapshot, legal_actions):
        metadata = {}
        if self.target_id is not None:
            metadata["action_args"] = {"target_id": self.target_id}
        return PolicyDecision(action_id="act-multi", reason="choose target", metadata=metadata)


class FailingPolicyError(PolicyError):
    error_code = "llm_parse_error"


class FailingPolicy:
    def decide(self, snapshot, legal_actions):
        raise FailingPolicyError("invalid llm response")


class CapturingBridge:
    def __init__(self) -> None:
        self.submissions: list[ActionSubmission] = []

    def attach_or_start(self, scenario: str = "live") -> BridgeSession:
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
                hand=[CardView(card_id="card-1", name="Strike", cost=1, playable=True)],
            ),
            enemies=[EnemyState(enemy_id="1", name="Louse", hp=20, max_hp=20, block=0, intent="unknown")],
            terminal=False,
            metadata={"current_side": "Player", "round_number": 1},
        )

    def get_legal_actions(self, session_id: str) -> list[LegalAction]:
        return [
            LegalAction(
                action_id="act-targeted",
                type="play_card",
                label="Play Strike",
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


class SequencedCombatBridge:
    def __init__(self, windows: list[dict[str, object]], advance_on_snapshot_reads: dict[int, int] | None = None) -> None:
        self.windows = windows
        self.advance_on_snapshot_reads = advance_on_snapshot_reads or {}
        self.index = 0
        self.submissions: list[str] = []
        self.snapshot_reads: dict[int, int] = {}

    def attach_or_start(self, scenario: str = "live") -> BridgeSession:
        self.index = 0
        self.snapshot_reads = {}
        self.submissions = []
        return BridgeSession(session_id="sess-seq1234", scenario=scenario)

    def get_snapshot(self, session_id: str) -> DecisionSnapshot:
        self.snapshot_reads[self.index] = self.snapshot_reads.get(self.index, 0) + 1
        threshold = self.advance_on_snapshot_reads.get(self.index)
        if threshold is not None and self.snapshot_reads[self.index] >= threshold and self.index < len(self.windows) - 1:
            self.index += 1
            self.snapshot_reads[self.index] = self.snapshot_reads.get(self.index, 0)
        window = self.windows[self.index]
        metadata = dict(window.get("metadata", {}))
        raw_enemies = window.get("enemies")
        return DecisionSnapshot(
            session_id=session_id,
            decision_id=f"dec-{self.index}",
            state_version=self.index,
            phase=str(window["phase"]),
            player=PlayerState(
                hp=80,
                max_hp=80,
                block=0,
                energy=int(window.get("energy", 3)),
                gold=99,
                hand=[
                    CardView(card_id=card_id, name=card_id, cost=1, playable=True)
                    for card_id in window.get("hand", ["card-1"])
                ],
            ),
            rewards=list(window.get("rewards", [])),
            map_nodes=list(window.get("map_nodes", [])),
            enemies=[EnemyState(**enemy) for enemy in raw_enemies] if raw_enemies is not None else [EnemyState(enemy_id="1", name="Louse", hp=20, max_hp=20, block=0, intent="unknown")],
            terminal=bool(window.get("terminal", False)),
            metadata=metadata,
        )

    def get_legal_actions(self, session_id: str) -> list[LegalAction]:
        window = self.windows[self.index]
        actions = []
        for idx, item in enumerate(window.get("actions", [])):
            item = dict(item)
            actions.append(
                LegalAction(
                    action_id=f"act-{self.index}-{idx}-{item['type']}",
                    type=str(item["type"]),
                    label=str(item.get("label", item["type"])),
                    params=dict(item.get("params", {})),
                    target_constraints=list(item.get("target_constraints", [])),
                    metadata={},
                )
            )
        return actions

    def submit_action(self, submission: ActionSubmission) -> ActionResult:
        legal_actions = {action.action_id: action for action in self.get_legal_actions(submission.session_id)}
        if submission.action_id not in legal_actions:
            raise InvalidPayloadError("action is not legal for the active decision window")
        accepted = legal_actions[submission.action_id]
        self.submissions.append(accepted.type)
        if self.index < len(self.windows) - 1:
            self.index += 1
        next_snapshot = self.get_snapshot(submission.session_id)
        return ActionResult(
            status=ActionStatus.ACCEPTED,
            session_id=submission.session_id,
            decision_id=next_snapshot.decision_id,
            state_version=next_snapshot.state_version,
            accepted_action_id=accepted.action_id,
            message="ok",
            terminal=next_snapshot.terminal,
            metadata={"phase": next_snapshot.phase},
        )

    def stop(self, session_id: str):
        raise NotImplementedError

    def reset(self, session_id: str):
        raise NotImplementedError


class MultiTargetBridge(CapturingBridge):
    def get_legal_actions(self, session_id: str) -> list[LegalAction]:
        return [
            LegalAction(
                action_id="act-multi",
                type="play_card",
                label="Play Strike",
                params={"card_id": "card-1", "target_type": "AnyEnemy"},
                target_constraints=["1", "2"],
                metadata={},
            )
        ]


class SnapshotDriftBridge(SequencedCombatBridge):
    def __init__(self) -> None:
        super().__init__(
            [
                make_window(actions=[{"type": "play_card", "label": "Strike", "params": {"card_id": "card-1"}}]),
                make_window(actions=[{"type": "end_turn", "label": "End Turn"}], energy=0, hand=[]),
                make_window(phase="reward", actions=[]),
            ]
        )
        self._snapshot_reads = 0

    def get_snapshot(self, session_id: str) -> DecisionSnapshot:
        snapshot = super().get_snapshot(session_id)
        self._snapshot_reads += 1
        if self._snapshot_reads == 2:
            self.index = 1
            return super().get_snapshot(session_id)
        return snapshot


class RetryableStaleBridge(SequencedCombatBridge):
    def __init__(self) -> None:
        super().__init__(
            [
                make_window(actions=[{"type": "play_card", "label": "Strike", "params": {"card_id": "card-1"}}]),
                make_window(actions=[{"type": "end_turn", "label": "End Turn"}], energy=0, hand=[]),
                make_window(phase="reward", actions=[]),
            ]
        )
        self._stale_raised = False

    def submit_action(self, submission: ActionSubmission) -> ActionResult:
        if not self._stale_raised:
            self._stale_raised = True
            self.index = 1
            raise StaleActionError("Requested decision_id is no longer current.")
        return super().submit_action(submission)


class RetryableAutoEndTurnStaleBridge(SequencedCombatBridge):
    def __init__(self) -> None:
        super().__init__(
            [
                make_window(actions=[{"type": "end_turn", "label": "End Turn"}], energy=0, hand=[]),
                make_window(phase="reward", actions=[], metadata={}),
            ]
        )
        self._stale_raised = False

    def submit_action(self, submission: ActionSubmission) -> ActionResult:
        if not self._stale_raised:
            self._stale_raised = True
            raise StaleActionError("Requested decision_id is no longer current.")
        return super().submit_action(submission)


class DelayedEndTurnResolutionBridge(SequencedCombatBridge):
    def __init__(self) -> None:
        super().__init__(
            [
                make_window(actions=[{"type": "end_turn", "label": "End Turn"}], energy=0, hand=[], metadata={"current_side": "Player", "round_number": 1}),
                make_window(actions=[], hand=[], metadata={"current_side": "Enemy", "round_number": 1}),
                make_window(phase="reward", actions=[], metadata={}),
            ]
        )
        self._end_turn_pending = False
        self._pending_reads = 0
        self._enemy_reads = 0

    def get_snapshot(self, session_id: str) -> DecisionSnapshot:
        if self._end_turn_pending:
            self._pending_reads += 1
            if self._pending_reads >= 3 and self.index == 0:
                self.index += 1
                self._end_turn_pending = False
                self._pending_reads = 0
        elif self.index == 1:
            self._enemy_reads += 1
            if self._enemy_reads >= 2:
                self.index = 2
        return super().get_snapshot(session_id)

    def submit_action(self, submission: ActionSubmission) -> ActionResult:
        legal_actions = {action.action_id: action for action in self.get_legal_actions(submission.session_id)}
        accepted = legal_actions[submission.action_id]
        self.submissions.append(accepted.type)
        self._end_turn_pending = True
        return ActionResult(
            status=ActionStatus.ACCEPTED,
            session_id=submission.session_id,
            decision_id="dec-0",
            state_version=0,
            accepted_action_id=accepted.action_id,
            message="Ended the current turn.",
            terminal=False,
            metadata={"phase": "combat"},
        )


def make_window(
    *,
    phase: str = "combat",
    actions: list[dict[str, object]] | None = None,
    terminal: bool = False,
    energy: int = 3,
    hand: list[str] | None = None,
    metadata: dict[str, object] | None = None,
    enemies: list[dict[str, object]] | None = None,
    rewards: list[str] | None = None,
    map_nodes: list[str] | None = None,
) -> dict[str, object]:
    return {
        "phase": phase,
        "actions": actions or [],
        "terminal": terminal,
        "energy": energy,
        "hand": hand or ["card-1"],
        "metadata": metadata or {"current_side": "Player", "round_number": 1},
        "enemies": enemies,
        "rewards": rewards or [],
        "map_nodes": map_nodes or [],
    }


class OrchestratorTests(unittest.TestCase):
    def test_battle_mode_completes_on_reward_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=MockGameBridge(),
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, stop_after_player_turn=False),
            )
            summary = orchestrator.run()

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertTrue(summary.battle_completed)
            self.assertEqual(summary.decisions, 1)
            self.assertEqual(summary.total_actions, 1)
            self.assertEqual(summary.turns_completed, 1)
            self.assertEqual(summary.current_turn_index, 1)
            self.assertEqual(summary.ended_by, "reward_phase_reached")
            records = Path(summary.trace_path).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(records), 2)

    def test_reward_mode_halt_stops_without_writes(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    phase="reward",
                    actions=[{"type": "skip_reward", "label": "Skip Reward"}],
                    metadata={},
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, stop_after_player_turn=False, reward_mode="halt"),
            )
            summary = orchestrator.run(scenario="live")

            self.assertFalse(summary.completed)
            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.ended_by, "reward_phase_reached")
            self.assertEqual(bridge.submissions, [])
            records = Path(summary.trace_path).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(records), 1)

    def test_reward_mode_skip_submits_skip_reward(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    phase="reward",
                    actions=[{"type": "skip_reward", "label": "Skip Reward"}],
                    metadata={},
                    rewards=["Add a card"],
                ),
                make_window(
                    phase="map",
                    actions=[{"type": "choose_map_node", "label": "Choose node", "params": {"node": "Monster@3,1"}}],
                    metadata={},
                    map_nodes=["Monster@3,1"],
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, stop_after_player_turn=False, reward_mode="skip", max_steps=4),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertEqual(summary.ended_by, "map_phase_reached")
            self.assertEqual(bridge.submissions, ["skip_reward"])
            self.assertEqual(summary.reward_actions_taken, 1)

    def test_reward_mode_llm_can_choose_reward(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    phase="reward",
                    actions=[
                        {"type": "choose_reward", "label": "Take Reward", "params": {"reward": "Gold", "reward_index": 0}},
                        {"type": "skip_reward", "label": "Skip Reward"},
                    ],
                    metadata={},
                    rewards=["Gold"],
                ),
                make_window(phase="map", actions=[], metadata={}),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, stop_after_player_turn=False, reward_mode="llm", max_steps=4),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertEqual(summary.ended_by, "map_phase_reached")
            self.assertEqual(bridge.submissions, ["choose_reward"])
            self.assertEqual(summary.reward_actions_taken, 1)

    def test_battle_mode_can_continue_reward_to_map_to_next_combat(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    phase="reward",
                    actions=[{"type": "skip_reward", "label": "Skip Reward"}],
                    metadata={"window_kind": "reward_choice", "reward_subphase": "reward_choice"},
                    rewards=["Add a card"],
                ),
                make_window(
                    phase="map",
                    actions=[
                        {"type": "choose_map_node", "label": "Choose Monster@1,2", "params": {"node": "Monster@1,2"}},
                        {"type": "choose_map_node", "label": "Choose Elite@2,2", "params": {"node": "Elite@2,2"}},
                    ],
                    metadata={"window_kind": "map_ready"},
                    map_nodes=["Monster@1,2", "Elite@2,2"],
                ),
                make_window(
                    phase="combat",
                    actions=[{"type": "end_turn", "label": "End Turn"}],
                    hand=[],
                    metadata={"current_side": "Player", "round_number": 1},
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(
                    trace_dir=tmpdir,
                    stop_after_player_turn=False,
                    reward_mode="safe-default",
                    map_mode="safe-default",
                    stop_after_next_combat=True,
                    max_steps=8,
                ),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertEqual(summary.ended_by, "next_combat_entered")
            self.assertEqual(bridge.submissions, ["skip_reward", "choose_map_node"])
            self.assertTrue(summary.next_combat_entered)
            self.assertEqual(summary.reward_actions_taken, 1)
            self.assertEqual(summary.map_actions_taken, 1)
            records = [json.loads(line) for line in Path(summary.trace_path).read_text(encoding="utf-8").splitlines()]
            self.assertIn("reward_choice", {record["step_kind"] for record in records})
            self.assertIn("map", {record["step_kind"] for record in records})
            self.assertEqual(records[-1]["step_kind"], "combat_resume")

    def test_battle_mode_can_advance_reward_screen_to_map(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    phase="reward",
                    actions=[{"type": "advance_reward", "label": "前进", "params": {"button_label": "前进"}}],
                    metadata={"window_kind": "reward_advance", "reward_subphase": "reward_advance", "reward_count": 0},
                    rewards=[],
                ),
                make_window(
                    phase="map",
                    actions=[{"type": "choose_map_node", "label": "Choose Monster@1,2", "params": {"node": "Monster@1,2"}}],
                    metadata={"window_kind": "map_ready"},
                    map_nodes=["Monster@1,2"],
                ),
                make_window(
                    phase="combat",
                    actions=[{"type": "end_turn", "label": "End Turn"}],
                    hand=[],
                    metadata={"current_side": "Player", "round_number": 2},
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(
                    trace_dir=tmpdir,
                    stop_after_player_turn=False,
                    reward_mode="safe-default",
                    map_mode="safe-default",
                    stop_after_next_combat=True,
                    max_steps=8,
                ),
            )

            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertEqual(summary.ended_by, "next_combat_entered")
            self.assertEqual(bridge.submissions, ["advance_reward", "choose_map_node"])
            records = [json.loads(line) for line in Path(summary.trace_path).read_text(encoding="utf-8").splitlines()]
            self.assertIn("reward_advance", {record["step_kind"] for record in records})

    def test_reward_advance_without_actions_times_out_with_specific_reason(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    phase="reward",
                    actions=[],
                    metadata={"window_kind": "reward_advance", "reward_subphase": "reward_advance", "reward_count": 0},
                    rewards=[],
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch("sts2_agent.orchestrator.time.sleep", return_value=None), patch(
            "sts2_agent.orchestrator.time.monotonic",
            side_effect=([0.0] * 8) + ([0.2] * 8),
        ):
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(
                    trace_dir=tmpdir,
                    stop_after_player_turn=False,
                    reward_mode="safe-default",
                    transition_timeout_seconds=0.1,
                    poll_interval_seconds=0.0,
                    max_steps=4,
                ),
            )

            summary = orchestrator.run(scenario="live")

            self.assertFalse(summary.completed)
            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.ended_by, "reward_advance_no_actions")

    def test_battle_mode_waits_for_transition_after_map_choice(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    phase="map",
                    actions=[{"type": "choose_map_node", "label": "Choose Monster@1,2", "params": {"node": "Monster@1,2"}}],
                    metadata={"window_kind": "map_ready"},
                    map_nodes=["Monster@1,2"],
                ),
                make_window(
                    phase="map",
                    actions=[],
                    metadata={"window_kind": "map_transition"},
                    map_nodes=[],
                ),
                make_window(
                    phase="combat",
                    actions=[{"type": "end_turn", "label": "End Turn"}],
                    hand=[],
                    metadata={"current_side": "Player", "round_number": 2},
                ),
            ],
            advance_on_snapshot_reads={1: 4},
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch("sts2_agent.orchestrator.time.sleep", return_value=None):
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(
                    trace_dir=tmpdir,
                    stop_after_player_turn=False,
                    map_mode="safe-default",
                    stop_after_next_combat=True,
                    max_steps=8,
                ),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertEqual(summary.ended_by, "next_combat_entered")
            records = [json.loads(line) for line in Path(summary.trace_path).read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(record["step_kind"] == "transition_wait" for record in records))

    def test_battle_mode_stops_when_transition_wait_times_out(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    phase="map",
                    actions=[],
                    metadata={"window_kind": "map_transition"},
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch("sts2_agent.orchestrator.time.sleep", return_value=None), patch(
            "sts2_agent.orchestrator.time.monotonic",
            side_effect=[0.0, 0.0, 0.2, 0.2],
        ):
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(
                    trace_dir=tmpdir,
                    stop_after_player_turn=False,
                    map_mode="safe-default",
                    transition_timeout_seconds=0.1,
                    poll_interval_seconds=0.0,
                    max_steps=4,
                ),
            )
            summary = orchestrator.run(scenario="live")

            self.assertFalse(summary.completed)
            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.ended_by, "transition_timeout")
            records = [json.loads(line) for line in Path(summary.trace_path).read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[-1]["step_kind"], "transition_wait")

    def test_battle_mode_stops_on_unknown_window_after_fuse(self) -> None:
        bridge = SequencedCombatBridge([make_window(phase="shop", actions=[], metadata={"window_kind": "shop"})])
        with tempfile.TemporaryDirectory() as tmpdir, patch("sts2_agent.orchestrator.time.sleep", return_value=None):
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(
                    trace_dir=tmpdir,
                    stop_after_player_turn=False,
                    unknown_window_fuse=1,
                    max_steps=2,
                ),
            )
            summary = orchestrator.run(scenario="live")

            self.assertFalse(summary.completed)
            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.ended_by, "unsupported_phase")

    def test_battle_mode_completes_when_no_enemies_remain_in_combat_snapshot(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    actions=[{"type": "end_turn", "label": "End Turn"}],
                    hand=[],
                    metadata={"current_side": "Player", "round_number": 4},
                    enemies=[],
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, stop_after_player_turn=False),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertTrue(summary.battle_completed)
            self.assertEqual(summary.ended_by, "battle_completed")

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
            self.assertTrue(record["is_final_step"])
            self.assertEqual(record["stop_reason"], "dry_run")

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

    def test_orchestrator_uses_policy_target_id_for_multi_target_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = MultiTargetBridge()
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=MultiTargetPolicy("2"),
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertEqual(len(bridge.submissions), 1)
            self.assertEqual(bridge.submissions[0].args["target_id"], "2")
            self.assertEqual(bridge.submissions[0].args["card_id"], "card-1")

    def test_orchestrator_rejects_multi_target_action_without_target_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = MultiTargetBridge()
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=MultiTargetPolicy(None),
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.reason, "policy_invalid_action_args")
            self.assertEqual(bridge.submissions, [])
            record = json.loads(Path(summary.trace_path).read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["bridge_result"]["error_code"], "policy_invalid_action_args")

    def test_orchestrator_rejects_target_id_outside_legal_target_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = MultiTargetBridge()
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=MultiTargetPolicy("99"),
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.reason, "policy_invalid_action_args")
            self.assertEqual(bridge.submissions, [])
            record = json.loads(Path(summary.trace_path).read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["bridge_result"]["error_code"], "policy_invalid_action_args")

    def test_orchestrator_continues_multiple_actions_in_same_turn(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    actions=[
                        {"type": "play_card", "label": "Strike", "params": {"card_id": "card-1"}},
                        {"type": "end_turn", "label": "End Turn"},
                    ],
                    hand=["card-1", "card-2"],
                ),
                make_window(
                    actions=[
                        {"type": "play_card", "label": "Defend", "params": {"card_id": "card-2"}},
                        {"type": "end_turn", "label": "End Turn"},
                    ],
                    energy=2,
                    hand=["card-2"],
                ),
                make_window(actions=[{"type": "end_turn", "label": "End Turn"}], energy=0, hand=[]),
                make_window(phase="reward", actions=[]),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertTrue(summary.turn_completed)
            self.assertEqual(summary.decisions, 3)
            self.assertEqual(summary.actions_this_turn, 3)
            self.assertEqual(summary.ended_by, "auto_end_turn")
            self.assertEqual(bridge.submissions, ["play_card", "play_card", "end_turn"])
            records = [json.loads(line) for line in Path(summary.trace_path).read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 3)
            self.assertEqual(records[-1]["stop_reason"], "auto_end_turn")
            self.assertTrue(records[-1]["is_final_step"])
            self.assertEqual(records[-1]["actions_this_turn"], 3)
            self.assertEqual(records[-1]["current_turn_index"], 1)

    def test_orchestrator_can_stop_cleanly_when_only_end_turn_remains(self) -> None:
        bridge = SequencedCombatBridge([make_window(actions=[{"type": "end_turn", "label": "End Turn"}], hand=[])])
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, auto_end_turn_when_only_end_turn=False),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertTrue(summary.turn_completed)
            self.assertEqual(summary.actions_this_turn, 0)
            self.assertEqual(summary.ended_by, "end_turn_only")
            self.assertEqual(bridge.submissions, [])

    def test_orchestrator_stops_when_phase_changes_after_combat_action(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(actions=[{"type": "play_card", "label": "Strike", "params": {"card_id": "card-1"}}]),
                make_window(phase="reward", actions=[{"type": "choose_reward", "label": "Take Reward"}], metadata={}),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertTrue(summary.turn_completed)
            self.assertEqual(summary.decisions, 1)
            self.assertEqual(summary.actions_this_turn, 1)
            self.assertEqual(summary.ended_by, "phase_changed")

    def test_orchestrator_respects_max_actions_per_turn(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(actions=[{"type": "play_card", "label": "Strike", "params": {"card_id": "card-1"}}]),
                make_window(actions=[{"type": "play_card", "label": "Defend", "params": {"card_id": "card-2"}}], hand=["card-2"]),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, max_actions_per_turn=1, max_steps=4),
            )
            summary = orchestrator.run(scenario="live")

            self.assertFalse(summary.completed)
            self.assertTrue(summary.interrupted)
            self.assertFalse(summary.turn_completed)
            self.assertEqual(summary.decisions, 1)
            self.assertEqual(summary.actions_this_turn, 1)
            self.assertEqual(summary.ended_by, "max_actions_per_turn")

    def test_orchestrator_retries_until_snapshot_and_actions_are_consistent(self) -> None:
        bridge = SnapshotDriftBridge()
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertEqual(summary.ended_by, "auto_end_turn")
            self.assertEqual(bridge.submissions, ["end_turn"])

    def test_orchestrator_retries_stale_action_with_fresh_state(self) -> None:
        bridge = RetryableStaleBridge()
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, stale_action_retries=1),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertEqual(summary.ended_by, "auto_end_turn")
            self.assertEqual(bridge.submissions, ["end_turn"])
            records = [json.loads(line) for line in Path(summary.trace_path).read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[0]["stop_reason"], "stale_action_retry")
            self.assertFalse(records[0]["is_final_step"])
            self.assertEqual(summary.recovery_attempts, 1)
            self.assertEqual(summary.recovery_successes, 1)
            self.assertEqual(summary.last_recovery_reason, "stale_action")

    def test_orchestrator_passes_battle_context_to_policy_and_trace(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(actions=[{"type": "play_card", "label": "Strike", "params": {"card_id": "card-1"}}]),
                make_window(phase="reward", actions=[], metadata={}),
            ]
        )
        policy = CapturingBattleContextPolicy()
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=policy,
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertEqual(len(policy.battle_contexts), 1)
            battle_context = policy.battle_contexts[0]
            assert battle_context is not None
            self.assertEqual(battle_context.phase, "combat")
            self.assertEqual(battle_context.current_turn_index, 1)
            self.assertEqual(battle_context.total_actions, 0)
            record = json.loads(Path(summary.trace_path).read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["battle_context"]["phase"], "combat")
            self.assertEqual(record["battle_context"]["current_turn_index"], 1)
            self.assertEqual(record["battle_context"]["recent_steps"], [])

    def test_orchestrator_supports_legacy_policy_without_battle_context(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(actions=[{"type": "play_card", "label": "Strike", "params": {"card_id": "card-1"}}]),
                make_window(phase="reward", actions=[], metadata={}),
            ]
        )
        policy = LegacyPolicy()
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=policy,
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertEqual(policy.calls, 1)

    def test_battle_mode_recovers_from_policy_invalid_action(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(actions=[{"type": "play_card", "label": "Strike", "params": {"card_id": "card-1"}}]),
                make_window(phase="reward", actions=[], metadata={}),
            ]
        )
        policy = RetryInvalidThenValidPolicy()
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=policy,
                config=OrchestratorConfig(trace_dir=tmpdir, stop_after_player_turn=False, max_steps=4),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertEqual(summary.recovery_attempts, 1)
            self.assertEqual(summary.recovery_successes, 1)
            self.assertEqual(summary.last_recovery_reason, "policy_invalid_action")
            records = [json.loads(line) for line in Path(summary.trace_path).read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[0]["bridge_result"]["error_code"], "policy_invalid_action")
            self.assertEqual(records[0]["stop_reason"], "policy_invalid_action_retry")

    def test_battle_mode_recovers_from_policy_error(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(actions=[{"type": "play_card", "label": "Strike", "params": {"card_id": "card-1"}}]),
                make_window(phase="reward", actions=[], metadata={}),
            ]
        )
        policy = RetryPolicyErrorThenValid()
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=policy,
                config=OrchestratorConfig(trace_dir=tmpdir, stop_after_player_turn=False, max_steps=4),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertEqual(summary.recovery_attempts, 1)
            self.assertEqual(summary.recovery_successes, 1)
            records = [json.loads(line) for line in Path(summary.trace_path).read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[0]["bridge_result"]["error_code"], "llm_parse_error")
            self.assertEqual(records[0]["stop_reason"], "llm_parse_error_retry")

    def test_orchestrator_retries_stale_auto_end_turn_with_fresh_state(self) -> None:
        bridge = RetryableAutoEndTurnStaleBridge()
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, stale_action_retries=1),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertEqual(summary.ended_by, "auto_end_turn")
            self.assertEqual(bridge.submissions, ["end_turn"])
            records = [json.loads(line) for line in Path(summary.trace_path).read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[0]["stop_reason"], "stale_action_retry")
            self.assertFalse(records[0]["is_final_step"])

    def test_battle_mode_waits_for_end_turn_resolution_before_retrying(self) -> None:
        bridge = DelayedEndTurnResolutionBridge()
        with tempfile.TemporaryDirectory() as tmpdir, patch("sts2_agent.orchestrator.time.sleep", return_value=None):
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, stop_after_player_turn=False, max_steps=12),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertTrue(summary.battle_completed)
            self.assertEqual(bridge.submissions, ["end_turn"])
            records = [json.loads(line) for line in Path(summary.trace_path).read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(record["bridge_result"].get("reason") == "pending_end_turn_transition" for record in records))

    def test_orchestrator_filters_unplayable_cards_and_auto_ends_turn(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    actions=[
                        {"type": "play_card", "label": "Strike", "params": {"card_id": "card-1"}},
                        {"type": "play_card", "label": "Defend", "params": {"card_id": "card-2"}},
                        {"type": "end_turn", "label": "End Turn"},
                    ],
                    energy=0,
                    hand=["card-1", "card-2"],
                ),
                make_window(phase="reward", actions=[]),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertEqual(summary.ended_by, "auto_end_turn")
            self.assertEqual(bridge.submissions, ["end_turn"])

    def test_orchestrator_filters_unsupported_potion_actions(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    actions=[
                        {"type": "use_potion", "label": "Use 迅捷药水", "params": {"potion_index": 0}},
                        {"type": "end_turn", "label": "End Turn"},
                    ],
                    energy=0,
                    hand=[],
                ),
                make_window(phase="reward", actions=[]),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertEqual(summary.ended_by, "auto_end_turn")
            self.assertEqual(bridge.submissions, ["end_turn"])

    def test_battle_mode_waits_for_enemy_turn_then_resumes(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    actions=[
                        {"type": "play_card", "label": "Strike", "params": {"card_id": "card-1"}},
                        {"type": "end_turn", "label": "End Turn"},
                    ],
                    metadata={"current_side": "Player", "round_number": 1},
                ),
                make_window(
                    actions=[{"type": "end_turn", "label": "End Turn"}],
                    energy=0,
                    hand=[],
                    metadata={"current_side": "Player", "round_number": 1},
                ),
                make_window(
                    actions=[],
                    hand=[],
                    metadata={"current_side": "Enemy", "round_number": 1},
                ),
                make_window(
                    actions=[
                        {"type": "play_card", "label": "Strike+", "params": {"card_id": "card-2"}},
                        {"type": "end_turn", "label": "End Turn"},
                    ],
                    hand=["card-2"],
                    metadata={"current_side": "Player", "round_number": 2},
                ),
                make_window(
                    actions=[{"type": "end_turn", "label": "End Turn"}],
                    energy=0,
                    hand=[],
                    metadata={"current_side": "Player", "round_number": 2},
                ),
                make_window(phase="reward", actions=[], metadata={}),
            ],
            advance_on_snapshot_reads={2: 4},
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch("sts2_agent.orchestrator.time.sleep", return_value=None):
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, stop_after_player_turn=False, max_steps=16),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertFalse(summary.interrupted)
            self.assertTrue(summary.battle_completed)
            self.assertEqual(summary.turns_completed, 2)
            self.assertEqual(summary.total_actions, 4)
            self.assertEqual(summary.current_turn_index, 2)
            self.assertEqual(bridge.submissions, ["play_card", "end_turn", "play_card", "end_turn"])
            records = [json.loads(line) for line in Path(summary.trace_path).read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(record["waiting_for_player_turn"] for record in records))
            self.assertTrue(any(record["current_turn_index"] == 2 for record in records))

    def test_orchestrator_handles_combat_card_selection_window(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    actions=[
                        {"type": "choose_combat_card", "label": "消耗 防御", "params": {"card_id": "card-2", "selection_index": 0}},
                        {"type": "cancel_combat_selection", "label": "取消", "params": {}},
                    ],
                    hand=["card-1", "card-2"],
                    metadata={
                        "window_kind": "combat_card_selection",
                        "current_side": "Player",
                        "selection_kind": "exhaust_card",
                        "selection_prompt": "消耗1张牌",
                    },
                ),
                make_window(
                    actions=[{"type": "end_turn", "label": "End Turn"}],
                    energy=0,
                    hand=[],
                    metadata={"window_kind": "player_turn", "current_side": "Player", "round_number": 1},
                ),
                make_window(phase="reward", actions=[], metadata={}),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, stop_after_player_turn=False, max_steps=6),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertEqual(bridge.submissions[0], "choose_combat_card")
            records = [json.loads(line) for line in Path(summary.trace_path).read_text(encoding="utf-8").splitlines()]
            self.assertIn("combat_card_selection", {record["step_kind"] for record in records})

    def test_battle_context_keeps_recent_steps_across_combat_selection(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    actions=[{"type": "play_card", "label": "True Grit", "params": {"card_id": "card-1"}}],
                    metadata={"window_kind": "player_turn", "current_side": "Player", "round_number": 1},
                ),
                make_window(
                    actions=[
                        {"type": "choose_combat_card", "label": "消耗 防御", "params": {"card_id": "card-2", "selection_index": 0}},
                        {"type": "cancel_combat_selection", "label": "取消", "params": {}},
                    ],
                    hand=["card-2"],
                    metadata={
                        "window_kind": "combat_card_selection",
                        "current_side": "Player",
                        "round_number": 1,
                        "selection_kind": "exhaust_card",
                        "selection_prompt": "消耗1张牌",
                    },
                ),
                make_window(phase="reward", actions=[], metadata={}),
            ]
        )
        policy = CapturingBattleContextPolicy()
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=policy,
                config=OrchestratorConfig(trace_dir=tmpdir, stop_after_player_turn=False, max_steps=6),
            )
            summary = orchestrator.run(scenario="live")

            self.assertTrue(summary.completed)
            self.assertGreaterEqual(len(policy.battle_contexts), 2)
            followup_context = policy.battle_contexts[1]
            assert followup_context is not None
            self.assertEqual(followup_context.phase_kind, "combat_card_selection")
            self.assertTrue(followup_context.recent_steps)
            self.assertEqual(followup_context.recent_steps[-1]["action_id"], "act-0-0-play_card")

    def test_battle_mode_stops_when_waiting_for_next_turn_times_out(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(actions=[{"type": "end_turn", "label": "End Turn"}], hand=[], metadata={"current_side": "Player", "round_number": 1}),
                make_window(actions=[], hand=[], metadata={"current_side": "Enemy", "round_number": 1}),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch("sts2_agent.orchestrator.time.sleep", return_value=None), patch(
            "sts2_agent.orchestrator.time.monotonic",
            side_effect=[0.0, 0.0, 0.2, 0.2],
        ):
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(
                    trace_dir=tmpdir,
                    stop_after_player_turn=False,
                    wait_for_next_player_turn_seconds=0.1,
                    poll_interval_seconds=0.0,
                    max_steps=6,
                ),
            )
            summary = orchestrator.run(scenario="live")

            self.assertFalse(summary.completed)
            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.ended_by, "next_player_turn_timeout")
            self.assertTrue(summary.turn_completed)
            records = [json.loads(line) for line in Path(summary.trace_path).read_text(encoding="utf-8").splitlines()]
            self.assertTrue(records[-1]["waiting_for_player_turn"])
            self.assertEqual(records[-1]["battle_stop_reason"], "next_player_turn_timeout")

    def test_battle_mode_stops_when_recovery_budget_exhausted(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(actions=[], hand=[], metadata={"current_side": "Enemy", "round_number": 1}),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch("sts2_agent.orchestrator.time.sleep", return_value=None):
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(
                    trace_dir=tmpdir,
                    stop_after_player_turn=False,
                    max_recovery_attempts=1,
                    wait_for_next_player_turn_seconds=30.0,
                    max_steps=4,
                ),
            )
            summary = orchestrator.run(scenario="live")

            self.assertFalse(summary.completed)
            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.ended_by, "recovery_budget_exhausted")
            self.assertEqual(summary.recovery_attempts, 1)
            self.assertEqual(summary.recovery_successes, 0)

    def test_battle_mode_respects_max_turns_per_battle(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(actions=[{"type": "end_turn", "label": "End Turn"}], hand=[], metadata={"current_side": "Player", "round_number": 1}),
                make_window(actions=[], hand=[], metadata={"current_side": "Enemy", "round_number": 1}),
                make_window(actions=[{"type": "end_turn", "label": "End Turn"}], hand=[], metadata={"current_side": "Player", "round_number": 2}),
            ],
            advance_on_snapshot_reads={1: 4},
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch("sts2_agent.orchestrator.time.sleep", return_value=None):
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, stop_after_player_turn=False, max_turns_per_battle=1, max_steps=8),
            )
            summary = orchestrator.run(scenario="live")

            self.assertFalse(summary.completed)
            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.ended_by, "max_turns_per_battle")
            self.assertEqual(summary.turns_completed, 1)
            self.assertEqual(summary.total_actions, 1)

    def test_battle_mode_respects_max_total_actions(self) -> None:
        bridge = SequencedCombatBridge(
            [
                make_window(
                    actions=[
                        {"type": "play_card", "label": "Strike", "params": {"card_id": "card-1"}},
                        {"type": "end_turn", "label": "End Turn"},
                    ],
                    metadata={"current_side": "Player", "round_number": 1},
                ),
                make_window(actions=[{"type": "end_turn", "label": "End Turn"}], hand=[], metadata={"current_side": "Player", "round_number": 1}),
                make_window(actions=[], hand=[], metadata={"current_side": "Enemy", "round_number": 1}),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir, patch("sts2_agent.orchestrator.time.sleep", return_value=None):
            orchestrator = AutoplayOrchestrator(
                bridge=bridge,
                policy=FirstLegalActionPolicy(),
                config=OrchestratorConfig(trace_dir=tmpdir, stop_after_player_turn=False, max_total_actions=2, max_steps=8),
            )
            summary = orchestrator.run(scenario="live")

            self.assertFalse(summary.completed)
            self.assertTrue(summary.interrupted)
            self.assertEqual(summary.ended_by, "max_total_actions")
            self.assertEqual(summary.total_actions, 2)


if __name__ == "__main__":
    unittest.main()

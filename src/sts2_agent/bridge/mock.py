from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from sts2_agent.bridge.base import (
    BridgeSession,
    GameBridge,
    InterruptedSessionError,
    InvalidPayloadError,
    SessionNotFoundError,
    StaleActionError,
)
from sts2_agent.ids import create_action_id, create_decision_id, create_session_id, ensure_state_version, validate_identifier
from sts2_agent.models import ActionResult, ActionStatus, ActionSubmission, CardView, DecisionSnapshot, EnemyState, LegalAction, PlayerState


@dataclass(slots=True)
class WindowFixture:
    phase: str
    player: dict[str, Any] | None
    enemies: list[dict[str, Any]]
    rewards: list[str]
    map_nodes: list[str]
    legal_actions: list[dict[str, Any]]
    metadata: dict[str, Any]
    terminal: bool = False


class MockGameBridge(GameBridge):
    def __init__(self, scenario: str = "combat_reward_map_terminal") -> None:
        self._default_scenario = scenario
        self._sessions: dict[str, BridgeSession] = {}
        self._states: dict[str, dict[str, Any]] = {}

    def attach_or_start(self, scenario: str = "combat_reward_map_terminal") -> BridgeSession:
        active_scenario = scenario or self._default_scenario
        session = BridgeSession(session_id=create_session_id(active_scenario), scenario=active_scenario)
        self._sessions[session.session_id] = session
        self._states[session.session_id] = {
            "index": 0,
            "windows": self._load_scenario(active_scenario),
            "stopped": False,
        }
        return session

    def get_snapshot(self, session_id: str) -> DecisionSnapshot:
        session, _ = self._require_session(session_id)
        window = self._current_window(session_id)
        decision_id = create_decision_id(session.session_id, session.state_version, window.phase)
        return DecisionSnapshot(
            session_id=session.session_id,
            decision_id=decision_id,
            state_version=session.state_version,
            phase=window.phase,
            player=self._build_player(window.player),
            enemies=[EnemyState(**enemy) for enemy in window.enemies],
            rewards=deepcopy(window.rewards),
            map_nodes=deepcopy(window.map_nodes),
            terminal=window.terminal,
            metadata={"scenario": session.scenario, **deepcopy(window.metadata)},
        )

    def get_legal_actions(self, session_id: str) -> list[LegalAction]:
        session, _ = self._require_session(session_id)
        window = self._current_window(session_id)
        if window.terminal:
            return []
        decision_id = create_decision_id(session.session_id, session.state_version, window.phase)
        actions = []
        for action in window.legal_actions:
            payload = {k: v for k, v in action.items() if k not in {"label", "type"}}
            actions.append(
                LegalAction(
                    action_id=create_action_id(decision_id, action["type"], payload),
                    type=action["type"],
                    label=action["label"],
                    params={k: v for k, v in action.items() if k not in {"label", "type", "target_constraints"}},
                    target_constraints=action.get("target_constraints", []),
                    metadata={"decision_id": decision_id},
                )
            )
        return actions

    def submit_action(self, submission: ActionSubmission) -> ActionResult:
        session, state = self._require_session(submission.session_id)
        validate_identifier(submission.session_id, "sess")
        ensure_state_version(submission.state_version)
        if state["stopped"] or session.interrupted:
            raise InterruptedSessionError("session is interrupted")

        snapshot = self.get_snapshot(submission.session_id)
        if submission.state_version != snapshot.state_version or submission.decision_id != snapshot.decision_id:
            raise StaleActionError("submitted action does not match active decision window")

        legal_actions = {action.action_id: action for action in self.get_legal_actions(submission.session_id)}
        if submission.action_id not in legal_actions:
            raise InvalidPayloadError("action is not legal for the active decision window")

        accepted = legal_actions[submission.action_id]
        if not snapshot.terminal and state["index"] < len(state["windows"]) - 1:
            state["index"] += 1
            session.state_version += 1
        next_snapshot = self.get_snapshot(submission.session_id)
        return ActionResult(
            status=ActionStatus.ACCEPTED,
            session_id=session.session_id,
            decision_id=next_snapshot.decision_id,
            state_version=next_snapshot.state_version,
            accepted_action_id=accepted.action_id,
            message=f"accepted {accepted.type}",
            terminal=next_snapshot.terminal,
            metadata={"phase": next_snapshot.phase},
        )

    def stop(self, session_id: str) -> BridgeSession:
        session, state = self._require_session(session_id)
        state["stopped"] = True
        session.interrupted = True
        return session

    def reset(self, session_id: str) -> BridgeSession:
        session, _ = self._require_session(session_id)
        return self.attach_or_start(session.scenario)

    def _require_session(self, session_id: str) -> tuple[BridgeSession, dict[str, Any]]:
        if session_id not in self._sessions:
            raise SessionNotFoundError(f"unknown session: {session_id}")
        return self._sessions[session_id], self._states[session_id]

    def _current_window(self, session_id: str) -> WindowFixture:
        session, state = self._require_session(session_id)
        if state["stopped"] or session.interrupted:
            raise InterruptedSessionError("session is interrupted")
        raw = state["windows"][state["index"]]
        return WindowFixture(**deepcopy(raw))

    def _load_scenario(self, scenario: str) -> list[dict[str, Any]]:
        if scenario != "combat_reward_map_terminal":
            raise InvalidPayloadError(f"unsupported scenario: {scenario}")
        fixture_dir = files("sts2_agent.fixtures")
        ordered = ["combat_turn.json", "reward_choice.json", "map_choice.json", "terminal.json"]
        windows = []
        for name in ordered:
            windows.append(json.loads((fixture_dir / name).read_text(encoding="utf-8-sig")))
        return windows

    @staticmethod
    def _build_player(raw: dict[str, Any] | None) -> PlayerState | None:
        if raw is None:
            return None
        hand = [CardView(**card) for card in raw.get("hand", [])]
        payload = {k: v for k, v in raw.items() if k != "hand"}
        return PlayerState(hand=hand, **payload)

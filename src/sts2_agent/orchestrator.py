from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone

UTC = timezone.utc
import inspect
from pathlib import Path
from typing import Any

from sts2_agent.bridge import BridgeError, GameBridge, InvalidPayloadError, InterruptedSessionError, StaleActionError
from sts2_agent.models import AgentStatusUpdate, ActionSubmission, ActionType, BattleContext, PolicyDecision, RunSummary, TraceEntry, to_dict
from sts2_agent.policy import PolicyDecisionValidationError, PolicyError
from sts2_agent.trace import JsonlTraceRecorder

RECOVERABLE_REJECT_CATEGORIES = {"recoverable_stale", "recoverable_timing", "recoverable_action"}
SELECTION_ACTION_TYPES = {"choose_combat_card", "cancel_combat_selection"}
TRANSITION_WINDOW_KINDS = {
    "combat_transition",
    "reward_transition",
    "map_transition",
    "event_transition",
    "shop_transition",
    "menu_transition",
}


@dataclass(slots=True)
class OrchestratorConfig:
    timeout_seconds: float = 5.0
    max_steps: int = 64
    max_actions_per_turn: int | None = None
    stop_after_player_turn: bool = True
    auto_end_turn_when_only_end_turn: bool = True
    menu_mode: str = "halt"  # halt|auto
    reward_mode: str = "halt"  # halt|skip|skip-only|safe-default|llm
    map_mode: str = "halt"  # halt|safe-default|llm
    event_mode: str = "halt"  # halt|safe-default|llm
    shop_mode: str = "halt"  # halt|safe-default|llm
    state_sync_retries: int = 3
    stale_action_retries: int = 2
    max_turns_per_battle: int | None = None
    max_total_actions: int | None = None
    max_consecutive_failures: int = 6
    max_recovery_attempts: int = 6
    wait_for_next_player_turn_seconds: float = 30.0
    transition_timeout_seconds: float = 30.0
    poll_interval_seconds: float = 0.5
    stable_window_required_observations: int = 2
    stable_window_timeout_seconds: float = 2.0
    max_non_combat_steps: int = 100
    unknown_window_fuse: int = 2
    stop_after_next_combat: bool = False
    battle_context_recent_steps: int = 4
    trace_dir: str = "traces"
    dry_run: bool = False


class AutoplayOrchestrator:
    def __init__(self, bridge: GameBridge, policy, config: OrchestratorConfig | None = None) -> None:
        self.bridge = bridge
        self.policy = policy
        self.config = config or OrchestratorConfig()
        self._stop_requested = False
        self._reward_actions_taken = 0
        self._map_actions_taken = 0
        self._non_combat_steps = 0
        self._next_combat_entered = False
        self._transition_attempt = 0
        self._battle_history: list[dict[str, Any]] = []
        self._recovery_attempts = 0
        self._recovery_successes = 0
        self._recovery_streak = 0
        self._pending_recovery_reason = ""
        self._last_recovery_reason = ""
        self._rejects_total = 0
        self._recoverable_rejects = 0
        self._hard_rejects = 0
        self._gate_intercepts = 0
        self._gate_wait_steps = 0
        self._gate_redecisions = 0
        self._gate_rebases = 0
        self._reject_counts: dict[str, int] = {}
        self._reject_code_counts: dict[str, int] = {}
        self._last_reject: dict[str, Any] = {}
        self._last_battle_context: dict[str, Any] = {}
        self._same_window_action_exclusions: dict[tuple[str, str, int, str, str], set[tuple[str, object | None, object | None]]] = {}

    def request_stop(self) -> None:
        self._stop_requested = True

    def _reset_run_state(self) -> None:
        self._reward_actions_taken = 0
        self._map_actions_taken = 0
        self._non_combat_steps = 0
        self._next_combat_entered = False
        self._transition_attempt = 0
        self._battle_history = []
        self._recovery_attempts = 0
        self._recovery_successes = 0
        self._recovery_streak = 0
        self._pending_recovery_reason = ""
        self._last_recovery_reason = ""
        self._rejects_total = 0
        self._recoverable_rejects = 0
        self._hard_rejects = 0
        self._gate_intercepts = 0
        self._gate_wait_steps = 0
        self._gate_redecisions = 0
        self._gate_rebases = 0
        self._reject_counts = {}
        self._reject_code_counts = {}
        self._last_reject = {}
        self._last_battle_context = {}
        self._same_window_action_exclusions = {}

    def _publish_agent_status(
        self,
        *,
        snapshot,
        policy_output: PolicyDecision,
        status: str,
        step_index: int,
        current_turn_index: int,
        action_label: str | None = None,
    ) -> None:
        updater = getattr(self.bridge, "update_agent_status", None)
        if not callable(updater):
            return

        confidence = policy_output.confidence
        payload = AgentStatusUpdate(
            session_id=snapshot.session_id,
            phase=getattr(snapshot, "phase", "unknown"),
            status=status,
            updated_at=datetime.now(UTC).isoformat(),
            action_id=policy_output.action_id,
            action_label=action_label,
            reason=policy_output.reason,
            detail=self._agent_status_detail(policy_output),
            confidence=None if confidence is None else str(confidence),
            turn=current_turn_index if current_turn_index > 0 else None,
            step=step_index,
        )
        try:
            updater(payload)
        except Exception:
            return

    @staticmethod
    def _agent_status_detail(policy_output: PolicyDecision) -> str | None:
        if policy_output.detail and policy_output.detail.strip():
            return policy_output.detail.strip()
        if policy_output.reason and policy_output.reason.strip():
            return policy_output.reason.strip()
        return None

    @staticmethod
    def _thinking_policy_output() -> PolicyDecision:
        return PolicyDecision(
            action_id=None,
            reason="等待策略决策",
            detail="正在读取当前局面并生成下一步动作。",
            metadata={"agent_status_only": True},
        )

    def _clear_agent_status(self) -> None:
        clearer = getattr(self.bridge, "clear_agent_status", None)
        if not callable(clearer):
            return
        try:
            clearer()
        except Exception:
            return

    def run(self, scenario: str = "combat_reward_map_terminal") -> RunSummary:
        self._reset_run_state()
        session = self.bridge.attach_or_start(scenario=scenario)
        trace_path = Path(self.config.trace_dir) / f"{session.session_id}.jsonl"
        recorder = JsonlTraceRecorder(trace_path)
        total_actions = 0
        current_turn_actions = 0
        current_turn_index = 0
        turns_completed = 0
        current_turn_marker: object | None = None
        waiting_since: float | None = None
        transition_wait_since: float | None = None
        pending_end_turn_transition: tuple[str, int] | None = None
        stale_action_attempts = 0
        consecutive_failures = 0
        step_index = 0
        previous_phase: str | None = None
        previous_snapshot: Any = None
        unknown_window_steps = 0

        while True:
            if (
                step_index >= self.config.max_steps
                and transition_wait_since is None
                and waiting_since is None
                and pending_end_turn_transition is None
            ):
                break

            snapshot, legal_actions = self._read_consistent_state(session.session_id)

            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=self._thinking_policy_output(),
                status="thinking",
                step_index=step_index,
                current_turn_index=current_turn_index,
            )

            legal_actions = self._effective_legal_actions(snapshot, legal_actions)
            if pending_end_turn_transition is not None:
                if (snapshot.decision_id, snapshot.state_version) != pending_end_turn_transition:
                    pending_end_turn_transition = None
                    waiting_since = None
            phase = self._normalize_phase(getattr(snapshot, "phase", ""))
            if previous_phase in {"reward", "map", "event", "shop"} and phase == "combat" and not snapshot.terminal:
                self._next_combat_entered = True
                transition_wait_since = None

            # New: Also clear transition_wait_since if the state version has changed
            if transition_wait_since is not None and previous_snapshot is not None:
                if (snapshot.decision_id, snapshot.state_version) != (previous_snapshot.decision_id, previous_snapshot.state_version):
                    transition_wait_since = None

            if previous_snapshot is not None and (snapshot.decision_id, snapshot.state_version) != (previous_snapshot.decision_id, previous_snapshot.state_version):
                # 全局状态变更后的缓冲等待，防止动画瞬间完成导致的状态不一致
                time.sleep(self.config.poll_interval_seconds)

            current_previous_snapshot = previous_snapshot
            previous_snapshot = snapshot
            player_turn = self._is_player_turn(snapshot)
            current_turn_marker, current_turn_index, current_turn_actions = self._update_turn_state(
                snapshot,
                player_turn,
                current_turn_marker,
                current_turn_index,
                current_turn_actions,
            )

            if not player_turn and current_turn_index > turns_completed:
                turns_completed = current_turn_index

            phase_kind = self._phase_kind(
                snapshot,
                legal_actions,
                player_turn=player_turn,
                pending_end_turn_transition=pending_end_turn_transition,
                previous_phase=previous_phase,
            )

            # Check if we are stuck in a transition (animation still playing)
            # even if the game still reports legal_actions from the old state.
            if transition_wait_since is not None:
                # If the state version has not changed yet, we MUST treat it as a transition wait
                # instead of letting the phase handlers re-execute the same action.
                # Only clear it when we see a combat phase (already handled below) or the state version updates.
                phase_kind = "transition_wait"

            if current_previous_snapshot is not None and not self._is_player_turn(current_previous_snapshot) and player_turn:
                # 进入新的玩家回合时，强制执行一次稳定等待。
                # 这有助于确保动画完全停止，并防止使用过时的 snapshot。
                if self.config.poll_interval_seconds > 0:
                    time.sleep(self.config.poll_interval_seconds)
                    continue

            if self._is_non_combat_phase_kind(phase_kind) and phase_kind != "transition_wait":
                self._non_combat_steps += 1

            if snapshot.terminal:
                return self._finish(
                    session_id=session.session_id,
                    trace_path=trace_path,
                    reason="terminal_state_reached",
                    completed=True,
                    interrupted=False,
                    turn_completed=current_turn_index > 0,
                    battle_completed=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                )

            if self._stop_requested:
                try:
                    self.bridge.stop(session.session_id)
                except BridgeError:
                    pass
                return self._finish(
                    session_id=session.session_id,
                    trace_path=trace_path,
                    reason="manual_stop",
                    completed=False,
                    interrupted=True,
                    turn_completed=turns_completed > 0,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                )

            budget_stop_reason = self._battle_budget_stop_reason(
                total_actions=total_actions,
                turns_completed=turns_completed,
                current_turn_index=current_turn_index,
                consecutive_failures=consecutive_failures,
            )
            if budget_stop_reason:
                effective_turns_completed = turns_completed
                if budget_stop_reason == "max_turns_per_battle" and current_turn_index > turns_completed:
                    effective_turns_completed = max(turns_completed, current_turn_index - 1)
                return self._finish(
                    session_id=session.session_id,
                    trace_path=trace_path,
                    reason=budget_stop_reason,
                    completed=False,
                    interrupted=True,
                    turn_completed=effective_turns_completed > 0,
                    actions_this_turn=current_turn_actions,
                    turns_completed=effective_turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                )

            if self.config.max_non_combat_steps >= 0 and self._non_combat_steps > self.config.max_non_combat_steps:
                return self._finish(
                    session_id=session.session_id,
                    trace_path=trace_path,
                    reason="max_non_combat_steps",
                    completed=False,
                    interrupted=True,
                    turn_completed=turns_completed > 0,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                )

            if self._next_combat_entered and self.config.stop_after_next_combat and phase == "combat":
                step_index += 1
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=PolicyDecision(action_id=None, reason="next combat entered; stop_after_next_combat=true", halt=True),
                    bridge_result={"status": "completed", "reason": "next_combat_entered"},
                    interrupted=False,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=True,
                    stop_reason="next_combat_entered",
                    battle_stop_reason="next_combat_entered",
                    step_kind="combat_resume",
                    phase_kind="combat_resume",
                )
                return self._finish(
                    session_id=session.session_id,
                    trace_path=trace_path,
                    reason="next_combat_entered",
                    completed=True,
                    interrupted=False,
                    turn_completed=turns_completed > 0,
                    battle_completed=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                )

            if phase == "reward":
                outcome = self._handle_reward_phase(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    turns_completed=turns_completed,
                    trace_path=trace_path,
                    session_id=session.session_id,
                    transition_wait_since=transition_wait_since,
                )
                step_index = outcome["step_index"]
                transition_wait_since = outcome.get("transition_wait_since", transition_wait_since)
                current_turn_actions = outcome["current_turn_actions"]
                total_actions = outcome["total_actions"]
                stale_action_attempts = outcome["stale_action_attempts"]
                consecutive_failures = outcome["consecutive_failures"]
                pending_end_turn_transition = outcome["pending_end_turn_transition"]
                if outcome["summary"] is not None:
                    return outcome["summary"]
                previous_phase = phase
                previous_snapshot = snapshot
                continue

            if phase == "map":
                outcome = self._handle_map_phase(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    turns_completed=turns_completed,
                    trace_path=trace_path,
                    session_id=session.session_id,
                    transition_wait_since=transition_wait_since,
                )
                step_index = outcome["step_index"]
                transition_wait_since = outcome.get("transition_wait_since", transition_wait_since)
                current_turn_actions = outcome["current_turn_actions"]
                total_actions = outcome["total_actions"]
                stale_action_attempts = outcome["stale_action_attempts"]
                consecutive_failures = outcome["consecutive_failures"]
                pending_end_turn_transition = outcome["pending_end_turn_transition"]
                if outcome["summary"] is not None:
                    return outcome["summary"]
                previous_phase = phase
                previous_snapshot = snapshot
                continue

            if phase == "event":
                outcome = self._handle_event_phase(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    turns_completed=turns_completed,
                    trace_path=trace_path,
                    session_id=session.session_id,
                    transition_wait_since=transition_wait_since,
                )
                step_index = outcome["step_index"]
                transition_wait_since = outcome.get("transition_wait_since", transition_wait_since)
                current_turn_actions = outcome["current_turn_actions"]
                total_actions = outcome["total_actions"]
                stale_action_attempts = outcome["stale_action_attempts"]
                consecutive_failures = outcome["consecutive_failures"]
                pending_end_turn_transition = outcome["pending_end_turn_transition"]
                if outcome["summary"] is not None:
                    return outcome["summary"]
                previous_phase = phase
                previous_snapshot = snapshot
                continue

            if phase == "shop":
                outcome = self._handle_shop_phase(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    turns_completed=turns_completed,
                    trace_path=trace_path,
                    session_id=session.session_id,
                    transition_wait_since=transition_wait_since,
                )
                step_index = outcome["step_index"]
                transition_wait_since = outcome.get("transition_wait_since", transition_wait_since)
                current_turn_actions = outcome["current_turn_actions"]
                total_actions = outcome["total_actions"]
                stale_action_attempts = outcome["stale_action_attempts"]
                consecutive_failures = outcome["consecutive_failures"]
                pending_end_turn_transition = outcome["pending_end_turn_transition"]
                if outcome["summary"] is not None:
                    return outcome["summary"]
                previous_phase = phase
                previous_snapshot = snapshot
                continue

            if phase == "menu":
                outcome = self._handle_menu_phase(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    turns_completed=turns_completed,
                    trace_path=trace_path,
                    session_id=session.session_id,
                    transition_wait_since=transition_wait_since,
                )
                step_index = outcome["step_index"]
                transition_wait_since = outcome.get("transition_wait_since", transition_wait_since)
                current_turn_actions = outcome["current_turn_actions"]
                total_actions = outcome["total_actions"]
                stale_action_attempts = outcome["stale_action_attempts"]
                consecutive_failures = outcome["consecutive_failures"]
                pending_end_turn_transition = outcome["pending_end_turn_transition"]
                if outcome["summary"] is not None:
                    return outcome["summary"]
                previous_phase = phase
                continue

            if phase_kind == "transition_wait" and pending_end_turn_transition is None:
                outcome = self._handle_transition_wait(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    turns_completed=turns_completed,
                    trace_path=trace_path,
                    waiting_since=transition_wait_since,
                    stop_reason="transition_timeout",
                    wait_reason=self._transition_wait_reason(snapshot),
                    step_kind="transition_wait",
                    phase_kind=phase_kind,
                )
                step_index = outcome["step_index"]
                transition_wait_since = outcome["transition_wait_since"]
                current_turn_actions = outcome["current_turn_actions"]
                total_actions = outcome["total_actions"]
                stale_action_attempts = outcome["stale_action_attempts"]
                consecutive_failures = outcome["consecutive_failures"]
                pending_end_turn_transition = outcome["pending_end_turn_transition"]
                if outcome["summary"] is not None:
                    return outcome["summary"]
                previous_phase = phase
                continue

            if phase not in {"combat", "terminal"}:
                unknown_window_steps += 1
                step_index += 1
                unsupported_reason = "unsupported_phase" if phase != "unknown" else "unknown_window"
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=PolicyDecision(action_id=None, reason=f"unsupported phase: {phase}", halt=True),
                    bridge_result={"status": "interrupted", "reason": unsupported_reason, "phase": phase},
                    interrupted=True,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=unknown_window_steps >= self.config.unknown_window_fuse,
                    stop_reason="" if unknown_window_steps < self.config.unknown_window_fuse else unsupported_reason,
                    battle_stop_reason="" if unknown_window_steps < self.config.unknown_window_fuse else unsupported_reason,
                    step_kind="unknown_window",
                    phase_kind="unknown_window",
                )
                if unknown_window_steps >= self.config.unknown_window_fuse:
                    return self._finish(
                        session_id=session.session_id,
                        trace_path=trace_path,
                        reason=unsupported_reason,
                        completed=False,
                        interrupted=True,
                        turn_completed=turns_completed > 0,
                        actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    )
                time.sleep(self.config.poll_interval_seconds)
                previous_phase = phase
                continue

            unknown_window_steps = 0
            transition_wait_since = None

            battle_stop_reason = self._battle_completion_reason(snapshot)
            if battle_stop_reason:
                if current_turn_index > turns_completed:
                    turns_completed = current_turn_index
                return self._finish(
                    session_id=session.session_id,
                    trace_path=trace_path,
                    reason=battle_stop_reason,
                    completed=True,
                    interrupted=False,
                    turn_completed=turns_completed > 0,
                    battle_completed=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                )

            if pending_end_turn_transition is not None:
                outcome = self._handle_pending_end_turn_transition(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    turns_completed=turns_completed,
                    trace_path=trace_path,
                    waiting_since=waiting_since,
                )
                step_index = outcome["step_index"]
                waiting_since = outcome["waiting_since"]
                if outcome["summary"] is not None:
                    return outcome["summary"]
                previous_phase = phase
                continue

            if not player_turn:
                outcome = self._handle_non_player_turn(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    turns_completed=turns_completed,
                    trace_path=trace_path,
                    waiting_since=waiting_since,
                )
                step_index = outcome["step_index"]
                waiting_since = outcome["waiting_since"]
                if outcome["summary"] is not None:
                    return outcome["summary"]
                previous_phase = phase
                continue

            empty_actions_outcome = self._handle_empty_player_actions(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                turns_completed=turns_completed,
                trace_path=trace_path,
                session_id=session.session_id,
                waiting_since=waiting_since,
            )
            if empty_actions_outcome is not None:
                step_index = empty_actions_outcome["step_index"]
                waiting_since = empty_actions_outcome["waiting_since"]
                consecutive_failures = empty_actions_outcome["consecutive_failures"]
                if empty_actions_outcome["summary"] is not None:
                    return empty_actions_outcome["summary"]
                previous_phase = phase
                continue

            waiting_since = None

            preflight_summary = self._player_turn_preflight(
                session_id=session.session_id,
                trace_path=trace_path,
                legal_actions=legal_actions,
                current_turn_actions=current_turn_actions,
                current_turn_index=current_turn_index,
                turns_completed=turns_completed,
                total_actions=total_actions,
            )
            if preflight_summary is not None:
                return preflight_summary

            auto_end_result = self._handle_auto_end_turn(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                turns_completed=turns_completed,
                total_actions=total_actions,
                trace_path=trace_path,
                stale_action_attempts=stale_action_attempts,
                consecutive_failures=consecutive_failures,
                session_id=session.session_id,
            )
            if auto_end_result["summary"] is not None:
                return auto_end_result["summary"]
            if auto_end_result["consumed"]:
                step_index = auto_end_result["step_index"]
                current_turn_actions = auto_end_result["current_turn_actions"]
                total_actions = auto_end_result["total_actions"]
                stale_action_attempts = auto_end_result["stale_action_attempts"]
                consecutive_failures = auto_end_result["consecutive_failures"]
                pending_end_turn_transition = auto_end_result["pending_end_turn_transition"]
                previous_phase = phase
                continue

            action_result = self._run_player_step(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                turns_completed=turns_completed,
                total_actions=total_actions,
                stale_action_attempts=stale_action_attempts,
                consecutive_failures=consecutive_failures,
                trace_path=trace_path,
                session_id=session.session_id,
                battle_context=self._build_battle_context(
                    snapshot=snapshot,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    phase_kind=phase_kind,
                ),
            )
            step_index = action_result["step_index"]
            current_turn_actions = action_result["current_turn_actions"]
            total_actions = action_result["total_actions"]
            stale_action_attempts = action_result["stale_action_attempts"]
            consecutive_failures = action_result["consecutive_failures"]
            pending_end_turn_transition = action_result["pending_end_turn_transition"]
            if action_result["summary"] is not None:
                return action_result["summary"]
            previous_phase = phase

        return self._finish(
            session_id=session.session_id,
            trace_path=trace_path,
            reason="max_steps_exceeded",
            completed=False,
            interrupted=True,
            turn_completed=turns_completed > 0,
            actions_this_turn=current_turn_actions,
            turns_completed=turns_completed,
            total_actions=total_actions,
            current_turn_index=current_turn_index,
        )

    def _normalized_reward_mode(self) -> str:
        value = str(getattr(self.config, "reward_mode", "") or "").strip().lower()
        if value in {"halt", "skip", "skip-only", "safe-default", "llm"}:
            return value
        return "halt"

    def _normalized_map_mode(self) -> str:
        value = str(getattr(self.config, "map_mode", "") or "").strip().lower()
        if value in {"halt", "safe-default", "llm"}:
            return value
        return "halt"

    def _normalized_event_mode(self) -> str:
        value = str(getattr(self.config, "event_mode", "") or "").strip().lower()
        if value in {"halt", "safe-default", "llm"}:
            return value
        return "halt"

    def _normalized_shop_mode(self) -> str:
        value = str(getattr(self.config, "shop_mode", "") or "").strip().lower()
        if value in {"halt", "safe-default", "llm"}:
            return value
        return "halt"

    def _normalized_menu_mode(self) -> str:
        value = str(getattr(self.config, "menu_mode", "") or "").strip().lower()
        if value in {"halt", "auto"}:
            return value
        return "halt"

    @staticmethod
    def _normalize_phase(value: object) -> str:
        text = str(value or "").strip().lower()
        return text or "unknown"

    def _phase_kind(
        self,
        snapshot,
        legal_actions,
        *,
        player_turn: bool,
        pending_end_turn_transition: tuple[str, int] | None,
        previous_phase: str | None,
    ) -> str:
        phase = self._normalize_phase(getattr(snapshot, "phase", ""))
        metadata = getattr(snapshot, "metadata", {}) or {}
        window_kind = str(metadata.get("window_kind") or "").strip().lower()
        reward_subphase = str(metadata.get("reward_subphase") or "").strip().lower()
        if pending_end_turn_transition is not None:
            return "pending_end_turn_transition"
        if phase == "reward":
            if reward_subphase == "card_reward_selection" or window_kind == "reward_card_selection":
                return "card_reward_selection"
            if reward_subphase == "reward_advance" or window_kind == "reward_advance":
                return "reward_advance"
            if legal_actions:
                return "reward_choice"
            return "transition_wait"
        if phase == "map":
            if legal_actions:
                return "map"
            return "transition_wait"
        if phase == "event":
            if window_kind == "event_choice":
                return "event_choice" if legal_actions else "transition_wait"
            if window_kind == "event_continue":
                return "event_continue" if legal_actions else "transition_wait"
            if window_kind == "event_transition":
                return "transition_wait"
            if legal_actions:
                if any(str(getattr(action, "type", "")) == "choose_event_option" for action in legal_actions):
                    return "event_choice"
                return "event_continue"
            return "transition_wait"
        if phase == "shop":
            if window_kind == "shop_transition":
                return "transition_wait"
            if legal_actions:
                return "shop"
            return "transition_wait"
        if phase == "combat":
            if window_kind == "combat_card_selection":
                return "combat_card_selection"
            if window_kind == "combat_transition" or bool(metadata.get("reward_pending")):
                return "transition_wait"
            if previous_phase in {"reward", "map", "event", "shop"} and self._next_combat_entered:
                return "combat_resume"
            if player_turn:
                return "combat"
            return "combat_wait"
        if phase == "menu":
            return "menu"
        if phase == "terminal":
            return "terminal"
        return "unknown_window"

    @staticmethod
    def _is_non_combat_phase_kind(phase_kind: str) -> bool:
        return phase_kind in {
            "reward_choice",
            "card_reward_selection",
            "reward_advance",
            "map",
            "event_choice",
            "event_continue",
            "shop",
            "menu",
            "transition_wait",
            "unknown_window",
        }

    def _handle_reward_phase(
        self,
        *,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        step_index: int,
        current_turn_index: int,
        current_turn_actions: int,
        total_actions: int,
        turns_completed: int,
        trace_path: Path,
        session_id: str,
        transition_wait_since: float | None = None,
    ) -> dict[str, object]:
        step_index += 1
        reward_mode = self._normalized_reward_mode()
        phase_kind = self._phase_kind(
            snapshot,
            legal_actions,
            player_turn=False,
            pending_end_turn_transition=None,
            previous_phase="reward",
        )

        if reward_mode == "halt":
            policy_output = PolicyDecision(action_id=None, reason="reward phase reached; reward_mode=halt", halt=True)
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=policy_output,
                bridge_result={"status": "interrupted", "reason": "reward_phase_reached"},
                interrupted=True,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=True,
                stop_reason="reward_phase_reached",
                battle_stop_reason="reward_phase_reached",
                step_kind=phase_kind,
                phase_kind=phase_kind,
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=transition_wait_since,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason="reward_phase_reached",
                    completed=total_actions > 0,
                    interrupted=total_actions == 0,
                    turn_completed=turns_completed > 0,
                    battle_completed=True,
                    actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                )

        if not legal_actions:
            wait_stop_reason = "transition_timeout"
            wait_reason = "reward_transition_wait"
            wait_step_kind = "transition_wait"
            if phase_kind == "reward_advance":
                wait_stop_reason = "reward_advance_no_actions"
                wait_reason = "reward_advance_wait"
                wait_step_kind = "reward_advance_wait"
            outcome = self._handle_transition_wait(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index - 1,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                turns_completed=turns_completed,
                trace_path=trace_path,
                waiting_since=transition_wait_since,
                stop_reason=wait_stop_reason,
                wait_reason=wait_reason,
                step_kind=wait_step_kind,
                phase_kind=phase_kind,
            )
            return self._step_result(
                step_index=outcome["step_index"],
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0 if outcome["summary"] is None else 1,
                pending_end_turn_transition=None,
                transition_wait_since=outcome["waiting_since"],
                summary=outcome["summary"],
            )

        policy_output: PolicyDecision
        selected_action = self._select_reward_action(snapshot, legal_actions, reward_mode)
        if reward_mode in {"skip", "skip-only"} and selected_action is None:
            policy_output = PolicyDecision(action_id=None, reason=f"reward_mode={reward_mode} but skip_reward is unavailable", halt=True)
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=policy_output,
                bridge_result={"status": "interrupted", "reason": "skip_reward_unavailable"},
                interrupted=True,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=True,
                stop_reason="reward_skip_unavailable",
                battle_stop_reason="reward_skip_unavailable",
                step_kind=phase_kind,
                phase_kind=phase_kind,
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=transition_wait_since,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason="reward_skip_unavailable",
                    completed=False,
                    interrupted=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )
        if selected_action is not None and reward_mode != "llm":
            policy_output = PolicyDecision(
                action_id=selected_action.action_id,
                reason=f"reward_mode={reward_mode}: select {selected_action.type}",
                metadata={"reward_mode": reward_mode, "step_kind": phase_kind},
            )
        else:
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=self._thinking_policy_output(),
                status="thinking",
                step_index=step_index,
                current_turn_index=current_turn_index,
            )
            policy_output = self._decide(snapshot, legal_actions)
            if policy_output.halt or not policy_output.action_id:
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=policy_output,
                    bridge_result={"status": "interrupted", "reason": "policy_halt"},
                    interrupted=True,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=True,
                    stop_reason="policy_halt",
                    battle_stop_reason="policy_halt",
                    step_kind=phase_kind,
                    phase_kind=phase_kind,
                )
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=0,
                    consecutive_failures=0,
                    pending_end_turn_transition=None,
                    transition_wait_since=transition_wait_since,
                    summary=self._finish(
                        session_id=session_id,
                        trace_path=trace_path,
                        reason="policy_halt",
                        completed=False,
                        interrupted=True,
                        actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                )

            legal_actions_by_id = {action.action_id: action for action in legal_actions}
            if policy_output.action_id not in legal_actions_by_id:
                return self._finalize_failure(
                    exc=InvalidPayloadError("policy returned an action outside the legal action set"),
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    current_turn_actions=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    stale_action_attempts=0,
                    consecutive_failures=1,
                    trace_path=trace_path,
                    session_id=session_id,
                    step_kind=phase_kind,
                    phase_kind=phase_kind,
                )
            selected_action = legal_actions_by_id[policy_output.action_id]

        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=policy_output,
            status="planned",
            step_index=step_index,
            current_turn_index=current_turn_index,
            action_label=selected_action.label,
        )

        if self.config.dry_run:
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=policy_output,
                bridge_result={
                    "status": "dry_run",
                    "planned_action_id": policy_output.action_id,
                    "message": "dry run enabled; bridge submission skipped",
                },
                interrupted=False,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=True,
                stop_reason="dry_run",
                battle_stop_reason="dry_run",
                step_kind=phase_kind,
                phase_kind=phase_kind,
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=transition_wait_since,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason="dry_run",
                    completed=False,
                    interrupted=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        try:
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=policy_output,
                status="submitted",
                step_index=step_index,
                current_turn_index=current_turn_index,
                action_label=selected_action.label,
            )
            result = self.bridge.submit_action(
                ActionSubmission(
                    session_id=snapshot.session_id,
                    decision_id=snapshot.decision_id,
                    state_version=snapshot.state_version,
                    action_id=selected_action.action_id,
                    args=self._build_action_args(selected_action, policy_output),
                )
            )
        except (InvalidPayloadError, InterruptedSessionError, BridgeError) as exc:
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=policy_output,
                status="rejected",
                step_index=step_index,
                current_turn_index=current_turn_index,
                action_label=selected_action.label,
            )
            return self._finalize_failure(
                exc=exc,
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                turns_completed=turns_completed,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=1,
                trace_path=trace_path,
                session_id=session_id,
                step_kind=phase_kind,
                phase_kind=phase_kind,
            )

        total_actions += 1
        self._reward_actions_taken += 1
        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=policy_output,
            status=str(result.status),
            step_index=step_index,
            current_turn_index=current_turn_index,
            action_label=selected_action.label,
        )
        reward_stop_reason = "reward_action_submitted"
        if selected_action.type == "skip_reward":
            reward_stop_reason = "reward_skipped"
        elif selected_action.type == "choose_reward":
            reward_stop_reason = "reward_chosen"

        self._record(
            recorder=recorder,
            snapshot=snapshot,
            legal_actions=legal_actions,
            policy_output=policy_output,
            bridge_result=to_dict(result),
            interrupted=False,
            step_index=step_index,
            current_turn_index=current_turn_index,
            actions_this_turn=current_turn_actions,
            total_actions=total_actions,
            waiting_for_player_turn=False,
            is_final_step=False,
            stop_reason="",
            battle_stop_reason="",
            step_kind=phase_kind,
            phase_kind=phase_kind,
        )

        # For reward transitions, give the game some time to process animations
        # especially for skip_reward or reward_advance scenarios.
        if str(result.status) == "accepted":
            time.sleep(1.0)
        new_transition_wait_since: float | None = time.time() if str(result.status) == "accepted" else transition_wait_since

        return self._step_result(
            step_index=step_index,
            current_turn_actions=current_turn_actions,
            total_actions=total_actions,
            stale_action_attempts=0,
            consecutive_failures=0,
            pending_end_turn_transition=None,
            transition_wait_since=new_transition_wait_since,
            summary=None,
        )

    def _handle_map_phase(
        self,
        *,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        step_index: int,
        current_turn_index: int,
        current_turn_actions: int,
        total_actions: int,
        turns_completed: int,
        trace_path: Path,
        session_id: str,
        transition_wait_since: float | None,
    ) -> dict[str, object]:
        step_index += 1
        map_mode = self._normalized_map_mode()
        phase_kind = "map"

        if map_mode == "halt":
            policy_output = PolicyDecision(action_id=None, reason="map phase reached; map_mode=halt", halt=True)
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=policy_output,
                bridge_result={"status": "interrupted", "reason": "map_phase_reached"},
                interrupted=True,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=True,
                stop_reason="map_phase_reached",
                battle_stop_reason="map_phase_reached",
                step_kind=phase_kind,
                phase_kind=phase_kind,
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=transition_wait_since,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason="map_phase_reached",
                    completed=total_actions > 0,
                    interrupted=total_actions == 0,
                    turn_completed=turns_completed > 0,
                    battle_completed=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        if not legal_actions:
            outcome = self._handle_transition_wait(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index - 1,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                turns_completed=turns_completed,
                trace_path=trace_path,
                waiting_since=transition_wait_since,
                stop_reason="transition_timeout",
                wait_reason="map_transition_wait",
                step_kind="transition_wait",
                phase_kind="transition_wait",
            )
            return self._step_result(
                step_index=outcome["step_index"],
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0 if outcome["summary"] is None else 1,
                pending_end_turn_transition=None,
                transition_wait_since=outcome["waiting_since"],
                summary=outcome["summary"],
            )

        selected_action = self._select_map_action(legal_actions, map_mode)
        if selected_action is not None and map_mode != "llm":
            policy_output = PolicyDecision(
                action_id=selected_action.action_id,
                reason=f"map_mode={map_mode}: select {selected_action.type}",
                metadata={"map_mode": map_mode, "step_kind": phase_kind},
            )
        else:
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=self._thinking_policy_output(),
                status="thinking",
                step_index=step_index,
                current_turn_index=current_turn_index,
            )
            policy_output = self._decide(snapshot, legal_actions)
            if policy_output.halt or not policy_output.action_id:
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=policy_output,
                    bridge_result={"status": "interrupted", "reason": "policy_halt"},
                    interrupted=True,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=True,
                    stop_reason="policy_halt",
                    battle_stop_reason="policy_halt",
                    step_kind=phase_kind,
                    phase_kind=phase_kind,
                )
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=0,
                    consecutive_failures=0,
                    pending_end_turn_transition=None,
                    transition_wait_since=transition_wait_since,
                    summary=self._finish(
                        session_id=session_id,
                        trace_path=trace_path,
                        reason="policy_halt",
                        completed=False,
                        interrupted=True,
                        actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                )

            legal_actions_by_id = {action.action_id: action for action in legal_actions}
            if policy_output.action_id not in legal_actions_by_id:
                return self._finalize_failure(
                    exc=InvalidPayloadError("policy returned an action outside the legal action set"),
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    current_turn_actions=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    stale_action_attempts=0,
                    consecutive_failures=1,
                    trace_path=trace_path,
                    session_id=session_id,
                    step_kind=phase_kind,
                    phase_kind=phase_kind,
                )
            selected_action = legal_actions_by_id[policy_output.action_id]

        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=policy_output,
            status="planned",
            step_index=step_index,
            current_turn_index=current_turn_index,
            action_label=selected_action.label,
        )

        if self.config.dry_run:
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=policy_output,
                bridge_result={
                    "status": "dry_run",
                    "planned_action_id": policy_output.action_id,
                    "message": "dry run enabled; bridge submission skipped",
                },
                interrupted=False,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=True,
                stop_reason="dry_run",
                battle_stop_reason="dry_run",
                step_kind=phase_kind,
                phase_kind=phase_kind,
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=transition_wait_since,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason="dry_run",
                    completed=False,
                    interrupted=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        try:
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=policy_output,
                status="submitted",
                step_index=step_index,
                current_turn_index=current_turn_index,
                action_label=selected_action.label,
            )
            result = self.bridge.submit_action(
                ActionSubmission(
                    session_id=snapshot.session_id,
                    decision_id=snapshot.decision_id,
                    state_version=snapshot.state_version,
                    action_id=selected_action.action_id,
                    args=self._build_action_args(selected_action, policy_output),
                )
            )
        except (InvalidPayloadError, InterruptedSessionError, BridgeError) as exc:
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=policy_output,
                status="rejected",
                step_index=step_index,
                current_turn_index=current_turn_index,
                action_label=selected_action.label,
            )
            return self._finalize_failure(
                exc=exc,
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                turns_completed=turns_completed,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=1,
                trace_path=trace_path,
                session_id=session_id,
                step_kind=phase_kind,
                phase_kind=phase_kind,
            )

        total_actions += 1
        self._map_actions_taken += 1
        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=policy_output,
            status=str(result.status),
            step_index=step_index,
            current_turn_index=current_turn_index,
            action_label=selected_action.label,
        )
        self._record(
            recorder=recorder,
            snapshot=snapshot,
            legal_actions=legal_actions,
            policy_output=policy_output,
            bridge_result=to_dict(result),
            interrupted=False,
            step_index=step_index,
            current_turn_index=current_turn_index,
            actions_this_turn=current_turn_actions,
            total_actions=total_actions,
            waiting_for_player_turn=False,
            is_final_step=False,
            stop_reason="",
            battle_stop_reason="",
            step_kind=phase_kind,
            phase_kind=phase_kind,
        )

        # For map transitions, give the game some time to start the animation
        # instead of immediately re-polling and re-deciding.
        # Wait at least poll_interval_seconds + 1s so the map scene has time to settle.
        if str(result.status) == "accepted":
            time.sleep(self.config.poll_interval_seconds + 1.0)
        new_transition_wait_since: float | None = time.time() if str(result.status) == "accepted" else transition_wait_since

        return self._step_result(
            step_index=step_index,
            current_turn_actions=current_turn_actions,
            total_actions=total_actions,
            stale_action_attempts=0,
            consecutive_failures=0,
            pending_end_turn_transition=None,
            transition_wait_since=new_transition_wait_since,
            summary=None,
        )

    def _handle_shop_phase(
        self,
        *,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        step_index: int,
        current_turn_index: int,
        current_turn_actions: int,
        total_actions: int,
        turns_completed: int,
        trace_path: Path,
        session_id: str,
        transition_wait_since: float | None,
    ) -> dict[str, object]:
        step_index += 1
        shop_mode = self._normalized_shop_mode()
        phase_kind = "shop"

        if shop_mode == "halt":
            policy_output = PolicyDecision(action_id=None, reason="shop phase reached; shop_mode=halt", halt=True)
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=policy_output,
                bridge_result={"status": "interrupted", "reason": "shop_phase_reached"},
                interrupted=True,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=True,
                stop_reason="shop_phase_reached",
                battle_stop_reason="shop_phase_reached",
                step_kind=phase_kind,
                phase_kind=phase_kind,
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=transition_wait_since,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason="shop_phase_reached",
                    completed=total_actions > 0,
                    interrupted=total_actions == 0,
                    turn_completed=turns_completed > 0,
                    battle_completed=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        if not legal_actions:
            outcome = self._handle_transition_wait(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index - 1,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                turns_completed=turns_completed,
                trace_path=trace_path,
                waiting_since=transition_wait_since,
                stop_reason="transition_timeout",
                wait_reason="shop_transition_wait",
                step_kind="transition_wait",
                phase_kind="transition_wait",
            )
            return self._step_result(
                step_index=outcome["step_index"],
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0 if outcome["summary"] is None else 1,
                pending_end_turn_transition=None,
                transition_wait_since=outcome["waiting_since"],
                summary=outcome["summary"],
            )

        selected_action = self._select_shop_action(snapshot, legal_actions, shop_mode)
        if selected_action is not None and shop_mode != "llm":
            policy_output = PolicyDecision(
                action_id=selected_action.action_id,
                reason=f"shop_mode={shop_mode}: select {selected_action.type}",
                metadata={"shop_mode": shop_mode, "step_kind": phase_kind},
            )
        else:
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=self._thinking_policy_output(),
                status="thinking",
                step_index=step_index,
                current_turn_index=current_turn_index,
            )
            policy_output = self._decide(snapshot, legal_actions)
            if policy_output.halt or not policy_output.action_id:
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=policy_output,
                    bridge_result={"status": "interrupted", "reason": "policy_halt"},
                    interrupted=True,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=True,
                    stop_reason="policy_halt",
                    battle_stop_reason="policy_halt",
                    step_kind=phase_kind,
                    phase_kind=phase_kind,
                )
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=0,
                    consecutive_failures=0,
                    pending_end_turn_transition=None,
                    transition_wait_since=transition_wait_since,
                    summary=self._finish(
                        session_id=session_id,
                        trace_path=trace_path,
                        reason="policy_halt",
                        completed=False,
                        interrupted=True,
                        actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                )

            legal_actions_by_id = {action.action_id: action for action in legal_actions}
            if policy_output.action_id not in legal_actions_by_id:
                return self._finalize_failure(
                    exc=InvalidPayloadError("policy returned an action outside the legal action set"),
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    current_turn_actions=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    stale_action_attempts=0,
                    consecutive_failures=1,
                    trace_path=trace_path,
                    session_id=session_id,
                    step_kind=phase_kind,
                    phase_kind=phase_kind,
                )
            selected_action = legal_actions_by_id[policy_output.action_id]

        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=policy_output,
            status="planned",
            step_index=step_index,
            current_turn_index=current_turn_index,
            action_label=selected_action.label,
        )

        if self.config.dry_run:
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=policy_output,
                bridge_result={
                    "status": "dry_run",
                    "planned_action_id": policy_output.action_id,
                    "message": "dry run enabled; bridge submission skipped",
                },
                interrupted=False,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=True,
                stop_reason="dry_run",
                battle_stop_reason="dry_run",
                step_kind=phase_kind,
                phase_kind=phase_kind,
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=transition_wait_since,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason="dry_run",
                    completed=False,
                    interrupted=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        try:
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=policy_output,
                status="submitted",
                step_index=step_index,
                current_turn_index=current_turn_index,
                action_label=selected_action.label,
            )
            result = self.bridge.submit_action(
                ActionSubmission(
                    session_id=snapshot.session_id,
                    decision_id=snapshot.decision_id,
                    state_version=snapshot.state_version,
                    action_id=selected_action.action_id,
                    args=self._build_action_args(selected_action, policy_output),
                )
            )
        except (InvalidPayloadError, InterruptedSessionError, BridgeError) as exc:
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=policy_output,
                status="rejected",
                step_index=step_index,
                current_turn_index=current_turn_index,
                action_label=selected_action.label,
            )
            return self._finalize_failure(
                exc=exc,
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                turns_completed=turns_completed,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=1,
                trace_path=trace_path,
                session_id=session_id,
                step_kind=phase_kind,
                phase_kind=phase_kind,
            )

        total_actions += 1
        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=policy_output,
            status=str(result.status),
            step_index=step_index,
            current_turn_index=current_turn_index,
            action_label=selected_action.label,
        )
        self._record(
            recorder=recorder,
            snapshot=snapshot,
            legal_actions=legal_actions,
            policy_output=policy_output,
            bridge_result=to_dict(result),
            interrupted=False,
            step_index=step_index,
            current_turn_index=current_turn_index,
            actions_this_turn=current_turn_actions,
            total_actions=total_actions,
            waiting_for_player_turn=False,
            is_final_step=False,
            stop_reason="",
            battle_stop_reason="",
            step_kind=phase_kind,
            phase_kind=phase_kind,
        )
        return self._step_result(
            step_index=step_index,
            current_turn_actions=current_turn_actions,
            total_actions=total_actions,
            stale_action_attempts=0,
            consecutive_failures=0,
            pending_end_turn_transition=None,
            transition_wait_since=None,
            summary=None,
        )

    def _handle_event_phase(
        self,
        *,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        step_index: int,
        current_turn_index: int,
        current_turn_actions: int,
        total_actions: int,
        turns_completed: int,
        trace_path: Path,
        session_id: str,
        transition_wait_since: float | None,
    ) -> dict[str, object]:
        step_index += 1
        event_mode = self._normalized_event_mode()
        phase_kind = self._phase_kind(
            snapshot,
            legal_actions,
            player_turn=False,
            pending_end_turn_transition=None,
            previous_phase="event",
        )

        if event_mode == "halt":
            policy_output = PolicyDecision(action_id=None, reason="event phase reached; event_mode=halt", halt=True)
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=policy_output,
                bridge_result={"status": "interrupted", "reason": "event_phase_reached"},
                interrupted=True,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=True,
                stop_reason="event_phase_reached",
                battle_stop_reason="event_phase_reached",
                step_kind=phase_kind,
                phase_kind=phase_kind,
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=transition_wait_since,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason="event_phase_reached",
                    completed=total_actions > 0,
                    interrupted=total_actions == 0,
                    turn_completed=turns_completed > 0,
                    battle_completed=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        if not legal_actions:
            outcome = self._handle_transition_wait(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index - 1,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                turns_completed=turns_completed,
                trace_path=trace_path,
                waiting_since=transition_wait_since,
                stop_reason="transition_timeout",
                wait_reason="event_transition_wait",
                step_kind="transition_wait",
                phase_kind="transition_wait",
            )
            return self._step_result(
                step_index=outcome["step_index"],
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0 if outcome["summary"] is None else 1,
                pending_end_turn_transition=None,
                transition_wait_since=outcome["waiting_since"],
                summary=outcome["summary"],
            )

        selected_action = self._select_event_action(snapshot, legal_actions, event_mode)
        if selected_action is not None and event_mode != "llm":
            policy_output = PolicyDecision(
                action_id=selected_action.action_id,
                reason=f"event_mode={event_mode}: select {selected_action.type}",
                metadata={"event_mode": event_mode, "step_kind": phase_kind},
            )
        else:
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=self._thinking_policy_output(),
                status="thinking",
                step_index=step_index,
                current_turn_index=current_turn_index,
            )
            policy_output = self._decide(snapshot, legal_actions)
            if policy_output.halt or not policy_output.action_id:
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=policy_output,
                    bridge_result={"status": "interrupted", "reason": "policy_halt"},
                    interrupted=True,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=True,
                    stop_reason="policy_halt",
                    battle_stop_reason="policy_halt",
                    step_kind=phase_kind,
                    phase_kind=phase_kind,
                )
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=0,
                    consecutive_failures=0,
                    pending_end_turn_transition=None,
                    transition_wait_since=transition_wait_since,
                    summary=self._finish(
                        session_id=session_id,
                        trace_path=trace_path,
                        reason="policy_halt",
                        completed=False,
                        interrupted=True,
                        actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                )

            legal_actions_by_id = {action.action_id: action for action in legal_actions}
            if policy_output.action_id not in legal_actions_by_id:
                return self._finalize_failure(
                    exc=InvalidPayloadError("policy returned an action outside the legal action set"),
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    current_turn_actions=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    stale_action_attempts=0,
                    consecutive_failures=1,
                    trace_path=trace_path,
                    session_id=session_id,
                    step_kind=phase_kind,
                    phase_kind=phase_kind,
                )
            selected_action = legal_actions_by_id[policy_output.action_id]

        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=policy_output,
            status="planned",
            step_index=step_index,
            current_turn_index=current_turn_index,
            action_label=selected_action.label,
        )

        if self.config.dry_run:
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=policy_output,
                bridge_result={
                    "status": "dry_run",
                    "planned_action_id": policy_output.action_id,
                    "message": "dry run enabled; bridge submission skipped",
                },
                interrupted=False,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=True,
                stop_reason="dry_run",
                battle_stop_reason="dry_run",
                step_kind=phase_kind,
                phase_kind=phase_kind,
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=transition_wait_since,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason="dry_run",
                    completed=False,
                    interrupted=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        try:
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=policy_output,
                status="submitted",
                step_index=step_index,
                current_turn_index=current_turn_index,
                action_label=selected_action.label,
            )
            result = self.bridge.submit_action(
                ActionSubmission(
                    session_id=snapshot.session_id,
                    decision_id=snapshot.decision_id,
                    state_version=snapshot.state_version,
                    action_id=selected_action.action_id,
                    args=self._build_action_args(selected_action, policy_output),
                )
            )
        except (InvalidPayloadError, InterruptedSessionError, BridgeError) as exc:
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=policy_output,
                status="rejected",
                step_index=step_index,
                current_turn_index=current_turn_index,
                action_label=selected_action.label,
            )
            return self._finalize_failure(
                exc=exc,
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                turns_completed=turns_completed,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=1,
                trace_path=trace_path,
                session_id=session_id,
                step_kind=phase_kind,
                phase_kind=phase_kind,
            )

        total_actions += 1
        self._note_same_window_action(snapshot, selected_action, result)
        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=policy_output,
            status=str(result.status),
            step_index=step_index,
            current_turn_index=current_turn_index,
            action_label=selected_action.label,
        )
        self._record(
            recorder=recorder,
            snapshot=snapshot,
            legal_actions=legal_actions,
            policy_output=policy_output,
            bridge_result=to_dict(result),
            interrupted=False,
            step_index=step_index,
            current_turn_index=current_turn_index,
            actions_this_turn=current_turn_actions,
            total_actions=total_actions,
            waiting_for_player_turn=False,
            is_final_step=False,
            stop_reason="",
            battle_stop_reason="",
            step_kind=phase_kind,
            phase_kind=phase_kind,
        )
        return self._step_result(
            step_index=step_index,
            current_turn_actions=current_turn_actions,
            total_actions=total_actions,
            stale_action_attempts=0,
            consecutive_failures=0,
            pending_end_turn_transition=None,
            transition_wait_since=None,
            summary=None,
        )

    def _handle_menu_phase(
        self,
        *,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        step_index: int,
        current_turn_index: int,
        current_turn_actions: int,
        total_actions: int,
        turns_completed: int,
        trace_path: Path,
        session_id: str,
        transition_wait_since: float | None = None,
    ) -> dict[str, Any]:
        menu_mode = self._normalized_menu_mode()
        phase_kind = "menu"

        if menu_mode == "halt":
            step_index += 1
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=PolicyDecision(action_id=None, reason="menu_mode=halt", halt=True),
                bridge_result={"status": "completed", "reason": "menu_halt"},
                interrupted=False,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=True,
                stop_reason="menu_halt",
                battle_stop_reason="menu_halt",
                step_kind="menu_halt",
                phase_kind=phase_kind,
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason="menu_halt",
                    completed=False,
                    interrupted=True,
                    turn_completed=turns_completed > 0,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        if not legal_actions:
            wait_reason = "waiting for menu actions"
            window_kind = snapshot.metadata.get("window_kind")
            
            # 增加更详细的诊断信息到等待原因中
            diagnostics = []
            if window_kind:
                diagnostics.append(f"window_kind: {window_kind}")
            
            # 检查是否有被抑制的动作原因
            suppressed_reason = snapshot.metadata.get("menu_action_suppressed_reason")
            if suppressed_reason:
                diagnostics.append(f"suppressed: {suppressed_reason}")
                
            # 记录发现的候选按钮数量
            candidate_count = snapshot.metadata.get("menu_button_candidate_count")
            if candidate_count is not None:
                diagnostics.append(f"candidates: {candidate_count}")

            if diagnostics:
                wait_reason = f"waiting for menu actions ({', '.join(diagnostics)})"
            
            # 菜单加载可能较慢，允许更长的等待时间
            menu_wait_timeout = max(self.config.wait_for_next_player_turn_seconds, 30.0)

            return self._handle_transition_wait(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                turns_completed=turns_completed,
                trace_path=trace_path,
                waiting_since=transition_wait_since,
                stop_reason="menu_transition_timeout",
                wait_reason=wait_reason,
                step_kind="menu_transition",
                phase_kind=phase_kind,
                timeout_seconds=menu_wait_timeout,
            )

        # 优先继续游戏，否则开始新游戏
        action = next((a for a in legal_actions if a.type == ActionType.CONTINUE_RUN), None)
        if not action:
            action = next((a for a in legal_actions if a.type == ActionType.START_NEW_RUN), None)
        if not action:
            action = next((a for a in legal_actions if a.type == ActionType.CONFIRM_NEW_RUN), None)

        if not action:
            # 记录所有可用的动作类型，方便调试
            available_types = [a.type for a in legal_actions]
            policy_reason = f"no supported menu action (available: {available_types})"
            step_index += 1
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=PolicyDecision(action_id=None, reason=policy_reason, halt=True),
                bridge_result={"status": "completed", "reason": "no_supported_menu_action"},
                interrupted=False,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=True,
                stop_reason="no_supported_menu_action",
                battle_stop_reason="no_supported_menu_action",
                step_kind="menu_halt",
                phase_kind=phase_kind,
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason="no_supported_menu_action",
                    completed=False,
                    interrupted=True,
                    turn_completed=turns_completed > 0,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        step_index += 1
        policy_output = PolicyDecision(action_id=action.action_id, reason=f"auto menu action: {action.type}")
        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=policy_output,
            status="applying",
            step_index=step_index,
            current_turn_index=current_turn_index,
            action_label=action.label,
        )

        try:
            result = self.bridge.submit_action(
                ActionSubmission(
                    session_id=session_id,
                    decision_id=snapshot.decision_id,
                    state_version=snapshot.state_version,
                    action_id=action.action_id,
                    args={},
                )
            )
        except Exception as e:
            return self._finalize_failure(
                exc=e,
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                turns_completed=turns_completed,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=1,
                trace_path=trace_path,
                session_id=session_id,
                step_kind="menu_action",
                phase_kind=phase_kind,
            )

        self._record(
            recorder=recorder,
            snapshot=snapshot,
            legal_actions=legal_actions,
            policy_output=policy_output,
            bridge_result=to_dict(result),
            interrupted=False,
            step_index=step_index,
            current_turn_index=current_turn_index,
            actions_this_turn=current_turn_actions,
            total_actions=total_actions,
            waiting_for_player_turn=False,
            is_final_step=False,
            stop_reason="",
            battle_stop_reason="",
            step_kind="menu_action",
            phase_kind=phase_kind,
        )

        if result.status == "accepted":
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions + 1,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=time.monotonic(),
                summary=None,
            )
        else:
            return self._finalize_failure(
                exc=RuntimeError(f"Menu action rejected: {result.error_code} {result.message}"),
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                turns_completed=turns_completed,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=1,
                trace_path=trace_path,
                session_id=session_id,
                step_kind="menu_action",
                phase_kind=phase_kind,
            )

    def _handle_transition_wait(
        self,
        *,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        step_index: int,
        current_turn_index: int,
        current_turn_actions: int,
        total_actions: int,
        turns_completed: int,
        trace_path: Path,
        waiting_since: float | None,
        stop_reason: str,
        wait_reason: str,
        step_kind: str,
        phase_kind: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        step_index += 1
        if waiting_since is None:
            waiting_since = time.monotonic()
            self._transition_attempt += 1
            self._note_recovery_attempt(wait_reason)
        elapsed = time.monotonic() - waiting_since
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.config.transition_timeout_seconds
        if elapsed > effective_timeout:
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=PolicyDecision(action_id=None, reason=wait_reason, halt=True),
                bridge_result={"status": "waiting", "reason": stop_reason, "elapsed_seconds": elapsed},
                interrupted=True,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=True,
                stop_reason=stop_reason,
                battle_stop_reason=stop_reason,
                step_kind=step_kind,
                phase_kind=phase_kind,
                transition_elapsed_seconds=elapsed,
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=waiting_since,
                summary=self._finish(
                    session_id=snapshot.session_id,
                    trace_path=trace_path,
                    reason=stop_reason,
                    completed=False,
                    interrupted=True,
                    turn_completed=turns_completed > 0,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        self._record(
            recorder=recorder,
            snapshot=snapshot,
            legal_actions=legal_actions,
            policy_output=PolicyDecision(action_id=None, reason=wait_reason, halt=True),
            bridge_result={"status": "waiting", "reason": wait_reason, "elapsed_seconds": elapsed},
            interrupted=False,
            step_index=step_index,
            current_turn_index=current_turn_index,
            actions_this_turn=current_turn_actions,
            total_actions=total_actions,
            waiting_for_player_turn=False,
            is_final_step=False,
            stop_reason="",
            battle_stop_reason="",
            step_kind=step_kind,
            phase_kind=phase_kind,
            transition_elapsed_seconds=elapsed,
        )
        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=PolicyDecision(action_id=None, reason=wait_reason),
            status="waiting",
            step_index=step_index,
            current_turn_index=current_turn_index,
        )
        time.sleep(self.config.poll_interval_seconds)
        return self._step_result(
            step_index=step_index,
            current_turn_actions=current_turn_actions,
            total_actions=total_actions,
            stale_action_attempts=0,
            consecutive_failures=0,
            pending_end_turn_transition=None,
            transition_wait_since=waiting_since,
            summary=None,
        )

    def _handle_non_player_turn(
        self,
        *,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        step_index: int,
        current_turn_index: int,
        current_turn_actions: int,
        total_actions: int,
        turns_completed: int,
        trace_path: Path,
        waiting_since: float | None,
    ) -> dict[str, object]:
        if self.config.stop_after_player_turn:
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=waiting_since,
                summary=self._finish(
                    session_id=snapshot.session_id,
                    trace_path=trace_path,
                    reason="phase_changed",
                    completed=total_actions > 0,
                    interrupted=total_actions == 0,
                    turn_completed=total_actions > 0,
                    battle_completed=False,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        step_index += 1
        if waiting_since is None:
            waiting_since = time.monotonic()
            self._note_recovery_attempt("enemy_turn_wait")
        if time.monotonic() - waiting_since > self.config.wait_for_next_player_turn_seconds:
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=PolicyDecision(action_id=None, reason="waiting for next player turn", halt=True),
                bridge_result={"status": "waiting", "reason": "next_player_turn_timeout"},
                interrupted=True,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=True,
                is_final_step=True,
                stop_reason="next_player_turn_timeout",
                battle_stop_reason="next_player_turn_timeout",
                step_kind="enemy_turn_wait",
                phase_kind="combat_wait",
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=waiting_since,
                summary=self._finish(
                    session_id=snapshot.session_id,
                    trace_path=trace_path,
                    reason="next_player_turn_timeout",
                    completed=False,
                    interrupted=True,
                    turn_completed=turns_completed > 0,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        self._record(
            recorder=recorder,
            snapshot=snapshot,
            legal_actions=legal_actions,
            policy_output=PolicyDecision(action_id=None, reason="waiting for next player turn", halt=True),
            bridge_result={"status": "waiting", "reason": "enemy_turn_or_animation"},
            interrupted=False,
            step_index=step_index,
            current_turn_index=current_turn_index,
            actions_this_turn=current_turn_actions,
            total_actions=total_actions,
            waiting_for_player_turn=True,
            is_final_step=False,
            stop_reason="",
            battle_stop_reason="",
            step_kind="enemy_turn_wait",
            phase_kind="combat_wait",
        )
        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=PolicyDecision(action_id=None, reason="waiting for next player turn"),
            status="waiting",
            step_index=step_index,
            current_turn_index=current_turn_index,
        )
        if waiting_since is not None:
            # 增加对动画状态的缓冲等待
            elapsed = time.monotonic() - waiting_since
            if elapsed < 2.0:
                time.sleep(min(1.0, self.config.poll_interval_seconds * 2 if self.config.poll_interval_seconds > 0 else 1.0))
            else:
                time.sleep(self.config.poll_interval_seconds)
        else:
            time.sleep(self.config.poll_interval_seconds)
        return self._step_result(
            step_index=step_index,
            current_turn_actions=current_turn_actions,
            total_actions=total_actions,
            stale_action_attempts=0,
            consecutive_failures=0,
            pending_end_turn_transition=None,
            transition_wait_since=waiting_since,
            summary=None,
        )

    def _handle_pending_end_turn_transition(
        self,
        *,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        step_index: int,
        current_turn_index: int,
        current_turn_actions: int,
        total_actions: int,
        turns_completed: int,
        trace_path: Path,
        waiting_since: float | None,
    ) -> dict[str, object]:
        step_index += 1
        if waiting_since is None:
            waiting_since = time.monotonic()
            self._note_recovery_attempt("pending_end_turn_transition")
        if time.monotonic() - waiting_since > self.config.wait_for_next_player_turn_seconds:
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=PolicyDecision(action_id=None, reason="waiting for end_turn transition", halt=True),
                bridge_result={"status": "waiting", "reason": "next_player_turn_timeout"},
                interrupted=True,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=True,
                is_final_step=True,
                stop_reason="next_player_turn_timeout",
                battle_stop_reason="next_player_turn_timeout",
                step_kind="pending_end_turn_transition",
                phase_kind="pending_end_turn_transition",
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=0,
                consecutive_failures=0,
                pending_end_turn_transition=None,
                transition_wait_since=waiting_since,
                summary=self._finish(
                    session_id=snapshot.session_id,
                    trace_path=trace_path,
                    reason="next_player_turn_timeout",
                    completed=False,
                    interrupted=True,
                    turn_completed=turns_completed > 0,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        self._record(
            recorder=recorder,
            snapshot=snapshot,
            legal_actions=legal_actions,
            policy_output=PolicyDecision(action_id=None, reason="waiting for end_turn transition", halt=True),
            bridge_result={"status": "waiting", "reason": "pending_end_turn_transition"},
            interrupted=False,
            step_index=step_index,
            current_turn_index=current_turn_index,
            actions_this_turn=current_turn_actions,
            total_actions=total_actions,
            waiting_for_player_turn=True,
            is_final_step=False,
            stop_reason="",
            battle_stop_reason="",
            step_kind="pending_end_turn_transition",
            phase_kind="pending_end_turn_transition",
        )
        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=PolicyDecision(action_id=None, reason="waiting for end_turn transition"),
            status="waiting",
            step_index=step_index,
            current_turn_index=current_turn_index,
        )
        # Check if the state has changed. If not, wait.
        if waiting_since is not None:
             elapsed = time.monotonic() - waiting_since
             if elapsed < 2.0:
                 time.sleep(1.0)
             else:
                 time.sleep(self.config.poll_interval_seconds)
        else:
             time.sleep(self.config.poll_interval_seconds)
        return self._step_result(
            step_index=step_index,
            current_turn_actions=current_turn_actions,
            total_actions=total_actions,
            stale_action_attempts=0,
            consecutive_failures=0,
            pending_end_turn_transition=None,
            transition_wait_since=waiting_since,
            summary=None,
        )

    def _player_turn_preflight(
        self,
        *,
        session_id: str,
        trace_path: Path,
        legal_actions,
        current_turn_actions: int,
        current_turn_index: int,
        turns_completed: int,
        total_actions: int,
    ) -> RunSummary | None:
        if current_turn_actions >= self._max_actions_per_turn():
            return self._finish(
                session_id=session_id,
                trace_path=trace_path,
                reason="max_actions_per_turn",
                completed=False,
                interrupted=True,
                actions_this_turn=current_turn_actions,
                turns_completed=turns_completed,
                total_actions=total_actions,
                current_turn_index=current_turn_index,
            )
        if not legal_actions:
            return self._finish(
                session_id=session_id,
                trace_path=trace_path,
                reason="no_legal_actions",
                completed=total_actions > 0,
                interrupted=total_actions == 0,
                turn_completed=total_actions > 0,
                battle_completed=False,
                actions_this_turn=current_turn_actions,
                turns_completed=turns_completed,
                total_actions=total_actions,
                current_turn_index=current_turn_index,
            )
        return None

    def _handle_empty_player_actions(
        self,
        *,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        step_index: int,
        current_turn_index: int,
        current_turn_actions: int,
        total_actions: int,
        turns_completed: int,
        trace_path: Path,
        session_id: str,
        waiting_since: float | None,
    ) -> dict[str, object] | None:
        if legal_actions:
            return None
        if self.config.stop_after_player_turn:
            return None

        recovery_reason = "empty_player_actions"
        if waiting_since is None:
            waiting_since = time.monotonic()
            self._note_recovery_attempt(recovery_reason)
        elapsed = time.monotonic() - waiting_since
        if elapsed >= self.config.wait_for_next_player_turn_seconds:
            step_index += 1
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=PolicyDecision(action_id=None, reason="waiting for playable actions", halt=True),
                bridge_result={"status": "waiting", "reason": recovery_reason, "elapsed_seconds": elapsed},
                interrupted=True,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=True,
                is_final_step=True,
                stop_reason="no_legal_actions",
                battle_stop_reason="no_legal_actions",
                step_kind="empty_player_actions",
                phase_kind="empty_player_actions",
            )
            return {
                "step_index": step_index,
                "current_turn_actions": current_turn_actions,
                "total_actions": total_actions,
                "stale_action_attempts": 0,
                "consecutive_failures": 1,
                "pending_end_turn_transition": None,
                "waiting_since": waiting_since,
                "summary": self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason="no_legal_actions",
                    completed=total_actions > 0,
                    interrupted=total_actions == 0,
                    turn_completed=total_actions > 0,
                    battle_completed=False,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            }

        step_index += 1
        self._record(
            recorder=recorder,
            snapshot=snapshot,
            legal_actions=legal_actions,
            policy_output=PolicyDecision(action_id=None, reason="waiting for playable actions", halt=True),
            bridge_result={"status": "waiting", "reason": recovery_reason, "elapsed_seconds": elapsed},
            interrupted=False,
            step_index=step_index,
            current_turn_index=current_turn_index,
            actions_this_turn=current_turn_actions,
            total_actions=total_actions,
            waiting_for_player_turn=True,
            is_final_step=False,
            stop_reason="",
            battle_stop_reason="",
            step_kind="empty_player_actions",
            phase_kind="empty_player_actions",
        )
        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=PolicyDecision(action_id=None, reason=recovery_reason),
            status="waiting",
            step_index=step_index,
            current_turn_index=current_turn_index,
        )
        time.sleep(self.config.poll_interval_seconds)
        return {
            "step_index": step_index,
            "current_turn_actions": current_turn_actions,
            "total_actions": total_actions,
            "stale_action_attempts": 0,
            "consecutive_failures": 0,
            "pending_end_turn_transition": None,
            "waiting_since": waiting_since,
            "summary": None,
        }

    def _handle_auto_end_turn(
        self,
        *,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        step_index: int,
        current_turn_index: int,
        current_turn_actions: int,
        turns_completed: int,
        total_actions: int,
        trace_path: Path,
        stale_action_attempts: int,
        consecutive_failures: int,
        session_id: str,
    ) -> dict[str, object]:
        if not self._is_only_end_turn(legal_actions):
            return {
                "consumed": False,
                "summary": None,
                "step_index": step_index,
                "current_turn_actions": current_turn_actions,
                "total_actions": total_actions,
                "stale_action_attempts": stale_action_attempts,
                "consecutive_failures": consecutive_failures,
                "pending_end_turn_transition": None,
            }

        if self.config.auto_end_turn_when_only_end_turn and not self.config.dry_run:
            try:
                step_index += 1
                auto_end_turn = legal_actions[0]
                policy_output = PolicyDecision(
                    action_id=auto_end_turn.action_id,
                    reason="only end_turn remains; runner auto ends turn",
                    metadata={"auto_end_turn": True},
                )
                self._publish_agent_status(
                    snapshot=snapshot,
                    policy_output=policy_output,
                    status="planned",
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    action_label=auto_end_turn.label,
                )
                self._publish_agent_status(
                    snapshot=snapshot,
                    policy_output=policy_output,
                    status="submitted",
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    action_label=auto_end_turn.label,
                )
                gate = self._pre_submit_gate(snapshot=snapshot, legal_actions=legal_actions, selected_action=auto_end_turn)
                if not gate["allowed"]:
                    raw_code = str(gate["raw_code"])
                    category = str(gate["category"])
                    gate_context = dict(gate.get("context") or {})
                    message = str(gate["message"])
                    if category == "recoverable_stale":
                        stale_action_attempts += 1
                        retrying = stale_action_attempts <= self.config.stale_action_retries
                    else:
                        stale_action_attempts = 0
                        retrying = True
                    consecutive_failures += 1
                    self._note_reject(
                        category=category,
                        raw_code=raw_code,
                        snapshot=snapshot,
                        selected_action=auto_end_turn,
                        step_index=step_index,
                        message=message,
                        gate_intercepted=True,
                        context=gate_context,
                    )
                    self._note_recovery_attempt(raw_code)
                    budget_stop_reason = self._battle_budget_stop_reason(
                        total_actions=total_actions,
                        turns_completed=turns_completed,
                        current_turn_index=current_turn_index,
                        consecutive_failures=consecutive_failures,
                    )
                    retrying = retrying and not budget_stop_reason
                    if retrying:
                        self._gate_redecisions += 1
                    self._publish_agent_status(
                        snapshot=snapshot,
                        policy_output=policy_output,
                        status="rejected",
                        step_index=step_index,
                        current_turn_index=current_turn_index,
                        action_label=auto_end_turn.label,
                    )
                    self._record(
                        recorder=recorder,
                        snapshot=snapshot,
                        legal_actions=legal_actions,
                        policy_output=policy_output,
                        bridge_result={
                            "status": "interrupted",
                            "error_code": raw_code,
                            "reject_category": category,
                            "message": message,
                            "retrying": retrying,
                            "consecutive_failures": consecutive_failures,
                            "gate_status": "intercepted",
                            "gate_reason": raw_code,
                            "gate_context": gate_context,
                        },
                        interrupted=not retrying,
                        step_index=step_index,
                        current_turn_index=current_turn_index,
                        actions_this_turn=current_turn_actions,
                        total_actions=total_actions,
                        waiting_for_player_turn=False,
                        is_final_step=not retrying,
                        stop_reason=budget_stop_reason if budget_stop_reason else self._reject_stop_reason(category, raw_code, retrying),
                        battle_stop_reason="" if retrying else (budget_stop_reason or self._reject_stop_reason(category, raw_code, False)),
                        reject_category=category,
                        reject_raw_code=raw_code,
                        gate_status="intercepted",
                        gate_reason=raw_code,
                    )
                    return {
                        "consumed": retrying,
                        "step_index": step_index,
                        "current_turn_actions": current_turn_actions,
                        "total_actions": total_actions,
                        "stale_action_attempts": stale_action_attempts,
                        "consecutive_failures": consecutive_failures,
                        "pending_end_turn_transition": None,
                        "summary": None if retrying else self._finish(
                            session_id=session_id,
                            trace_path=trace_path,
                            reason=budget_stop_reason or raw_code,
                            completed=False,
                            interrupted=True,
                            actions_this_turn=current_turn_actions,
                            turns_completed=turns_completed,
                            total_actions=total_actions,
                            current_turn_index=current_turn_index,
                        ),
                    }

                snapshot = gate["snapshot"]
                legal_actions = gate["legal_actions"]
                auto_end_turn = gate["selected_action"]
                gate_status = str(gate.get("gate_status") or "passed")
                gate_reason = str(gate.get("gate_reason") or "")
                if gate_status == "rebased":
                    self._gate_rebases += 1
                result = self.bridge.submit_action(
                    ActionSubmission(
                        session_id=snapshot.session_id,
                        decision_id=snapshot.decision_id,
                        state_version=snapshot.state_version,
                        action_id=auto_end_turn.action_id,
                        args=self._build_action_args(auto_end_turn),
                    )
                )
                # For end_turn transitions, give the game some time to start the animation
                if str(result.status) == "accepted":
                    time.sleep(2.0)
                result_payload = to_dict(result)
                result_payload["submitted_action_id"] = auto_end_turn.action_id
                result_payload["submitted_action_type"] = auto_end_turn.type
                result_payload["submitted_action_label"] = auto_end_turn.label
                total_actions += 1
                current_turn_actions += 1
                stale_action_attempts = 0
                consecutive_failures = 0
                self._publish_agent_status(
                    snapshot=snapshot,
                    policy_output=policy_output,
                    status=str(result.status),
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    action_label=auto_end_turn.label,
                )
                stop_reason = "auto_end_turn" if self.config.stop_after_player_turn else ""
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=policy_output,
                    bridge_result=result_payload,
                    interrupted=False,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=bool(stop_reason),
                    stop_reason=stop_reason,
                    battle_stop_reason=stop_reason,
                    gate_status=gate_status,
                    gate_reason=gate_reason,
                )
                self._mark_recovery_resolved()
            except StaleActionError as exc:
                raw_code = getattr(exc, "error_code", "stale_action")
                category = self._classify_reject_category(raw_code)
                if category == "recoverable_stale":
                    stale_action_attempts += 1
                    retrying = stale_action_attempts <= self.config.stale_action_retries
                else:
                    stale_action_attempts = 0
                    retrying = self._is_recoverable_reject_category(category)
                consecutive_failures += 1
                fallback_output = PolicyDecision(
                    action_id=legal_actions[0].action_id,
                    reason="only end_turn remains; runner auto ends turn",
                    metadata={"auto_end_turn": True},
                )
                self._note_reject(
                    category=category,
                    raw_code=raw_code,
                    snapshot=snapshot,
                    selected_action=legal_actions[0],
                    step_index=step_index,
                    message=str(exc),
                )
                self._publish_agent_status(
                    snapshot=snapshot,
                    policy_output=fallback_output,
                    status="rejected",
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    action_label=legal_actions[0].label,
                )
                if self._is_recoverable_reject_category(category):
                    self._note_recovery_attempt(raw_code)
                budget_stop_reason = self._battle_budget_stop_reason(
                    total_actions=total_actions,
                    turns_completed=turns_completed,
                    current_turn_index=current_turn_index,
                    consecutive_failures=consecutive_failures,
                )
                retrying = retrying and not budget_stop_reason
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=fallback_output,
                    bridge_result={
                        "status": "interrupted",
                        "error_code": raw_code,
                        "reject_category": category,
                        "message": str(exc),
                        "retrying": retrying,
                        "stale_action_attempts": stale_action_attempts,
                        "consecutive_failures": consecutive_failures,
                    },
                    interrupted=not retrying,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=not retrying,
                    stop_reason=budget_stop_reason if budget_stop_reason else self._reject_stop_reason(category, raw_code, retrying),
                    battle_stop_reason="" if retrying else (budget_stop_reason or self._reject_stop_reason(category, raw_code, False)),
                    reject_category=category,
                    reject_raw_code=raw_code,
                )
                return {
                    "consumed": retrying,
                    "step_index": step_index,
                    "current_turn_actions": current_turn_actions,
                    "total_actions": total_actions,
                    "stale_action_attempts": stale_action_attempts,
                    "consecutive_failures": consecutive_failures,
                    "pending_end_turn_transition": None,
                    "summary": None if retrying else self._finish(
                        session_id=session_id,
                        trace_path=trace_path,
                        reason=budget_stop_reason or self._reject_stop_reason(category, raw_code, False),
                        completed=False,
                        interrupted=True,
                        actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                }
            except (InvalidPayloadError, InterruptedSessionError, BridgeError) as exc:
                failure = self._finalize_failure(
                    exc=exc,
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    current_turn_actions=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    stale_action_attempts=stale_action_attempts,
                    consecutive_failures=consecutive_failures + 1,
                    trace_path=trace_path,
                    session_id=session_id,
                )
                return {
                    "consumed": True,
                    "step_index": failure["step_index"],
                    "current_turn_actions": failure["current_turn_actions"],
                    "total_actions": failure["total_actions"],
                    "stale_action_attempts": failure["stale_action_attempts"],
                    "consecutive_failures": failure["consecutive_failures"],
                    "pending_end_turn_transition": failure["pending_end_turn_transition"],
                    "summary": failure["summary"],
                }
            if self.config.stop_after_player_turn:
                return {
                    "consumed": True,
                    "step_index": step_index,
                    "current_turn_actions": current_turn_actions,
                    "total_actions": total_actions,
                    "stale_action_attempts": stale_action_attempts,
                    "consecutive_failures": consecutive_failures,
                    "pending_end_turn_transition": None,
                    "summary": self._finish(
                        session_id=snapshot.session_id,
                        trace_path=trace_path,
                        reason="auto_end_turn",
                        completed=True,
                        interrupted=False,
                        turn_completed=True,
                        actions_this_turn=current_turn_actions,
                        turns_completed=max(turns_completed, current_turn_index),
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                }
            return {
                "consumed": True,
                "step_index": step_index,
                "current_turn_actions": current_turn_actions,
                "total_actions": total_actions,
                "stale_action_attempts": stale_action_attempts,
                "consecutive_failures": consecutive_failures,
                "pending_end_turn_transition": (snapshot.decision_id, snapshot.state_version),
                "summary": None,
            }

        return {
            "consumed": True,
            "step_index": step_index,
            "current_turn_actions": current_turn_actions,
            "total_actions": total_actions,
            "stale_action_attempts": stale_action_attempts,
            "consecutive_failures": consecutive_failures,
            "pending_end_turn_transition": None,
            "summary": self._finish(
                session_id=snapshot.session_id,
                trace_path=trace_path,
                reason="end_turn_only",
                completed=True,
                interrupted=False,
                turn_completed=True,
                actions_this_turn=current_turn_actions,
                turns_completed=max(turns_completed, current_turn_index),
                total_actions=total_actions,
                current_turn_index=current_turn_index,
            ),
        }

    def _run_player_step(
        self,
        *,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        step_index: int,
        current_turn_index: int,
        current_turn_actions: int,
        turns_completed: int,
        total_actions: int,
        stale_action_attempts: int,
        consecutive_failures: int,
        trace_path: Path,
        session_id: str,
        battle_context: BattleContext | None = None,
    ) -> dict[str, object]:
        try:
            stabilized = self._stabilize_player_window(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                turns_completed=turns_completed,
                trace_path=trace_path,
                session_id=session_id,
            )
            step_index = int(stabilized["step_index"])
            if stabilized["summary"] is not None:
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=stale_action_attempts,
                    consecutive_failures=consecutive_failures,
                    pending_end_turn_transition=None,
                    summary=stabilized["summary"],
                )
            if not stabilized["ready"]:
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=stale_action_attempts,
                    consecutive_failures=consecutive_failures,
                    pending_end_turn_transition=None,
                    summary=None,
                )
            snapshot = stabilized["snapshot"]
            legal_actions = stabilized["legal_actions"]
            if battle_context is not None:
                stable_phase_kind = self._phase_kind(
                    snapshot,
                    legal_actions,
                    player_turn=self._is_player_turn(snapshot),
                    pending_end_turn_transition=None,
                    previous_phase=None,
                )
                battle_context = self._build_battle_context(
                    snapshot=snapshot,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    phase_kind=stable_phase_kind,
                )
            step_index += 1
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=self._thinking_policy_output(),
                status="thinking",
                step_index=step_index,
                current_turn_index=current_turn_index,
            )
            policy_output = self._decide(snapshot, legal_actions, battle_context=battle_context)
            if policy_output.halt or not policy_output.action_id:
                self._publish_agent_status(
                    snapshot=snapshot,
                    policy_output=policy_output,
                    status="halted",
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                )
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=policy_output,
                    bridge_result={"status": "interrupted", "reason": "policy_halt"},
                    interrupted=True,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=True,
                    stop_reason="policy_halt",
                    battle_stop_reason="policy_halt",
                )
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=stale_action_attempts,
                    consecutive_failures=consecutive_failures,
                    pending_end_turn_transition=None,
                    summary=self._finish(
                        session_id=session_id,
                        trace_path=trace_path,
                        reason="policy_halt",
                        completed=False,
                        interrupted=True,
                        actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                )

            legal_actions_by_id = {action.action_id: action for action in legal_actions}
            if policy_output.action_id not in legal_actions_by_id:
                raw_code = "policy_invalid_action"
                category = "invalid_policy_decision"
                message = "policy returned an action outside the legal action set"
                self._note_reject(
                    category=category,
                    raw_code=raw_code,
                    snapshot=snapshot,
                    step_index=step_index,
                    message=message,
                )
                self._publish_agent_status(
                    snapshot=snapshot,
                    policy_output=policy_output,
                    status="rejected",
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                )
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=policy_output,
                    bridge_result={
                        "status": "interrupted",
                        "error_code": raw_code,
                        "reject_category": category,
                        "message": message,
                    },
                    interrupted=True,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=True,
                    stop_reason=category,
                    battle_stop_reason=category,
                    reject_category=category,
                    reject_raw_code=raw_code,
                )
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=0,
                    consecutive_failures=consecutive_failures + 1,
                    pending_end_turn_transition=None,
                    summary=self._finish(
                        session_id=session_id,
                        trace_path=trace_path,
                        reason=category,
                        completed=False,
                        interrupted=True,
                        actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                )
            selected_action = legal_actions_by_id[policy_output.action_id]
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=policy_output,
                status="planned",
                step_index=step_index,
                current_turn_index=current_turn_index,
                action_label=selected_action.label,
            )

            if self.config.dry_run:
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=policy_output,
                    bridge_result={
                        "status": "dry_run",
                        "planned_action_id": policy_output.action_id,
                        "message": "dry run enabled; bridge submission skipped",
                    },
                    interrupted=False,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=True,
                    stop_reason="dry_run",
                    battle_stop_reason="dry_run",
                )
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=stale_action_attempts,
                    consecutive_failures=consecutive_failures,
                    pending_end_turn_transition=None,
                    summary=self._finish(
                        session_id=session_id,
                        trace_path=trace_path,
                        reason="dry_run",
                        completed=False,
                        interrupted=True,
                        actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                )

            gate = self._pre_submit_gate(
                snapshot=snapshot,
                legal_actions=legal_actions,
                selected_action=selected_action,
            )
            if not gate["allowed"]:
                raw_code = str(gate["raw_code"])
                category = str(gate["category"])
                gate_context = dict(gate.get("context") or {})
                message = str(gate["message"])
                if category == "recoverable_stale":
                    stale_action_attempts += 1
                    retrying = stale_action_attempts <= self.config.stale_action_retries
                else:
                    stale_action_attempts = 0
                    retrying = True
                consecutive_failures += 1
                self._note_reject(
                    category=category,
                    raw_code=raw_code,
                    snapshot=snapshot,
                    selected_action=selected_action,
                    step_index=step_index,
                    message=message,
                    gate_intercepted=True,
                    context=gate_context,
                )
                self._note_recovery_attempt(raw_code)
                budget_stop_reason = self._battle_budget_stop_reason(
                    total_actions=total_actions,
                    turns_completed=turns_completed,
                    current_turn_index=current_turn_index,
                    consecutive_failures=consecutive_failures,
                )
                retrying = retrying and not budget_stop_reason
                if retrying:
                    self._gate_redecisions += 1
                self._publish_agent_status(
                    snapshot=snapshot,
                    policy_output=policy_output,
                    status="rejected",
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    action_label=selected_action.label,
                )
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=policy_output,
                    bridge_result={
                        "status": "interrupted",
                        "error_code": raw_code,
                        "reject_category": category,
                        "message": message,
                        "retrying": retrying,
                        "consecutive_failures": consecutive_failures,
                        "gate_status": "intercepted",
                        "gate_reason": raw_code,
                        "gate_context": gate_context,
                    },
                    interrupted=not retrying,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=not retrying,
                    stop_reason=budget_stop_reason if budget_stop_reason else self._reject_stop_reason(category, raw_code, retrying),
                    battle_stop_reason="" if retrying else (budget_stop_reason or self._reject_stop_reason(category, raw_code, False)),
                    reject_category=category,
                    reject_raw_code=raw_code,
                    gate_status="intercepted",
                    gate_reason=raw_code,
                )
                if retrying:
                    return self._step_result(
                        step_index=step_index,
                        current_turn_actions=current_turn_actions,
                        total_actions=total_actions,
                        stale_action_attempts=stale_action_attempts,
                        consecutive_failures=consecutive_failures,
                        pending_end_turn_transition=None,
                        summary=None,
                    )
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=stale_action_attempts,
                    consecutive_failures=consecutive_failures,
                    pending_end_turn_transition=None,
                    summary=self._finish(
                        session_id=session_id,
                        trace_path=trace_path,
                        reason=budget_stop_reason or raw_code,
                        completed=False,
                        interrupted=True,
                        actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                )

            snapshot = gate["snapshot"]
            legal_actions = gate["legal_actions"]
            selected_action = gate["selected_action"]
            gate_status = str(gate.get("gate_status") or "passed")
            gate_reason = str(gate.get("gate_reason") or "")
            if gate_status == "rebased":
                self._gate_rebases += 1
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=policy_output,
                status="submitted",
                step_index=step_index,
                current_turn_index=current_turn_index,
                action_label=selected_action.label,
            )
            result = self.bridge.submit_action(
                ActionSubmission(
                    session_id=snapshot.session_id,
                    decision_id=snapshot.decision_id,
                    state_version=snapshot.state_version,
                    action_id=selected_action.action_id,
                    args=self._build_action_args(selected_action, policy_output),
                )
            )
            # For end_turn transitions, give the game some time to start the animation
            if str(result.status) == "accepted" and selected_action.type == "end_turn":
                time.sleep(2.0 if self.config.poll_interval_seconds < 1.0 else self.config.poll_interval_seconds * 2)
            
            if str(result.status) != "accepted":
                raw_code = str(result.error_code or "action_rejected")
                category = self._classify_reject_category(raw_code)
                if category == "recoverable_action":
                    stale_action_attempts += 1
                    retrying = stale_action_attempts <= self.config.stale_action_retries
                else:
                    stale_action_attempts = 0
                    retrying = self._is_recoverable_reject_category(category)
                consecutive_failures += 1
                self._note_reject(
                    category=category,
                    raw_code=raw_code,
                    snapshot=snapshot,
                    selected_action=selected_action,
                    step_index=step_index,
                    message=str(result.message or "action was rejected by bridge"),
                )
                if self._is_recoverable_reject_category(category):
                    self._note_recovery_attempt(raw_code)
                    # For rejected actions that are recoverable, we might want to wait a bit
                    # as it might be an animation or UI lock.
                    time.sleep(self.config.poll_interval_seconds)

                budget_stop_reason = self._battle_budget_stop_reason(
                    total_actions=total_actions,
                    turns_completed=turns_completed,
                    current_turn_index=current_turn_index,
                    consecutive_failures=consecutive_failures,
                )
                retrying = retrying and not budget_stop_reason
                
                self._publish_agent_status(
                    snapshot=snapshot,
                    policy_output=policy_output,
                    status="rejected",
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    action_label=selected_action.label,
                )
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=policy_output,
                    bridge_result=to_dict(result),
                    interrupted=not retrying,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=not retrying,
                    stop_reason=budget_stop_reason if budget_stop_reason else self._reject_stop_reason(category, raw_code, retrying),
                    battle_stop_reason="" if retrying else (budget_stop_reason or self._reject_stop_reason(category, raw_code, False)),
                    reject_category=category,
                    reject_raw_code=raw_code,
                )
                if retrying:
                    return self._step_result(
                        step_index=step_index,
                        current_turn_actions=current_turn_actions,
                        total_actions=total_actions,
                        stale_action_attempts=stale_action_attempts,
                        consecutive_failures=consecutive_failures,
                        pending_end_turn_transition=None,
                        summary=None,
                    )
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=stale_action_attempts,
                    consecutive_failures=consecutive_failures,
                    pending_end_turn_transition=None,
                    summary=self._finish(
                        session_id=session_id,
                        trace_path=trace_path,
                        reason=budget_stop_reason or self._reject_stop_reason(category, raw_code, False),
                        completed=False,
                        interrupted=True,
                        actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                )

            result_payload = to_dict(result)
            result_payload["submitted_action_id"] = selected_action.action_id
            result_payload["submitted_action_type"] = selected_action.type
            result_payload["submitted_action_label"] = selected_action.label
            total_actions += 1
            current_turn_actions += 1
            stale_action_attempts = 0
            consecutive_failures = 0
            self._note_same_window_action(snapshot, selected_action, result)
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=policy_output,
                status=str(result.status),
                step_index=step_index,
                current_turn_index=current_turn_index,
                action_label=selected_action.label,
            )
            stop_reason = self._post_action_stop_reason(selected_action.type, policy_output, result)
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=policy_output,
                bridge_result=result_payload,
                interrupted=False,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=bool(stop_reason),
                stop_reason=stop_reason,
                battle_stop_reason=stop_reason,
                gate_status=gate_status,
                gate_reason=gate_reason,
            )
            self._mark_recovery_resolved()
            if stop_reason:
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=stale_action_attempts,
                    consecutive_failures=consecutive_failures,
                    pending_end_turn_transition=None if self.config.stop_after_player_turn or selected_action.type != "end_turn" else (snapshot.decision_id, snapshot.state_version),
                    summary=self._finish(
                        session_id=session_id,
                        trace_path=trace_path,
                        reason=stop_reason,
                        completed=True,
                        interrupted=False,
                        turn_completed=True,
                        battle_completed=stop_reason == "terminal_action_accepted",
                        actions_this_turn=current_turn_actions,
                        turns_completed=max(turns_completed, current_turn_index),
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=stale_action_attempts,
                consecutive_failures=consecutive_failures,
                pending_end_turn_transition=None if selected_action.type != "end_turn" or self.config.stop_after_player_turn else (snapshot.decision_id, snapshot.state_version),
                summary=None,
            )
        except StaleActionError as exc:
            raw_code = getattr(exc, "error_code", "stale_action")
            category = self._classify_reject_category(raw_code)
            if category == "recoverable_stale":
                stale_action_attempts += 1
                retrying = stale_action_attempts <= self.config.stale_action_retries
            else:
                stale_action_attempts = 0
                retrying = self._is_recoverable_reject_category(category)
            consecutive_failures += 1
            self._note_reject(
                category=category,
                raw_code=raw_code,
                snapshot=snapshot,
                selected_action=locals().get("selected_action"),
                step_index=step_index,
                message=str(exc),
            )
            if self._is_recoverable_reject_category(category):
                self._note_recovery_attempt(raw_code)
            budget_stop_reason = self._battle_budget_stop_reason(
                total_actions=total_actions,
                turns_completed=turns_completed,
                current_turn_index=current_turn_index,
                consecutive_failures=consecutive_failures,
            )
            retrying = retrying and not budget_stop_reason
            interrupted_payload = {
                "status": "interrupted",
                "error_code": raw_code,
                "reject_category": category,
                "message": str(exc),
                "retrying": retrying,
                "stale_action_attempts": stale_action_attempts,
                "consecutive_failures": consecutive_failures,
            }
            fallback_output = locals().get("policy_output", PolicyDecision(action_id=None, reason="policy unavailable", halt=True))
            selected_action = locals().get("selected_action")
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=fallback_output,
                status="rejected",
                step_index=step_index,
                current_turn_index=current_turn_index,
                action_label=selected_action.label if selected_action is not None else None,
            )
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=fallback_output,
                bridge_result=interrupted_payload,
                interrupted=not retrying,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=not retrying,
                stop_reason=budget_stop_reason if budget_stop_reason else self._reject_stop_reason(category, raw_code, retrying),
                battle_stop_reason="" if retrying else (budget_stop_reason or self._reject_stop_reason(category, raw_code, False)),
                reject_category=category,
                reject_raw_code=raw_code,
            )
            if retrying:
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=stale_action_attempts,
                    consecutive_failures=consecutive_failures,
                    pending_end_turn_transition=None,
                    summary=None,
                )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=stale_action_attempts,
                consecutive_failures=consecutive_failures,
                pending_end_turn_transition=None,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason=budget_stop_reason or self._reject_stop_reason(category, raw_code, False),
                    completed=False,
                    interrupted=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )
        except (InvalidPayloadError, InterruptedSessionError, BridgeError) as exc:
            return self._finalize_failure(
                exc=exc,
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                turns_completed=turns_completed,
                total_actions=total_actions,
                stale_action_attempts=stale_action_attempts,
                consecutive_failures=consecutive_failures + 1,
                trace_path=trace_path,
                session_id=session_id,
            )
        except PolicyError as exc:
            return self._finalize_failure(
                exc=exc,
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                step_index=step_index,
                current_turn_index=current_turn_index,
                current_turn_actions=current_turn_actions,
                turns_completed=turns_completed,
                total_actions=total_actions,
                stale_action_attempts=stale_action_attempts,
                consecutive_failures=consecutive_failures + 1,
                trace_path=trace_path,
                session_id=session_id,
                is_policy_error=True,
            )

    def _finalize_failure(
        self,
        *,
        exc: Exception,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        step_index: int,
        current_turn_index: int,
        current_turn_actions: int,
        turns_completed: int,
        total_actions: int,
        stale_action_attempts: int,
        consecutive_failures: int,
        trace_path: Path,
        session_id: str,
        is_policy_error: bool = False,
        step_kind: str | None = None,
        phase_kind: str | None = None,
    ) -> dict[str, object]:
        error_code = getattr(exc, "error_code", "policy_error" if is_policy_error else "bridge_error")
        reject_category = self._classify_reject_category(error_code)
        is_reject = reject_category in {
            "recoverable_stale",
            "recoverable_timing",
            "recoverable_action",
            "invalid_policy_decision",
            "hard_runtime_reject",
        } and (not is_policy_error or error_code == "policy_invalid_action_args")

        if is_reject:
            self._note_reject(
                category=reject_category,
                raw_code=error_code,
                snapshot=snapshot,
                step_index=step_index,
                message=str(exc),
            )
            if self._is_recoverable_reject_category(reject_category):
                self._note_recovery_attempt(error_code)
                if reject_category == "recoverable_action":
                    stale_action_attempts += 1
                    retrying = stale_action_attempts <= self.config.stale_action_retries
                else:
                    retrying = True
                budget_stop_reason = self._battle_budget_stop_reason(
                    total_actions=total_actions,
                    turns_completed=turns_completed,
                    current_turn_index=current_turn_index,
                    consecutive_failures=consecutive_failures,
                )
                retrying = retrying and not budget_stop_reason
                interrupted_payload = {
                    "status": "interrupted",
                    "error_code": error_code,
                    "reject_category": reject_category,
                    "message": str(exc),
                    "consecutive_failures": consecutive_failures,
                    "retrying": retrying,
                }
                fallback_output = PolicyDecision(
                    action_id=None,
                    reason=str(exc) if is_policy_error else "policy unavailable",
                    halt=True,
                    metadata={"error_code": error_code},
                )
                self._publish_agent_status(
                    snapshot=snapshot,
                    policy_output=fallback_output,
                    status="rejected",
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                )
                self._record(
                    recorder=recorder,
                    snapshot=snapshot,
                    legal_actions=legal_actions,
                    policy_output=fallback_output,
                    bridge_result=interrupted_payload,
                    interrupted=not retrying,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=False,
                    is_final_step=not retrying,
                    stop_reason=budget_stop_reason if budget_stop_reason else self._reject_stop_reason(reject_category, error_code, retrying),
                    battle_stop_reason="" if retrying else (budget_stop_reason or self._reject_stop_reason(reject_category, error_code, False)),
                    step_kind=step_kind,
                    phase_kind=phase_kind,
                    reject_category=reject_category,
                    reject_raw_code=error_code,
                )
                if retrying:
                    return self._step_result(
                        step_index=step_index,
                        current_turn_actions=current_turn_actions,
                        total_actions=total_actions,
                        stale_action_attempts=stale_action_attempts,
                        consecutive_failures=consecutive_failures,
                        pending_end_turn_transition=None,
                        summary=None,
                    )
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=stale_action_attempts,
                    consecutive_failures=consecutive_failures,
                    pending_end_turn_transition=None,
                    summary=self._finish(
                        session_id=session_id,
                        trace_path=trace_path,
                        reason=budget_stop_reason or self._reject_stop_reason(reject_category, error_code, False),
                        completed=False,
                        interrupted=True,
                        actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                )

            interrupted_payload = {
                "status": "interrupted",
                "error_code": error_code,
                "reject_category": reject_category,
                "message": str(exc),
                "consecutive_failures": consecutive_failures,
            }
            fallback_output = PolicyDecision(
                action_id=None,
                reason=str(exc) if is_policy_error else "policy unavailable",
                halt=True,
                metadata={"error_code": error_code},
            )
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=fallback_output,
                status="rejected",
                step_index=step_index,
                current_turn_index=current_turn_index,
            )
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=fallback_output,
                bridge_result=interrupted_payload,
                interrupted=True,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=True,
                stop_reason=reject_category,
                battle_stop_reason=reject_category,
                step_kind=step_kind,
                phase_kind=phase_kind,
                reject_category=reject_category,
                reject_raw_code=error_code,
            )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=stale_action_attempts,
                consecutive_failures=consecutive_failures,
                pending_end_turn_transition=None,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason=reject_category,
                    completed=False,
                    interrupted=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )

        if is_policy_error and not self.config.stop_after_player_turn:
            self._note_recovery_attempt(error_code)
            budget_stop_reason = self._battle_budget_stop_reason(
                total_actions=total_actions,
                turns_completed=turns_completed,
                current_turn_index=current_turn_index,
                consecutive_failures=consecutive_failures,
            )
            retrying = not budget_stop_reason
            interrupted_payload = {
                "status": "interrupted",
                "error_code": error_code,
                "message": str(exc),
                "consecutive_failures": consecutive_failures,
                "retrying": retrying,
            }
            fallback_output = PolicyDecision(
                action_id=None,
                reason=str(exc),
                halt=True,
                metadata={"error_code": error_code},
            )
            self._publish_agent_status(
                snapshot=snapshot,
                policy_output=fallback_output,
                status="rejected",
                step_index=step_index,
                current_turn_index=current_turn_index,
            )
            self._record(
                recorder=recorder,
                snapshot=snapshot,
                legal_actions=legal_actions,
                policy_output=fallback_output,
                bridge_result=interrupted_payload,
                interrupted=not retrying,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=not retrying,
                stop_reason=budget_stop_reason if budget_stop_reason else f"{error_code}_retry",
                battle_stop_reason=budget_stop_reason,
                step_kind=step_kind,
                phase_kind=phase_kind,
            )
            if retrying:
                return self._step_result(
                    step_index=step_index,
                    current_turn_actions=current_turn_actions,
                    total_actions=total_actions,
                    stale_action_attempts=stale_action_attempts,
                    consecutive_failures=consecutive_failures,
                    pending_end_turn_transition=None,
                    summary=None,
                )
            return self._step_result(
                step_index=step_index,
                current_turn_actions=current_turn_actions,
                total_actions=total_actions,
                stale_action_attempts=stale_action_attempts,
                consecutive_failures=consecutive_failures,
                pending_end_turn_transition=None,
                summary=self._finish(
                    session_id=session_id,
                    trace_path=trace_path,
                    reason=budget_stop_reason,
                    completed=False,
                    interrupted=True,
                    actions_this_turn=current_turn_actions,
                    turns_completed=turns_completed,
                    total_actions=total_actions,
                    current_turn_index=current_turn_index,
                ),
            )
        interrupted_payload = {
            "status": "interrupted",
            "error_code": error_code,
            "message": str(exc),
            "consecutive_failures": consecutive_failures,
        }
        if is_policy_error:
            fallback_output = PolicyDecision(
                action_id=None,
                reason=str(exc),
                halt=True,
                metadata={"error_code": error_code},
            )
        else:
            fallback_output = PolicyDecision(action_id=None, reason="policy unavailable", halt=True)
        self._publish_agent_status(
            snapshot=snapshot,
            policy_output=fallback_output,
            status="rejected",
            step_index=step_index,
            current_turn_index=current_turn_index,
        )
        self._record(
            recorder=recorder,
            snapshot=snapshot,
            legal_actions=legal_actions,
            policy_output=fallback_output,
            bridge_result=interrupted_payload,
            interrupted=True,
            step_index=step_index,
            current_turn_index=current_turn_index,
            actions_this_turn=current_turn_actions,
            total_actions=total_actions,
            waiting_for_player_turn=False,
            is_final_step=True,
            stop_reason=error_code,
            battle_stop_reason=error_code,
            step_kind=step_kind,
            phase_kind=phase_kind,
        )
        return self._step_result(
            step_index=step_index,
            current_turn_actions=current_turn_actions,
            total_actions=total_actions,
            stale_action_attempts=stale_action_attempts,
            consecutive_failures=consecutive_failures,
            pending_end_turn_transition=None,
            summary=self._finish(
                session_id=session_id,
                trace_path=trace_path,
                reason=error_code,
                completed=False,
                interrupted=True,
                actions_this_turn=current_turn_actions,
                turns_completed=turns_completed,
                total_actions=total_actions,
                current_turn_index=current_turn_index,
            ),
        )

    @staticmethod
    def _step_result(
        *,
        step_index: int,
        current_turn_actions: int,
        total_actions: int,
        stale_action_attempts: int,
        consecutive_failures: int,
        pending_end_turn_transition: tuple[str, int] | None,
        transition_wait_since: float | None = None,
        summary: RunSummary | None,
    ) -> dict[str, object]:
        return {
            "step_index": step_index,
            "current_turn_actions": current_turn_actions,
            "total_actions": total_actions,
            "stale_action_attempts": stale_action_attempts,
            "consecutive_failures": consecutive_failures,
            "pending_end_turn_transition": pending_end_turn_transition,
            "transition_wait_since": transition_wait_since,
            "waiting_since": transition_wait_since,  # Compatibility alias
            "summary": summary,
        }

    def _build_battle_context(
        self,
        *,
        snapshot,
        current_turn_index: int,
        actions_this_turn: int,
        total_actions: int,
        waiting_for_player_turn: bool,
        phase_kind: str,
    ) -> BattleContext:
        metadata = getattr(snapshot, "metadata", {}) or {}
        metadata_summary = {
            key: metadata[key]
            for key in (
                "window_kind",
                "current_side",
                "round_number",
                "round",
                "turn_index",
                "selection_kind",
                "selection_prompt",
                "selection_choice_count",
                "selection_cancel_available",
                "reward_subphase",
                "transition_kind",
                "event_subphase",
                "event_title",
                "event_body",
                "event_selection_prompt",
                "event_continue_available",
            )
            if key in metadata
        }
        return BattleContext(
            phase=getattr(snapshot, "phase", ""),
            phase_kind=phase_kind,
            current_turn_index=current_turn_index,
            actions_this_turn=actions_this_turn,
            total_actions=total_actions,
            rejects_total=self._rejects_total,
            recoverable_rejects=self._recoverable_rejects,
            hard_rejects=self._hard_rejects,
            waiting_for_player_turn=waiting_for_player_turn,
            recovery_attempts=self._recovery_attempts,
            recovery_successes=self._recovery_successes,
            recovery_streak=self._recovery_streak,
            pending_recovery_reason=self._pending_recovery_reason,
            last_recovery_reason=self._last_recovery_reason,
            reject_counts=dict(self._reject_counts),
            metadata=metadata_summary,
            recent_steps=list(self._battle_history[-self.config.battle_context_recent_steps :]),
        )

    def _append_battle_history(
        self,
        *,
        snapshot,
        policy_output,
        bridge_result,
        current_turn_index: int,
        actions_this_turn: int,
        total_actions: int,
        waiting_for_player_turn: bool,
        phase_kind: str,
        step_kind: str,
        step_index: int,
    ) -> None:
        entry = {
            "step_index": step_index,
            "phase": getattr(snapshot, "phase", ""),
            "phase_kind": phase_kind,
            "step_kind": step_kind,
            "current_turn_index": current_turn_index,
            "actions_this_turn": actions_this_turn,
            "total_actions": total_actions,
            "waiting_for_player_turn": waiting_for_player_turn,
            "action_id": getattr(policy_output, "action_id", None),
            "reason": getattr(policy_output, "reason", ""),
            "confidence": getattr(policy_output, "confidence", None),
            "bridge_status": bridge_result.get("status") if isinstance(bridge_result, dict) else None,
            "bridge_reason": (
                bridge_result.get("reason") or bridge_result.get("error_code")
                if isinstance(bridge_result, dict)
                else None
            ),
            "reject_category": bridge_result.get("reject_category") if isinstance(bridge_result, dict) else None,
            "gate_status": bridge_result.get("gate_status") if isinstance(bridge_result, dict) else None,
            "gate_reason": bridge_result.get("gate_reason") if isinstance(bridge_result, dict) else None,
            "submitted_action_type": bridge_result.get("submitted_action_type") if isinstance(bridge_result, dict) else None,
        }
        self._battle_history.append(entry)
        max_history = max(1, self.config.battle_context_recent_steps * 2)
        if len(self._battle_history) > max_history:
            self._battle_history = self._battle_history[-max_history:]

    def _note_recovery_attempt(self, reason: str) -> None:
        self._recovery_attempts += 1
        self._recovery_streak += 1
        self._pending_recovery_reason = reason
        self._last_recovery_reason = reason

    def _mark_recovery_resolved(self) -> None:
        if not self._pending_recovery_reason:
            return
        self._recovery_successes += 1
        self._recovery_streak = 0
        self._pending_recovery_reason = ""

    @staticmethod
    def _is_recoverable_reject_category(category: str) -> bool:
        return category in RECOVERABLE_REJECT_CATEGORIES

    @staticmethod
    def _classify_reject_category(raw_code: str) -> str:
        normalized = str(raw_code or "").strip().lower()
        if normalized in {"stale_decision", "stale_action", "selection_window_changed", "pre_submit_state_drift"}:
            return "recoverable_stale"
        if normalized in {"play_rejected", "use_potion_rejected", "discard_rejected"}:
            return "recoverable_action"
        if normalized in {
            "not_player_turn",
            "pending_transition",
            "pending_end_turn_transition",
            "non_player_window",
            "transition_window",
        }:
            return "recoverable_timing"
        if normalized in {
            "policy_invalid_action",
            "policy_invalid_action_args",
            "illegal_action",
            "invalid_action",
            "invalid_payload",
        }:
            return "invalid_policy_decision"
        return "hard_runtime_reject"

    def _note_reject(
        self,
        *,
        category: str,
        raw_code: str,
        snapshot,
        selected_action=None,
        step_index: int,
        message: str,
        gate_intercepted: bool = False,
        context: dict[str, Any] | None = None,
    ) -> None:
        self._rejects_total += 1
        self._reject_counts[category] = self._reject_counts.get(category, 0) + 1
        self._reject_code_counts[raw_code] = self._reject_code_counts.get(raw_code, 0) + 1
        if self._is_recoverable_reject_category(category):
            self._recoverable_rejects += 1
        else:
            self._hard_rejects += 1
        if gate_intercepted:
            self._gate_intercepts += 1

        metadata = getattr(snapshot, "metadata", {}) or {}
        reject_context = {
            "category": category,
            "raw_code": raw_code,
            "phase": getattr(snapshot, "phase", ""),
            "decision_id": getattr(snapshot, "decision_id", ""),
            "state_version": getattr(snapshot, "state_version", 0),
            "window_kind": str(metadata.get("window_kind") or ""),
            "current_side": str(metadata.get("current_side") or metadata.get("turn_owner") or ""),
            "transition_kind": str(metadata.get("transition_kind") or ""),
            "selection_kind": str(metadata.get("selection_kind") or ""),
            "reward_subphase": str(metadata.get("reward_subphase") or ""),
            "step_index": step_index,
            "message": message,
            "gate_intercepted": gate_intercepted,
        }
        if selected_action is not None:
            reject_context["action_id"] = getattr(selected_action, "action_id", None)
            reject_context["action_label"] = getattr(selected_action, "label", None)
            reject_context["action_type"] = getattr(selected_action, "type", None)
        if context:
            reject_context["context"] = dict(context)
        self._last_reject = reject_context

    def _stabilize_player_window(
        self,
        *,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        step_index: int,
        current_turn_index: int,
        current_turn_actions: int,
        total_actions: int,
        turns_completed: int,
        trace_path: Path,
        session_id: str,
    ) -> dict[str, Any]:
        required = max(1, int(self.config.stable_window_required_observations))
        if required <= 1:
            return {
                "ready": True,
                "snapshot": snapshot,
                "legal_actions": legal_actions,
                "step_index": step_index,
                "summary": None,
            }

        candidate_snapshot = snapshot
        candidate_legal_actions = list(legal_actions)
        candidate_signature = self._stable_window_signature(candidate_snapshot, candidate_legal_actions)
        candidate_version = getattr(candidate_snapshot, "state_version", 0)
        stable_observations = 1
        waiting_since: float | None = None

        while stable_observations < required:
            latest_snapshot, latest_legal_actions = self._read_consistent_state(session_id)
            latest_legal_actions = self._effective_legal_actions(latest_snapshot, latest_legal_actions)
            latest_phase = self._normalize_phase(getattr(latest_snapshot, "phase", ""))
            latest_player_turn = self._is_player_turn(latest_snapshot)
            if latest_phase != "combat" or not latest_player_turn:
                self._gate_wait_steps += 1
                step_index += 1
                self._record(
                    recorder=recorder,
                    snapshot=latest_snapshot,
                    legal_actions=latest_legal_actions,
                    policy_output=PolicyDecision(action_id=None, reason="waiting for stable combat window", halt=True),
                    bridge_result={
                        "status": "waiting",
                        "reason": "stable_window_drift",
                        "message": "combat window changed before policy call",
                    },
                    interrupted=False,
                    step_index=step_index,
                    current_turn_index=current_turn_index,
                    actions_this_turn=current_turn_actions,
                    total_actions=total_actions,
                    waiting_for_player_turn=not latest_player_turn,
                    is_final_step=False,
                    stop_reason="",
                    battle_stop_reason="",
                    step_kind="stable_window_wait",
                    gate_status="waiting_stable_window",
                    gate_reason="window_drift",
                )
                return {
                    "ready": False,
                    "snapshot": latest_snapshot,
                    "legal_actions": latest_legal_actions,
                    "step_index": step_index,
                    "summary": None,
                }

            latest_signature = self._stable_window_signature(latest_snapshot, latest_legal_actions)
            latest_version = getattr(latest_snapshot, "state_version", 0)
            if latest_signature == candidate_signature and latest_version == candidate_version:
                stable_observations += 1
                candidate_snapshot = latest_snapshot
                candidate_legal_actions = latest_legal_actions
                if stable_observations < required:
                    time.sleep(self.config.poll_interval_seconds)
                continue

            if waiting_since is None:
                waiting_since = time.monotonic()
                self._note_recovery_attempt("stable_window_wait")
            elapsed = time.monotonic() - waiting_since
            self._gate_wait_steps += 1
            step_index += 1
            # Scale timeout so it's always at least poll_interval * required_observations.
            # Without this, large --poll-interval-seconds values cause the window to time
            # out after a single poll cycle, triggering spurious stable_window_timeout exits.
            effective_stable_timeout = max(
                self.config.stable_window_timeout_seconds,
                self.config.poll_interval_seconds * max(2, required + 1),
            )
            timed_out = elapsed > effective_stable_timeout
            self._record(
                recorder=recorder,
                snapshot=latest_snapshot,
                legal_actions=latest_legal_actions,
                policy_output=PolicyDecision(action_id=None, reason="waiting for stable combat window", halt=True),
                bridge_result={
                    "status": "waiting",
                    "reason": "stable_window_wait",
                    "elapsed_seconds": elapsed,
                    "required_observations": required,
                },
                interrupted=timed_out,
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=current_turn_actions,
                total_actions=total_actions,
                waiting_for_player_turn=False,
                is_final_step=timed_out,
                stop_reason="stable_window_timeout" if timed_out else "",
                battle_stop_reason="stable_window_timeout" if timed_out else "",
                step_kind="stable_window_wait",
                phase_kind="combat",
                gate_status="waiting_stable_window",
                gate_reason="window_drift",
            )
            if timed_out:
                return {
                    "ready": False,
                    "snapshot": latest_snapshot,
                    "legal_actions": latest_legal_actions,
                    "step_index": step_index,
                    "summary": self._finish(
                        session_id=session_id,
                        trace_path=trace_path,
                        reason="stable_window_timeout",
                        completed=False,
                        interrupted=True,
                        turn_completed=turns_completed > 0,
                        actions_this_turn=current_turn_actions,
                        turns_completed=turns_completed,
                        total_actions=total_actions,
                        current_turn_index=current_turn_index,
                    ),
                }

            candidate_snapshot = latest_snapshot
            candidate_legal_actions = latest_legal_actions
            candidate_signature = latest_signature
            candidate_version = latest_version
            stable_observations = 1
            time.sleep(self.config.poll_interval_seconds)

        return {
            "ready": True,
            "snapshot": candidate_snapshot,
            "legal_actions": candidate_legal_actions,
            "step_index": step_index,
            "summary": None,
        }

    @classmethod
    def _stable_window_signature(cls, snapshot, legal_actions) -> tuple[Any, ...]:
        metadata = getattr(snapshot, "metadata", {}) or {}
        round_marker = ""
        for key in ("round_number", "round", "turn_index", "turn_number"):
            value = metadata.get(key)
            if value is not None and str(value) != "":
                round_marker = str(value)
                break
        action_signature = tuple(sorted((cls._action_semantic_signature(action) for action in legal_actions), key=repr))
        return (
            cls._normalize_phase(getattr(snapshot, "phase", "")),
            str(metadata.get("window_kind") or "").strip().lower(),
            str(metadata.get("current_side") or metadata.get("turn_owner") or "").strip().lower(),
            round_marker,
            str(metadata.get("selection_kind") or "").strip().lower(),
            action_signature,
        )

    @staticmethod
    def _can_rebase_action_within_window(action_type: str) -> bool:
        return action_type in {"play_card", "choose_combat_card", "cancel_combat_selection"}

    def _pre_submit_gate(
        self,
        *,
        snapshot,
        legal_actions,
        selected_action,
    ) -> dict[str, Any]:
        latest_snapshot, latest_legal_actions = self._read_consistent_state(snapshot.session_id)
        latest_legal_actions = self._effective_legal_actions(latest_snapshot, latest_legal_actions)
        latest_by_id = {action.action_id: action for action in latest_legal_actions}
        latest_metadata = getattr(latest_snapshot, "metadata", {}) or {}
        original_metadata = getattr(snapshot, "metadata", {}) or {}
        original_signature = self._stable_window_signature(snapshot, legal_actions)
        latest_signature = self._stable_window_signature(latest_snapshot, latest_legal_actions)
        same_stable_window = original_signature == latest_signature
        gate_context = {
            "observed_phase": getattr(latest_snapshot, "phase", ""),
            "observed_decision_id": getattr(latest_snapshot, "decision_id", ""),
            "observed_state_version": getattr(latest_snapshot, "state_version", 0),
            "original_window_kind": str(original_metadata.get("window_kind") or ""),
            "observed_window_kind": str(latest_metadata.get("window_kind") or ""),
            "original_current_side": str(original_metadata.get("current_side") or original_metadata.get("turn_owner") or ""),
            "observed_current_side": str(latest_metadata.get("current_side") or latest_metadata.get("turn_owner") or ""),
            "observed_transition_kind": str(latest_metadata.get("transition_kind") or ""),
            "original_selection_kind": str(original_metadata.get("selection_kind") or ""),
            "observed_selection_kind": str(latest_metadata.get("selection_kind") or ""),
            "same_stable_window": same_stable_window,
        }
        state_drifted = (
            latest_snapshot.decision_id != snapshot.decision_id
            or latest_snapshot.state_version != snapshot.state_version
        )

        latest_phase = self._normalize_phase(getattr(latest_snapshot, "phase", ""))
        if latest_phase != "combat":
            return {
                "allowed": False,
                "category": "recoverable_timing",
                "raw_code": "pending_transition",
                "message": "combat action gated because the phase changed before submit",
                "context": gate_context,
            }

        if not self._is_player_turn(latest_snapshot):
            return {
                "allowed": False,
                "category": "recoverable_timing",
                "raw_code": "not_player_turn",
                "message": "combat action gated because it is no longer the player turn",
                "context": gate_context,
            }

        window_kind = str(latest_metadata.get("window_kind") or "").strip().lower()
        transition_kind = str(latest_metadata.get("transition_kind") or "").strip().lower()
        if (
            window_kind in TRANSITION_WINDOW_KINDS
            or transition_kind
            or bool(latest_metadata.get("reward_pending"))
        ):
            gate_context["observed_reward_pending"] = bool(latest_metadata.get("reward_pending"))
            return {
                "allowed": False,
                "category": "recoverable_timing",
                "raw_code": "transition_window",
                "message": "combat action gated because the runtime is in a transition window",
                "context": gate_context,
            }

        in_selection_window = window_kind == "combat_card_selection"
        selected_is_selection_action = selected_action.type in SELECTION_ACTION_TYPES
        if in_selection_window != selected_is_selection_action:
            return {
                "allowed": False,
                "category": "recoverable_stale",
                "raw_code": "selection_window_changed",
                "message": "combat action gated because the selection window changed before submit",
                "context": gate_context,
            }

        if not same_stable_window:
            return {
                "allowed": False,
                "category": "recoverable_stale",
                "raw_code": "pre_submit_state_drift",
                "message": "combat action gated because the stable decision window changed before submit",
                "context": gate_context,
            }

        refreshed_action = latest_by_id.get(selected_action.action_id)
        if refreshed_action is None and self._can_rebase_action_within_window(str(selected_action.type or "")):
            refreshed_action = self._match_equivalent_action(selected_action, latest_legal_actions)

        if state_drifted and refreshed_action is None:
            return {
                "allowed": False,
                "category": "recoverable_stale",
                "raw_code": "pre_submit_state_drift",
                "message": "state drifted before submit; reobserve before applying action",
                "context": gate_context,
            }

        if refreshed_action is None:
            return {
                "allowed": False,
                "category": "recoverable_stale",
                "raw_code": "stale_action",
                "message": "combat action gated because the selected action is no longer legal",
                "context": gate_context,
            }

        gate_status = "rebased" if state_drifted else "passed"
        gate_context["gate_status"] = gate_status
        return {
            "allowed": True,
            "snapshot": latest_snapshot,
            "legal_actions": latest_legal_actions,
            "selected_action": refreshed_action,
            "gate_status": gate_status,
            "gate_reason": "pre_submit_rebase" if state_drifted else "",
            "context": gate_context,
        }

    @classmethod
    def _match_equivalent_action(cls, selected_action, legal_actions):
        exact_signature = cls._action_semantic_signature(selected_action)
        matches = [action for action in legal_actions if cls._action_semantic_signature(action) == exact_signature]
        if len(matches) == 1:
            return matches[0]
        return None

    @classmethod
    def _action_semantic_signature(cls, action) -> tuple[Any, ...]:
        return (
            str(getattr(action, "type", "") or ""),
            cls._normalize_action_value(dict(getattr(action, "params", {}) or {})),
            tuple(str(item) for item in list(getattr(action, "target_constraints", []) or [])),
        )

    @classmethod
    def _normalize_action_value(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return tuple(sorted((str(key), cls._normalize_action_value(item)) for key, item in value.items()))
        if isinstance(value, list):
            return tuple(cls._normalize_action_value(item) for item in value)
        return value

    @classmethod
    def _reject_stop_reason(cls, category: str, raw_code: str, retrying: bool) -> str:
        if retrying:
            return f"{raw_code}_retry"
        if category in {"invalid_policy_decision", "hard_runtime_reject"}:
            return category
        return raw_code

    def _supports_battle_context(self) -> bool:
        try:
            parameters = inspect.signature(self.policy.decide).parameters.values()
        except (TypeError, ValueError):
            return True
        return any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters) or "battle_context" in {
            parameter.name for parameter in parameters
        }

    @staticmethod
    def _is_actionable_phase_kind(phase_kind: str, legal_actions) -> bool:
        return bool(legal_actions) and phase_kind not in {
            "combat_wait",
            "pending_end_turn_transition",
            "transition_wait",
            "empty_player_actions",
            "unknown_window",
        }

    def _decide(self, snapshot, legal_actions, battle_context: BattleContext | None = None):
        def invoke_policy():
            if battle_context is not None and self._supports_battle_context():
                return self.policy.decide(snapshot, legal_actions, battle_context=battle_context)
            return self.policy.decide(snapshot, legal_actions)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(invoke_policy)
            try:
                return future.result(timeout=self.config.timeout_seconds)
            except FutureTimeoutError as exc:
                raise InterruptedSessionError("policy timed out") from exc

    def _record(
        self,
        *,
        recorder: JsonlTraceRecorder,
        snapshot,
        legal_actions,
        policy_output,
        bridge_result,
        interrupted: bool,
        step_index: int,
        current_turn_index: int,
        actions_this_turn: int,
        total_actions: int,
        waiting_for_player_turn: bool,
        is_final_step: bool,
        stop_reason: str,
        battle_stop_reason: str,
        step_kind: str | None = None,
        phase_kind: str | None = None,
        transition_elapsed_seconds: float = 0.0,
        reject_category: str = "",
        reject_raw_code: str = "",
        gate_status: str = "",
        gate_reason: str = "",
    ) -> None:
        effective_phase_kind = phase_kind or self._phase_kind(
            snapshot,
            legal_actions,
            player_turn=self._is_player_turn(snapshot),
            pending_end_turn_transition=None,
            previous_phase=None,
        )
        effective_step_kind = step_kind or effective_phase_kind
        battle_context = self._build_battle_context(
            snapshot=snapshot,
            current_turn_index=current_turn_index,
            actions_this_turn=actions_this_turn,
            total_actions=total_actions,
            waiting_for_player_turn=waiting_for_player_turn,
            phase_kind=effective_phase_kind,
        )
        recorder.append(
            TraceEntry(
                session_id=snapshot.session_id,
                decision_id=snapshot.decision_id,
                state_version=snapshot.state_version,
                phase=snapshot.phase,
                legal_actions=[to_dict(action) for action in legal_actions],
                observation=to_dict(snapshot),
                policy_output=to_dict(policy_output),
                bridge_result=to_dict(bridge_result),
                battle_context=to_dict(battle_context),
                step_index=step_index,
                current_turn_index=current_turn_index,
                actions_this_turn=actions_this_turn,
                total_actions=total_actions,
                waiting_for_player_turn=waiting_for_player_turn,
                rejects_total=self._rejects_total,
                recoverable_rejects=self._recoverable_rejects,
                hard_rejects=self._hard_rejects,
                recovery_attempts=self._recovery_attempts,
                recovery_successes=self._recovery_successes,
                recovery_streak=self._recovery_streak,
                last_recovery_reason=self._last_recovery_reason,
                reject_category=reject_category,
                reject_raw_code=reject_raw_code,
                gate_status=gate_status,
                gate_reason=gate_reason,
                gate_wait_steps=self._gate_wait_steps,
                gate_redecisions=self._gate_redecisions,
                gate_rebases=self._gate_rebases,
                phase_kind=effective_phase_kind,
                step_kind=effective_step_kind,
                transition_elapsed_seconds=transition_elapsed_seconds,
                transition_attempt=self._transition_attempt,
                reward_actions_taken=self._reward_actions_taken,
                map_actions_taken=self._map_actions_taken,
                non_combat_steps=self._non_combat_steps,
                next_combat_entered=self._next_combat_entered,
                is_final_step=is_final_step,
                stop_reason=stop_reason,
                battle_stop_reason=battle_stop_reason,
                interrupted=interrupted,
                timestamp=datetime.now(UTC).isoformat(),
            )
        )
        self._last_battle_context = to_dict(battle_context)
        self._append_battle_history(
            snapshot=snapshot,
            policy_output=policy_output,
            bridge_result=bridge_result if isinstance(bridge_result, dict) else to_dict(bridge_result),
            current_turn_index=current_turn_index,
            actions_this_turn=actions_this_turn,
            total_actions=total_actions,
            waiting_for_player_turn=waiting_for_player_turn,
            phase_kind=effective_phase_kind,
            step_kind=effective_step_kind,
            step_index=step_index,
        )

    def _finish(
        self,
        session_id: str,
        trace_path: Path,
        *,
        reason: str,
        completed: bool,
        interrupted: bool,
        turn_completed: bool = False,
        battle_completed: bool = False,
        actions_this_turn: int = 0,
        turns_completed: int = 0,
        total_actions: int = 0,
        current_turn_index: int = 0,
    ) -> RunSummary:
        self._clear_agent_status()
        return RunSummary(
            session_id=session_id,
            completed=completed,
            interrupted=interrupted,
            decisions=total_actions,
            trace_path=str(trace_path),
            reason=reason,
            turn_completed=turn_completed,
            actions_this_turn=actions_this_turn,
            battle_completed=battle_completed,
            turns_completed=turns_completed,
            total_actions=total_actions,
            current_turn_index=current_turn_index,
            reward_actions_taken=self._reward_actions_taken,
            map_actions_taken=self._map_actions_taken,
            non_combat_steps=self._non_combat_steps,
            next_combat_entered=self._next_combat_entered,
            rejects_total=self._rejects_total,
            recoverable_rejects=self._recoverable_rejects,
            hard_rejects=self._hard_rejects,
            gate_intercepts=self._gate_intercepts,
            gate_wait_steps=self._gate_wait_steps,
            gate_redecisions=self._gate_redecisions,
            gate_rebases=self._gate_rebases,
            reject_counts=dict(self._reject_counts),
            reject_code_counts=dict(self._reject_code_counts),
            last_reject=dict(self._last_reject),
            recovery_attempts=self._recovery_attempts,
            recovery_successes=self._recovery_successes,
            recovery_streak=self._recovery_streak,
            last_recovery_reason=self._last_recovery_reason,
            battle_context=dict(self._last_battle_context),
            ended_by=reason,
        )

    def _battle_completion_reason(self, snapshot) -> str:
        if self.config.stop_after_player_turn:
            return ""
        metadata = getattr(snapshot, "metadata", {}) or {}
        if str(metadata.get("window_kind") or "").strip().lower() == "combat_transition" or metadata.get("reward_pending"):
            return ""
        phase = self._normalize_phase(getattr(snapshot, "phase", ""))
        if phase == "reward" and self._normalized_reward_mode() != "halt":
            return ""
        if phase == "map" and self._normalized_map_mode() != "halt":
            return ""
        if phase == "event" and self._normalized_event_mode() != "halt":
            return ""
        if phase == "shop" and self._normalized_shop_mode() != "halt":
            return ""
        if phase != "combat":
            return "battle_completed"
        enemies = getattr(snapshot, "enemies", []) or []
        if enemies and not any(getattr(enemy, "is_alive", True) for enemy in enemies):
            return "battle_completed"
        if not enemies:
            return "battle_completed"
        return ""

    def _transition_wait_reason(self, snapshot) -> str:
        metadata = getattr(snapshot, "metadata", {}) or {}
        window_kind = str(metadata.get("window_kind") or "").strip().lower()
        if window_kind:
            return window_kind
        detection = metadata.get("phase_detection")
        if isinstance(detection, dict):
            reward_subphase = detection.get("reward_subphase")
            if isinstance(reward_subphase, str) and reward_subphase.strip():
                return reward_subphase.strip().lower()
        return f"{self._normalize_phase(getattr(snapshot, 'phase', ''))}_transition_wait"

    def _select_reward_action(self, snapshot, legal_actions, reward_mode: str):
        metadata = getattr(snapshot, "metadata", {}) or {}
        reward_subphase = str(metadata.get("reward_subphase") or "").strip().lower()
        advance_action = next((action for action in legal_actions if action.type == "advance_reward"), None)
        if advance_action is not None and reward_subphase == "reward_advance":
            return advance_action
        if reward_mode not in {"skip", "skip-only", "safe-default"}:
            return None
        skip_action = next((action for action in legal_actions if action.type == "skip_reward"), None)
        if skip_action is not None and reward_mode in {"skip", "skip-only"}:
            return skip_action
        if reward_mode in {"skip", "skip-only"}:
            return None
        reward_actions = [action for action in legal_actions if action.type == "choose_reward"]
        if not reward_actions:
            return skip_action
        for action in reward_actions:
            label = str(action.label or action.params.get("reward") or "").lower()
            if "gold" in label or "金币" in label:
                return action
        if reward_subphase == "card_reward_selection":
            return reward_actions[0]
        return reward_actions[0]

    def _select_map_action(self, legal_actions, map_mode: str):
        if map_mode != "safe-default":
            return None
        candidates = [action for action in legal_actions if action.type == "choose_map_node"]
        if not candidates:
            return None
        ranked = sorted(candidates, key=self._map_action_rank)
        return ranked[0]

    @staticmethod
    def _select_event_action(snapshot, legal_actions, event_mode: str):
        if event_mode != "safe-default":
            return None
        metadata = getattr(snapshot, "metadata", {}) or {}
        window_kind = str(metadata.get("window_kind") or "").strip().lower()
        continue_action = next((action for action in legal_actions if action.type == "continue_event"), None)
        choice_actions = [action for action in legal_actions if action.type == "choose_event_option"]
        if window_kind == "event_continue":
            return continue_action
        if choice_actions:
            return choice_actions[0]
        return continue_action

    @staticmethod
    def _select_shop_action(snapshot, legal_actions, shop_mode: str):
        if shop_mode != "safe-default":
            return None
        leave_action = next((action for action in legal_actions if action.type == "leave_shop"), None)
        if leave_action is not None:
            return leave_action
        return None

    @staticmethod
    def _map_action_rank(action) -> tuple[int, int, int, str]:
        text = str(action.params.get("node") or action.label or "").strip().lower()
        danger_score = 3
        if any(token in text for token in ("monster", "combat", "battle", "enemy", "普通战斗")):
            danger_score = 0
        elif any(token in text for token in ("question", "mystery", "event", "?", "事件")):
            danger_score = 1
        elif any(token in text for token in ("shop", "merchant", "商店", "rest", "camp", "篝火")):
            danger_score = 2
        elif any(token in text for token in ("elite", "boss", "精英", "首领")):
            danger_score = 4
        x_value = 999
        y_value = 999
        raw_node = str(action.params.get("node") or "")
        if "@" in raw_node:
            _, _, coord_text = raw_node.rpartition("@")
            parts = [part.strip() for part in coord_text.split(",", maxsplit=1)]
            if len(parts) == 2:
                try:
                    x_value = int(parts[0])
                    y_value = int(parts[1])
                except ValueError:
                    pass
        return (danger_score, x_value, y_value, text)

    def _battle_budget_stop_reason(
        self,
        *,
        total_actions: int,
        turns_completed: int,
        current_turn_index: int,
        consecutive_failures: int,
    ) -> str:
        if self.config.max_total_actions is not None and total_actions >= self.config.max_total_actions:
            return "max_total_actions"
        if self.config.max_turns_per_battle is not None:
            if turns_completed >= self.config.max_turns_per_battle or current_turn_index > self.config.max_turns_per_battle:
                return "max_turns_per_battle"
        if self.config.max_recovery_attempts >= 0 and self._recovery_streak >= self.config.max_recovery_attempts:
            return "recovery_budget_exhausted"
        if self.config.max_consecutive_failures >= 0 and consecutive_failures >= self.config.max_consecutive_failures:
            return "max_consecutive_failures"
        return ""

    def _update_turn_state(
        self,
        snapshot,
        player_turn: bool,
        current_turn_marker: object | None,
        current_turn_index: int,
        current_turn_actions: int,
    ) -> tuple[object | None, int, int]:
        marker = self._current_turn_marker(snapshot, player_turn)
        if player_turn:
            if marker != current_turn_marker:
                current_turn_index += 1
                current_turn_actions = 0
                current_turn_marker = marker
        else:
            current_turn_marker = marker
        return current_turn_marker, current_turn_index, current_turn_actions

    def _current_turn_marker(self, snapshot, player_turn: bool) -> object:
        metadata = getattr(snapshot, "metadata", {}) or {}
        for key in ("round_number", "round", "turn_index", "turn_number"):
            value = metadata.get(key)
            if value is not None and str(value) != "":
                return ("round", str(value), player_turn)
        side = metadata.get("current_side") or metadata.get("turn_owner")
        if isinstance(side, str) and side.strip():
            return ("side", side.strip().lower())
        return ("player_turn", player_turn)

    def _is_player_turn(self, snapshot) -> bool:
        if snapshot.phase != "combat":
            return False
        metadata = getattr(snapshot, "metadata", {}) or {}
        side = metadata.get("current_side") or metadata.get("turn_owner")
        if isinstance(side, str) and side.strip():
            return side.strip().lower() == "player"
        return True

    def _max_actions_per_turn(self) -> int:
        if self.config.max_actions_per_turn is not None:
            return self.config.max_actions_per_turn
        return self.config.max_steps

    @staticmethod
    def _is_only_end_turn(legal_actions) -> bool:
        return len(legal_actions) == 1 and legal_actions[0].type == "end_turn"

    def _post_action_stop_reason(self, action_type: str, policy_output: PolicyDecision, result) -> str:
        if result.terminal:
            return "terminal_action_accepted"
        metadata_phase = str(result.metadata.get("phase") or "")
        if self.config.stop_after_player_turn and action_type == "end_turn":
            if policy_output.metadata.get("auto_end_turn"):
                return "auto_end_turn"
            return "end_turn_submitted"
        if self.config.stop_after_player_turn and metadata_phase and metadata_phase != "combat":
            return "phase_changed"
        return ""

    def _read_consistent_state(self, session_id: str) -> tuple[Any, list[Any]]:
        snapshot = self.bridge.get_snapshot(session_id)
        legal_actions = self.bridge.get_legal_actions(session_id)
        retries = max(1, self.config.state_sync_retries)
        for _ in range(retries):
            confirm_snapshot = self.bridge.get_snapshot(session_id)
            if confirm_snapshot.decision_id == snapshot.decision_id and confirm_snapshot.state_version == snapshot.state_version:
                return snapshot, legal_actions
            snapshot = confirm_snapshot
            legal_actions = self.bridge.get_legal_actions(session_id)
        return snapshot, legal_actions

    def _effective_legal_actions(self, snapshot, legal_actions):
        player = getattr(snapshot, "player", None)
        if player is None:
            return self._apply_same_window_action_filters(snapshot, list(legal_actions))
        hand_by_id = {card.card_id: card for card in player.hand}
        effective_actions = []
        for action in legal_actions:
            if action.type != "play_card":
                effective_actions.append(action)
                continue
            card_id = action.params.get("card_id")
            if not isinstance(card_id, str):
                effective_actions.append(action)
                continue
            card = hand_by_id.get(card_id)
            if card is None:
                continue
            keywords = [str(k).lower() for k in (getattr(card, "keywords", None) or [])]
            if card.playable and card.cost >= 0 and card.cost <= player.energy and "unplayable" not in keywords:
                effective_actions.append(action)
        return self._apply_same_window_action_filters(snapshot, effective_actions)

    @staticmethod
    def _window_action_filter_key(snapshot) -> tuple[str, str, int, str, str]:
        metadata = getattr(snapshot, "metadata", {}) or {}
        return (
            str(getattr(snapshot, "phase", "") or ""),
            str(getattr(snapshot, "decision_id", "") or ""),
            int(getattr(snapshot, "state_version", 0) or 0),
            str(metadata.get("window_kind") or ""),
            str(metadata.get("event_subphase") or ""),
        )

    @staticmethod
    def _same_window_action_signature(action) -> tuple[str, object | None, object | None]:
        params = getattr(action, "params", {}) or {}
        return (
            str(getattr(action, "type", "") or ""),
            params.get("card_id"),
            params.get("option_index"),
            params.get("potion_index"),
            params.get("canonical_potion_id"),
        )

    @classmethod
    def _should_exclude_same_window_action(cls, snapshot, action) -> bool:
        metadata = getattr(snapshot, "metadata", {}) or {}
        if str(getattr(snapshot, "phase", "") or "") != "event":
            return (
                str(getattr(snapshot, "phase", "") or "") == "combat"
                and str(metadata.get("window_kind") or "") == "player_turn"
                and str(getattr(action, "type", "") or "") == "use_potion"
            )
        if str(metadata.get("window_kind") or "") != "event_choice":
            return False
        return str(getattr(action, "type", "") or "") == "choose_event_option"

    def _apply_same_window_action_filters(self, snapshot, legal_actions):
        key = self._window_action_filter_key(snapshot)
        exclusions = self._same_window_action_exclusions.get(key)
        if self._same_window_action_exclusions:
            self._same_window_action_exclusions = {} if exclusions is None else {key: exclusions}
        if not exclusions:
            return legal_actions
        filtered = [
            action
            for action in legal_actions
            if not (
                self._should_exclude_same_window_action(snapshot, action)
                and self._same_window_action_signature(action) in exclusions
            )
        ]
        return filtered or legal_actions

    def _note_same_window_action(self, snapshot, action, result) -> None:
        if not self._should_exclude_same_window_action(snapshot, action):
            return
        if str(getattr(result, "status", "") or "") != "accepted":
            return
        key = self._window_action_filter_key(snapshot)
        exclusions = self._same_window_action_exclusions.setdefault(key, set())
        exclusions.add(self._same_window_action_signature(action))

    @staticmethod
    def _policy_action_args(policy_output: PolicyDecision | None) -> dict[str, object]:
        if policy_output is None:
            return {}
        raw_args = policy_output.metadata.get("action_args")
        if raw_args is None:
            return {}
        if not isinstance(raw_args, dict):
            raise PolicyDecisionValidationError("policy action_args must be an object")
        return dict(raw_args)

    @classmethod
    def _build_action_args(cls, action, policy_output: PolicyDecision | None = None) -> dict[str, object]:
        args = dict(action.params)
        policy_args = cls._policy_action_args(policy_output)
        for key, value in policy_args.items():
            if key in args and args[key] != value:
                raise PolicyDecisionValidationError(f"policy cannot override legal action param '{key}'")
            args.setdefault(key, value)
        target_constraints = [str(c) for c in action.target_constraints]
        target_id = args.get("target_id")
        if target_id is not None:
            # Normalize target_id to string as most LLMs might return integers.
            target_id = str(target_id)
            args["target_id"] = target_id

        if not target_constraints:
            if target_id is not None:
                # Some LLMs may provide a redundant target_id even for non-targeted actions.
                # We log this (if we had a logger here) and just strip it to be more robust.
                args.pop("target_id", None)
            return args

        if target_id is None:
            if len(target_constraints) == 1:
                args["target_id"] = target_constraints[0]
                return args
            raise PolicyDecisionValidationError("policy must provide args.target_id for multi-target actions")

        if target_id not in target_constraints:
            raise PolicyDecisionValidationError("policy target_id is outside the legal target set")
        return args

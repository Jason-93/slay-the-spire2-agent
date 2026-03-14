from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sts2_agent.bridge import BridgeError, GameBridge, InvalidPayloadError, InterruptedSessionError, StaleActionError
from sts2_agent.models import ActionSubmission, PolicyDecision, RunSummary, TraceEntry, to_dict
from sts2_agent.policy import PolicyError
from sts2_agent.trace import JsonlTraceRecorder


@dataclass(slots=True)
class OrchestratorConfig:
    timeout_seconds: float = 2.0
    max_steps: int = 32
    max_actions_per_turn: int | None = None
    stop_after_player_turn: bool = True
    auto_end_turn_when_only_end_turn: bool = True
    trace_dir: str = "traces"
    dry_run: bool = False


class AutoplayOrchestrator:
    def __init__(self, bridge: GameBridge, policy, config: OrchestratorConfig | None = None) -> None:
        self.bridge = bridge
        self.policy = policy
        self.config = config or OrchestratorConfig()
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self, scenario: str = "combat_reward_map_terminal") -> RunSummary:
        session = self.bridge.attach_or_start(scenario=scenario)
        trace_path = Path(self.config.trace_dir) / f"{session.session_id}.jsonl"
        recorder = JsonlTraceRecorder(trace_path)
        decisions = 0
        actions_this_turn = 0

        for step_index in range(1, self.config.max_steps + 1):
            snapshot = self.bridge.get_snapshot(session.session_id)
            legal_actions = self.bridge.get_legal_actions(session.session_id)
            if snapshot.terminal:
                return self._finish(
                    session.session_id,
                    decisions,
                    trace_path,
                    reason="terminal_state_reached",
                    completed=True,
                    interrupted=False,
                    turn_completed=True,
                    actions_this_turn=actions_this_turn,
                )
            if self._stop_requested:
                try:
                    self.bridge.stop(session.session_id)
                except BridgeError:
                    pass
                return self._finish(
                    session.session_id,
                    decisions,
                    trace_path,
                    reason="manual_stop",
                    completed=False,
                    interrupted=True,
                    actions_this_turn=actions_this_turn,
                )
            if self.config.stop_after_player_turn and snapshot.phase != "combat":
                return self._finish(
                    session.session_id,
                    decisions,
                    trace_path,
                    reason="phase_changed",
                    completed=actions_this_turn > 0,
                    interrupted=actions_this_turn == 0,
                    turn_completed=actions_this_turn > 0,
                    actions_this_turn=actions_this_turn,
                )
            if snapshot.phase == "combat" and actions_this_turn >= self._max_actions_per_turn():
                return self._finish(
                    session.session_id,
                    decisions,
                    trace_path,
                    reason="max_actions_per_turn",
                    completed=False,
                    interrupted=True,
                    actions_this_turn=actions_this_turn,
                )
            if not legal_actions:
                return self._finish(
                    session.session_id,
                    decisions,
                    trace_path,
                    reason="no_legal_actions",
                    completed=actions_this_turn > 0,
                    interrupted=actions_this_turn == 0,
                    turn_completed=actions_this_turn > 0,
                    actions_this_turn=actions_this_turn,
                )
            if snapshot.phase == "combat" and self._is_only_end_turn(legal_actions):
                if self.config.auto_end_turn_when_only_end_turn and not self.config.dry_run:
                    auto_end_turn = legal_actions[0]
                    policy_output = PolicyDecision(
                        action_id=auto_end_turn.action_id,
                        reason="only end_turn remains; runner auto ends turn",
                        metadata={"auto_end_turn": True},
                    )
                    result = self.bridge.submit_action(
                        ActionSubmission(
                            session_id=snapshot.session_id,
                            decision_id=snapshot.decision_id,
                            state_version=snapshot.state_version,
                            action_id=auto_end_turn.action_id,
                            args=self._build_action_args(auto_end_turn),
                    )
                    )
                    decisions += 1
                    if snapshot.phase == "combat":
                        actions_this_turn += 1
                    self._record(
                        recorder,
                        snapshot,
                        legal_actions,
                        policy_output,
                        to_dict(result),
                        False,
                        step_index,
                        actions_this_turn,
                        True,
                        "auto_end_turn",
                    )
                    return self._finish(
                        session.session_id,
                        decisions,
                        trace_path,
                        reason="auto_end_turn",
                        completed=True,
                        interrupted=False,
                        turn_completed=True,
                        actions_this_turn=actions_this_turn,
                    )
                return self._finish(
                    session.session_id,
                    decisions,
                    trace_path,
                    reason="end_turn_only",
                    completed=True,
                    interrupted=False,
                    turn_completed=True,
                    actions_this_turn=actions_this_turn,
                )

            try:
                policy_output = self._decide(snapshot, legal_actions)
                if policy_output.halt or not policy_output.action_id:
                    self._record(
                        recorder,
                        snapshot,
                        legal_actions,
                        policy_output,
                        {"status": "interrupted", "reason": "policy_halt"},
                        True,
                        step_index,
                        actions_this_turn,
                        True,
                        "policy_halt",
                    )
                    return self._finish(
                        session.session_id,
                        decisions,
                        trace_path,
                        reason="policy_halt",
                        completed=False,
                        interrupted=True,
                        actions_this_turn=actions_this_turn,
                    )

                legal_actions_by_id = {action.action_id: action for action in legal_actions}
                if policy_output.action_id not in legal_actions_by_id:
                    raise InvalidPayloadError("policy returned an action outside the legal action set")
                selected_action = legal_actions_by_id[policy_output.action_id]

                if self.config.dry_run:
                    self._record(
                        recorder,
                        snapshot,
                        legal_actions,
                        policy_output,
                        {
                            "status": "dry_run",
                            "planned_action_id": policy_output.action_id,
                            "message": "dry run enabled; bridge submission skipped",
                        },
                        False,
                        step_index,
                        actions_this_turn,
                        True,
                        "dry_run",
                    )
                    return self._finish(
                        session.session_id,
                        decisions,
                        trace_path,
                        reason="dry_run",
                        completed=False,
                        interrupted=True,
                        actions_this_turn=actions_this_turn,
                    )

                result = self.bridge.submit_action(
                    ActionSubmission(
                        session_id=snapshot.session_id,
                        decision_id=snapshot.decision_id,
                        state_version=snapshot.state_version,
                        action_id=policy_output.action_id,
                        args=self._build_action_args(selected_action),
                    )
                )
                decisions += 1
                if snapshot.phase == "combat":
                    actions_this_turn += 1
                stop_reason = self._post_action_stop_reason(selected_action.type, policy_output, result)
                self._record(
                    recorder,
                    snapshot,
                    legal_actions,
                    policy_output,
                    to_dict(result),
                    False,
                    step_index,
                    actions_this_turn,
                    bool(stop_reason),
                    stop_reason,
                )
                if stop_reason:
                    return self._finish(
                        session.session_id,
                        decisions,
                        trace_path,
                        reason=stop_reason,
                        completed=True,
                        interrupted=False,
                        turn_completed=True,
                        actions_this_turn=actions_this_turn,
                    )
            except (StaleActionError, InvalidPayloadError, InterruptedSessionError, BridgeError) as exc:
                interrupted_payload = {"status": "interrupted", "error_code": getattr(exc, "error_code", "bridge_error"), "message": str(exc)}
                fallback_output = locals().get("policy_output", PolicyDecision(action_id=None, reason="policy unavailable", halt=True))
                self._record(
                    recorder,
                    snapshot,
                    legal_actions,
                    fallback_output,
                    interrupted_payload,
                    True,
                    step_index,
                    actions_this_turn,
                    True,
                    interrupted_payload["error_code"],
                )
                return self._finish(
                    session.session_id,
                    decisions,
                    trace_path,
                    reason=interrupted_payload["error_code"],
                    completed=False,
                    interrupted=True,
                    actions_this_turn=actions_this_turn,
                )
            except PolicyError as exc:
                interrupted_payload = {"status": "interrupted", "error_code": getattr(exc, "error_code", "policy_error"), "message": str(exc)}
                fallback_output = PolicyDecision(action_id=None, reason=str(exc), halt=True, metadata={"error_code": interrupted_payload["error_code"]})
                self._record(
                    recorder,
                    snapshot,
                    legal_actions,
                    fallback_output,
                    interrupted_payload,
                    True,
                    step_index,
                    actions_this_turn,
                    True,
                    interrupted_payload["error_code"],
                )
                return self._finish(
                    session.session_id,
                    decisions,
                    trace_path,
                    reason=interrupted_payload["error_code"],
                    completed=False,
                    interrupted=True,
                    actions_this_turn=actions_this_turn,
                )

        return self._finish(
            session.session_id,
            decisions,
            trace_path,
            reason="max_steps_exceeded",
            completed=False,
            interrupted=True,
            actions_this_turn=actions_this_turn,
        )

    def _decide(self, snapshot, legal_actions):
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.policy.decide, snapshot, legal_actions)
            try:
                return future.result(timeout=self.config.timeout_seconds)
            except FutureTimeoutError as exc:
                raise InterruptedSessionError("policy timed out") from exc

    def _record(
        self,
        recorder,
        snapshot,
        legal_actions,
        policy_output,
        bridge_result,
        interrupted,
        step_index,
        actions_this_turn,
        is_final_step,
        stop_reason,
    ):
        recorder.append(
            TraceEntry(
                session_id=snapshot.session_id,
                decision_id=snapshot.decision_id,
                state_version=snapshot.state_version,
                phase=snapshot.phase,
                legal_actions=[to_dict(action) for action in legal_actions],
                observation=to_dict(snapshot),
                policy_output=to_dict(policy_output),
                bridge_result=bridge_result,
                step_index=step_index,
                actions_this_turn=actions_this_turn,
                is_final_step=is_final_step,
                stop_reason=stop_reason,
                interrupted=interrupted,
                timestamp=datetime.now(UTC).isoformat(),
            )
        )

    def _finish(
        self,
        session_id: str,
        decisions: int,
        trace_path: Path,
        *,
        reason: str,
        completed: bool,
        interrupted: bool,
        turn_completed: bool = False,
        actions_this_turn: int = 0,
    ) -> RunSummary:
        return RunSummary(
            session_id=session_id,
            completed=completed,
            interrupted=interrupted,
            decisions=decisions,
            trace_path=str(trace_path),
            reason=reason,
            turn_completed=turn_completed,
            actions_this_turn=actions_this_turn,
            ended_by=reason,
        )

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

    @staticmethod
    def _build_action_args(action) -> dict[str, object]:
        args = dict(action.params)
        if len(action.target_constraints) == 1 and "target_id" not in args:
            args["target_id"] = action.target_constraints[0]
        return args

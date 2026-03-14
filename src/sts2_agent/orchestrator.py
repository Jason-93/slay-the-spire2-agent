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

        for _ in range(self.config.max_steps):
            snapshot = self.bridge.get_snapshot(session.session_id)
            legal_actions = self.bridge.get_legal_actions(session.session_id)
            if snapshot.terminal:
                return RunSummary(
                    session_id=session.session_id,
                    completed=True,
                    interrupted=False,
                    decisions=decisions,
                    trace_path=str(trace_path),
                    reason="terminal_state_reached",
                )
            if self._stop_requested:
                self.bridge.stop(session.session_id)
                return RunSummary(
                    session_id=session.session_id,
                    completed=False,
                    interrupted=True,
                    decisions=decisions,
                    trace_path=str(trace_path),
                    reason="manual_stop",
                )

            try:
                policy_output = self._decide(snapshot, legal_actions)
                if policy_output.halt or not policy_output.action_id:
                    self._record(recorder, snapshot, legal_actions, policy_output, {"status": "interrupted", "reason": "policy_halt"}, True)
                    return RunSummary(
                        session_id=session.session_id,
                        completed=False,
                        interrupted=True,
                        decisions=decisions,
                        trace_path=str(trace_path),
                        reason="policy_halt",
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
                    )
                    return RunSummary(
                        session_id=session.session_id,
                        completed=False,
                        interrupted=True,
                        decisions=decisions,
                        trace_path=str(trace_path),
                        reason="dry_run",
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
                self._record(recorder, snapshot, legal_actions, policy_output, to_dict(result), False)
                if result.terminal:
                    return RunSummary(
                        session_id=session.session_id,
                        completed=True,
                        interrupted=False,
                        decisions=decisions,
                        trace_path=str(trace_path),
                        reason="terminal_action_accepted",
                    )
            except (StaleActionError, InvalidPayloadError, InterruptedSessionError, BridgeError) as exc:
                interrupted_payload = {"status": "interrupted", "error_code": getattr(exc, "error_code", "bridge_error"), "message": str(exc)}
                fallback_output = locals().get("policy_output", PolicyDecision(action_id=None, reason="policy unavailable", halt=True))
                self._record(recorder, snapshot, legal_actions, fallback_output, interrupted_payload, True)
                return RunSummary(
                    session_id=session.session_id,
                    completed=False,
                    interrupted=True,
                    decisions=decisions,
                    trace_path=str(trace_path),
                    reason=interrupted_payload["error_code"],
                )
            except PolicyError as exc:
                interrupted_payload = {"status": "interrupted", "error_code": getattr(exc, "error_code", "policy_error"), "message": str(exc)}
                fallback_output = PolicyDecision(action_id=None, reason=str(exc), halt=True, metadata={"error_code": interrupted_payload["error_code"]})
                self._record(recorder, snapshot, legal_actions, fallback_output, interrupted_payload, True)
                return RunSummary(
                    session_id=session.session_id,
                    completed=False,
                    interrupted=True,
                    decisions=decisions,
                    trace_path=str(trace_path),
                    reason=interrupted_payload["error_code"],
                )

        return RunSummary(
            session_id=session.session_id,
            completed=False,
            interrupted=True,
            decisions=decisions,
            trace_path=str(trace_path),
            reason="max_steps_exceeded",
        )

    def _decide(self, snapshot, legal_actions):
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.policy.decide, snapshot, legal_actions)
            try:
                return future.result(timeout=self.config.timeout_seconds)
            except FutureTimeoutError as exc:
                raise InterruptedSessionError("policy timed out") from exc

    def _record(self, recorder, snapshot, legal_actions, policy_output, bridge_result, interrupted):
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
                interrupted=interrupted,
                timestamp=datetime.now(UTC).isoformat(),
            )
        )

    @staticmethod
    def _build_action_args(action) -> dict[str, object]:
        args = dict(action.params)
        if len(action.target_constraints) == 1 and "target_id" not in args:
            args["target_id"] = action.target_constraints[0]
        return args

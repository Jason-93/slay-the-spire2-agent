from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sts2_agent.bridge.base import (
    BridgeSession,
    GameBridge,
    InvalidPayloadError,
    RemoteBridgeError,
    SessionNotFoundError,
    StaleActionError,
    UnsupportedLifecycleCommandError,
)
from sts2_agent.models import ActionResult, ActionSubmission, CardView, DecisionSnapshot, EnemyState, LegalAction, PlayerState


@dataclass(slots=True)
class HttpGameBridgeConfig:
    base_url: str = "http://127.0.0.1:17654"
    timeout_seconds: float = 5.0
    scenario: str = "live_http_bridge"


class HttpGameBridge(GameBridge):
    def __init__(self, config: HttpGameBridgeConfig | None = None) -> None:
        self.config = config or HttpGameBridgeConfig()
        self._sessions: dict[str, BridgeSession] = {}

    def attach_or_start(self, scenario: str = "combat_reward_map_terminal") -> BridgeSession:
        self._read_json("/health")
        snapshot = self._read_json("/snapshot")
        session = BridgeSession(
            session_id=str(snapshot.get("session_id") or scenario or self.config.scenario),
            scenario=scenario or self.config.scenario,
            state_version=int(snapshot.get("state_version") or 0),
            metadata={"base_url": self.config.base_url},
        )
        self._sessions[session.session_id] = session
        return session

    def get_snapshot(self, session_id: str) -> DecisionSnapshot:
        session = self._require_session(session_id)
        payload = self._read_json("/snapshot")
        snapshot = self._decode_snapshot(payload)
        session.state_version = snapshot.state_version
        return snapshot

    def get_legal_actions(self, session_id: str) -> list[LegalAction]:
        self._require_session(session_id)
        payload = self._read_json("/actions")
        if not isinstance(payload, list):
            raise RemoteBridgeError("bridge /actions returned a non-list payload", error_code="invalid_payload")
        actions: list[LegalAction] = []
        for item in payload:
            if not isinstance(item, dict):
                raise RemoteBridgeError("bridge /actions returned an invalid action payload", error_code="invalid_payload")
            actions.append(
                LegalAction(
                    action_id=str(item.get("action_id") or ""),
                    type=str(item.get("type") or ""),
                    label=str(item.get("label") or item.get("type") or ""),
                    params=dict(item.get("params") or {}),
                    target_constraints=list(item.get("target_constraints") or []),
                    metadata=dict(item.get("metadata") or {}),
                )
            )
        return actions

    def submit_action(self, submission: ActionSubmission) -> ActionResult:
        session = self._require_session(submission.session_id)
        payload = {
            "decision_id": submission.decision_id,
            "action_id": submission.action_id,
            "params": submission.args,
        }
        response = self._post_json("/apply", payload)
        status = str(response.get("status") or "")
        error_code = response.get("error_code")
        if status == "accepted":
            metadata = dict(response.get("metadata") or {})
            if "state_version" in metadata:
                session.state_version = int(metadata["state_version"])
            return ActionResult(
                status=status,
                session_id=session.session_id,
                decision_id=str(response.get("decision_id") or submission.decision_id),
                state_version=session.state_version,
                accepted_action_id=str(response.get("action_id") or submission.action_id),
                error_code=None,
                message=str(response.get("message") or ""),
                terminal=False,
                metadata=metadata,
            )

        message = str(response.get("message") or "bridge rejected the action")
        if error_code == "stale_decision":
            raise StaleActionError(message)
        if error_code in {"illegal_action", "invalid_action"}:
            raise InvalidPayloadError(message)
        raise RemoteBridgeError(message, error_code=str(error_code or "bridge_error"))

    def stop(self, session_id: str) -> BridgeSession:
        raise UnsupportedLifecycleCommandError("http bridge does not support remote stop")

    def reset(self, session_id: str) -> BridgeSession:
        raise UnsupportedLifecycleCommandError("http bridge does not support remote reset")

    def _require_session(self, session_id: str) -> BridgeSession:
        if session_id not in self._sessions:
            raise SessionNotFoundError(f"unknown session: {session_id}")
        return self._sessions[session_id]

    def _read_json(self, path: str) -> Any:
        request = Request(self._url(path), method="GET")
        return self._send(request)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self._url(path),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response = self._send(request)
        if not isinstance(response, dict):
            raise RemoteBridgeError("bridge /apply returned a non-object payload", error_code="invalid_payload")
        return response

    def _send(self, request: Request) -> Any:
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = self._decode_error_body(exc)
            if isinstance(body, dict):
                return body
            raise RemoteBridgeError(f"bridge request failed with http {exc.code}", error_code="http_error") from exc
        except URLError as exc:
            raise RemoteBridgeError(f"bridge connection failed: {exc.reason}", error_code="bridge_unreachable") from exc

    @staticmethod
    def _decode_error_body(exc: HTTPError) -> Any:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return None

    def _url(self, path: str) -> str:
        return self.config.base_url.rstrip("/") + path

    @staticmethod
    def _decode_snapshot(payload: Any) -> DecisionSnapshot:
        if not isinstance(payload, dict):
            raise RemoteBridgeError("bridge /snapshot returned a non-object payload", error_code="invalid_payload")

        player_payload = payload.get("player")
        player = None
        if isinstance(player_payload, dict):
            hand = [CardView(**item) for item in player_payload.get("hand", [])]
            player_values = {k: v for k, v in player_payload.items() if k != "hand"}
            player = PlayerState(hand=hand, **player_values)

        enemies = []
        for item in payload.get("enemies", []):
            if isinstance(item, dict):
                enemies.append(EnemyState(**item))

        metadata = dict(payload.get("metadata") or {})
        compatibility = payload.get("compatibility")
        if isinstance(compatibility, dict):
            metadata["compatibility"] = compatibility

        return DecisionSnapshot(
            session_id=str(payload.get("session_id") or ""),
            decision_id=str(payload.get("decision_id") or ""),
            state_version=int(payload.get("state_version") or 0),
            phase=str(payload.get("phase") or "unknown"),
            player=player,
            enemies=enemies,
            rewards=list(payload.get("rewards") or []),
            map_nodes=list(payload.get("map_nodes") or []),
            terminal=bool(payload.get("terminal")),
            metadata=metadata,
        )

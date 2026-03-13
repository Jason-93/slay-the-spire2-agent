from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sts2_agent.models import ActionResult, ActionSubmission, DecisionSnapshot, LegalAction


class BridgeError(RuntimeError):
    error_code = "bridge_error"


class SessionNotFoundError(BridgeError):
    error_code = "session_not_found"


class InvalidPayloadError(BridgeError):
    error_code = "invalid_payload"


class StaleActionError(BridgeError):
    error_code = "stale_action"


class UnsupportedLifecycleCommandError(BridgeError):
    error_code = "unsupported_lifecycle_command"


class InterruptedSessionError(BridgeError):
    error_code = "interrupted"


@dataclass(slots=True)
class BridgeSession:
    session_id: str
    scenario: str
    state_version: int = 0
    interrupted: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class GameBridge(ABC):
    @abstractmethod
    def attach_or_start(self, scenario: str = "combat_reward_map_terminal") -> BridgeSession:
        raise NotImplementedError

    @abstractmethod
    def get_snapshot(self, session_id: str) -> DecisionSnapshot:
        raise NotImplementedError

    @abstractmethod
    def get_legal_actions(self, session_id: str) -> list[LegalAction]:
        raise NotImplementedError

    @abstractmethod
    def submit_action(self, submission: ActionSubmission) -> ActionResult:
        raise NotImplementedError

    @abstractmethod
    def stop(self, session_id: str) -> BridgeSession:
        raise NotImplementedError

    @abstractmethod
    def reset(self, session_id: str) -> BridgeSession:
        raise NotImplementedError

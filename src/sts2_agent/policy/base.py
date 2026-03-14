from __future__ import annotations

from typing import Protocol

from sts2_agent.models import DecisionSnapshot, LegalAction, PolicyDecision


class PolicyError(RuntimeError):
    error_code = "policy_error"


class PolicyDecisionValidationError(PolicyError):
    error_code = "policy_invalid_action_args"


class Policy(Protocol):
    def decide(self, snapshot: DecisionSnapshot, legal_actions: list[LegalAction]) -> PolicyDecision:
        ...

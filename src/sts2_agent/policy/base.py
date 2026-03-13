from __future__ import annotations

from typing import Protocol

from sts2_agent.models import DecisionSnapshot, LegalAction, PolicyDecision


class Policy(Protocol):
    def decide(self, snapshot: DecisionSnapshot, legal_actions: list[LegalAction]) -> PolicyDecision:
        ...

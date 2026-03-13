from __future__ import annotations

from sts2_agent.models import DecisionSnapshot, LegalAction, PolicyDecision


class FirstLegalActionPolicy:
    def decide(self, snapshot: DecisionSnapshot, legal_actions: list[LegalAction]) -> PolicyDecision:
        if not legal_actions:
            return PolicyDecision(action_id=None, reason="no legal actions available", halt=True)
        preferred = next((action for action in legal_actions if action.type not in {"end_turn", "skip"}), legal_actions[0])
        return PolicyDecision(action_id=preferred.action_id, reason=f"select {preferred.type}")

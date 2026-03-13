from __future__ import annotations

import unittest

from sts2_agent.bridge import InvalidPayloadError, MockGameBridge, StaleActionError
from sts2_agent.models import ActionSubmission


class MockBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = MockGameBridge()
        self.session = self.bridge.attach_or_start()

    def test_combat_snapshot_exposes_expected_actions(self) -> None:
        snapshot = self.bridge.get_snapshot(self.session.session_id)
        actions = self.bridge.get_legal_actions(self.session.session_id)

        self.assertEqual(snapshot.phase, "combat")
        self.assertEqual(len(actions), 4)
        self.assertEqual({action.type for action in actions}, {"play_card", "use_potion", "end_turn"})

    def test_bridge_rejects_stale_action_without_state_mutation(self) -> None:
        snapshot = self.bridge.get_snapshot(self.session.session_id)
        first_action = self.bridge.get_legal_actions(self.session.session_id)[0]

        self.bridge.submit_action(
            ActionSubmission(
                session_id=snapshot.session_id,
                decision_id=snapshot.decision_id,
                state_version=snapshot.state_version,
                action_id=first_action.action_id,
            )
        )

        with self.assertRaises(StaleActionError):
            self.bridge.submit_action(
                ActionSubmission(
                    session_id=snapshot.session_id,
                    decision_id=snapshot.decision_id,
                    state_version=snapshot.state_version,
                    action_id=first_action.action_id,
                )
            )

        latest = self.bridge.get_snapshot(self.session.session_id)
        self.assertEqual(latest.state_version, 1)
        self.assertEqual(latest.phase, "reward")

    def test_bridge_rejects_invalid_action(self) -> None:
        snapshot = self.bridge.get_snapshot(self.session.session_id)
        with self.assertRaises(InvalidPayloadError):
            self.bridge.submit_action(
                ActionSubmission(
                    session_id=snapshot.session_id,
                    decision_id=snapshot.decision_id,
                    state_version=snapshot.state_version,
                    action_id="act-not-legal",
                )
            )


if __name__ == "__main__":
    unittest.main()

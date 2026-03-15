from __future__ import annotations

import unittest

from tools.validate_live_apply import detect_progress, select_candidate


class LiveApplyValidationTests(unittest.TestCase):
    def test_select_candidate_prefers_choose_combat_card_in_combat_selection(self) -> None:
        snapshot = {"phase": "combat"}
        actions = [
            {
                "action_id": "act-cancel",
                "type": "cancel_combat_selection",
                "label": "取消",
                "params": {},
                "target_constraints": [],
                "metadata": {"selection_kind": "exhaust_card"},
            },
            {
                "action_id": "act-select",
                "type": "choose_combat_card",
                "label": "消耗 防御",
                "params": {"card_id": "card-2", "selection_index": 0},
                "target_constraints": [],
                "metadata": {"selection_kind": "exhaust_card"},
            },
        ]

        candidate = select_candidate(snapshot, actions)

        self.assertIsNotNone(candidate.action)
        self.assertEqual(candidate.action["action_id"], "act-select")

    def test_select_candidate_prefers_safe_play_card_in_combat(self) -> None:
        snapshot = {"phase": "combat"}
        actions = [
            {
                "action_id": "act-end",
                "type": "end_turn",
                "label": "End Turn",
                "params": {},
                "target_constraints": [],
            },
            {
                "action_id": "act-card",
                "type": "play_card",
                "label": "打击",
                "params": {"card_id": "card-1"},
                "target_constraints": [],
            },
        ]

        candidate = select_candidate(snapshot, actions)

        self.assertIsNotNone(candidate.action)
        self.assertEqual(candidate.action["action_id"], "act-card")

    def test_select_candidate_skips_ambiguous_map_choices(self) -> None:
        snapshot = {"phase": "map"}
        actions = [
            {"action_id": "map-1", "type": "choose_map_node", "label": "左", "params": {}, "target_constraints": []},
            {"action_id": "map-2", "type": "choose_map_node", "label": "右", "params": {}, "target_constraints": []},
        ]

        candidate = select_candidate(snapshot, actions)

        self.assertIsNone(candidate.action)
        self.assertIn("不存在满足默认安全策略的候选动作", candidate.reason)

    def test_detect_progress_reports_decision_change_and_card_consumed(self) -> None:
        before_snapshot = {
            "decision_id": "dec-1",
            "phase": "combat",
            "state_version": 1,
            "player": {"energy": 3, "hand": [{"card_id": "card-1"}, {"card_id": "card-2"}]},
        }
        before_actions = [
            {"action_id": "act-card", "type": "play_card"},
            {"action_id": "act-end", "type": "end_turn"},
        ]
        after_snapshot = {
            "decision_id": "dec-2",
            "phase": "combat",
            "state_version": 2,
            "player": {"energy": 2, "hand": [{"card_id": "card-2"}]},
        }
        after_actions = [{"action_id": "act-end", "type": "end_turn"}]
        candidate = {"action_id": "act-card", "params": {"card_id": "card-1"}}

        evidence = detect_progress(before_snapshot, before_actions, after_snapshot, after_actions, candidate)

        self.assertIn("decision_id_changed", evidence)
        self.assertIn("state_version_changed", evidence)
        self.assertIn("action_no_longer_legal", evidence)
        self.assertIn("selected_card_left_hand", evidence)
        self.assertIn("player_energy_changed", evidence)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from tools.validate_live_apply import audit_card_descriptions, contains_description_placeholder, detect_progress, select_candidate


class LiveApplyValidationTests(unittest.TestCase):
    def test_contains_description_placeholder_detects_template_dsl(self) -> None:
        self.assertTrue(contains_description_placeholder("获得9点**格挡**。\n{IfUpgraded:show:| 随机}**消耗**1张牌。"))
        self.assertFalse(contains_description_placeholder("获得9点**格挡**。\n**消耗**1张牌。"))

    def test_audit_card_descriptions_reports_placeholders_and_preview_mismatch(self) -> None:
        snapshot = {
            "phase": "combat",
            "player": {
                "hand": [
                    {
                        "card_id": "card-true-grit",
                        "description": "获得9点**格挡**。\n{IfUpgraded:show:| 随机}**消耗**1张牌。",
                    }
                ],
                "draw_pile_cards": [],
                "discard_pile_cards": [],
                "exhaust_pile_cards": [],
                "relics": [],
                "potions": [],
            },
        }
        actions = [
            {
                "action_id": "act-play",
                "type": "play_card",
                "metadata": {
                    "card_preview": {
                        "card_id": "card-true-grit",
                        "description": "获得9点**格挡**。\n**消耗**1张牌。",
                    }
                },
            }
        ]

        audit = audit_card_descriptions(snapshot, actions)

        self.assertEqual(audit["placeholder_description_count"], 1)
        self.assertIn("snapshot.player.hand[0].description", audit["placeholder_description_paths"])
        self.assertEqual(audit["preview_mismatch_count"], 1)
        self.assertEqual(audit["preview_mismatches"][0]["card_id"], "card-true-grit")
        self.assertEqual(audit["low_quality_relic_glossary_count"], 0)
        self.assertEqual(audit["low_quality_potion_glossary_count"], 0)

    def test_audit_card_descriptions_reports_low_quality_relic_glossary(self) -> None:
        snapshot = {
            "phase": "combat",
            "player": {
                "hand": [],
                "draw_pile_cards": [],
                "discard_pile_cards": [],
                "exhaust_pile_cards": [],
                "potions": [],
                "relics": [
                    {
                        "name": "永冻冰晶",
                        "description": "当你在战斗中第一次打出能力牌时，获得6点**格挡**。",
                        "glossary": [
                            {
                                "glossary_id": "block",
                                "display_text": "格挡",
                                "hint": None,
                                "source": "missing_hint",
                            },
                            {
                                "glossary_id": "relicpermafrost",
                                "display_text": "永冻冰晶",
                                "hint": "当你在战斗中第一次打出能力牌时，获得{Block}点**格挡**。",
                                "source": "runtime_hover_tip",
                            },
                        ],
                    }
                ],
            },
        }

        audit = audit_card_descriptions(snapshot, [])

        self.assertEqual(audit["low_quality_relic_glossary_count"], 2)
        self.assertEqual(audit["low_quality_relic_glossary"][0]["reason"], "empty_hint")
        self.assertEqual(audit["low_quality_relic_glossary"][1]["reason"], "template_hint")

    def test_audit_card_descriptions_reports_low_quality_potion_glossary(self) -> None:
        snapshot = {
            "phase": "combat",
            "player": {
                "hand": [],
                "draw_pile_cards": [],
                "discard_pile_cards": [],
                "exhaust_pile_cards": [],
                "relics": [],
                "potions": [
                    {
                        "name": "肌肉药水",
                        "description": "获得5点**力量**。在你的这个回合结束时，失去5点**力量**。",
                        "canonical_potion_id": "POTION.FLEX_POTION",
                        "glossary": [
                            {
                                "glossary_id": "potionflexpotion",
                                "display_text": "肌肉药水",
                                "hint": "获得{StrengthPower}点**力量**。在你的这个回合结束时，失去{StrengthPower}点**力量**。",
                                "source": "runtime_hover_tip",
                            },
                            {
                                "glossary_id": "strength",
                                "display_text": "力量",
                                "hint": "使攻击造成更多伤害。",
                                "source": "runtime_hover_tip",
                            },
                        ],
                    }
                ],
            },
        }

        audit = audit_card_descriptions(snapshot, [])

        self.assertEqual(audit["low_quality_potion_glossary_count"], 1)
        self.assertEqual(audit["low_quality_potion_glossary"][0]["reason"], "template_hint")

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

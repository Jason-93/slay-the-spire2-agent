from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.validate_reward_map_next_battle import choose_action, is_empty_reward_window, run_validation


class RewardMapNextBattleValidationTests(unittest.TestCase):
    def test_choose_action_prefers_advance_reward_on_reward_advance_screen(self) -> None:
        snapshot = {
            "phase": "reward",
            "metadata": {
                "reward_subphase": "reward_advance",
                "window_kind": "reward_advance",
                "reward_count": 0,
            },
        }
        actions = [
            {
                "action_id": "act-advance",
                "type": "advance_reward",
                "label": "前进",
                "params": {"button_label": "前进"},
                "target_constraints": [],
            }
        ]

        candidate, reason = choose_action(snapshot, actions)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["type"], "advance_reward")
        self.assertIn("前进", reason)

    def test_choose_action_prefers_gold_reward_before_skip(self) -> None:
        snapshot = {"phase": "reward", "metadata": {"reward_subphase": "reward_choice", "reward_count": 2}}
        actions = [
            {
                "action_id": "act-skip",
                "type": "skip_reward",
                "label": "Skip Reward",
                "params": {},
                "target_constraints": [],
            },
            {
                "action_id": "act-gold",
                "type": "choose_reward",
                "label": "Choose 17金币",
                "params": {"reward": "17金币", "reward_index": 0},
                "target_constraints": [],
            },
        ]

        candidate, _ = choose_action(snapshot, actions)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["action_id"], "act-gold")

    def test_empty_reward_window_is_detected(self) -> None:
        snapshot = {
            "phase": "reward",
            "metadata": {
                "window_kind": "reward_choice",
                "reward_count": 0,
            },
        }

        self.assertTrue(is_empty_reward_window(snapshot, []))
        self.assertFalse(is_empty_reward_window(snapshot, [{"action_id": "a", "type": "advance_reward"}]))

    def test_run_validation_succeeds_once_map_is_reached_by_default(self) -> None:
        reward_snapshot = {
            "phase": "reward",
            "decision_id": "dec-reward",
            "metadata": {"window_kind": "reward_advance", "reward_subphase": "reward_advance", "reward_count": 0},
        }
        map_snapshot = {
            "phase": "map",
            "decision_id": "dec-map",
            "metadata": {"window_kind": "map_ready"},
        }
        actions = [
            {
                "action_id": "act-advance",
                "type": "advance_reward",
                "label": "ProceedButton",
                "params": {"button_label": "ProceedButton"},
                "target_constraints": [],
                "metadata": {},
            }
        ]
        args = SimpleNamespace(
            artifact_root="unused",
            port=17654,
            apply=True,
            allow_write=True,
            max_steps=4,
            transition_timeout_seconds=1.0,
            poll_interval_seconds=0.0,
            require_next_combat=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "tools.validate_reward_map_next_battle.create_artifact_dir",
            return_value=Path(tmpdir),
        ), patch(
            "tools.validate_reward_map_next_battle.read_health",
            return_value={"healthy": True, "provider_mode": "in-game-runtime", "read_only": False},
        ), patch(
            "tools.validate_reward_map_next_battle.ensure_live_runtime",
            return_value="",
        ), patch(
            "tools.validate_reward_map_next_battle.parse_bool_env",
            return_value=True,
        ), patch(
            "tools.validate_reward_map_next_battle.read_snapshot",
            side_effect=[reward_snapshot, map_snapshot],
        ), patch(
            "tools.validate_reward_map_next_battle.read_actions",
            side_effect=[actions, []],
        ), patch(
            "tools.validate_reward_map_next_battle.post_json",
            return_value=(200, {"status": "accepted"}),
        ), patch(
            "tools.validate_reward_map_next_battle.time.sleep",
            return_value=None,
        ):
            result = run_validation(args)

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()

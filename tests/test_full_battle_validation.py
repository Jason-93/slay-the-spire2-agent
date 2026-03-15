from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.validate_full_battle_llm import _build_result


class FullBattleValidationTests(unittest.TestCase):
    def test_build_result_reports_reject_quality_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _build_result(
                artifact_dir=Path(tmpdir),
                health={"provider_mode": "in-game-runtime", "read_only": False},
                summary={
                    "completed": True,
                    "interrupted": False,
                    "battle_completed": True,
                    "turns_completed": 3,
                    "total_actions": 8,
                    "current_turn_index": 3,
                    "rejects_total": 3,
                    "recoverable_rejects": 3,
                    "hard_rejects": 0,
                    "gate_intercepts": 1,
                    "reject_counts": {"recoverable_stale": 2, "recoverable_timing": 1},
                    "reject_code_counts": {"stale_action": 2, "not_player_turn": 1},
                    "last_reject": {"raw_code": "not_player_turn"},
                    "recovery_attempts": 3,
                    "recovery_successes": 3,
                    "recovery_streak": 0,
                    "ended_by": "battle_completed",
                    "trace_path": "trace.jsonl",
                },
                trace_tail=[],
            )

        self.assertEqual(result["rejects_total"], 3)
        self.assertAlmostEqual(result["reject_rate"], 3 / 11)
        self.assertEqual(result["quality"], "reject_heavy")
        self.assertEqual(result["gate_intercepts"], 1)
        self.assertEqual(result["last_reject"]["raw_code"], "not_player_turn")


if __name__ == "__main__":
    unittest.main()

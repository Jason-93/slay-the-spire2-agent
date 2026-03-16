from __future__ import annotations

import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sts2_agent.live_autoplay import LiveAutoplayConfig, run_live_autoplay
from sts2_agent.models import RunSummary


class LiveAutoplayTests(unittest.TestCase):
    def test_run_live_autoplay_wires_bridge_policy_and_orchestrator(self) -> None:
        captured = {}

        class FakeOrchestrator:
            def __init__(self, bridge, policy, config) -> None:
                captured["bridge"] = bridge
                captured["policy"] = policy
                captured["config"] = config

            def run(self, scenario: str) -> RunSummary:
                captured["scenario"] = scenario
                return RunSummary(
                    session_id="sess-live1234",
                    completed=True,
                    interrupted=False,
                    decisions=4,
                    trace_path="trace.jsonl",
                    reason="battle_completed",
                    turn_completed=True,
                    actions_this_turn=2,
                    battle_completed=True,
                    turns_completed=2,
                    total_actions=4,
                    current_turn_index=2,
                    ended_by="battle_completed",
                )

        with patch("sts2_agent.live_autoplay.AutoplayOrchestrator", FakeOrchestrator):
            summary = run_live_autoplay(
                LiveAutoplayConfig(
                    bridge_base_url="http://127.0.0.1:17654",
                    llm_base_url="http://127.0.0.1:8080/v1",
                    model="local-model",
                    battle_mode=True,
                    dry_run=True,
                    max_steps=4,
                    max_actions_per_turn=2,
                    max_turns_per_battle=3,
                    max_total_actions=9,
                    max_consecutive_failures=5,
                    max_recovery_attempts=4,
                    wait_for_next_player_turn_seconds=12.5,
                    transition_timeout_seconds=8.0,
                    poll_interval_seconds=0.2,
                    stable_window_required_observations=3,
                    stable_window_timeout_seconds=1.5,
                    max_non_combat_steps=11,
                    unknown_window_fuse=3,
                    battle_context_recent_steps=5,
                    reward_mode="safe-default",
                    map_mode="safe-default",
                    event_mode="safe-default",
                    stop_after_next_combat=True,
                    auto_end_turn_when_only_end_turn=False,
                )
            )

        self.assertEqual(summary.reason, "battle_completed")
        self.assertEqual(captured["bridge"].config.base_url, "http://127.0.0.1:17654")
        self.assertEqual(captured["policy"].config.base_url, "http://127.0.0.1:8080/v1")
        self.assertEqual(captured["policy"].config.model, "local-model")
        self.assertTrue(captured["config"].dry_run)
        self.assertEqual(captured["config"].max_steps, 4)
        self.assertEqual(captured["config"].max_actions_per_turn, 2)
        self.assertFalse(captured["config"].stop_after_player_turn)
        self.assertEqual(captured["config"].max_turns_per_battle, 3)
        self.assertEqual(captured["config"].max_total_actions, 9)
        self.assertEqual(captured["config"].max_consecutive_failures, 5)
        self.assertEqual(captured["config"].max_recovery_attempts, 4)
        self.assertEqual(captured["config"].wait_for_next_player_turn_seconds, 12.5)
        self.assertEqual(captured["config"].transition_timeout_seconds, 8.0)
        self.assertEqual(captured["config"].poll_interval_seconds, 0.2)
        self.assertEqual(captured["config"].stable_window_required_observations, 3)
        self.assertEqual(captured["config"].stable_window_timeout_seconds, 1.5)
        self.assertEqual(captured["config"].max_non_combat_steps, 11)
        self.assertEqual(captured["config"].unknown_window_fuse, 3)
        self.assertEqual(captured["config"].battle_context_recent_steps, 5)
        self.assertEqual(captured["config"].reward_mode, "safe-default")
        self.assertEqual(captured["config"].map_mode, "safe-default")
        self.assertEqual(captured["config"].event_mode, "safe-default")
        self.assertTrue(captured["config"].stop_after_next_combat)
        self.assertFalse(captured["config"].auto_end_turn_when_only_end_turn)

    def test_cli_main_prints_json_summary(self) -> None:
        script_path = Path("tools/run_llm_autoplay.py")
        spec = importlib.util.spec_from_file_location("run_llm_autoplay", script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with patch.object(
            module,
            "run_live_autoplay",
            return_value=RunSummary(
                session_id="sess-live1234",
                completed=True,
                interrupted=False,
                decisions=4,
                trace_path="trace.jsonl",
                reason="battle_completed",
                turn_completed=True,
                actions_this_turn=2,
                battle_completed=True,
                turns_completed=2,
                total_actions=4,
                current_turn_index=2,
                ended_by="battle_completed",
            ),
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = module.main(
                    [
                        "--model",
                        "local-model",
                        "--battle-mode",
                        "--max-turns-per-battle",
                        "5",
                        "--max-total-actions",
                        "12",
                        "--max-recovery-attempts",
                        "5",
                        "--transition-timeout-seconds",
                        "9",
                        "--max-non-combat-steps",
                        "10",
                        "--unknown-window-fuse",
                        "3",
                        "--battle-context-recent-steps",
                        "6",
                        "--reward-mode",
                        "safe-default",
                        "--map-mode",
                        "safe-default",
                        "--event-mode",
                        "safe-default",
                        "--stop-after-next-combat",
                    ]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["reason"], "battle_completed")
        self.assertEqual(payload["decisions"], 4)
        self.assertEqual(payload["battle_completed"], True)
        self.assertEqual(payload["turns_completed"], 2)
        self.assertEqual(payload["total_actions"], 4)

    def test_cli_parser_accepts_battle_flags_and_turn_flags(self) -> None:
        script_path = Path("tools/run_llm_autoplay.py")
        spec = importlib.util.spec_from_file_location("run_llm_autoplay", script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        args = module.build_parser().parse_args(
            [
                "--battle-mode",
                "--max-actions-per-turn",
                "6",
                "--max-turns-per-battle",
                "3",
                "--max-total-actions",
                "10",
                "--max-consecutive-failures",
                "4",
                "--max-recovery-attempts",
                "3",
                "--wait-for-next-player-turn-seconds",
                "9",
                "--transition-timeout-seconds",
                "7",
                        "--poll-interval-seconds",
                        "0.25",
                        "--stable-window-required-observations",
                        "3",
                        "--stable-window-timeout-seconds",
                        "1.25",
                        "--max-non-combat-steps",
                "12",
                "--unknown-window-fuse",
                "3",
                "--battle-context-recent-steps",
                "5",
                "--reward-mode",
                "safe-default",
                "--map-mode",
                "safe-default",
                "--event-mode",
                "safe-default",
                "--stop-after-next-combat",
                "--no-auto-end-turn-when-only-end-turn",
                "--no-stop-after-player-turn",
            ]
        )

        self.assertTrue(args.battle_mode)
        self.assertEqual(args.max_actions_per_turn, 6)
        self.assertEqual(args.max_turns_per_battle, 3)
        self.assertEqual(args.max_total_actions, 10)
        self.assertEqual(args.max_consecutive_failures, 4)
        self.assertEqual(args.max_recovery_attempts, 3)
        self.assertEqual(args.wait_for_next_player_turn_seconds, 9)
        self.assertEqual(args.transition_timeout_seconds, 7)
        self.assertEqual(args.poll_interval_seconds, 0.25)
        self.assertEqual(args.stable_window_required_observations, 3)
        self.assertEqual(args.stable_window_timeout_seconds, 1.25)
        self.assertEqual(args.max_non_combat_steps, 12)
        self.assertEqual(args.unknown_window_fuse, 3)
        self.assertEqual(args.battle_context_recent_steps, 5)
        self.assertEqual(args.reward_mode, "safe-default")
        self.assertEqual(args.map_mode, "safe-default")
        self.assertEqual(args.event_mode, "safe-default")
        self.assertTrue(args.stop_after_next_combat)
        self.assertFalse(args.auto_end_turn_when_only_end_turn)
        self.assertFalse(args.stop_after_player_turn)


if __name__ == "__main__":
    unittest.main()

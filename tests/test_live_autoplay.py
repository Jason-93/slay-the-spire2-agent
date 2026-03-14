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
                    completed=False,
                    interrupted=True,
                    decisions=0,
                    trace_path="trace.jsonl",
                    reason="dry_run",
                    turn_completed=False,
                    actions_this_turn=0,
                    ended_by="dry_run",
                )

        with patch("sts2_agent.live_autoplay.AutoplayOrchestrator", FakeOrchestrator):
            summary = run_live_autoplay(
                LiveAutoplayConfig(
                    bridge_base_url="http://127.0.0.1:17654",
                    llm_base_url="http://127.0.0.1:8080/v1",
                    model="local-model",
                    dry_run=True,
                    max_steps=4,
                    max_actions_per_turn=2,
                    auto_end_turn_when_only_end_turn=False,
                )
            )

        self.assertEqual(summary.reason, "dry_run")
        self.assertEqual(captured["bridge"].config.base_url, "http://127.0.0.1:17654")
        self.assertEqual(captured["policy"].config.base_url, "http://127.0.0.1:8080/v1")
        self.assertEqual(captured["policy"].config.model, "local-model")
        self.assertTrue(captured["config"].dry_run)
        self.assertEqual(captured["config"].max_steps, 4)
        self.assertEqual(captured["config"].max_actions_per_turn, 2)
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
                completed=False,
                interrupted=True,
                decisions=1,
                trace_path="trace.jsonl",
                reason="dry_run",
                turn_completed=False,
                actions_this_turn=1,
                ended_by="dry_run",
            ),
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = module.main(["--model", "local-model", "--dry-run", "--max-actions-per-turn", "5"])

        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["reason"], "dry_run")
        self.assertEqual(payload["decisions"], 1)
        self.assertEqual(payload["actions_this_turn"], 1)
        self.assertEqual(payload["ended_by"], "dry_run")

    def test_cli_parser_accepts_turn_level_flags(self) -> None:
        script_path = Path("tools/run_llm_autoplay.py")
        spec = importlib.util.spec_from_file_location("run_llm_autoplay", script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        args = module.build_parser().parse_args(
            [
                "--max-actions-per-turn",
                "6",
                "--no-auto-end-turn-when-only-end-turn",
                "--no-stop-after-player-turn",
            ]
        )

        self.assertEqual(args.max_actions_per_turn, 6)
        self.assertFalse(args.auto_end_turn_when_only_end_turn)
        self.assertFalse(args.stop_after_player_turn)


if __name__ == "__main__":
    unittest.main()

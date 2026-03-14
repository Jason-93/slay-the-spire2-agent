from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from sts2_agent.live_autoplay import LiveAutoplayConfig, run_live_autoplay
from sts2_agent.models import to_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run STS2 live autoplay through an OpenAI-compatible chat completions API.")
    parser.add_argument("--bridge-base-url", default=os.environ.get("STS2_BRIDGE_BASE_URL", "http://127.0.0.1:17654"))
    parser.add_argument("--base-url", default=os.environ.get("STS2_LLM_BASE_URL", "http://127.0.0.1:8080/v1"))
    parser.add_argument("--model", default=os.environ.get("STS2_LLM_MODEL", "default"))
    parser.add_argument("--api-key", default=os.environ.get("STS2_LLM_API_KEY"))
    parser.add_argument("--trace-dir", default=os.environ.get("STS2_TRACE_DIR", "traces/live_llm"))
    parser.add_argument("--max-steps", type=int, default=int(os.environ.get("STS2_MAX_STEPS", "32")))
    parser.add_argument("--max-actions-per-turn", type=int, default=_read_optional_int("STS2_MAX_ACTIONS_PER_TURN"))
    parser.add_argument("--max-turns-per-battle", type=int, default=_read_optional_int("STS2_MAX_TURNS_PER_BATTLE"))
    parser.add_argument("--max-total-actions", type=int, default=_read_optional_int("STS2_MAX_TOTAL_ACTIONS"))
    parser.add_argument("--max-consecutive-failures", type=int, default=int(os.environ.get("STS2_MAX_CONSECUTIVE_FAILURES", "6")))
    parser.add_argument(
        "--wait-for-next-player-turn-seconds",
        type=float,
        default=float(os.environ.get("STS2_WAIT_FOR_NEXT_PLAYER_TURN_SECONDS", "30")),
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=float(os.environ.get("STS2_POLL_INTERVAL_SECONDS", "0.5")),
    )
    parser.add_argument("--policy-timeout-seconds", type=float, default=float(os.environ.get("STS2_POLICY_TIMEOUT_SECONDS", "20")))
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("STS2_LLM_TEMPERATURE", "0.2")))
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("STS2_LLM_MAX_TOKENS", "256")))
    parser.add_argument("--dry-run", action="store_true")
    parser.set_defaults(
        battle_mode=_read_optional_bool("STS2_BATTLE_MODE", False),
        stop_after_player_turn=_read_optional_bool("STS2_STOP_AFTER_PLAYER_TURN", True),
        auto_end_turn_when_only_end_turn=_read_optional_bool("STS2_AUTO_END_TURN_WHEN_ONLY_END_TURN", True),
    )
    parser.add_argument("--battle-mode", dest="battle_mode", action="store_true")
    parser.add_argument("--turn-mode", dest="battle_mode", action="store_false")
    parser.add_argument("--stop-after-player-turn", dest="stop_after_player_turn", action="store_true")
    parser.add_argument("--no-stop-after-player-turn", dest="stop_after_player_turn", action="store_false")
    parser.add_argument("--auto-end-turn-when-only-end-turn", dest="auto_end_turn_when_only_end_turn", action="store_true")
    parser.add_argument("--no-auto-end-turn-when-only-end-turn", dest="auto_end_turn_when_only_end_turn", action="store_false")
    return parser


def _read_optional_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    return int(raw)


def _read_optional_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_live_autoplay(
        LiveAutoplayConfig(
            bridge_base_url=args.bridge_base_url,
            llm_base_url=args.base_url,
            model=args.model,
            api_key=args.api_key,
            trace_dir=args.trace_dir,
            max_steps=args.max_steps,
            max_actions_per_turn=args.max_actions_per_turn,
            battle_mode=args.battle_mode,
            stop_after_player_turn=args.stop_after_player_turn,
            auto_end_turn_when_only_end_turn=args.auto_end_turn_when_only_end_turn,
            max_turns_per_battle=args.max_turns_per_battle,
            max_total_actions=args.max_total_actions,
            max_consecutive_failures=args.max_consecutive_failures,
            wait_for_next_player_turn_seconds=args.wait_for_next_player_turn_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
            policy_timeout_seconds=args.policy_timeout_seconds,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            dry_run=args.dry_run,
        )
    )
    print(json.dumps(to_dict(summary), ensure_ascii=False, indent=2))
    return 0 if summary.completed and not summary.interrupted else 1


if __name__ == "__main__":
    raise SystemExit(main())

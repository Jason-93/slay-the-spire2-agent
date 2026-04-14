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
    parser = argparse.ArgumentParser(description="Run STS2 live autoplay through MCTS Policy.")
    parser.add_argument("--bridge-base-url", default=os.environ.get("STS2_BRIDGE_BASE_URL", "http://127.0.0.1:17654"))
    parser.add_argument("--trace-dir", default=os.environ.get("STS2_TRACE_DIR", "traces/live_mcts"))
    parser.add_argument("--max-steps", type=int, default=int(os.environ.get("STS2_MAX_STEPS", "1000")))
    parser.add_argument("--iterations", type=int, default=int(os.environ.get("STS2_MCTS_ITERATIONS", "100")))
    parser.add_argument("--max-actions-per-turn", type=int, default=_read_optional_int("STS2_MAX_ACTIONS_PER_TURN"))
    parser.add_argument("--max-turns-per-battle", type=int, default=_read_optional_int("STS2_MAX_TURNS_PER_BATTLE"))
    parser.add_argument("--max-total-actions", type=int, default=_read_optional_int("STS2_MAX_TOTAL_ACTIONS"))
    parser.add_argument("--max-consecutive-failures", type=int, default=int(os.environ.get("STS2_MAX_CONSECUTIVE_FAILURES", "10")))
    parser.add_argument("--max-recovery-attempts", type=int, default=int(os.environ.get("STS2_MAX_RECOVERY_ATTEMPTS", "10")))
    parser.add_argument(
        "--wait-for-next-player-turn-seconds",
        type=float,
        default=float(os.environ.get("STS2_WAIT_FOR_NEXT_PLAYER_TURN_SECONDS", "30")),
    )
    parser.add_argument(
        "--transition-timeout-seconds",
        type=float,
        default=float(os.environ.get("STS2_TRANSITION_TIMEOUT_SECONDS", "15")),
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=float(os.environ.get("STS2_POLL_INTERVAL_SECONDS", "0.5")),
    )
    parser.add_argument(
        "--stable-window-required-observations",
        type=int,
        default=int(os.environ.get("STS2_STABLE_WINDOW_REQUIRED_OBSERVATIONS", "2")),
    )
    parser.add_argument(
        "--stable-window-timeout-seconds",
        type=float,
        default=float(os.environ.get("STS2_STABLE_WINDOW_TIMEOUT_SECONDS", "2.0")),
    )
    parser.add_argument("--max-non-combat-steps", type=int, default=int(os.environ.get("STS2_MAX_NON_COMBAT_STEPS", "100")))
    parser.add_argument("--unknown-window-fuse", type=int, default=int(os.environ.get("STS2_UNKNOWN_WINDOW_FUSE", "5")))
    parser.add_argument(
        "--battle-context-recent-steps",
        type=int,
        default=int(os.environ.get("STS2_BATTLE_CONTEXT_RECENT_STEPS", "4")),
    )
    parser.add_argument("--policy-timeout-seconds", type=float, default=float(os.environ.get("STS2_POLICY_TIMEOUT_SECONDS", "60")))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--full-auto", action="store_true", help="Enable safe-default for all non-combat phases, including menu.")
    parser.add_argument(
        "--menu-mode",
        default=os.environ.get("STS2_MENU_MODE", "halt"),
        help="How to handle the main menu: halt|auto (default: halt)",
    )
    parser.add_argument(
        "--reward-mode",
        default=os.environ.get("STS2_REWARD_MODE", "safe-default"),
        choices=("halt", "skip", "skip-only", "safe-default"),
    )
    parser.add_argument(
        "--map-mode",
        default=os.environ.get("STS2_MAP_MODE", "safe-default"),
        choices=("halt", "safe-default"),
    )
    parser.add_argument(
        "--event-mode",
        default=os.environ.get("STS2_EVENT_MODE", "safe-default"),
        choices=("halt", "safe-default"),
    )
    parser.add_argument(
        "--shop-mode",
        default=os.environ.get("STS2_SHOP_MODE", "safe-default"),
        choices=("halt", "safe-default"),
    )
    parser.set_defaults(
        battle_mode=_read_optional_bool("STS2_BATTLE_MODE", True),
        stop_after_player_turn=_read_optional_bool("STS2_STOP_AFTER_PLAYER_TURN", False),
        auto_end_turn_when_only_end_turn=_read_optional_bool("STS2_AUTO_END_TURN_WHEN_ONLY_END_TURN", True),
        stop_after_next_combat=_read_optional_bool("STS2_STOP_AFTER_NEXT_COMBAT", False),
    )
    parser.add_argument("--battle-mode", dest="battle_mode", action="store_true")
    parser.add_argument("--turn-mode", dest="battle_mode", action="store_false")
    parser.add_argument("--stop-after-player-turn", dest="stop_after_player_turn", action="store_true")
    parser.add_argument("--no-stop-after-player-turn", dest="stop_after_player_turn", action="store_false")
    parser.add_argument("--stop-after-next-combat", dest="stop_after_next_combat", action="store_true")
    parser.add_argument("--no-stop-after-next-combat", dest="stop_after_next_combat", action="store_false")
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

    reward_mode = args.reward_mode
    map_mode = args.map_mode
    event_mode = args.event_mode
    shop_mode = args.shop_mode
    menu_mode = args.menu_mode
    battle_mode = args.battle_mode
    stop_after_player_turn = args.stop_after_player_turn

    if args.full_auto:
        if menu_mode == "halt":
            menu_mode = "auto"
        if reward_mode == "halt":
            reward_mode = "safe-default"
        if map_mode == "halt":
            map_mode = "safe-default"
        if event_mode == "halt":
            event_mode = "safe-default"
        if shop_mode == "halt":
            shop_mode = "safe-default"
        battle_mode = True
        stop_after_player_turn = False

    summary = run_live_autoplay(
        LiveAutoplayConfig(
            policy_type="mcts",
            bridge_base_url=args.bridge_base_url,
            trace_dir=args.trace_dir,
            max_steps=args.max_steps,
            mcts_iterations=args.iterations,
            max_actions_per_turn=args.max_actions_per_turn,
            battle_mode=battle_mode,
            stop_after_player_turn=stop_after_player_turn,
            auto_end_turn_when_only_end_turn=args.auto_end_turn_when_only_end_turn,
            max_turns_per_battle=args.max_turns_per_battle,
            max_total_actions=args.max_total_actions,
            max_consecutive_failures=args.max_consecutive_failures,
            max_recovery_attempts=args.max_recovery_attempts,
            wait_for_next_player_turn_seconds=args.wait_for_next_player_turn_seconds,
            transition_timeout_seconds=args.transition_timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
            stable_window_required_observations=args.stable_window_required_observations,
            stable_window_timeout_seconds=args.stable_window_timeout_seconds,
            max_non_combat_steps=args.max_non_combat_steps,
            unknown_window_fuse=args.unknown_window_fuse,
            battle_context_recent_steps=args.battle_context_recent_steps,
            policy_timeout_seconds=args.policy_timeout_seconds,
            reward_mode=reward_mode,
            map_mode=map_mode,
            event_mode=event_mode,
            shop_mode=shop_mode,
            menu_mode=menu_mode,
            stop_after_next_combat=args.stop_after_next_combat,
            dry_run=args.dry_run,
        )
    )
    print(json.dumps(to_dict(summary), ensure_ascii=False, indent=2))
    return 0 if summary.completed and not summary.interrupted else 1


if __name__ == "__main__":
    raise SystemExit(main())

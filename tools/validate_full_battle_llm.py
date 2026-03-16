from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .validate_live_apply import create_artifact_dir, ensure_live_runtime, parse_bool_env, read_health, write_json
except ImportError:
    from validate_live_apply import create_artifact_dir, ensure_live_runtime, parse_bool_env, read_health, write_json

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from sts2_agent.live_autoplay import LiveAutoplayConfig, run_live_autoplay
from sts2_agent.models import to_dict


def _read_trace_tail(trace_path: Path, limit: int = 8) -> list[dict[str, Any]]:
    if not trace_path.exists():
        return []
    lines = [line for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    tail = lines[-limit:]
    return [json.loads(line) for line in tail]


def _read_trace_records(trace_path: Path) -> list[dict[str, Any]]:
    if not trace_path.exists():
        return []
    return [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _find_invalid_end_turns(trace_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for entry in trace_records:
        bridge_result = dict(entry.get("bridge_result") or {})
        if str(bridge_result.get("submitted_action_type") or "") != "end_turn":
            continue
        if str(bridge_result.get("status") or "") != "accepted":
            continue
        legal_actions = list(entry.get("legal_actions") or [])
        stronger_actions = [
            {
                "action_id": action.get("action_id"),
                "type": action.get("type"),
                "label": action.get("label"),
            }
            for action in legal_actions
            if action.get("type") in {"play_card", "choose_combat_card", "use_potion"}
        ]
        if not stronger_actions:
            continue
        violations.append(
            {
                "step_index": entry.get("step_index"),
                "decision_id": entry.get("decision_id"),
                "current_turn_index": entry.get("current_turn_index"),
                "gate_status": entry.get("gate_status"),
                "gate_reason": entry.get("gate_reason"),
                "submitted_action_id": bridge_result.get("submitted_action_id"),
                "submitted_action_label": bridge_result.get("submitted_action_label"),
                "available_stronger_actions": stronger_actions,
            }
        )
    return violations


def _build_result(
    *,
    artifact_dir: Path,
    health: dict[str, Any],
    summary: dict[str, Any],
    trace_tail: list[dict[str, Any]],
    invalid_end_turns: list[dict[str, Any]],
) -> dict[str, Any]:
    rejects_total = int(summary.get("rejects_total") or 0)
    total_actions = int(summary.get("total_actions") or 0)
    total_attempts = total_actions + rejects_total
    reject_rate = (rejects_total / total_attempts) if total_attempts > 0 else 0.0
    hard_rejects = int(summary.get("hard_rejects") or 0)
    if rejects_total == 0:
        quality = "clean"
    elif hard_rejects > 0:
        quality = "hard_reject"
    elif reject_rate >= 0.25:
        quality = "reject_heavy"
    else:
        quality = "recovered"
    return {
        "timestamp": datetime.now().isoformat(),
        "artifact_dir": str(artifact_dir),
        "provider_mode": health.get("provider_mode"),
        "read_only": health.get("read_only"),
        "completed": bool(summary.get("completed")),
        "interrupted": bool(summary.get("interrupted")),
        "battle_completed": bool(summary.get("battle_completed")),
        "turns_completed": int(summary.get("turns_completed") or 0),
        "total_actions": total_actions,
        "current_turn_index": int(summary.get("current_turn_index") or 0),
        "rejects_total": rejects_total,
        "recoverable_rejects": int(summary.get("recoverable_rejects") or 0),
        "hard_rejects": hard_rejects,
        "gate_intercepts": int(summary.get("gate_intercepts") or 0),
        "gate_wait_steps": int(summary.get("gate_wait_steps") or 0),
        "gate_redecisions": int(summary.get("gate_redecisions") or 0),
        "gate_rebases": int(summary.get("gate_rebases") or 0),
        "reject_counts": dict(summary.get("reject_counts") or {}),
        "reject_code_counts": dict(summary.get("reject_code_counts") or {}),
        "reject_rate": reject_rate,
        "quality": quality,
        "last_reject": dict(summary.get("last_reject") or {}),
        "recovery_attempts": int(summary.get("recovery_attempts") or 0),
        "recovery_successes": int(summary.get("recovery_successes") or 0),
        "recovery_streak": int(summary.get("recovery_streak") or 0),
        "stop_reason": summary.get("ended_by") or summary.get("reason"),
        "trace_path": summary.get("trace_path"),
        "trace_tail_count": len(trace_tail),
        "had_recovery": int(summary.get("recovery_attempts") or 0) > 0,
        "trace_tail_stop_reasons": [entry.get("stop_reason") for entry in trace_tail],
        "trace_tail_battle_stop_reasons": [entry.get("battle_stop_reason") for entry in trace_tail],
        "invalid_end_turns": invalid_end_turns,
        "invalid_end_turn_count": len(invalid_end_turns),
    }


def run_validation(args: argparse.Namespace) -> int:
    artifact_root = Path(args.artifact_root) if args.artifact_root else ROOT / "tmp" / "full-battle-llm-validation"
    artifact_dir = create_artifact_dir(artifact_root)
    health = read_health(args.bridge_base_url.rstrip("/"))
    write_json(artifact_dir / "health.json", health)

    live_error = ensure_live_runtime(health)
    if live_error:
        result = {
            "timestamp": datetime.now().isoformat(),
            "artifact_dir": str(artifact_dir),
            "verdict": "failed",
            "summary": live_error,
        }
        write_json(artifact_dir / "result.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    if not args.dry_run:
        if not args.allow_write:
            result = {
                "timestamp": datetime.now().isoformat(),
                "artifact_dir": str(artifact_dir),
                "verdict": "rejected",
                "summary": "缺少 --allow-write 显式确认，拒绝执行真实 battle autoplay。",
            }
            write_json(artifact_dir / "result.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        if health.get("read_only", True):
            result = {
                "timestamp": datetime.now().isoformat(),
                "artifact_dir": str(artifact_dir),
                "verdict": "rejected",
                "summary": "bridge 当前 read_only=true，无法执行真实 battle autoplay。",
            }
            write_json(artifact_dir / "result.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        if not parse_bool_env("STS2_BRIDGE_ENABLE_WRITES"):
            result = {
                "timestamp": datetime.now().isoformat(),
                "artifact_dir": str(artifact_dir),
                "verdict": "rejected",
                "summary": "当前进程未开启 STS2_BRIDGE_ENABLE_WRITES=true。",
            }
            write_json(artifact_dir / "result.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

    trace_dir = artifact_dir / "trace"
    summary = run_live_autoplay(
        LiveAutoplayConfig(
            bridge_base_url=args.bridge_base_url,
            llm_base_url=args.base_url,
            model=args.model,
            api_key=args.api_key,
            trace_dir=str(trace_dir),
            max_steps=args.max_steps,
            max_actions_per_turn=args.max_actions_per_turn,
            battle_mode=True,
            stop_after_player_turn=False,
            auto_end_turn_when_only_end_turn=args.auto_end_turn_when_only_end_turn,
            reward_mode=args.reward_mode,
            map_mode=args.map_mode,
            event_mode=args.event_mode,
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
            stop_after_next_combat=args.stop_after_next_combat,
            battle_context_recent_steps=args.battle_context_recent_steps,
            policy_timeout_seconds=args.policy_timeout_seconds,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            dry_run=args.dry_run,
        )
    )
    summary_payload = to_dict(summary)
    write_json(artifact_dir / "summary.json", summary_payload)

    trace_tail = []
    invalid_end_turns: list[dict[str, Any]] = []
    trace_path = summary.trace_path
    if trace_path:
        trace_records = _read_trace_records(Path(trace_path))
        trace_tail = _read_trace_tail(Path(trace_path))
        write_json(artifact_dir / "trace_tail.json", trace_tail)
        invalid_end_turns = _find_invalid_end_turns(trace_records)
        write_json(artifact_dir / "invalid_end_turns.json", invalid_end_turns)

    result = _build_result(
        artifact_dir=artifact_dir,
        health=health,
        summary=summary_payload,
        trace_tail=trace_tail,
        invalid_end_turns=invalid_end_turns,
    )
    if invalid_end_turns:
        result["verdict"] = "failed"
        result["summary"] = "发现错误 end_turn：同一稳定窗口中仍存在更高价值动作。"
    elif summary.battle_completed and not summary.interrupted:
        result["verdict"] = {
            "clean": "success_clean",
            "recovered": "success_recovered",
            "reject_heavy": "success_reject_heavy",
            "hard_reject": "success_with_hard_reject",
        }.get(result["quality"], "success_recovered")
        result["summary"] = "整场战斗 autoplay 已完成。"
    else:
        result["verdict"] = "failed"
        result["summary"] = "整场战斗 autoplay 未完成，请检查 summary 与 trace_tail。"
    write_json(artifact_dir / "result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"].startswith("success") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a live full-battle LLM autoplay smoke validation and write artifacts.")
    parser.add_argument("--bridge-base-url", default="http://127.0.0.1:17654")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--model", default="default")
    parser.add_argument("--api-key")
    parser.add_argument("--artifact-root", help="Override output root for validation artifacts.")
    parser.add_argument("--dry-run", action="store_true", help="Call the model and write artifacts without submitting in-game actions.")
    parser.add_argument("--allow-write", action="store_true", help="Explicitly acknowledge that real in-game actions will be sent.")
    parser.add_argument("--max-steps", type=int, default=64)
    parser.add_argument("--max-actions-per-turn", type=int)
    parser.add_argument("--max-turns-per-battle", type=int, default=12)
    parser.add_argument("--max-total-actions", type=int, default=48)
    parser.add_argument("--max-consecutive-failures", type=int, default=6)
    parser.add_argument("--max-recovery-attempts", type=int, default=6)
    parser.add_argument("--wait-for-next-player-turn-seconds", type=float, default=30.0)
    parser.add_argument("--transition-timeout-seconds", type=float, default=15.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.5)
    parser.add_argument("--stable-window-required-observations", type=int, default=2)
    parser.add_argument("--stable-window-timeout-seconds", type=float, default=2.0)
    parser.add_argument("--max-non-combat-steps", type=int, default=24)
    parser.add_argument("--unknown-window-fuse", type=int, default=2)
    parser.add_argument("--battle-context-recent-steps", type=int, default=4)
    parser.add_argument("--policy-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--reward-mode", choices=("halt", "skip", "skip-only", "safe-default", "llm"), default="safe-default")
    parser.add_argument("--map-mode", choices=("halt", "safe-default", "llm"), default="safe-default")
    parser.add_argument("--event-mode", choices=("halt", "safe-default", "llm"), default="safe-default")
    parser.add_argument("--stop-after-next-combat", action="store_true")
    parser.set_defaults(auto_end_turn_when_only_end_turn=True)
    parser.add_argument("--auto-end-turn-when-only-end-turn", dest="auto_end_turn_when_only_end_turn", action="store_true")
    parser.add_argument("--no-auto-end-turn-when-only-end-turn", dest="auto_end_turn_when_only_end_turn", action="store_false")
    return parser


def main() -> int:
    return run_validation(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .validate_live_apply import (
        create_artifact_dir,
        ensure_live_runtime,
        parse_bool_env,
        post_json,
        read_actions,
        read_health,
        read_snapshot,
        write_json,
    )
except ImportError:
    from validate_live_apply import (
        create_artifact_dir,
        ensure_live_runtime,
        parse_bool_env,
        post_json,
        read_actions,
        read_health,
        read_snapshot,
        write_json,
    )

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 17654


def choose_reward_action(snapshot: dict[str, Any], actions: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    metadata = snapshot.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    reward_subphase = str(metadata.get("reward_subphase") or "").strip().lower()

    if reward_subphase == "reward_advance":
        advance_action = next((action for action in actions if str(action.get("type") or "") == "advance_reward"), None)
        if advance_action is not None:
            return advance_action, "奖励收尾窗口优先点击前进按钮。"
        return None, "奖励收尾窗口缺少 advance_reward 动作。"

    reward_actions = [action for action in actions if str(action.get("type") or "") == "choose_reward"]
    if reward_actions:
        for action in reward_actions:
            label = str(action.get("label") or (action.get("params") or {}).get("reward") or "")
            if "金币" in label or "gold" in label.lower():
                return action, "奖励窗口优先领取金币，避免卡在奖励链路。"
        return reward_actions[0], "奖励窗口缺少更明确的保守策略，退回选择第一个 choose_reward。"

    skip_action = next((action for action in actions if str(action.get("type") or "") == "skip_reward"), None)
    if skip_action is not None:
        return skip_action, "奖励窗口没有可领奖励时，回退到 skip_reward。"
    return None, "奖励窗口没有可执行的 choose_reward / skip_reward / advance_reward。"


def map_action_rank(action: dict[str, Any]) -> tuple[int, int, int, str]:
    params = action.get("params")
    params = params if isinstance(params, dict) else {}
    text = str(params.get("node") or action.get("label") or "").strip().lower()
    score = 3
    if any(token in text for token in ("monster", "combat", "battle", "enemy", "普通战斗")):
        score = 0
    elif any(token in text for token in ("question", "mystery", "event", "?", "事件")):
        score = 1
    elif any(token in text for token in ("shop", "merchant", "商店", "rest", "camp", "篝火")):
        score = 2
    elif any(token in text for token in ("elite", "boss", "精英", "首领")):
        score = 4
    x_value = 999
    y_value = 999
    raw_node = str(params.get("node") or "")
    if "@" in raw_node:
        _, _, coord_text = raw_node.rpartition("@")
        parts = [part.strip() for part in coord_text.split(",", maxsplit=1)]
        if len(parts) == 2:
            try:
                x_value = int(parts[0])
                y_value = int(parts[1])
            except ValueError:
                pass
    return score, x_value, y_value, text


def choose_map_action(actions: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    candidates = [action for action in actions if str(action.get("type") or "") == "choose_map_node"]
    if not candidates:
        return None, "地图窗口没有 choose_map_node。"
    selected = sorted(candidates, key=map_action_rank)[0]
    return selected, "地图窗口使用 safe-default 选路，优先普通战斗或更靠左节点。"


def choose_action(snapshot: dict[str, Any], actions: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    phase = str(snapshot.get("phase") or "unknown").lower()
    if phase == "reward":
        return choose_reward_action(snapshot, actions)
    if phase == "map":
        return choose_map_action(actions)
    return None, f"当前 phase={phase} 不在 reward/map 自动化范围内。"


def build_apply_payload(snapshot: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    params = action.get("params")
    return {
        "decision_id": snapshot.get("decision_id"),
        "action_id": action.get("action_id"),
        "params": params if isinstance(params, dict) else {},
    }


def is_empty_reward_window(snapshot: dict[str, Any], actions: list[dict[str, Any]]) -> bool:
    metadata = snapshot.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    if str(snapshot.get("phase") or "").lower() != "reward":
        return False
    reward_count = metadata.get("reward_count")
    return int(reward_count or 0) == 0 and not actions


def run_validation(args: argparse.Namespace) -> int:
    artifact_dir = create_artifact_dir(Path(args.artifact_root) if args.artifact_root else ROOT / "tmp" / "reward-map-next-battle-validation")
    base_url = f"http://127.0.0.1:{args.port}"
    health = read_health(base_url)
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

    if args.apply:
        if not args.allow_write:
            result = {
                "timestamp": datetime.now().isoformat(),
                "artifact_dir": str(artifact_dir),
                "verdict": "rejected",
                "summary": "缺少 --allow-write 显式确认，拒绝发送真实写入。",
            }
            write_json(artifact_dir / "result.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        if health.get("read_only", True):
            result = {
                "timestamp": datetime.now().isoformat(),
                "artifact_dir": str(artifact_dir),
                "verdict": "rejected",
                "summary": "bridge 当前 read_only=true，无法执行 reward/map 自动化写入。",
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

    steps: list[dict[str, Any]] = []
    entered_reward_chain = False
    waiting_since: float | None = None
    last_decision_id = ""
    empty_reward_since: float | None = None

    for step_index in range(args.max_steps):
        snapshot = read_snapshot(base_url)
        actions = read_actions(base_url)
        phase = str(snapshot.get("phase") or "unknown").lower()
        metadata = snapshot.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        step_dir = artifact_dir / f"step-{step_index:02d}"
        step_dir.mkdir(parents=True, exist_ok=True)
        write_json(step_dir / "snapshot.json", snapshot)
        write_json(step_dir / "actions.json", actions)

        if phase == "reward":
            entered_reward_chain = True

        if entered_reward_chain and phase == "map" and not args.require_next_combat:
            result = {
                "timestamp": datetime.now().isoformat(),
                "artifact_dir": str(artifact_dir),
                "verdict": "success",
                "summary": "已从 reward 收尾窗口成功推进到 map。",
                "steps": steps,
                "final_phase": phase,
                "final_window_kind": metadata.get("window_kind"),
            }
            write_json(artifact_dir / "result.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if entered_reward_chain and phase == "combat":
            result = {
                "timestamp": datetime.now().isoformat(),
                "artifact_dir": str(artifact_dir),
                "verdict": "success",
                "summary": "已从 reward/map 自动推进回下一场 combat。",
                "steps": steps,
                "final_phase": phase,
            }
            write_json(artifact_dir / "result.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if is_empty_reward_window(snapshot, actions):
            if empty_reward_since is None or snapshot.get("decision_id") != last_decision_id:
                empty_reward_since = time.time()
            elif time.time() - empty_reward_since > args.transition_timeout_seconds:
                result = {
                    "timestamp": datetime.now().isoformat(),
                    "artifact_dir": str(artifact_dir),
                    "verdict": "failed",
                    "summary": "奖励窗口已经领空，但 bridge 仍停留在空 reward 窗口，没有导出前进动作。",
                    "steps": steps,
                    "final_phase": phase,
                    "final_window_kind": metadata.get("window_kind"),
                }
                write_json(artifact_dir / "result.json", result)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1
        else:
            empty_reward_since = None

        candidate, reason = choose_action(snapshot, actions)
        if candidate is None:
            if phase in {"reward", "map"}:
                if waiting_since is None or snapshot.get("decision_id") != last_decision_id:
                    waiting_since = time.time()
                elif time.time() - waiting_since > args.transition_timeout_seconds:
                    result = {
                        "timestamp": datetime.now().isoformat(),
                        "artifact_dir": str(artifact_dir),
                        "verdict": "failed",
                        "summary": "reward/map 过渡等待超时，未进入下一窗口。",
                        "steps": steps,
                        "final_phase": phase,
                        "final_window_kind": metadata.get("window_kind"),
                    }
                    write_json(artifact_dir / "result.json", result)
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    return 1
                time.sleep(args.poll_interval_seconds)
                last_decision_id = str(snapshot.get("decision_id") or "")
                continue

            result = {
                "timestamp": datetime.now().isoformat(),
                "artifact_dir": str(artifact_dir),
                "verdict": "failed",
                "summary": reason,
                "steps": steps,
                "final_phase": phase,
            }
            write_json(artifact_dir / "result.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

        waiting_since = None
        step_payload = {
            "phase": phase,
            "window_kind": metadata.get("window_kind"),
            "candidate_reason": reason,
            "action": candidate,
        }
        if args.apply:
            apply_payload = build_apply_payload(snapshot, candidate)
            http_status, response = post_json(base_url, "/apply", apply_payload)
            step_payload["apply_request"] = apply_payload
            step_payload["apply_response"] = {"http_status": http_status, "body": response}
            write_json(step_dir / "apply_request.json", apply_payload)
            write_json(step_dir / "apply_response.json", step_payload["apply_response"])
            if http_status >= 400 or response.get("status") != "accepted":
                result = {
                    "timestamp": datetime.now().isoformat(),
                    "artifact_dir": str(artifact_dir),
                    "verdict": "failed",
                    "summary": f"bridge 未接受动作，http_status={http_status} status={response.get('status')!r}。",
                    "steps": steps + [step_payload],
                    "final_phase": phase,
                }
                write_json(artifact_dir / "result.json", result)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1
        steps.append(step_payload)
        write_json(step_dir / "decision.json", step_payload)
        time.sleep(args.poll_interval_seconds)
        last_decision_id = str(snapshot.get("decision_id") or "")

    result = {
        "timestamp": datetime.now().isoformat(),
        "artifact_dir": str(artifact_dir),
        "verdict": "failed",
        "summary": "超过最大步骤数，仍未到达目标窗口。" if not args.require_next_combat else "超过最大步骤数，仍未回到下一场 combat。",
        "steps": steps,
    }
    write_json(artifact_dir / "result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate reward advance -> map flow, with optional continuation into the next combat.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bridge port exposed by the in-game mod.")
    parser.add_argument("--artifact-root", help="Override output root for validation artifacts.")
    parser.add_argument("--apply", action="store_true", help="Submit real reward/map actions through POST /apply.")
    parser.add_argument("--allow-write", action="store_true", help="Explicitly acknowledge that real in-game writes will be sent.")
    parser.add_argument("--max-steps", type=int, default=8, help="Maximum reward/map decisions to attempt.")
    parser.add_argument("--transition-timeout-seconds", type=float, default=12.0, help="How long to wait for reward/map transitions.")
    parser.add_argument("--poll-interval-seconds", type=float, default=0.5, help="Polling interval while waiting for the next window.")
    parser.add_argument(
        "--require-next-combat",
        action="store_true",
        help="Keep going after map appears and only succeed once the next combat snapshot is reached.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run_validation(args)


if __name__ == "__main__":
    sys.exit(main())

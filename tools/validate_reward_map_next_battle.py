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


def choose_reward_action(actions: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    skip_action = next((action for action in actions if str(action.get("type") or "") == "skip_reward"), None)
    if skip_action is not None:
        return skip_action, "???????? skip_reward?????????"
    reward_actions = [action for action in actions if str(action.get("type") or "") == "choose_reward"]
    if reward_actions:
        return reward_actions[0], "?????? skip_reward???????? choose_reward?"
    return None, "?????????? choose_reward/skip_reward?"


def map_action_rank(action: dict[str, Any]) -> tuple[int, int, int, str]:
    params = action.get("params")
    params = params if isinstance(params, dict) else {}
    text = str(params.get("node") or action.get("label") or "").strip().lower()
    score = 3
    if any(token in text for token in ("monster", "combat", "battle", "enemy", "????")):
        score = 0
    elif any(token in text for token in ("question", "mystery", "event", "?", "??")):
        score = 1
    elif any(token in text for token in ("shop", "merchant", "??", "rest", "camp", "??")):
        score = 2
    elif any(token in text for token in ("elite", "boss", "??", "??")):
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
        return None, "?????? choose_map_node?"
    selected = sorted(candidates, key=map_action_rank)[0]
    return selected, "?????? safe-default ?????????/??????"


def choose_action(snapshot: dict[str, Any], actions: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    phase = str(snapshot.get("phase") or "unknown").lower()
    if phase == "reward":
        return choose_reward_action(actions)
    if phase == "map":
        return choose_map_action(actions)
    return None, f"?? phase={phase} ?? reward/map ???????"


def build_apply_payload(snapshot: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    params = action.get("params")
    return {
        "decision_id": snapshot.get("decision_id"),
        "action_id": action.get("action_id"),
        "params": params if isinstance(params, dict) else {},
    }


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
                "summary": "?? --allow-write ??????????????",
            }
            write_json(artifact_dir / "result.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        if health.get("read_only", True):
            result = {
                "timestamp": datetime.now().isoformat(),
                "artifact_dir": str(artifact_dir),
                "verdict": "rejected",
                "summary": "bridge ?? read_only=true????? reward/map ??????",
            }
            write_json(artifact_dir / "result.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1
        if not parse_bool_env("STS2_BRIDGE_ENABLE_WRITES"):
            result = {
                "timestamp": datetime.now().isoformat(),
                "artifact_dir": str(artifact_dir),
                "verdict": "rejected",
                "summary": "??????? STS2_BRIDGE_ENABLE_WRITES=true?",
            }
            write_json(artifact_dir / "result.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

    steps: list[dict[str, Any]] = []
    entered_non_combat = False
    waiting_since: float | None = None
    last_phase = ""

    for step_index in range(args.max_steps):
        snapshot = read_snapshot(base_url)
        actions = read_actions(base_url)
        phase = str(snapshot.get("phase") or "unknown").lower()
        step_dir = artifact_dir / f"step-{step_index:02d}"
        step_dir.mkdir(parents=True, exist_ok=True)
        write_json(step_dir / "snapshot.json", snapshot)
        write_json(step_dir / "actions.json", actions)

        if phase in {"reward", "map"}:
            entered_non_combat = True

        if entered_non_combat and phase == "combat":
            result = {
                "timestamp": datetime.now().isoformat(),
                "artifact_dir": str(artifact_dir),
                "verdict": "success",
                "summary": "?? reward/map ???????? combat?",
                "steps": steps,
                "final_phase": phase,
            }
            write_json(artifact_dir / "result.json", result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        candidate, reason = choose_action(snapshot, actions)
        if candidate is None:
            if phase in {"reward", "map"}:
                if waiting_since is None or phase != last_phase:
                    waiting_since = time.time()
                elif time.time() - waiting_since > args.transition_timeout_seconds:
                    result = {
                        "timestamp": datetime.now().isoformat(),
                        "artifact_dir": str(artifact_dir),
                        "verdict": "failed",
                        "summary": "reward/map ???????????????",
                        "steps": steps,
                        "final_phase": phase,
                    }
                    write_json(artifact_dir / "result.json", result)
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    return 1
                time.sleep(args.poll_interval_seconds)
                last_phase = phase
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
                    "summary": f"bridge ??????http_status={http_status} status={response.get('status')!r}?",
                    "steps": steps + [step_payload],
                    "final_phase": phase,
                }
                write_json(artifact_dir / "result.json", result)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1
        steps.append(step_payload)
        write_json(step_dir / "decision.json", step_payload)
        time.sleep(args.poll_interval_seconds)
        last_phase = phase

    result = {
        "timestamp": datetime.now().isoformat(),
        "artifact_dir": str(artifact_dir),
        "verdict": "failed",
        "summary": "??????????????? combat?",
        "steps": steps,
    }
    write_json(artifact_dir / "result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate reward -> map -> next combat bridge flow.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bridge port exposed by the in-game mod.")
    parser.add_argument("--artifact-root", help="Override output root for validation artifacts.")
    parser.add_argument("--apply", action="store_true", help="Submit real reward/map actions through POST /apply.")
    parser.add_argument("--allow-write", action="store_true", help="Explicitly acknowledge that real in-game writes will be sent.")
    parser.add_argument("--max-steps", type=int, default=8, help="Maximum reward/map decisions to attempt.")
    parser.add_argument("--transition-timeout-seconds", type=float, default=12.0, help="How long to wait for reward/map transitions.")
    parser.add_argument("--poll-interval-seconds", type=float, default=0.5, help="Polling interval while waiting for the next window.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run_validation(args)


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
import socket
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 17654


def pick_free_port(preferred: int = DEFAULT_PORT) -> int:
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return int(sock.getsockname()[1])
    raise RuntimeError("could not allocate a free TCP port")


def fetch(base_url: str, path: str) -> dict | list:
    with urlopen(base_url + path, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    import urllib.request

    request = urllib.request.Request(
        base_url + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as ex:
        return ex.code, json.loads(ex.read().decode("utf-8"))


def wait_for_menu_actions(base_url: str, timeout_seconds: float = 10.0) -> tuple[dict, list[dict]]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        snapshot = fetch(base_url, "/snapshot?phase=menu")
        actions = fetch(base_url, "/actions?phase=menu")
        if snapshot.get("phase") == "menu" and isinstance(actions, list) and actions:
            return snapshot, actions
        time.sleep(0.25)
    raise RuntimeError("menu phase did not expose any legal actions in time")


def resolve_host_dll() -> Path:
    candidates = sorted(
        (ROOT / "mod" / "Sts2Mod.StateBridge.Host" / "bin" / "Debug").glob("net*/Sts2Mod.StateBridge.Host.dll"),
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("could not find Sts2Mod.StateBridge.Host.dll; build the solution first")
    return candidates[0]


def main() -> int:
    """
    This script validates the menu run start flow in fixture-host mode.

    For live in-game validation:
    - Start STS2 with the mod enabled (in-game-runtime mode)
    - Ensure the bridge is reachable at http://127.0.0.1:17654
    - Then run the same steps against that base_url by adapting this script.
    """
    port = pick_free_port()
    base_url = f"http://127.0.0.1:{port}"
    command = [
        "dotnet",
        str(resolve_host_dll()),
        "--port",
        str(port),
        "--game-version",
        "prototype",
        "--read-only",
        "false",
    ]
    process = subprocess.Popen(command, cwd=ROOT)
    try:
        # Fixture starts in combat; request menu explicitly to set phase.
        snapshot, actions = wait_for_menu_actions(base_url)
        assert snapshot["phase"] == "menu"

        action = next((a for a in actions if a.get("type") in {"continue_run", "start_new_run"}), None)
        assert action is not None, f"expected continue_run/start_new_run in menu actions, got {[a.get('type') for a in actions]}"

        status_code, apply_response = post_json(
            base_url,
            "/apply",
            {
                "decision_id": snapshot["decision_id"],
                "action_id": action["action_id"],
                "params": {},
            },
        )
        assert status_code == 200, apply_response
        assert apply_response["status"] == "accepted"

        # After applying, fixture should move into map phase (run started).
        next_snapshot = fetch(base_url, "/snapshot")
        assert next_snapshot["phase"] in {"map", "combat", "reward"}, next_snapshot
        print("menu run start validation passed")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())


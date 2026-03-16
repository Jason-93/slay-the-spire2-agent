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
    """Pick a free localhost TCP port.

    Prefer the well-known bridge port when available, but fall back to an ephemeral port
    to avoid collisions with a running in-game bridge.
    """
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


def wait_for_server(base_url: str) -> None:
    for _ in range(40):
        try:
            payload = fetch(base_url, "/health")
            if payload.get("healthy") is True:
                return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("bridge server did not become healthy in time")


def resolve_host_dll() -> Path:
    candidates = sorted(
        (ROOT / "mod" / "Sts2Mod.StateBridge.Host" / "bin" / "Debug").glob("net*/Sts2Mod.StateBridge.Host.dll"),
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("could not find Sts2Mod.StateBridge.Host.dll; build the solution first")
    return candidates[0]


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


def validate_shop_flow() -> None:
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
        wait_for_server(base_url)
        shop_snapshot = fetch(base_url, "/snapshot?phase=shop")
        shop_actions = fetch(base_url, "/actions?phase=shop")
        assert shop_snapshot["phase"] == "shop"
        assert shop_snapshot["metadata"]["window_kind"] == "shop_main"
        assert isinstance(shop_snapshot["metadata"]["shop_offers"], list)
        assert shop_snapshot["metadata"]["shop_offer_count"] == len(shop_snapshot["metadata"]["shop_offers"])
        assert any(action["type"] == "leave_shop" for action in shop_actions)
        assert any(action["type"] == "buy_shop_card" for action in shop_actions)

        buy_shop_card = next(action for action in shop_actions if action["type"] == "buy_shop_card")
        status_code, apply_response = post_json(
            base_url,
            "/apply",
            {
                "decision_id": shop_snapshot["decision_id"],
                "action_id": buy_shop_card["action_id"],
                "params": {},
            },
        )
        assert status_code == 200
        assert apply_response["status"] == "accepted"

        shop_low_gold_snapshot = fetch(base_url, "/snapshot")
        assert shop_low_gold_snapshot["phase"] == "shop"
        assert any(offer["unavailable_reason"] == "not_affordable" for offer in shop_low_gold_snapshot["metadata"]["shop_offers"])

        shop_low_gold_actions = fetch(base_url, "/actions")
        leave_low_gold_shop = next(action for action in shop_low_gold_actions if action["type"] == "leave_shop")
        status_code, leave_response = post_json(
            base_url,
            "/apply",
            {
                "decision_id": shop_low_gold_snapshot["decision_id"],
                "action_id": leave_low_gold_shop["action_id"],
                "params": {},
            },
        )
        assert status_code == 200
        assert leave_response["status"] == "accepted"

        post_shop_map_snapshot = fetch(base_url, "/snapshot")
        assert post_shop_map_snapshot["phase"] == "map"

        status_code, stale_shop_response = post_json(
            base_url,
            "/apply",
            {
                "decision_id": shop_snapshot["decision_id"],
                "action_id": leave_low_gold_shop["action_id"],
                "params": {},
            },
        )
        assert status_code == 409
        assert stale_shop_response["error_code"] == "stale_decision"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main() -> int:
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
        wait_for_server(base_url)
        health = fetch(base_url, "/health")
        assert health["protocol_version"] == "0.1.0"
        for phase in ("combat", "reward", "map", "event", "shop", "terminal"):
            snapshot = fetch(base_url, f"/snapshot?phase={phase}")
            actions = fetch(base_url, f"/actions?phase={phase}")
            assert snapshot["phase"] == phase
            assert snapshot["compatibility"]["provider_mode"] == "fixture"
            if phase == "terminal":
                assert snapshot["terminal"] is True
                assert actions == []
            else:
                assert snapshot["terminal"] is False
                assert len(actions) >= 1
        combat_snapshot = fetch(base_url, "/snapshot?phase=combat")
        assert combat_snapshot["player"]["hand"][0]["description"]
        assert combat_snapshot["player"]["hand"][0]["glossary"]
        assert combat_snapshot["player"]["hand"][0]["glossary"][0]["source"] == "runtime_hover_tip"
        assert "description_quality" not in combat_snapshot["player"]["hand"][0]
        assert "description_source" not in combat_snapshot["player"]["hand"][0]
        assert "description_vars" not in combat_snapshot["player"]["hand"][0]
        assert combat_snapshot["player"]["relics"][0]["name"] == "Burning Blood"
        assert combat_snapshot["player"]["relics"][0]["description"] == "At the end of combat, heal 6 HP."
        assert combat_snapshot["player"]["relics"][0]["canonical_relic_id"] == "burning_blood"
        assert "description_quality" not in combat_snapshot["player"]["relics"][0]
        assert "description_source" not in combat_snapshot["player"]["relics"][0]
        assert "description_vars" not in combat_snapshot["player"]["relics"][0]
        for relic in combat_snapshot["player"]["relics"]:
            for anchor in relic.get("glossary", []):
                assert anchor.get("hint") not in (None, "")
                assert anchor.get("source") != "missing_hint"
                assert "{" not in str(anchor.get("hint") or "")
        for potion in combat_snapshot["player"]["potions"]:
            assert potion.get("description")
            for anchor in potion.get("glossary", []):
                assert anchor.get("hint") not in (None, "")
                assert anchor.get("source") != "missing_hint"
                assert "{" not in str(anchor.get("hint") or "")
        assert isinstance(combat_snapshot["player"]["draw_pile_cards"], list)
        assert isinstance(combat_snapshot["player"]["discard_pile_cards"], list)
        assert isinstance(combat_snapshot["player"]["exhaust_pile_cards"], list)
        assert combat_snapshot["player"]["draw_pile"] == len(combat_snapshot["player"]["draw_pile_cards"])
        assert combat_snapshot["player"]["discard_pile"] == len(combat_snapshot["player"]["discard_pile_cards"])
        assert combat_snapshot["player"]["exhaust_pile"] == len(combat_snapshot["player"]["exhaust_pile_cards"])
        assert combat_snapshot["player"]["draw_pile_cards"][0]["description"]
        assert combat_snapshot["player"]["discard_pile_cards"][0]["glossary"]
        assert combat_snapshot["player"]["powers"][0]["name"]
        assert any(anchor["source"] == "model_description" for anchor in combat_snapshot["player"]["powers"][0]["glossary"])
        assert "description_vars" not in combat_snapshot["player"]["powers"][0]
        assert combat_snapshot["enemies"][0]["intent_type"]
        assert combat_snapshot["enemies"][0]["move_name"]
        assert combat_snapshot["enemies"][0]["move_description"]
        assert combat_snapshot["enemies"][0]["move_glossary"]
        assert combat_snapshot["enemies"][0]["traits"]
        assert combat_snapshot["enemies"][0]["keywords"]
        for keyword in combat_snapshot["enemies"][0]["keywords"]:
            assert "." not in keyword
        assert combat_snapshot["enemies"][0]["powers"][0]["name"]
        assert combat_snapshot["enemies"][0]["powers"][0]["glossary"]
        assert not any(
            anchor["glossary_id"] == combat_snapshot["enemies"][0]["powers"][0].get("canonical_power_id")
            for anchor in combat_snapshot["enemies"][0]["powers"][0]["glossary"]
        )
        assert "degraded" in combat_snapshot["metadata"]["enemy_export"]
        assert combat_snapshot["run_state"]["act"] == 1
        assert combat_snapshot["run_state"]["map"]["reachable_nodes"]
        combat_actions = fetch(base_url, "/actions?phase=combat")
        status_code, apply_response = post_json(
            base_url,
            "/apply",
            {
                "decision_id": combat_snapshot["decision_id"],
                "action_id": combat_actions[0]["action_id"],
                "params": {},
            },
        )
        assert status_code == 200
        assert apply_response["status"] == "accepted"
        reward_snapshot = fetch(base_url, "/snapshot")
        assert reward_snapshot["phase"] == "reward"
        assert isinstance(reward_snapshot["player"]["draw_pile_cards"], list)
        assert isinstance(reward_snapshot["player"]["discard_pile_cards"], list)

        # Simulate reward chain: choose a reward, then select a concrete card reward.
        reward_actions = fetch(base_url, "/actions")
        choose_reward = next(action for action in reward_actions if action["type"] == "choose_reward")
        status_code, apply_response = post_json(
            base_url,
            "/apply",
            {
                "decision_id": reward_snapshot["decision_id"],
                "action_id": choose_reward["action_id"],
                "params": {},
            },
        )
        assert status_code == 200
        assert apply_response["status"] == "accepted"
        card_snapshot = fetch(base_url, "/snapshot")
        assert card_snapshot["phase"] == "reward"
        assert card_snapshot["metadata"]["window_kind"] == "reward_card_selection"
        assert card_snapshot["metadata"]["reward_subphase"] == "card_reward_selection"
        card_actions = fetch(base_url, "/actions")
        assert any(action["type"] == "choose_reward" for action in card_actions)
        assert any(action["type"] == "skip_reward" for action in card_actions)

        choose_card = next(action for action in card_actions if action["type"] == "choose_reward")
        status_code, apply_response = post_json(
            base_url,
            "/apply",
            {
                "decision_id": card_snapshot["decision_id"],
                "action_id": choose_card["action_id"],
                "params": {},
            },
        )
        assert status_code == 200
        assert apply_response["status"] == "accepted"
        map_snapshot = fetch(base_url, "/snapshot")
        assert map_snapshot["phase"] == "map"
        assert isinstance(map_snapshot["player"]["draw_pile_cards"], list)
        assert isinstance(map_snapshot["player"]["discard_pile_cards"], list)

        event_snapshot = fetch(base_url, "/snapshot?phase=event")
        assert event_snapshot["phase"] == "event"
        assert event_snapshot["metadata"]["window_kind"] == "event_choice"
        assert event_snapshot["metadata"]["event_title"]
        assert event_snapshot["metadata"]["event_body"]
        assert isinstance(event_snapshot["metadata"]["event_options"], list)
        event_actions = fetch(base_url, "/actions?phase=event")
        choose_event = next(action for action in event_actions if action["type"] == "choose_event_option")
        assert "option_label" not in choose_event["params"]
        status_code, apply_response = post_json(
            base_url,
            "/apply",
            {
                "decision_id": event_snapshot["decision_id"],
                "action_id": choose_event["action_id"],
                "params": {},
            },
        )
        assert status_code == 200
        assert apply_response["status"] == "accepted"
        event_card_snapshot = fetch(base_url, "/snapshot?phase=event")
        assert event_card_snapshot["metadata"]["window_kind"] == "event_choice"
        assert event_card_snapshot["metadata"]["event_subphase"] == "card_selection"
        assert event_card_snapshot["metadata"]["event_selection_prompt"]
        assert event_card_snapshot["metadata"]["event_options"][0]["card_id"]
        assert event_card_snapshot["metadata"]["event_options"][0]["description"]
        assert event_card_snapshot["metadata"]["event_options"][0]["glossary"][0]["source"] == "runtime_hover_tip"
        event_card_actions = fetch(base_url, "/actions?phase=event")
        choose_event_card = next(action for action in event_card_actions if action["type"] == "choose_event_option")
        assert "option_label" not in choose_event_card["params"]
        assert choose_event_card["metadata"]["event_option"]["description"]
        assert choose_event_card["metadata"]["event_option"]["glossary"][0]["display_text"]
        status_code, apply_response = post_json(
            base_url,
            "/apply",
            {
                "decision_id": event_card_snapshot["decision_id"],
                "action_id": choose_event_card["action_id"],
                "params": {},
            },
        )
        assert status_code == 200
        assert apply_response["status"] == "accepted"
        event_continue_snapshot = fetch(base_url, "/snapshot?phase=event")
        assert event_continue_snapshot["metadata"]["window_kind"] == "event_continue"
        continue_actions = fetch(base_url, "/actions?phase=event")
        continue_event = next(action for action in continue_actions if action["type"] == "continue_event")
        status_code, apply_response = post_json(
            base_url,
            "/apply",
            {
                "decision_id": event_continue_snapshot["decision_id"],
                "action_id": continue_event["action_id"],
                "params": {},
            },
        )
        assert status_code == 200
        assert apply_response["status"] == "accepted"
        event_map_snapshot = fetch(base_url, "/snapshot?phase=map")
        assert event_map_snapshot["phase"] == "map"

        status_code, stale_response = post_json(
            base_url,
            "/apply",
            {
                "decision_id": combat_snapshot["decision_id"],
                "action_id": combat_actions[0]["action_id"],
                "params": {},
            },
        )
        assert status_code == 409
        assert stale_response["status"] == "rejected"
        assert stale_response["error_code"] == "stale_decision"
        validate_shop_flow()
        print("mod bridge validation passed")
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

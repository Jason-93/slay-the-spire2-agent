from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from sts2_agent.bridge import (
    BridgeSession,
    HttpGameBridge,
    HttpGameBridgeConfig,
    InvalidPayloadError,
    MockGameBridge,
    RemoteBridgeError,
    StaleActionError,
)
from sts2_agent.models import ActionSubmission


class MockBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = MockGameBridge()
        self.session = self.bridge.attach_or_start()

    def test_combat_snapshot_exposes_expected_actions(self) -> None:
        snapshot = self.bridge.get_snapshot(self.session.session_id)
        actions = self.bridge.get_legal_actions(self.session.session_id)

        self.assertEqual(snapshot.phase, "combat")
        self.assertEqual(len(actions), 4)
        self.assertEqual({action.type for action in actions}, {"play_card", "use_potion", "end_turn"})

    def test_bridge_rejects_stale_action_without_state_mutation(self) -> None:
        snapshot = self.bridge.get_snapshot(self.session.session_id)
        first_action = self.bridge.get_legal_actions(self.session.session_id)[0]

        self.bridge.submit_action(
            ActionSubmission(
                session_id=snapshot.session_id,
                decision_id=snapshot.decision_id,
                state_version=snapshot.state_version,
                action_id=first_action.action_id,
            )
        )

        with self.assertRaises(StaleActionError):
            self.bridge.submit_action(
                ActionSubmission(
                    session_id=snapshot.session_id,
                    decision_id=snapshot.decision_id,
                    state_version=snapshot.state_version,
                    action_id=first_action.action_id,
                )
            )

        latest = self.bridge.get_snapshot(self.session.session_id)
        self.assertEqual(latest.state_version, 1)
        self.assertEqual(latest.phase, "reward")

    def test_bridge_rejects_invalid_action(self) -> None:
        snapshot = self.bridge.get_snapshot(self.session.session_id)
        with self.assertRaises(InvalidPayloadError):
            self.bridge.submit_action(
                ActionSubmission(
                    session_id=snapshot.session_id,
                    decision_id=snapshot.decision_id,
                    state_version=snapshot.state_version,
                    action_id="act-not-legal",
                )
            )


class FakeHttpResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def make_http_error(url: str, payload: dict[str, object]) -> HTTPError:
    return HTTPError(
        url=url,
        code=409,
        msg="conflict",
        hdrs=None,
        fp=io.BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
    )


class HttpBridgeTests(unittest.TestCase):
    def test_attach_or_start_rejects_unreachable_bridge(self) -> None:
        bridge = HttpGameBridge(HttpGameBridgeConfig(base_url="http://127.0.0.1:17654"))
        with patch("sts2_agent.bridge.http.urlopen", side_effect=URLError("refused")):
            with self.assertRaises(RemoteBridgeError) as ctx:
                bridge.attach_or_start()

        self.assertEqual(ctx.exception.error_code, "bridge_unreachable")

    def test_http_bridge_reads_snapshot_actions_and_accepted_apply(self) -> None:
        bridge = HttpGameBridge(HttpGameBridgeConfig(base_url="http://127.0.0.1:17654"))
        calls = iter(
            [
                {"healthy": True},
                {
                    "session_id": "sess-live1234",
                    "decision_id": "dec-live1234",
                    "state_version": 7,
                    "phase": "combat",
                    "player": {"hp": 80, "max_hp": 80, "block": 0, "energy": 3, "gold": 99, "hand": []},
                    "enemies": [],
                    "rewards": [],
                    "map_nodes": [],
                    "terminal": False,
                    "metadata": {"source": "runtime"},
                },
                {
                    "session_id": "sess-live1234",
                    "decision_id": "dec-live1234",
                    "state_version": 7,
                    "phase": "combat",
                    "player": {"hp": 80, "max_hp": 80, "block": 0, "energy": 3, "gold": 99, "hand": []},
                    "enemies": [],
                    "rewards": [],
                    "map_nodes": [],
                    "terminal": False,
                    "metadata": {"source": "runtime"},
                },
                [
                    {
                        "action_id": "act-live1234",
                        "type": "end_turn",
                        "label": "End Turn",
                        "params": {},
                        "target_constraints": [],
                        "metadata": {},
                    }
                ],
                {
                    "request_id": "req-live",
                    "decision_id": "dec-live1234",
                    "action_id": "act-live1234",
                    "status": "accepted",
                    "message": "ok",
                    "metadata": {"state_version": 8, "phase": "combat"},
                },
            ]
        )

        def fake_urlopen(request, timeout=0):
            return FakeHttpResponse(next(calls))

        with patch("sts2_agent.bridge.http.urlopen", side_effect=fake_urlopen):
            session = bridge.attach_or_start()
            snapshot = bridge.get_snapshot(session.session_id)
            actions = bridge.get_legal_actions(session.session_id)
            result = bridge.submit_action(
                ActionSubmission(
                    session_id=session.session_id,
                    decision_id=snapshot.decision_id,
                    state_version=snapshot.state_version,
                    action_id=actions[0].action_id,
                )
            )

        self.assertEqual(session.session_id, "sess-live1234")
        self.assertEqual(snapshot.phase, "combat")
        self.assertEqual(len(actions), 1)
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.accepted_action_id, "act-live1234")
        self.assertEqual(result.state_version, 8)

    def test_http_bridge_maps_stale_decision(self) -> None:
        bridge = HttpGameBridge(HttpGameBridgeConfig(base_url="http://127.0.0.1:17654"))
        bridge._sessions["sess-live1234"] = BridgeSession(session_id="sess-live1234", scenario="live", state_version=7)

        with patch(
            "sts2_agent.bridge.http.urlopen",
            side_effect=make_http_error(
                "http://127.0.0.1:17654/apply",
                {
                    "status": "rejected",
                    "error_code": "stale_decision",
                    "message": "stale",
                },
            ),
        ):
            with self.assertRaises(StaleActionError):
                bridge.submit_action(
                    ActionSubmission(
                        session_id="sess-live1234",
                        decision_id="dec-live1234",
                        state_version=7,
                        action_id="act-live1234",
                    )
                )

    def test_http_bridge_maps_illegal_action(self) -> None:
        bridge = HttpGameBridge(HttpGameBridgeConfig(base_url="http://127.0.0.1:17654"))
        bridge._sessions["sess-live1234"] = BridgeSession(session_id="sess-live1234", scenario="live", state_version=7)

        with patch(
            "sts2_agent.bridge.http.urlopen",
            side_effect=make_http_error(
                "http://127.0.0.1:17654/apply",
                {
                    "status": "rejected",
                    "error_code": "illegal_action",
                    "message": "illegal",
                },
            ),
        ):
            with self.assertRaises(InvalidPayloadError):
                bridge.submit_action(
                    ActionSubmission(
                        session_id="sess-live1234",
                        decision_id="dec-live1234",
                        state_version=7,
                        action_id="act-illegal",
                    )
                )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sts2_agent.models import BattleContext, DecisionSnapshot, LegalAction, PolicyDecision, to_dict
from sts2_agent.policy.base import PolicyError


class ChatCompletionsRequestError(PolicyError):
    error_code = "llm_request_error"


class ChatCompletionsTimeoutError(PolicyError):
    error_code = "llm_timeout"


class ChatCompletionsParseError(PolicyError):
    error_code = "llm_parse_error"


@dataclass(slots=True)
class ChatCompletionsConfig:
    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "default"
    api_key: str | None = None
    timeout_seconds: float = 20.0
    temperature: float = 0.2
    max_tokens: int = 256


class ChatCompletionsPolicy:
    def __init__(self, config: ChatCompletionsConfig | None = None) -> None:
        self.config = config or ChatCompletionsConfig()

    def decide(
        self,
        snapshot: DecisionSnapshot,
        legal_actions: list[LegalAction],
        battle_context: BattleContext | None = None,
    ) -> PolicyDecision:
        messages = self._build_messages(snapshot, legal_actions, battle_context=battle_context)
        request_payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": False,
        }
        response_payload = self._post_json("/chat/completions", request_payload)
        raw_content = self._extract_content(response_payload)
        parsed = self._parse_response_text(raw_content)
        decision = PolicyDecision(
            action_id=parsed["action_id"],
            reason=parsed["reason"],
            detail=parsed["detail"],
            halt=parsed["halt"],
            metadata={
                "provider": "chat_completions",
                "model": self.config.model,
                "parse_status": "ok",
                "request_payload_summary": {
                    "message_count": len(messages),
                    "legal_action_count": len(legal_actions),
                    "phase": snapshot.phase,
                    "battle_context_present": battle_context is not None,
                },
                "raw_response_text": raw_content,
            },
            confidence=parsed["confidence"],
        )
        if parsed["args"]:
            decision.metadata["action_args"] = parsed["args"]
        if parsed["confidence"] is not None:
            decision.metadata["confidence"] = parsed["confidence"]
        return decision

    def _build_messages(
        self,
        snapshot: DecisionSnapshot,
        legal_actions: list[LegalAction],
        *,
        battle_context: BattleContext | None = None,
    ) -> list[dict[str, str]]:
        system_prompt = (
            "你是 Slay the Spire 2 自动打牌 agent。"
            "只能从给定 legal actions 中选择一个 action_id。"
            "battle_context 只用于理解最近发生了什么，里面若出现历史动作摘要也绝不能直接复用旧 action_id。"
            "必须返回 JSON，字段为 action_id、target_id、reason、detail、halt、confidence。"
            "如果你认为当前不应继续自动操作，可以返回 halt=true 且 action_id=null。"
            "若所选动作有多个 target_constraints，必须显式返回一个合法 target_id。"
            "confidence 必须返回你对本次决策把握度的简短分级，例如 high、medium、low。"
            "reason 用一句短话概括本次动作。"
            "detail 用 1-3 句中文说明关键依据，便于在游戏 HUD 中显示；不要长篇展开。"
            "snapshot 里的手牌、敌人、powers、intent 和 run_state 都是当前局面的事实层信息，应优先基于这些字段判断，而不是只猜卡名。"
            "当 snapshot.phase=combat 且 metadata.window_kind=combat_card_selection 时，说明当前不是普通出牌窗口，而是在处理战斗中的额外选牌；"
            "此时应优先在 choose_combat_card 或 cancel_combat_selection 中决策，而不是继续选择 play_card。"
            "当 snapshot.phase=reward 时，你需要在 choose_reward 或 skip_reward 等奖励动作中做选择；"
            "若不确定，优先返回 halt=true 或选择 skip_reward（并在 reason 说明原因）。"
            "当 snapshot.phase=map 时，只能在 choose_map_node 中选择一个可达节点；"
            "若没有足够信息判断路线，请优先选择更保守的普通战斗节点。"
        )
        user_payload = {
            "snapshot": self._summarize_snapshot(snapshot),
            "legal_actions": [self._summarize_action(action) for action in legal_actions],
            "output_schema": {
                "action_id": "string|null",
                "target_id": "string|null, required when selected action has multiple target_constraints",
                "reason": "string",
                "detail": "string, optional concise rationale for HUD",
                "halt": "boolean",
                "confidence": "string|number",
            },
        }
        if battle_context is not None:
            user_payload["battle_context"] = self._summarize_battle_context(battle_context)
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = Request(
            self.config.base_url.rstrip("/") + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            message = self._read_error_body(exc) or f"http {exc.code}"
            raise ChatCompletionsRequestError(message) from exc
        except TimeoutError as exc:
            raise ChatCompletionsTimeoutError("chat completions request timed out") from exc
        except URLError as exc:
            raise ChatCompletionsRequestError(f"chat completions request failed: {exc.reason}") from exc

    @staticmethod
    def _read_error_body(exc: HTTPError) -> str | None:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            return None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error)
            return str(payload.get("message") or payload)
        return None

    @staticmethod
    def _extract_content(payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ChatCompletionsParseError("chat completions response missing choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise ChatCompletionsParseError("chat completions choice payload is invalid")
        message = first.get("message")
        if not isinstance(message, dict):
            raise ChatCompletionsParseError("chat completions response missing message")
        content = message.get("content")
        if not isinstance(content, str):
            raise ChatCompletionsParseError("chat completions response content is not a string")
        return content.strip()

    @staticmethod
    def _parse_response_text(text: str) -> dict[str, Any]:
        candidate = text.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            candidate = "\n".join(lines).strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            extracted = ChatCompletionsPolicy._extract_json_object(candidate)
            if extracted is None:
                raise ChatCompletionsParseError("chat completions response is not valid JSON") from exc
            try:
                payload = json.loads(extracted)
            except json.JSONDecodeError as nested_exc:
                raise ChatCompletionsParseError("chat completions response is not valid JSON") from nested_exc
        if not isinstance(payload, dict):
            raise ChatCompletionsParseError("chat completions response JSON must be an object")
        action_id = payload.get("action_id")
        target_id = payload.get("target_id")
        reason = payload.get("reason")
        detail = payload.get("detail")
        halt = payload.get("halt")
        confidence = payload.get("confidence")
        args = payload.get("args")
        if action_id is not None and not isinstance(action_id, str):
            raise ChatCompletionsParseError("action_id must be a string or null")
        if target_id is not None and not isinstance(target_id, str):
            raise ChatCompletionsParseError("target_id must be a string or null")
        if not isinstance(reason, str) or not reason.strip():
            raise ChatCompletionsParseError("reason must be a non-empty string")
        if detail is not None and (not isinstance(detail, str) or not detail.strip()):
            raise ChatCompletionsParseError("detail must be a non-empty string when provided")
        if not isinstance(halt, bool):
            raise ChatCompletionsParseError("halt must be a boolean")
        if confidence is None or not isinstance(confidence, (str, int, float)) or isinstance(confidence, bool):
            raise ChatCompletionsParseError("confidence must be a string or number")
        if args is None:
            normalized_args: dict[str, Any] = {}
        else:
            if not isinstance(args, dict):
                raise ChatCompletionsParseError("args must be an object when provided")
            normalized_args = dict(args)
            nested_target_id = normalized_args.get("target_id")
            if nested_target_id is not None and not isinstance(nested_target_id, str):
                raise ChatCompletionsParseError("args.target_id must be a string when provided")
        if target_id is not None:
            normalized_args["target_id"] = target_id
        return {
            "action_id": action_id,
            "reason": reason.strip(),
            "detail": detail.strip() if isinstance(detail, str) and detail.strip() else reason.strip(),
            "halt": halt,
            "args": normalized_args,
            "confidence": confidence,
        }

    @staticmethod
    def _extract_json_object(text: str) -> str | None:
        start = text.find("{")
        if start < 0:
            return None
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return None

    @staticmethod
    def _summarize_action(action: LegalAction) -> dict[str, Any]:
        payload = {
            "action_id": action.action_id,
            "type": action.type,
            "label": action.label,
            "params": to_dict(action.params),
            "target_constraints": to_dict(action.target_constraints),
        }
        card_preview = action.metadata.get("card_preview")
        if isinstance(card_preview, dict):
            payload["card_preview"] = to_dict(card_preview)
        potion_preview = action.metadata.get("potion_preview")
        if isinstance(potion_preview, dict):
            payload["potion_preview"] = to_dict(potion_preview)
        return payload

    @staticmethod
    def _summarize_battle_context(battle_context: BattleContext) -> dict[str, Any]:
        payload = to_dict(battle_context)
        recent_steps = payload.get("recent_steps")
        if isinstance(recent_steps, list):
            sanitized_steps: list[dict[str, Any]] = []
            for step in recent_steps:
                if not isinstance(step, dict):
                    continue
                sanitized_step = {
                    key: value
                    for key, value in step.items()
                    if key not in {"action_id"}
                }
                sanitized_steps.append(sanitized_step)
            payload["recent_steps"] = sanitized_steps
        return payload

    @staticmethod
    def _summarize_snapshot(snapshot: DecisionSnapshot) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_id": snapshot.session_id,
            "decision_id": snapshot.decision_id,
            "state_version": snapshot.state_version,
            "phase": snapshot.phase,
            "terminal": snapshot.terminal,
        }
        if snapshot.player is not None:
            payload["player"] = {
                "hp": snapshot.player.hp,
                "max_hp": snapshot.player.max_hp,
                "block": snapshot.player.block,
                "energy": snapshot.player.energy,
                "gold": snapshot.player.gold,
                "draw_pile": snapshot.player.draw_pile,
                "discard_pile": snapshot.player.discard_pile,
                "exhaust_pile": snapshot.player.exhaust_pile,
                "hand": [ChatCompletionsPolicy._summarize_card(card) for card in snapshot.player.hand],
                "draw_pile_cards": [ChatCompletionsPolicy._summarize_card(card) for card in snapshot.player.draw_pile_cards],
                "discard_pile_cards": [ChatCompletionsPolicy._summarize_card(card) for card in snapshot.player.discard_pile_cards],
                "exhaust_pile_cards": [ChatCompletionsPolicy._summarize_card(card) for card in snapshot.player.exhaust_pile_cards],
                "relics": [ChatCompletionsPolicy._summarize_relic(relic) for relic in snapshot.player.relics],
                "potions": [ChatCompletionsPolicy._summarize_potion(potion) for potion in snapshot.player.potions],
                "potion_capacity": snapshot.player.potion_capacity,
                "powers": [ChatCompletionsPolicy._summarize_power(power) for power in snapshot.player.powers],
            }
        if snapshot.enemies:
            payload["enemies"] = [ChatCompletionsPolicy._summarize_enemy(enemy) for enemy in snapshot.enemies]
        if snapshot.rewards:
            payload["rewards"] = list(snapshot.rewards)
        if snapshot.map_nodes:
            payload["map_nodes"] = list(snapshot.map_nodes)
        if snapshot.run_state is not None:
            payload["run_state"] = ChatCompletionsPolicy._summarize_run_state(snapshot)
        if snapshot.metadata:
            metadata_summary = {
                key: snapshot.metadata[key]
                for key in (
                    "window_kind",
                    "current_side",
                    "selection_kind",
                    "selection_prompt",
                    "selection_choice_count",
                    "selection_cancel_available",
                    "transition_kind",
                    "reward_subphase",
                    "map_ready",
                    "reward_pending",
                )
                if key in snapshot.metadata
            }
            if metadata_summary:
                payload["metadata"] = metadata_summary
        return payload

    @staticmethod
    def _summarize_card(card: Any) -> dict[str, Any]:
        payload = {
            "card_id": card.card_id,
            "name": card.name,
            "cost": card.cost,
            "playable": card.playable,
        }
        optional_values = {
            "canonical_card_id": card.canonical_card_id,
            "description": ChatCompletionsPolicy._preferred_description_text(card),
            "glossary": ChatCompletionsPolicy._summarize_glossary(getattr(card, "glossary", [])),
            "cost_for_turn": card.cost_for_turn,
            "upgraded": card.upgraded,
            "target_type": card.target_type,
            "card_type": card.card_type,
            "rarity": card.rarity,
            "traits": list(card.traits),
            "keywords": list(card.keywords),
        }
        for key, value in optional_values.items():
            if value not in (None, [], ""):
                payload[key] = value
        return payload

    @staticmethod
    def _summarize_power(power: Any) -> dict[str, Any]:
        payload = {
            "power_id": power.power_id,
            "name": power.name,
        }
        preferred_description = ChatCompletionsPolicy._preferred_description_text(power)
        if power.amount is not None:
            payload["amount"] = power.amount
        if preferred_description:
            payload["description"] = preferred_description
        glossary = ChatCompletionsPolicy._summarize_glossary(getattr(power, "glossary", []))
        if glossary:
            payload["glossary"] = glossary
        if power.canonical_power_id:
            payload["canonical_power_id"] = power.canonical_power_id
        return payload

    @staticmethod
    def _summarize_potion(potion: Any) -> dict[str, Any]:
        payload = {
            "name": potion.name,
        }
        preferred_description = ChatCompletionsPolicy._preferred_description_text(potion)
        if preferred_description:
            payload["description"] = preferred_description
        glossary = ChatCompletionsPolicy._summarize_glossary(getattr(potion, "glossary", []))
        if glossary:
            payload["glossary"] = glossary
        canonical_potion_id = getattr(potion, "canonical_potion_id", None)
        if isinstance(canonical_potion_id, str) and canonical_potion_id:
            payload["canonical_potion_id"] = canonical_potion_id
        return payload

    @staticmethod
    def _summarize_relic(relic: Any) -> dict[str, Any]:
        payload = {
            "name": relic.name,
        }
        preferred_description = ChatCompletionsPolicy._preferred_description_text(relic)
        if preferred_description:
            payload["description"] = preferred_description
        glossary = ChatCompletionsPolicy._summarize_glossary(getattr(relic, "glossary", []))
        if glossary:
            payload["glossary"] = glossary
        canonical_relic_id = getattr(relic, "canonical_relic_id", None)
        if isinstance(canonical_relic_id, str) and canonical_relic_id:
            payload["canonical_relic_id"] = canonical_relic_id
        return payload

    @staticmethod
    def _summarize_enemy(enemy: Any) -> dict[str, Any]:
        move_name = enemy.move_name
        if move_name in {enemy.intent, enemy.intent_raw, enemy.intent_type}:
            move_name = None

        payload = {
            "enemy_id": enemy.enemy_id,
            "name": enemy.name,
            "hp": enemy.hp,
            "max_hp": enemy.max_hp,
            "block": enemy.block,
            "intent": enemy.intent,
            "is_alive": enemy.is_alive,
        }
        optional_values = {
            "canonical_enemy_id": enemy.canonical_enemy_id,
            "intent_type": enemy.intent_type,
            "intent_damage": enemy.intent_damage,
            "intent_hits": enemy.intent_hits,
            "intent_block": enemy.intent_block,
            "intent_effects": list(enemy.intent_effects),
            "move_name": move_name,
            "move_description": ChatCompletionsPolicy._preferred_description_text(enemy),
            "move_glossary": ChatCompletionsPolicy._summarize_glossary(getattr(enemy, "move_glossary", [])),
            "traits": list(enemy.traits),
            "keywords": list(enemy.keywords),
        }
        for key, value in optional_values.items():
            if value not in (None, [], ""):
                payload[key] = value
        if enemy.powers:
            payload["powers"] = [ChatCompletionsPolicy._summarize_power(power) for power in enemy.powers]
        return payload

    @staticmethod
    def _summarize_run_state(snapshot: DecisionSnapshot) -> dict[str, Any]:
        assert snapshot.run_state is not None
        payload = {
            "act": snapshot.run_state.act,
            "floor": snapshot.run_state.floor,
            "current_room_type": snapshot.run_state.current_room_type,
            "current_location_type": snapshot.run_state.current_location_type,
            "current_act_index": snapshot.run_state.current_act_index,
            "ascension_level": snapshot.run_state.ascension_level,
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        if snapshot.run_state.map is not None:
            map_payload = {
                "current_coord": snapshot.run_state.map.current_coord,
                "current_node_type": snapshot.run_state.map.current_node_type,
                "reachable_nodes": list(snapshot.run_state.map.reachable_nodes),
                "source": snapshot.run_state.map.source,
            }
            payload["map"] = {
                key: value
                for key, value in map_payload.items()
                if value not in (None, [], "")
            }
        return payload

    @staticmethod
    def _preferred_description_text(item: Any) -> str | None:
        move_description = getattr(item, "move_description", None)
        if isinstance(move_description, str) and move_description:
            return move_description
        description = getattr(item, "description", None)
        if isinstance(description, str) and description:
            return description
        return None

    @staticmethod
    def _summarize_glossary(glossary: Any) -> list[dict[str, str]]:
        if not isinstance(glossary, list):
            return []
        payload: list[dict[str, str]] = []
        for item in glossary[:4]:
            glossary_id = getattr(item, "glossary_id", None)
            display_text = getattr(item, "display_text", None)
            if not isinstance(glossary_id, str) or not glossary_id:
                continue
            if not isinstance(display_text, str) or not display_text:
                continue
            entry = {"id": glossary_id, "text": display_text}
            hint = getattr(item, "hint", None)
            if isinstance(hint, str) and hint:
                entry["hint"] = hint
            payload.append(entry)
        return payload

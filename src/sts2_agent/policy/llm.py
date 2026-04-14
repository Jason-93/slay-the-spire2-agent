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
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str = "llama3"
    api_key: str | None = "ollama"
    timeout_seconds: float = 20.0
    temperature: float = 0.2
    max_tokens: int = 256


class ChatCompletionsPolicy:
    GENERIC_RULES: tuple[str, ...] = (
        "只能依据当前 snapshot、legal_actions、battle_context 决策；若某效果不在这些信息里，不要脑补。",
        "必须逐字区分时机词：'回合结束时' 只在当前回合结束触发，'战斗结束时' 只在战斗胜利/结束后触发，二者不能混淆。",
        "结束回合会放弃当前剩余能量与继续出牌机会；除非确实没有更有价值的合法动作，否则不要轻易选择 end_turn。",
        "格挡用于抵挡即将到来的伤害；若敌人意图攻击，你应通过 intent_damage * intent_hits 计算本回合总预期伤害，并比较格挡、减伤、直接击杀或其他动作的优劣。",
        "每回合都应尽可能减少本回合战损。注意观察抽牌堆 (draw_pile) 与弃牌堆 (discard_pile) 的剩余牌量及具体牌面，这有助于预判后续回合的资源。",
        "弃牌堆中包含你已经使用过或丢弃的牌；抽牌堆是即将抽入手的牌；消耗堆 (exhaust_pile) 中的牌在本次战斗中通常不再可用。",
        "敌人的力量、易伤、格挡等状态默认只影响对应敌人本身；除非 description 明确写作用于玩家，否则不要把敌方状态当成玩家增益。",
        "若某张牌、药水、遗物、能力提供了 description 或 glossary，优先按这些文本的字面效果理解，不要把别的卡牌/遗物规则套过来。",
        "若描述写的是战斗结束回血、回合结束得格挡、抽牌后触发等，必须严格按描述时机判断，不能提前或延后生效。",
        "当 legal_actions 中仍有可打出的牌、可用药水或额外选牌动作时，只有在你明确判断这些动作价值都不足时，才考虑 end_turn。",
    )

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
            "你是 Slay the Spire 2 自动打牌 agent。\n"
            "### 输出格式要求 (CRITICAL):\n"
            "1. 必须返回合法 JSON 对象，严禁包含任何 Markdown 代码块外包装（如 ```json ... ```）或前后解释文字。\n"
            "2. 必须包含字段: action_id (string|null), reason (string), detail (string), halt (boolean), confidence (string|number)。\n"
            "3. 只能从给定 legal_actions 中选择一个 action_id。若 selected action 包含 target_constraints，必须在顶层返回 target_id (或在 args 中包含 target_id)。\n"
            "4. 只要 legal_actions 不为空且包含可用的 action_id，禁止返回 halt=true 或 action_id=null（除非当前处于强制等待状态）。\n"
            "5. confidence 必须是 high、medium 或 low。\n"
            "6. detail 应包含 1-3 句中文，解释决策的数值依据（如：预计造成X伤害，抵挡Y伤害，余Z能量）。同时分析当前状态（HP、资源等）的安全性。\n"
            "7. **重要：请确保 JSON 内部不包含未转义的换行符或多余的逗号，且字符串值必须用双引号包裹。**\n"
            "8. 对于 deepseek-r1 等模型，即使在 <thought> 标签之后，也必须确保最后输出的 JSON 格式完整且符合要求。\n"
            "9. 严禁在 Map 阶段因为 'HP 不满'、'感觉没准备好' 或 '想离开商店'（如果不是在商店）而返回 halt=true；必须在 legal_actions 中选择一个节点前进。\n"
            "\n"
            "### JSON 结构示例 (EXAMPLE):\n"
            "```json\n"
            "{\n"
            "  \"action_id\": \"act-123\",\n"
            "  \"target_id\": \"1\",\n"
            "  \"reason\": \"使用打击攻击敌人\",\n"
            "  \"detail\": \"预计造成6点伤害，敌人剩余10点生命值。\",\n"
            "  \"halt\": false,\n"
            "  \"confidence\": \"high\"\n"
            "}\n"
            "```\n"
            "\n"
            "### 目标选择指南 (CRITICAL):\n"
            "- 如果你选择的 action 包含 `target_constraints` 列表（例如 `[\"1\", \"2\"]`），你必须从该列表中选择一个 ID 作为 `target_id`。\n"
            "- 如果 `target_constraints` 为空或不存在，则不要提供 `target_id`。\n"
            "- `target_id` 必须是字符串，且必须出现在 JSON 的顶层或 `args` 对象中。\n"
            "\n"
            "### 决策指南:\n"
            "- 只能依据当前 snapshot、legal_actions、battle_context 决策；若某效果不在这些信息里，不要脑补。\n"
            "- battle_context 只用于理解最近发生了什么，里面若出现历史动作摘要也绝不能直接复用旧 action_id。\n"
            "- 必须逐字区分时机词：'回合结束时' 只在当前回合结束触发，'战斗结束时' 只在战斗胜利/结束后触发，二者不能混淆。\n"
            "- 结束回合会放弃当前剩余能量与继续出牌机会；除非确实没有更有价值的合法动作，否则不要轻易选择 end_turn。\n"
            "- 格挡用于抵挡即将到来的伤害；若敌人意图攻击，你应通过 intent_damage * intent_hits 计算本回合总预期伤害，并比较格挡、减伤、直接击杀或其他动作的优劣。\n"
            "- 每回合都应尽可能减少本回合战损。注意观察抽牌堆 (draw_pile) 与弃牌堆 (discard_pile) 的剩余牌量及具体牌面，这有助于预判后续回合的资源。\n"
            "- 弃牌堆中包含你已经使用过或丢弃的牌；抽牌堆是即将抽入手的牌；消耗堆 (exhaust_pile) 中的牌在本次战斗中通常不再可用。\n"
            "- 敌人的力量、易伤、格挡等状态默认只影响对应敌人本身；除非 description 明确写作用于玩家，否则不要把敌方状态当成玩家增益。\n"
            "- 若某张牌、药水、遗物、能力提供了 description 或 glossary，优先按这些文本的字面效果理解，不要把别的卡牌/遗物规则套过来。\n"
            "- 若描述写的是战斗结束回血、回合结束得格挡、抽牌后触发等，必须严格按描述时机判断，不能提前或延后生效。\n"
            "- snapshot 里的手牌 (hand)、抽牌堆 (draw_pile)、弃牌堆 (discard_pile)、消耗堆 (exhaust_pile) 以及敌人的意图 (intent/intent_damage/intent_hits)、能力 (powers) 和运行状态 (run_state) 都是当前局面的事实层信息，应优先基于这些字段判断，而不是只猜卡名。\n"
            "- 当敌人意图攻击时，请计算意图伤害总量，并据此选择最优的防御、减伤或击杀策略。\n"
            "- 当 snapshot.phase=combat 且 metadata.window_kind=combat_card_selection 时，说明当前不是普通出牌窗口，而是在处理战斗中的额外选牌；\n"
            "  此时应优先在 choose_combat_card 或 cancel_combat_selection 中决策，而不是继续选择 play_card。\n"
            "- 当 snapshot.phase=reward 时，你需要结合 snapshot.rewards 列表（包含当前可领取的卡牌、遗物或金币等名字）与 legal_actions 中的 choose_reward 或 skip_reward 动作做选择；\n"
            "  即使 snapshot.rewards 只是一串名字，你也应该根据这些名字所代表的卡牌强度来做出最优选，并只能通过 legal_actions 中对应的 action_id 来执行。\n"
            "  若不确定，优先返回 halt=true 或选择 skip_reward（并在 reason 说明原因）。\n"
            "- 当 snapshot.phase=map 时，必须在 legal_actions 中选择一个 action_id。禁止返回 halt=true；\n"
            "  如果你不知道选哪个，优先选择 Monster 节点。即使 HP 只有 50% 以上在第一层也是健康的，不要随意停止。\n"
            "- 当 snapshot.phase=event 时，你需要结合事件标题、正文和 event_options，在 choose_event_option 或 continue_event 中做选择；\n"
            "  若 window_kind=event_continue，优先只考虑 continue_event。\n"
            "- 当 snapshot.phase=shop 时，你需要结合玩家金币、shop_offers 与 legal_actions，在购买或 leave_shop 间做选择；\n"
            "  若信息不足以支撑消费决策，优先 leave_shop 或 halt=true，而不是盲买。\n"
            "- 你必须严格遵守 payload.game_rules 中列出的基础通用规则，尤其不要混淆'回合结束时'与'战斗结束时'。"
        )
        user_payload = {
            "game_rules": list(self.GENERIC_RULES),
            "snapshot": self._summarize_snapshot(snapshot),
            "legal_actions": [self._summarize_action(action) for action in legal_actions],
            "output_format": {
                "action_id": "string (must match one from legal_actions or null if halt=true)",
                "target_id": "string (MANDATORY if action has target_constraints, must be one of target_constraints, e.g., \"1\")",
                "args": "object (optional, can contain target_id)",
                "reason": "string (one-sentence Chinese summary)",
                "detail": "string (1-3 sentences Chinese, must include numerical analysis)",
                "halt": "boolean (true if you want to pause/stop and wait for manual intervention, false to continue)",
                "confidence": "string (high/medium/low. MUST BE STRING, NOT NUMBER OR BOOLEAN)",
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
        except OSError as exc:
            raise ChatCompletionsRequestError(f"chat completions request failed: {exc}") from exc

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
        # Remove thinking process if present
        if "<thought>" in candidate.lower() and "</thought>" in candidate.lower():
            import re
            candidate = re.sub(r'(?si)<thought>.*?</thought>', '', candidate).strip()

        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            candidate = "\n".join(lines).strip()
        def _try_load(candidate: str) -> dict[str, Any]:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                # If first try fails, attempt to fix common issues or extract JSON
                # 1. Try simple extraction first
                extracted = ChatCompletionsPolicy._extract_json_object(candidate)
                if extracted is not None:
                    try:
                        return json.loads(extracted)
                    except json.JSONDecodeError:
                        # Fallback to the fixing logic if extraction alone doesn't work
                        pass
                
                # 2. Heuristic fixes for truncated or slightly malformed JSON
                # 2.1 Fix unterminated strings by adding missing quote and closing braces
                if "Unterminated string" in str(exc):
                    # Simple heuristic: append a quote and enough braces to close the structure
                    # This often happens with max_tokens truncation
                    candidate_fixed = candidate.rstrip()
                    if not candidate_fixed.endswith('"'):
                        candidate_fixed += '"'
                    
                    # Try to close braces/brackets based on balance
                    brace_depth = candidate_fixed.count('{') - candidate_fixed.count('}')
                    bracket_depth = candidate_fixed.count('[') - candidate_fixed.count(']')
                    candidate_fixed += ']' * max(0, bracket_depth)
                    candidate_fixed += '}' * max(0, brace_depth)
                    
                    try:
                        return json.loads(candidate_fixed)
                    except json.JSONDecodeError:
                        pass

                # 3. Regular expression based fixes for trailing commas
                import re
                candidate_fixed = re.sub(r',\s*([\]}])', r'\1', candidate)
                extracted = ChatCompletionsPolicy._extract_json_object(candidate_fixed)
                if extracted:
                    try:
                        return json.loads(extracted)
                    except json.JSONDecodeError:
                        # One last try: fix trailing commas inside the extracted object
                        try:
                            extracted_fixed = re.sub(r',\s*([\]}])', r'\1', extracted)
                            return json.loads(extracted_fixed)
                        except json.JSONDecodeError:
                            pass
                
                raise ChatCompletionsParseError("chat completions response is not valid JSON") from exc
        
        payload = _try_load(candidate)
        
        if not isinstance(payload, dict):
            raise ChatCompletionsParseError("chat completions response JSON must be an object")
        action_id = payload.get("action_id")
        target_id = payload.get("target_id")
        reason = payload.get("reason")
        detail = payload.get("detail")
        halt_val = payload.get("halt")
        if halt_val is None:
            halt = False
        elif isinstance(halt_val, bool):
            halt = halt_val
        elif isinstance(halt_val, str):
            halt = halt_val.lower() in ("true", "1", "yes")
        else:
            halt = bool(halt_val)

        confidence_val = payload.get("confidence")
        if confidence_val is None:
            # For robustness, we now provide a default value "medium" instead of failing.
            # This handles cases where models like deepseek-r1:7b omit the field.
            confidence = "medium"
        elif isinstance(confidence_val, (int, float)) and not isinstance(confidence_val, bool):
            # Preserve numeric types if they are actually numbers, not booleans
            confidence = confidence_val
        else:
            # Otherwise normalize to string
            confidence = str(confidence_val)

        args = payload.get("args")
        if action_id is not None and not isinstance(action_id, str):
            raise ChatCompletionsParseError("action_id must be a string or null")
        if target_id is not None and not isinstance(target_id, str):
            raise ChatCompletionsParseError("target_id must be a string or null")
        if not isinstance(reason, str) or not reason.strip():
            raise ChatCompletionsParseError("reason must be a non-empty string")
        if detail is not None and (not isinstance(detail, str) or not detail.strip()):
            raise ChatCompletionsParseError("detail must be a non-empty string when provided")
        
        # We've normalized halt and confidence above
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
        event_option = action.metadata.get("event_option")
        if isinstance(event_option, dict):
            payload["event_option"] = to_dict(event_option)
        shop_metadata = {
            key: action.metadata.get(key)
            for key in ("offer_id", "offer_index", "offer_kind", "offer_name", "price", "canonical_id", "service_kind", "choice", "display_label")
            if key in action.metadata
        }
        if shop_metadata:
            payload["shop_context"] = to_dict(shop_metadata)
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
                "hand": [ChatCompletionsPolicy._summarize_card(card) for card in snapshot.player.hand],
                "draw_pile": {
                    "count": snapshot.player.draw_pile,
                    "cards": [ChatCompletionsPolicy._summarize_card(card) for card in snapshot.player.draw_pile_cards],
                },
                "discard_pile": {
                    "count": snapshot.player.discard_pile,
                    "cards": [ChatCompletionsPolicy._summarize_card(card) for card in snapshot.player.discard_pile_cards],
                },
                "exhaust_pile": {
                    "count": snapshot.player.exhaust_pile,
                    "cards": [ChatCompletionsPolicy._summarize_card(card) for card in snapshot.player.exhaust_pile_cards],
                },
                "relics": [ChatCompletionsPolicy._summarize_relic(relic) for relic in snapshot.player.relics],
                "potions": [ChatCompletionsPolicy._summarize_potion(potion) for potion in snapshot.player.potions],
                "potion_capacity": snapshot.player.potion_capacity,
                "powers": [ChatCompletionsPolicy._summarize_power(power) for power in snapshot.player.powers],
            }
        if snapshot.enemies:
            payload["enemies"] = [ChatCompletionsPolicy._summarize_enemy(enemy) for enemy in snapshot.enemies]
        if snapshot.rewards:
            payload["rewards"] = list(snapshot.rewards)
            if snapshot.phase == "reward":
                payload["reward_instruction"] = "These are the available items to choose from in the reward screen. Use choose_reward with the corresponding action_id from legal_actions."
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
                    "event_title",
                    "event_body",
                    "event_subphase",
                    "event_selection_prompt",
                    "event_options",
                    "event_continue_available",
                    "event_continue_label",
                    "shop_offers",
                    "shop_offer_count",
                    "shop_leave_available",
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
            "intent_damage": enemy.intent_damage if enemy.intent_damage is not None else 0,
            "intent_hits": enemy.intent_hits if enemy.intent_hits is not None else 0,
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

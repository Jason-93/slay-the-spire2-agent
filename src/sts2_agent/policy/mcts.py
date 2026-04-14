from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from typing import Iterable, Optional, Any


class MCTSState(ABC):
    @abstractmethod
    def get_legal_actions(self) -> Iterable[Any]:
        pass

    @abstractmethod
    def take_action(self, action: Any) -> MCTSState:
        pass

    @abstractmethod
    def is_terminal(self) -> bool:
        pass

    @abstractmethod
    def get_reward(self) -> float:
        pass

    @abstractmethod
    def get_current_player(self) -> int:
        pass


class MCTSNode:
    def __init__(self, state: MCTSState, parent: Optional[MCTSNode] = None, action: Optional[Any] = None, prior: float = 0.0):
        self.state = state
        self.parent = parent
        self.action = action
        self.children: list[MCTSNode] = []
        self.visits = 0
        self.value = 0.0
        self.prior = prior # Policy network prior probability
        self.untried_actions = list(state.get_legal_actions())

    def is_fully_expanded(self) -> bool:
        return len(self.untried_actions) == 0

    def best_child(self, exploration_weight: float = 1.414) -> MCTSNode:
        # UCB1: Q(s,a) + c * sqrt(ln(N) / n)
        log_n = math.log(self.visits + 1)
        choices_weights = [
            (child.value / (child.visits + 1e-6)) +
            exploration_weight * math.sqrt(log_n / (child.visits + 1e-6))
            for child in self.children
        ]
        return self.children[choices_weights.index(max(choices_weights))]

    def expand(self) -> MCTSNode:
        action = self.untried_actions.pop()
        next_state = self.state.take_action(action)
        child_node = MCTSNode(next_state, parent=self, action=action)
        self.children.append(child_node)
        return child_node

    def update(self, reward: float):
        self.visits += 1
        self.value += reward


class MCTS:
    def __init__(self, exploration_weight: float = 1.414, model: Any = None, feature_encoder: Any = None):
        self.exploration_weight = exploration_weight
        self.model = model
        self.feature_encoder = feature_encoder

    def search(self, initial_state: MCTSState, iterations: int) -> Optional[Any]:
        root = MCTSNode(initial_state)

        for _ in range(iterations):
            node = root
            # Selection
            while node.is_fully_expanded() and not node.state.is_terminal():
                node = node.best_child(self.exploration_weight)

            # Expansion & Evaluation
            if not node.state.is_terminal():
                if self.model and hasattr(node.state, 'snapshot'):
                    # Neural Network Guided Expansion
                    # 确保模型在正确的设备上运行
                    device = next(self.model.parameters()).device if hasattr(self.model, 'parameters') else 'cpu'
                    reward = self._expand_and_evaluate(node, device)
                else:
                    # Classical Expansion
                    node = node.expand()
                    # Simulation (Rollout) - Optimized with heuristic or random
                    reward = self._rollout(node.state)
            else:
                reward = node.state.get_reward()

            # Backpropagation
            curr: Optional[MCTSNode] = node
            while curr is not None:
                curr.update(reward)
                curr = curr.parent

        if not root.children:
            return None

        # Return action of the child with most visits
        best_child = max(root.children, key=lambda c: c.visits)
        return best_child.action

    def _expand_and_evaluate(self, node: MCTSNode, device: Any = 'cpu') -> float:
        """
        Use Policy-Value network to expand all children and return state value.
        """
        import torch
        state_tensor = self.feature_encoder.encode(node.state.snapshot).to(device)
        with torch.no_grad():
            log_pi, v = self.model(state_tensor.unsqueeze(0))
            probs = torch.exp(log_pi).squeeze(0).cpu().numpy()
            value = v.item()

        # Expand all actions at once
        actions = node.untried_actions
        node.untried_actions = []
        
        # Simple action mapping: this needs to be more robust in real scenarios
        for i, action in enumerate(actions):
            # i mod len(probs) to avoid index out of bounds if model output dim != actions
            prior = probs[i % len(probs)]
            next_state = node.state.take_action(action)
            child_node = MCTSNode(next_state, parent=node, action=action, prior=prior)
            node.children.append(child_node)
        
        return value

    def _rollout(self, state: MCTSState) -> float:
        current_state = state
        # 增加深度以覆盖多个回合的模拟；每回合最多约 10 张牌 + end_turn，共模拟 3 回合
        limit = 30
        while not current_state.is_terminal() and limit > 0:
            legal_actions = list(current_state.get_legal_actions())
            if not legal_actions:
                break

            action = self._rollout_select(legal_actions)
            current_state = current_state.take_action(action)
            limit -= 1
        return current_state.get_reward()

    @staticmethod
    def _rollout_select(legal_actions: list) -> object:
        """
        启发式选择 Rollout 动作：
        1. 优先选择高伤害/高费比的攻击牌（消灭敌人）
        2. 次选防御牌（减少受伤）
        3. 最后才选 end_turn
        """
        import re as _re

        def action_priority(action) -> tuple:
            """
            返回 (tier, value)，越大越优先（配合 reverse=True 排序）。
            tier: 3=攻击 > 2=防御 > 1=其他 > 0=end_turn
            """
            atype = getattr(action, "type", "")
            if atype == "end_turn":
                return (0, 0)  # 最低优先级
            if atype != "play_card":
                return (1, 0)  # 其他动作中等优先级

            meta = getattr(action, "metadata", {}) or {}
            label = getattr(action, "label", "") or ""
            card_desc = meta.get("card_description", "") or ""
            card_type = meta.get("card_type", "") or ""

            dmg, blk = GameStateWrapper._estimate_card_effects(label, label, card_desc, card_type)

            if dmg > 0:
                return (3, dmg)  # 攻击牌：优先（tier=3，值越大越好）
            if blk > 0:
                return (2, blk)  # 防御牌：次优先（tier=2）
            return (2, 1)  # 未知牌（按防御类处理）

        legal_actions_sorted = sorted(legal_actions, key=action_priority, reverse=True)
        # 在最高优先级类别中随机选择，避免每次都选同一张牌
        best_priority = action_priority(legal_actions_sorted[0])
        candidates = [a for a in legal_actions_sorted if action_priority(a) == best_priority]
        return random.choice(candidates)


from sts2_agent.models import BattleContext, DecisionSnapshot, LegalAction, PolicyDecision


class MCTSPolicy:
    def __init__(self, iterations: int = 100, model_path: str | None = None):
        self.iterations = iterations
        self.model = None
        self.feature_encoder = None
        
        if model_path:
            import torch
            from sts2_agent.policy.mcts_nn import STS2PolicyValueNet, FeatureEncoder
            self.feature_encoder = FeatureEncoder()
            # 假设 input_dim=25, action_dim=10 (根据 FeatureEncoder 的默认配置)
            # p_feat(5) + e_feats(4*4=16) + c_feats(10*2=20) = 41
            self.model = STS2PolicyValueNet(input_dim=41, action_dim=20)
            try:
                self.model.load_state_dict(torch.load(model_path))
                self.model.eval()
            except Exception:
                pass # 如果加载失败，回退到无模型 MCTS
                
        self.mcts = MCTS(model=self.model, feature_encoder=self.feature_encoder)

    @staticmethod
    def _heuristic_card_selection(legal_actions: list[LegalAction]) -> PolicyDecision:
        """
        在 combat_card_selection 窗口中启发式选牌：
        优先选攻击牌（高伤害） > 防御牌（高格挡） > 其他，
        不选 cancel（会导致窗口循环）。
        """
        card_actions = [a for a in legal_actions if a.type == "choose_combat_card"]
        if not card_actions:
            cancel = next((a for a in legal_actions if a.type == "cancel_combat_selection"), legal_actions[0])
            return PolicyDecision(action_id=cancel.action_id, reason="card_selection: no choose_combat_card, cancel")

        def _card_score(action: LegalAction) -> tuple:
            preview = (action.metadata or {}).get("card_preview") or {}
            desc = str(preview.get("description") or "")
            card_type = str(preview.get("card_type") or "")
            card_name = str(preview.get("card_name") or action.label or "")
            dmg, blk = GameStateWrapper._estimate_card_effects(card_name, card_name, desc, card_type)
            if dmg > 0:
                return (2, dmg)
            if blk > 0:
                return (1, blk)
            return (1, 0)

        best = max(card_actions, key=_card_score)
        return PolicyDecision(
            action_id=best.action_id,
            reason=f"card_selection heuristic: best choose_combat_card",
            confidence=0.5,
        )

    def decide(
        self,
        snapshot: DecisionSnapshot,
        legal_actions: list[LegalAction],
        battle_context: BattleContext | None = None,
    ) -> PolicyDecision:
        if not legal_actions:
            return PolicyDecision(action_id=None, reason="no legal actions available", halt=True)

        # combat_card_selection 窗口：MCTS 无法模拟选牌效果，直接用启发式
        window_kind = str((getattr(snapshot, "metadata", {}) or {}).get("window_kind") or "")
        if window_kind == "combat_card_selection" or any(
            a.type in {"choose_combat_card", "cancel_combat_selection"} for a in legal_actions
        ):
            return self._heuristic_card_selection(legal_actions)

        # 这里我们需要一个能将 snapshot 转换为 MCTSState 的转换器
        # 暂时实现一个占位逻辑，如果无法模拟，则回退到启发式或第一个动作
        initial_state = GameStateWrapper(snapshot, legal_actions)
        best_action = self.mcts.search(initial_state, self.iterations)

        if best_action:
            metadata = {}
            if best_action.type == "play_card":
                target_id = best_action.metadata.get("selected_target_id")
                if target_id:
                    metadata["action_args"] = {"target_id": target_id}

            return PolicyDecision(
                action_id=best_action.action_id,
                reason=f"MCTS selected {best_action.type}",
                metadata=metadata,
                confidence=0.5 # 占位
            )

        # Fallback
        preferred = next((action for action in legal_actions if action.type not in {"end_turn", "skip_reward"}),
                         legal_actions[0])
        return PolicyDecision(action_id=preferred.action_id, reason=f"fallback to {preferred.type}")


class GameStateWrapper(MCTSState):
    """
    将游戏的 DecisionSnapshot 包装成 MCTS 可用的状态。
    实现一个简单的向前模型 (Forward Model) 用于模拟。
    """
    # 假设最大能量为 3（STS默认值）
    _MAX_ENERGY = 3
    # 每回合抽牌数
    _DRAW_PER_TURN = 5

    def __init__(self, snapshot: DecisionSnapshot, legal_actions: list[LegalAction]):
        self.snapshot = snapshot
        # 只在根节点时从真实 legal_actions 初始化；子节点会通过 _compute_legal_actions 生成
        self._root_legal_actions = legal_actions

    def _compute_legal_actions(self) -> list[LegalAction]:
        """根据当前模拟状态计算合法动作，确保能量/手牌约束正确。"""
        if not self.snapshot.player:
            return []

        player = self.snapshot.player
        living_enemy_ids = [e.enemy_id for e in self.snapshot.enemies if e.hp > 0]
        actions: list[LegalAction] = []

        for card in player.hand:
            if not card.playable:
                continue
            # Skip X-cost / negative-cost / Unplayable cards (curses, Ascender's Bane, etc.)
            if card.cost < 0 or card.cost > player.energy:
                continue
            kw_lower = [str(k).lower() for k in (getattr(card, "keywords", None) or [])]
            if "unplayable" in kw_lower:
                continue
            card_id = card.instance_card_id or card.card_id
            base_meta = {
                "card_description": getattr(card, "description", "") or "",
                "card_type": getattr(card, "card_type", "") or "",
            }
            if living_enemy_ids:
                # 为每个存活敌人创建一个目标版本
                for i, eid in enumerate(living_enemy_ids):
                    import copy as _copy
                    act = LegalAction(
                        action_id=f"play_{card_id}_t{i}",
                        type="play_card",
                        label=card.name,
                        params={"card_id": card_id},
                        target_constraints=living_enemy_ids,
                        metadata={**base_meta, "selected_target_id": eid, "selected_target_index": i},
                    )
                    actions.append(act)
            else:
                act = LegalAction(
                    action_id=f"play_{card_id}",
                    type="play_card",
                    label=card.name,
                    params={"card_id": card_id},
                    target_constraints=[],
                    metadata=base_meta,
                )
                actions.append(act)

        # 总是允许结束回合
        actions.append(LegalAction(
            action_id="end_turn_sim",
            type="end_turn",
            label="End Turn",
            params={},
            target_constraints=[],
            metadata={},
        ))
        return actions

    def get_legal_actions(self) -> Iterable[LegalAction]:
        # 根节点：展开真实动作（含目标约束）
        if self._root_legal_actions is not None:
            expanded: list[LegalAction] = []
            for action in self._root_legal_actions:
                if action.type == "play_card" and action.target_constraints:
                    import copy as _copy
                    for i, target_id in enumerate(action.target_constraints):
                        targeted = _copy.copy(action)
                        targeted.metadata = dict(action.metadata or {})
                        targeted.metadata["selected_target_id"] = target_id
                        targeted.metadata["selected_target_index"] = i
                        expanded.append(targeted)
                else:
                    expanded.append(action)
            return expanded
        # 模拟节点：从快照计算
        return self._compute_legal_actions()

    @staticmethod
    def _estimate_card_effects(
        card_name: str,
        card_label: str,
        card_description: str = "",
        card_type: str = "",
    ) -> tuple[int, int]:
        """估算卡牌的攻击/防御数值。返回 (damage, block)。"""
        import re as _re
        # Strip markdown bold markers
        clean_desc = _re.sub(r'\*\*', '', card_description or "")
        for text in (clean_desc, card_label or ""):
            if not text:
                continue
            # Chinese: 造成 N 点伤害 / N 点伤害
            dm = _re.search(r'造成\s*(\d+)\s*点.*?伤害|(\d+)\s*点.*?伤害', text)
            # Chinese block: 获得 N 点格挡/护甲/护盾
            bm = _re.search(r'获得\s*(\d+)\s*点.*?(?:格挡|格档|护甲|护盾)|(\d+)\s*点.*?(?:格挡|格档|护甲|护盾)', text)
            # English fallback
            if not dm:
                dm = _re.search(r'(\d+)\s*(?:damage|attack)', text, _re.IGNORECASE)
            if not bm:
                bm = _re.search(r'(\d+)\s*(?:block|shield|armor)', text, _re.IGNORECASE)
            dmg = int(next(g for g in (dm.group(1), dm.group(2)) if g) if dm else 0)
            blk = int(next(g for g in (bm.group(1), bm.group(2)) if g) if bm else 0)
            if dmg > 0 or blk > 0:
                return dmg, blk
        # Fallback: use card_type
        if card_type == "Attack":
            return 6, 0
        if card_type == "Skill":
            return 0, 5
        if card_type in ("Power", "Curse", "Status"):
            return 0, 0
        # Name-based heuristics (English and Chinese)
        name_lower = (card_name or "").lower()
        if any(k in name_lower for k in ("strike", "bash", "cleave", "slam", "hit", "cut", "slash", "attack",
                                          "打击", "痛击", "重击", "斩击")):
            return 6, 0
        if any(k in name_lower for k in ("defend", "block", "fortify", "shield", "guard", "防御", "护盾")):
            return 0, 5
        return 4, 0  # 保守估算

    def take_action(self, action: LegalAction) -> "GameStateWrapper":
        """
        模拟动作效果，返回新状态。
        保持简单以维持 MCTS 搜索效率。
        """
        import copy as _copy
        new_snapshot = _copy.deepcopy(self.snapshot)

        if action.type == "play_card":
            card_id = action.params.get("card_id")
            card = next(
                (c for c in new_snapshot.player.hand
                 if (c.instance_card_id or c.card_id) == card_id),
                None,
            )
            if card:
                meta = action.metadata or {}
                dmg, blk = self._estimate_card_effects(
                    card.name,
                    action.label,
                    meta.get("card_description") or getattr(card, "description", "") or "",
                    meta.get("card_type") or getattr(card, "card_type", "") or "",
                )
                cost = max(0, card.cost)  # treat X-cost / negative-cost as 0

                if dmg > 0:
                    target_idx = action.metadata.get("selected_target_index", 0)
                    living = [e for e in new_snapshot.enemies if e.hp > 0]
                    if living:
                        target = living[min(target_idx, len(living) - 1)]
                        net_dmg = max(0, dmg - target.block)
                        target.block = max(0, target.block - dmg)
                        target.hp -= net_dmg

                if blk > 0:
                    new_snapshot.player.block += blk

                # 移除使用的牌并加入弃牌堆，扣除能量
                new_snapshot.player.hand = [
                    c for c in new_snapshot.player.hand
                    if (c.instance_card_id or c.card_id) != card_id
                ]
                new_snapshot.player.discard_pile_cards = list(new_snapshot.player.discard_pile_cards) + [card]
                new_snapshot.player.energy = max(0, new_snapshot.player.energy - cost)

        elif action.type == "end_turn":
            # 1. 敌人攻击玩家
            remaining_block = new_snapshot.player.block
            total_incoming = 0
            for enemy in new_snapshot.enemies:
                if enemy.hp > 0:
                    dmg = (enemy.intent_damage or 0) * (enemy.intent_hits or 1)
                    total_incoming += dmg
            actual_dmg = max(0, total_incoming - remaining_block)
            new_snapshot.player.block = max(0, remaining_block - total_incoming)
            new_snapshot.player.hp -= actual_dmg

            if new_snapshot.player.hp <= 0:
                new_snapshot.terminal = True
            else:
                # 2. 玩家回合开始：恢复能量、清空护甲、抽新手牌
                new_snapshot.player.energy = self._MAX_ENERGY
                new_snapshot.player.block = 0
                # 将当前手牌送入弃牌堆，重新从抽牌堆/弃牌堆补牌
                discard = list(new_snapshot.player.hand) + list(new_snapshot.player.discard_pile_cards)
                draw = list(new_snapshot.player.draw_pile_cards)
                # 如果抽牌堆不够，将弃牌堆洗入
                if len(draw) < self._DRAW_PER_TURN:
                    draw = draw + discard
                    discard = []
                # 若牌库信息完全缺失，使用原始手牌作为回退（无限循环模拟）
                if not draw:
                    import copy as _copy2
                    draw = _copy2.deepcopy(list(self.snapshot.player.hand) if self.snapshot.player else [])
                new_hand = draw[:self._DRAW_PER_TURN]
                new_draw = draw[self._DRAW_PER_TURN:]
                new_snapshot.player.hand = new_hand
                new_snapshot.player.draw_pile_cards = new_draw
                new_snapshot.player.discard_pile_cards = discard
                # 将手牌重新标记为可打出（简化）
                for c in new_snapshot.player.hand:
                    c.playable = True

        # 清理死亡敌人
        new_snapshot.enemies = [e for e in new_snapshot.enemies if e.hp > 0]
        if not new_snapshot.enemies:
            new_snapshot.terminal = True

        # 子节点不持有根节点 legal_actions，由 _compute_legal_actions 生成
        child = GameStateWrapper(new_snapshot, None)  # type: ignore[arg-type]
        return child

    def is_terminal(self) -> bool:
        if self.snapshot.terminal:
            return True
        if self.snapshot.player and self.snapshot.player.hp <= 0:
            return True
        if not self.snapshot.enemies or all(e.hp <= 0 for e in self.snapshot.enemies):
            return True
        return False

    def get_reward(self) -> float:
        """
        归一化奖励值 [-1, 1]。
        胜利（敌人全灭）给予高奖励，失败（玩家死亡）给予最低奖励。
        """
        if not self.snapshot.player:
            return -1.0

        player_hp = self.snapshot.player.hp
        max_hp = max(1, self.snapshot.player.max_hp)

        if player_hp <= 0:
            return -1.0

        living_enemies = [e for e in self.snapshot.enemies if e.hp > 0]
        if not living_enemies:
            # 胜利：奖励 = 0.5 + 剩余血量比例 * 0.5
            return 0.5 + 0.5 * (player_hp / max_hp)

        # 玩家血量比例
        hp_ratio = player_hp / max_hp

        # 敌人剩余血量比例（相对于其最大血量）
        total_enemy_hp = sum(max(0, e.hp) for e in living_enemies)
        total_enemy_max = sum(max(1, e.max_hp or e.hp * 2) for e in living_enemies)
        enemy_ratio = total_enemy_hp / total_enemy_max

        # 最终奖励：玩家血量比例 - 敌人血量比例，范围约 (-1, 1)
        return hp_ratio - enemy_ratio

    def get_current_player(self) -> int:
        return 0

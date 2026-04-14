import unittest
from dataclasses import dataclass, field
from typing import Any, List, Optional, Dict
from sts2_agent.models import DecisionSnapshot, PlayerState, EnemyState, LegalAction, PolicyDecision
from sts2_agent.policy.mcts import MCTSPolicy, GameStateWrapper

class TestMCTSTargetSelection(unittest.TestCase):
    def test_mcts_must_provide_target_id_for_multi_target_actions(self):
        # 1. 模拟一个有两个敌人的场景
        enemy1 = EnemyState(enemy_id="enemy-1", name="Enemy 1", hp=10, max_hp=10, block=0, intent="Attack", is_alive=True, intent_damage=5)
        enemy2 = EnemyState(enemy_id="enemy-2", name="Enemy 2", hp=10, max_hp=10, block=0, intent="Attack", is_alive=True, intent_damage=5)
        player = PlayerState(hp=50, max_hp=50, energy=3, block=0, gold=100, hand=[])
        
        snapshot = DecisionSnapshot(
            session_id="sess-test",
            decision_id="dec-test",
            state_version=100,
            phase="combat",
            player=player,
            enemies=[enemy1, enemy2]
        )
        
        # 2. 模拟一个需要选择目标的动作 (例如 Strike)
        # 注意：在真实的 Bridge 中，如果一个卡牌有多个合法目标，它会有多个 LegalAction 吗？
        # 还是一个 LegalAction 包含 target_constraints？
        # 根据 Orchestrator 逻辑，如果 target_constraints > 1，Policy 必须在 metadata.action_args 中提供 target_id。
        
        action = LegalAction(
            action_id="act-strike",
            type="play_card",
            label="Strike (6 伤害)",
            params={"card_id": "card-strike"},
            target_constraints=["enemy-1", "enemy-2"]
        )
        
        # 为了模拟 card 存在
        from sts2_agent.models import CardView
        strike_card = CardView(card_id="Strike", name="Strike", cost=1, playable=True, instance_card_id="card-strike")
        player.hand = [strike_card]
        
        policy = MCTSPolicy(iterations=10)
        decision = policy.decide(snapshot, [action])
        
        # 3. 验证决策是否包含 target_id
        # 目前的代码很可能会失败（即不包含 target_id），从而触发 Orchestrator 的报错
        self.assertIsNotNone(decision.action_id)
        
        # 如果是 targeted action，metadata 中应该有 action_args.target_id
        action_args = decision.metadata.get("action_args", {})
        self.assertIn("target_id", action_args, f"Decision for multi-target action must include target_id. Decision: {decision}")
        self.assertIn(action_args["target_id"], ["enemy-1", "enemy-2"])

if __name__ == "__main__":
    unittest.main()

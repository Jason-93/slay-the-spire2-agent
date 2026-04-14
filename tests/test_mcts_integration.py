import unittest
from sts2_agent.models import DecisionSnapshot, PlayerState, EnemyState, LegalAction, CardView
from sts2_agent.policy.mcts import MCTSPolicy, GameStateWrapper

class TestMCTSIntegration(unittest.TestCase):
    def test_mcts_decides_attack_when_lethal(self):
        # Setup a scenario where player has an attack card that can kill the enemy
        player = PlayerState(hp=50, max_hp=50, block=0, energy=3, gold=100)
        player.hand = [
            CardView(card_id="strike", name="Strike", cost=1, instance_card_id="strike_1")
        ]
        enemy = EnemyState(enemy_id="slime", name="Slime", hp=5, max_hp=10, block=0, intent="Attack", intent_damage=10)
        
        snapshot = DecisionSnapshot(
            session_id="test",
            decision_id="d1",
            state_version=1,
            phase="Combat",
            player=player,
            enemies=[enemy]
        )
        
        legal_actions = [
            LegalAction(action_id="a1", type="play_card", label="Strike (6 伤害)", params={"card_id": "strike_1", "target_index": 0}),
            LegalAction(action_id="a2", type="end_turn", label="End Turn", params={})
        ]
        
        policy = MCTSPolicy(iterations=50)
        decision = policy.decide(snapshot, legal_actions)
        
        # MCTS should prefer playing the card to win/reduce HP over ending turn and taking damage
        self.assertEqual(decision.action_id, "a1")

    def test_mcts_prefers_block_when_threatened(self):
        # Setup a scenario where player takes lethal damage next turn unless they block
        player = PlayerState(hp=5, max_hp=50, block=0, energy=3, gold=100)
        player.hand = [
            CardView(card_id="defend", name="Defend", cost=1, instance_card_id="defend_1")
        ]
        enemy = EnemyState(enemy_id="nob", name="Nob", hp=50, max_hp=50, block=0, intent="Attack", intent_damage=10)
        
        snapshot = DecisionSnapshot(
            session_id="test",
            decision_id="d1",
            state_version=1,
            phase="Combat",
            player=player,
            enemies=[enemy]
        )
        
        legal_actions = [
            LegalAction(action_id="a1", type="play_card", label="Defend (5 防御)", params={"card_id": "defend_1"}),
            LegalAction(action_id="a2", type="end_turn", label="End Turn", params={})
        ]
        
        policy = MCTSPolicy(iterations=50)
        decision = policy.decide(snapshot, legal_actions)
        
        # MCTS should prefer blocking to survive
        self.assertEqual(decision.action_id, "a1")

if __name__ == "__main__":
    unittest.main()

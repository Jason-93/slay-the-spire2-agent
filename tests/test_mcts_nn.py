import unittest
import torch
import os
from sts2_agent.models import DecisionSnapshot, PlayerState, EnemyState, LegalAction, CardView
from sts2_agent.policy.mcts import MCTSPolicy
from sts2_agent.policy.mcts_nn import STS2PolicyValueNet, FeatureEncoder, AlphaZeroMCTSTrainer

class TestMCTSNeural(unittest.TestCase):
    def setUp(self):
        self.encoder = FeatureEncoder()
        self.model = STS2PolicyValueNet(input_dim=41, action_dim=20)
        self.trainer = AlphaZeroMCTSTrainer(self.model)

    def test_feature_encoding(self):
        player = PlayerState(hp=50, max_hp=50, block=0, energy=3, gold=100)
        player.hand = [CardView(card_id="strike", name="Strike", cost=1, instance_card_id="s1")]
        snapshot = DecisionSnapshot(session_id="t", decision_id="d", state_version=1, phase="Combat", player=player, enemies=[])
        
        tensor = self.encoder.encode(snapshot)
        self.assertEqual(tensor.shape[0], 41)
        self.assertTrue(torch.is_tensor(tensor))

    def test_model_forward(self):
        x = torch.randn(1, 41)
        pi, v = self.model(x)
        self.assertEqual(pi.shape, (1, 20))
        self.assertEqual(v.shape, (1, 1))
        self.assertTrue(-1 <= v.item() <= 1)

    def test_trainer_step(self):
        # Mock trajectory
        for _ in range(35):
            s = torch.randn(41)
            p = torch.randn(20).softmax(dim=0)
            r = 1.0
            self.trainer.save_trajectory(s, p, r)
        
        loss = self.trainer.train_step(batch_size=32)
        self.assertIsNotNone(loss)
        self.assertIsInstance(loss, float)

    def test_policy_with_mock_model(self):
        # 保存一个临时模型
        torch.save(self.model.state_dict(), "tmp_model.pth")
        
        player = PlayerState(hp=50, max_hp=50, block=0, energy=3, gold=100)
        player.hand = [CardView(card_id="strike", name="Strike", cost=1, instance_card_id="s1")]
        snapshot = DecisionSnapshot(session_id="t", decision_id="d", state_version=1, phase="Combat", player=player, enemies=[])
        
        legal_actions = [
            LegalAction(action_id="a1", type="play_card", label="Strike (6伤害)", params={"card_id": "s1", "target_index": 0}),
            LegalAction(action_id="a2", type="end_turn", label="End Turn", params={})
        ]
        
        policy = MCTSPolicy(iterations=10, model_path="tmp_model.pth")
        decision = policy.decide(snapshot, legal_actions)
        
        self.assertIn(decision.action_id, ["a1", "a2"])
        
        if os.path.exists("tmp_model.pth"):
            os.remove("tmp_model.pth")

if __name__ == "__main__":
    unittest.main()

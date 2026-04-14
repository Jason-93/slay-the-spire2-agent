import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import List, Dict, Any
from sts2_agent.models import DecisionSnapshot, LegalAction

class FeatureEncoder:
    """
    将 DecisionSnapshot 转换为神经网络张量特征。
    简单起见，这里固定几个核心特征：玩家HP/能量/护甲，敌人HP/护甲/攻击意图。
    卡牌使用索引映射（需要一个 ID 字典）。
    """
    def __init__(self, max_cards=10, max_enemies=4):
        self.max_cards = max_cards
        self.max_enemies = max_enemies
        # 预定义一些常见的卡牌 ID 映射
        self.card_id_map = {"strike": 1, "defend": 2, "bash": 3}
        self.enemy_id_map = {"slime": 1, "nob": 2}

    def encode(self, snapshot: DecisionSnapshot) -> torch.Tensor:
        # 1. 玩家特征 (5维): HP比例, MaxHP比例, Block/100, Energy/5, 手牌数量/10
        player = snapshot.player
        p_feat = [
            player.hp / max(1, player.max_hp),
            player.max_hp / 100.0,
            player.block / 100.0,
            player.energy / 5.0,
            len(player.hand) / float(self.max_cards)
        ]

        # 2. 敌人特征 (每个敌人 4维): HP比例, Block/100, IntentDamage/50, IntentHits/5
        e_feats = []
        for i in range(self.max_enemies):
            if i < len(snapshot.enemies):
                e = snapshot.enemies[i]
                e_feats.extend([
                    e.hp / max(1, e.max_hp),
                    e.block / 100.0,
                    (e.intent_damage or 0) / 50.0,
                    (e.intent_hits or 1) / 5.0
                ])
            else:
                e_feats.extend([0.0, 0.0, 0.0, 0.0])

        # 3. 手牌特征 (每张牌 2维): ID映射/10, Cost/5
        c_feats = []
        for i in range(self.max_cards):
            if i < len(player.hand):
                c = player.hand[i]
                card_id_val = self.card_id_map.get(c.card_id.lower(), 0) / 10.0
                c_feats.extend([card_id_val, (c.cost or 0) / 5.0])
            else:
                c_feats.extend([0.0, 0.0])

        features = p_feat + e_feats + c_feats
        return torch.tensor(features, dtype=torch.float32)

class STS2PolicyValueNet(nn.Module):
    def __init__(self, input_dim: int, action_dim: int):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, 256) # 增加神经元数量，利用高性能 CPU/GPU
        self.fc2 = nn.Linear(256, 128)
        self.fc3 = nn.Linear(128, 64)
        
        # Policy Head
        self.policy_head = nn.Linear(64, action_dim)
        
        # Value Head
        self.value_head = nn.Linear(64, 1)

    def forward(self, x: torch.Tensor):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.relu(self.fc3(x))
        
        # Policy: log_softmax for training stability
        pi = F.log_softmax(self.policy_head(x), dim=-1)
        
        # Value: tanh for -1 to 1 range (win/loss signal)
        v = torch.tanh(self.value_head(x))
        return pi, v

class AlphaZeroMCTSTrainer:
    """
    负责自我学习的数据收集和网络更新逻辑。
    针对 AMD 7800X3D + 7900XTX 进行优化：
    1. 自动检测设备 (CUDA/ROCm/CPU)
    2. 增大经验回放池 (Replay Buffer)
    3. 支持批量并行训练
    """
    def __init__(self, model: STS2PolicyValueNet, lr=1e-3, max_memory=50000):
        # 检测设备：AMD GPU 在 Windows 下可能通过 ROCm 或 DirectML 支持
        # 如果是 ROCm/CUDA 环境，torch.cuda.is_available() 为 True
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = model.to(self.device)
        self.optimizer = torch.optim.Adam(model.parameters(), lr=lr)
        self.memory = [] # Replay buffer
        self.max_memory = max_memory # 增大内存占用以存储更多轨迹

    def save_trajectory(self, state_tensor, mcts_probs, reward):
        # mcts_probs: MCTS 搜索出的动作概率分布
        if len(self.memory) >= self.max_memory:
            self.memory.pop(0)
        self.memory.append((state_tensor.to(self.device), mcts_probs.to(self.device), reward))

    def train_step(self, batch_size=256): # 增大 Batch Size 以利用 7900XTX 显存
        if len(self.memory) < batch_size:
            return None
        
        import random
        batch = random.sample(self.memory, batch_size)
        states, target_pis, target_vs = zip(*batch)
        
        s_batch = torch.stack(states).to(self.device)
        pi_batch = torch.stack(target_pis).to(self.device)
        v_batch = torch.tensor(target_vs, dtype=torch.float32).unsqueeze(1).to(self.device)
        
        self.optimizer.zero_grad()
        log_pi, v = self.model(s_batch)
        
        # Loss = (v - target_v)^2 - pi * log_pi
        value_loss = F.mse_loss(v, v_batch)
        policy_loss = -torch.mean(torch.sum(pi_batch * log_pi, dim=1))
        
        loss = value_loss + policy_loss
        loss.backward()
        self.optimizer.step()
        
        return loss.item()

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from sts2_agent.policy.mcts_nn import STS2PolicyValueNet, AlphaZeroMCTSTrainer, FeatureEncoder
from sts2_agent.models import DecisionSnapshot

def load_traces(trace_dir: str):
    traces = []
    path = Path(trace_dir)
    if not path.exists():
        return traces
    
    for file in path.glob("*.jsonl"):
        with open(file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    # 我们需要 DecisionSnapshot 和对应的 MCTS 结果
                    # trace 文件中通常包含 observation 和 policy_output
                    if "observation" in data and "policy_output" in data:
                        traces.append(data)
                except Exception:
                    continue
    return traces

def train(trace_dir: str, output_model: str, epochs: int = 10, batch_size: int = 256):
    encoder = FeatureEncoder()
    # input_dim 与 FeatureEncoder.encode 输出维度一致，目前是 41
    model = STS2PolicyValueNet(input_dim=41, action_dim=20)
    trainer = AlphaZeroMCTSTrainer(model)
    
    print(f"Loading traces from {trace_dir}...")
    trace_data = load_traces(trace_dir)
    if not trace_data:
        print("No valid traces found.")
        return

    print(f"Processing {len(trace_data)} steps...")
    for entry in trace_data:
        obs = entry["observation"]
        # 简单将 dict 转换为 DecisionSnapshot (部分字段可能缺失，需容错)
        try:
            # 这是一个简化的转换，实际可能需要更复杂的 Marshmallow/Pydantic 处理
            # 但为了示例脚本能跑，我们假设数据格式兼容
            from dataclasses import fields
            # 转换逻辑... 这里省略复杂转换，直接提取核心特征
            # 由于 FeatureEncoder 只用了 player 和 enemies，我们手动构造最小 Snapshot
            from sts2_agent.models import PlayerState, EnemyState, CardView
            
            p_data = obs.get("player", {})
            player = PlayerState(
                hp=p_data.get("hp", 0),
                max_hp=p_data.get("max_hp", 100),
                block=p_data.get("block", 0),
                energy=p_data.get("energy", 0),
                gold=p_data.get("gold", 0),
                hand=[CardView(card_id=c.get("card_id", ""), name=c.get("name", ""), cost=c.get("cost", 0)) for c in p_data.get("hand", [])]
            )
            
            enemies = []
            for e_data in obs.get("enemies", []):
                enemies.append(EnemyState(
                    enemy_id=e_data.get("enemy_id", ""),
                    name=e_data.get("name", ""),
                    hp=e_data.get("hp", 0),
                    max_hp=e_data.get("max_hp", 100),
                    block=e_data.get("block", 0),
                    intent=e_data.get("intent", ""),
                    intent_damage=e_data.get("intent_damage"),
                    intent_hits=e_data.get("intent_hits")
                ))
            
            snapshot = DecisionSnapshot(
                session_id=obs.get("session_id", ""),
                decision_id=obs.get("decision_id", ""),
                state_version=obs.get("state_version", 0),
                phase=obs.get("phase", ""),
                player=player,
                enemies=enemies
            )
            
            state_tensor = encoder.encode(snapshot)
            
            # 构造 target_pi (根据 policy_output.action_id，设该动作为 1.0)
            # 在真实的 AlphaZero 中，这里应该是 MCTS 的 visit counts 比例
            target_pi = torch.zeros(20)
            # 简单假设 action_id 能映射到索引 (这里仅演示)
            target_pi[0] = 1.0 
            
            # 构造 target_v (根据战斗胜负，这里简单设为 0)
            target_v = 0.0
            
            trainer.save_trajectory(state_tensor, target_pi, target_v)
        except Exception as e:
            continue

    print(f"Starting training on {trainer.device}...")
    for epoch in range(epochs):
        loss = trainer.train_step(batch_size=min(len(trainer.memory), batch_size))
        if loss is not None:
            print(f"Epoch {epoch+1}/{epochs}, Loss: {loss:.4f}")

    print(f"Saving model to {output_model}...")
    os.makedirs(os.path.dirname(output_model), exist_ok=True)
    torch.save(model.state_dict(), output_model)
    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", default="traces/collection")
    parser.add_argument("--output-model", default="models/sts2_mcts_v1.pth")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=256)
    args = parser.parse_args()
    
    train(args.trace_dir, args.output_model, args.epochs, args.batch_size)

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

def main():
    parser = argparse.ArgumentParser(description="Export training data from traces.")
    parser.add_argument("--trace-dir", default="traces/live_llm", help="Directory containing JSONL traces")
    parser.add_argument("--output", default="training_data.jsonl", help="Output JSONL file for fine-tuning")
    parser.add_argument("--only-ok", action="store_true", help="Only export steps where the action was successfully applied")
    args = parser.parse_args()

    trace_dir = Path(args.trace_dir)
    if not trace_dir.exists():
        print(f"Error: Trace directory {trace_dir} does not exist.")
        return 1

    output_path = Path(args.output)
    count = 0

    with output_path.open("w", encoding="utf-8") as out_f:
        for jsonl_file in trace_dir.glob("*.jsonl"):
            with jsonl_file.open("r", encoding="utf-8") as in_f:
                for line in in_f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        
                        # 检查是否有决策输出
                        policy_output = entry.get("policy_output")
                        if not policy_output or policy_output.get("action_id") is None:
                            continue
                            
                        # 过滤执行失败的动作
                        if args.only_ok:
                            bridge_result = entry.get("bridge_result")
                            if not bridge_result or bridge_result.get("status") != "ok":
                                continue

                        # 构造训练样本 (简单示例：OpenAI Fine-tuning 格式)
                        # 系统提示词、用户输入(snapshot + actions)、助手输出(decision)
                        
                        # 注意：这里只是一个示例结构，实际微调时可能需要更精细的 Prompt 构造
                        sample = {
                            "messages": [
                                {"role": "system", "content": "You are a Slay the Spire 2 agent. Selected the best action_id from the legal actions based on the game snapshot."},
                                {"role": "user", "content": json.dumps({
                                    "snapshot": entry.get("snapshot"),
                                    "legal_actions": entry.get("legal_actions"),
                                    "battle_context": entry.get("battle_context")
                                }, ensure_ascii=False)},
                                {"role": "assistant", "content": json.dumps({
                                    "action_id": policy_output.get("action_id"),
                                    "reason": policy_output.get("reason"),
                                    "detail": policy_output.get("detail")
                                }, ensure_ascii=False)}
                            ]
                        }
                        out_f.write(json.dumps(sample, ensure_ascii=False) + "\n")
                        count += 1
                    except Exception as e:
                        print(f"Error parsing line in {jsonl_file}: {e}")

    print(f"Successfully exported {count} training samples to {output_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

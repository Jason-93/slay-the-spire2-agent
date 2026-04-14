# Ollama 接入与训练集生成指南

本项目支持通过 Ollama 接入本地大语言模型（如 Llama 3, Qwen 等），并利用自动运行（Autoplay）功能产生大量的训练数据集。

## 1. 安装与启动 Ollama

1. 前往 [ollama.com](https://ollama.com) 下载并安装 Ollama。
2. 启动 Ollama 并下载你想要使用的模型（推荐 llama3 或 qwen2）：
   ```bash
   ollama run llama3
   ```
3. 确保 Ollama 服务正在运行。默认情况下，它会在 `http://127.0.0.1:11434` 提供服务。

## 2. 配置 Agent 接入 Ollama

项目默认配置已指向 Ollama 的 OpenAI 兼容接口：
- `llm_base_url`: `http://127.0.0.1:11434/v1`
- `model`: `llama3` (可根据需要修改)
- `api_key`: `ollama` (Ollama 接口通常不需要实际的 key，但为了兼容性填入非空值)

你可以在启动脚本中通过命令行参数覆盖这些设置。

## 3. 产生训练数据集

训练集是通过记录 Agent 在游戏中的决策过程产生的。

### 3.1 运行自动打牌

确保游戏已启动并安装了 Bridge Mod，然后运行：

```bash
$env:PYTHONPATH='src'; python tools/run_llm_autoplay.py --model llama3 --max-steps 100
```

- `--max-steps`: 设置最大执行步数。
- Agent 会自动观察游戏状态、向 Ollama 发送请求、执行动作并记录过程。

### 3.2 训练数据存储位置

所有的运行记录（Traces）都会保存到 `traces/live_llm/` 目录下，格式为 JSONL。
每个 JSONL 文件代表一次运行，每一行（TraceEntry）包含：
- `snapshot`: 决策时的完整游戏状态。
- `legal_actions`: 当时的合法动作列表。
- `policy_output`: LLM 返回的决策结果（包含 action_id, reason, detail 等）。
- `bridge_result`: 执行动作后的反馈（成功或失败）。

### 3.3 提取训练数据

你可以使用 `tools/export_training_data.py`（如果已提供）或自定义脚本解析这些 JSONL 文件。

典型的训练数据（Fine-tuning 格式）可以从 `TraceEntry` 中提取：
- **Input**: `snapshot` + `legal_actions` (作为 Prompt)
- **Output**: `policy_output.action_id` + `policy_output.reason` + `policy_output.detail`

## 4. 提高数据质量

为了产生高质量的训练集，建议：
1. **使用更强的模型进行生成**：例如使用 `llama3:70b` 或 `gpt-4o` 产生的 Traces 来训练更小的本地模型。
2. **筛选成功动作**：在处理 Traces 时，只保留 `bridge_result.status == "ok"` 的记录。
3. **多样化场景**：在不同的角色、层数和战斗类型下运行采集。

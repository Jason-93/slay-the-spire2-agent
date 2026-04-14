# sts2-agent

简体中文 | [English](README.md)

`sts2-agent` 是一个面向《Slay the Spire 2》的 Agent/Mod 原型仓库，包含游戏内 C# bridge mod、Python 侧策略与 orchestrator，以及配套的构建、校验和联调脚本，为后续接入大模型自动打牌提供基础设施。

## 仓库内容

- `src/sts2_agent/`：Python 侧 bridge client、policy、orchestrator、trace
- `mod/Sts2Mod.StateBridge/`：STS2 游戏内 bridge mod
- `mod/Sts2Mod.StateBridge.Host/`：fixture / runtime-host 联调宿主
- `tests/`：Python 单元测试
- `tools/`：构建、安装、验证、live 调试脚本
- `docs/`：详细开发文档、兼容性说明与升级注意事项

## 环境要求

- Python 3.11+
- .NET SDK 9
- Godot 4.5.1
- Windows 版《Slay the Spire 2》

## 快速开始

基于真实 STS2 安装构建 mod：

```bash
dotnet build mod/Sts2Mod.StateBridge.sln \
  -p:Sts2ManagedDir="C:\\Program Files (x86)\\Steam\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64" \
  -p:Sts2ModLoaderDir="C:\\Program Files (x86)\\Steam\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64"
```

安装并启动 bridge mod：

```bash
python tools/debug_sts2_mod.py install --game-dir "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Slay the Spire 2"
python tools/debug_sts2_mod.py debug --game-dir "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Slay the Spire 2"
```

运行 Python 测试：

```bash
$env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

## 自动对局 (Autoplay)

Agent 可以使用 LLM (通过 Ollama/OpenAI) 或 MCTS 策略自动进行游戏。

### 全自动运行 (推荐用于测试)

要以全自动模式运行 Agent (自动处理战斗、奖励、地图和事件)：

**LLM 模式 (需要 Ollama):**
```bash
$env:PYTHONPATH='src'; python tools/run_llm_autoplay.py --full-auto --model llama3
```

**MCTS 模式 (启发式/搜索):**
```bash
$env:PYTHONPATH='src'; python tools/run_mcts_autoplay.py --full-auto
```

*注意：请确保游戏已启动并安装了 Bridge Mod，且已启用写操作权限，以便 Agent 能够在游戏中实际执行动作。*

## MCTS 自我学习与 AlphaZero

Agent 支持基于 Policy-Value 神经网络的 MCTS 自我学习模式。该模式不依赖外部大模型，可以通过你自己的游戏对局轨迹进行训练。

### 硬件优化 (AMD 7800X3D + 7900XTX)

针对 AMD 7800X3D 和 7900XTX 高端配置的优化：
- **CPU**: 7800X3D 的强大单核性能非常适合 MCTS 树搜索。你可以将 `--mcts-iterations` 增加到 400-800 以获得更高的决策质量。
- **GPU**: 7900XTX 可用于加速神经网络训练。请确保安装了支持 ROCm 的 PyTorch (在 Windows 上也可尝试通过 DirectML 使用)。
- **内存**: 针对 32GB 内存，经验回放池 (Replay Buffer) 默认增大至 50,000 条，以存储更多样化的对局数据。

### 如何训练

1. **收集数据**：使用 MCTS (启发式模式) 运行 Agent 以收集对局轨迹。
   ```powershell
   $env:PYTHONPATH='src'; python tools/run_mcts_autoplay.py --full-auto --trace-dir traces/collection
   ```
2. **训练模型**：使用收集到的轨迹训练 Policy-Value 网络。
   ```powershell
   $env:PYTHONPATH='src'; python tools/train_mcts_model.py --trace-dir traces/collection --output-model models/sts2_mcts_v1.pth
   ```
3. **加载模型**：使用训练好的模型运行 Agent。
   ```powershell
   $env:PYTHONPATH='src'; python tools/run_mcts_autoplay.py --full-auto --model-path models/sts2_mcts_v1.pth
   ```

## Bridge 接口

mod 成功注入后，会暴露：

- `GET /health`
- `GET /snapshot`
- `GET /actions`
- `POST /apply`
- `GET/POST/DELETE /agent-status`

默认只读；如需 live 写动作，请显式开启写入。

## 重点文档

- `docs/sts2-mod-local-development.md`：构建、安装、live 联调与验证
- `docs/sts2-mod-upgrade-notes.md`：游戏更新后的 mod 升级注意事项
- `docs/sts2-mod-agent-compatibility.md`：当前 bridge/runtime 兼容性说明
- `docs/local-development.md`：本地 Python 工作流说明
- `docs/prototype-validation.md`：fixture / prototype 校验说明

## 编码说明

- 中文文档与 OpenSpec artifacts 统一使用 UTF-8 无 BOM。
- 避免通过 PowerShell 文本管道写中文文件，否则可能出现 `???`。

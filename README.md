# sts2-agent

`sts2-agent` 是一个面向《Slay the Spire 2》的 Agent/Mod 原型仓库，目标是把游戏内状态抽取、动作接口、自动决策和调试工具串起来，为后续接入大模型自动打牌提供稳定基础。

## 当前能力

- 提供 Python 侧的 Agent 协议模型、bridge 抽象、启发式策略和 orchestrator
- 提供 C# in-game mod，可在游戏进程内暴露本地 HTTP bridge
- 已支持读取真实运行时状态，并提供 `/health`、`/snapshot`、`/actions`、`/apply`
- 支持在无活动 run 的主菜单/开局流程导出 `phase="menu"`，为自动化测试提供可重复的进入 run 起点（详见 `docs/sts2-mod-agent-compatibility.md`）
- 已提供 `.pck` 打包、安装、启动和联调脚本

## 仓库结构

- `src/sts2_agent/`：Python 侧核心逻辑，包括 bridge、policy、orchestrator、trace
- `tests/`：Python 单元测试
- `mod/Sts2Mod.StateBridge/`：STS2 in-game bridge mod
- `mod/Sts2Mod.StateBridge.Host/`：本地宿主程序，用于 fixture 或 runtime-host 联调
- `tools/`：构建 `.pck`、安装 mod、启动调试、校验产物的脚本
- `docs/`：补充开发文档，重点参考 `docs/sts2-mod-local-development.md`
- `openspec/`：需求、设计和变更记录

## 环境要求

- Python 3.11+
- .NET SDK 9
- Godot 4.5.1（用于生成与游戏兼容的 `.pck`）
- 已安装的《Slay the Spire 2》Windows 版

## 文档编码注意事项

- 仓库内中文文档、OpenSpec artifacts 与说明文件统一使用 UTF-8 无 BOM。
- 不要通过 PowerShell 文本管道写中文文件，例如 `@'...'@ | python -`；这类写法在当前环境下可能把中文写成 `???`。
- 更新中文文档时，优先使用直接文件写入方式或 `apply_patch`。

## 常用命令

### Python 侧

```bash
python -m pytest
```

运行 Python 单元测试。

### 构建 STS2 mod

```bash
dotnet build mod/Sts2Mod.StateBridge.sln \
  -p:Sts2ManagedDir="F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64" \
  -p:Sts2ModLoaderDir="F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2\\data_sts2_windows_x86_64"
```

### 一键构建 / 安装 / 调试 mod

```bash
python tools/debug_sts2_mod.py build
python tools/debug_sts2_mod.py install
python tools/debug_sts2_mod.py debug --game-dir "F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2"
```

### 真实 `POST /apply` 验证

只读 discovery：

```bash
python tools/validate_live_apply.py
```

启动游戏并开启写入后做一次真实自动出牌验证：

```bash
python tools/validate_live_apply.py \
  --launch \
  --enable-writes \
  --apply \
  --allow-write \
  --game-dir "F:\\SteamLibrary\\steamapps\\common\\Slay the Spire 2"
```

每次执行都会在 `tmp/live-apply-validation/<timestamp>/` 下输出结构化 artifacts，包括 `health.json`、`before_snapshot.json`、`before_actions.json`、`apply_request.json`、`apply_response.json`、`after_snapshot.json`、`after_actions.json` 和 `result.json`。

### reward -> map -> 下一场战斗链路验证

当游戏已经来到 reward 或 map 窗口，且 bridge 允许写入时，可用保守默认策略验证整段过渡链路：

```bash
python tools/validate_reward_map_next_battle.py \
  --apply \
  --allow-write
```

脚本会优先 `skip_reward`，并在地图阶段使用保守默认选路，直到回到下一场 `combat` 或命中超时。artifacts 默认写到 `tmp/reward-map-next-battle-validation/<timestamp>/`。

## Bridge 接口

mod 成功注入后，会在本地暴露以下接口：

- `GET /health`：健康状态与 provider 模式
- `GET /snapshot`：当前局面快照
- `GET /actions`：当前合法动作列表
- `POST /apply`：提交动作

默认以只读模式启动；如需真实执行动作，需显式开启写入能力。

`tools/validate_live_apply.py` 会额外要求 `--allow-write` 显式确认，避免误发真实动作。

## 大模型自动打牌

仓库现在已经提供了：

- `src/sts2_agent/bridge/http.py`：把本地 STS2 HTTP bridge 封装成 `GameBridge`
- `src/sts2_agent/policy/llm.py`：OpenAI 兼容 `chat/completions` policy
- `tools/run_llm_autoplay.py`：live autoplay 调试入口

默认本地模型接口为：

```text
http://127.0.0.1:8080/v1
```

可先查看可用模型：

```bash
curl http://127.0.0.1:8080/v1/models
```

### Dry-run

只读取局面并调用模型，不真实提交动作：

```bash
python tools/run_llm_autoplay.py \
  --base-url "http://127.0.0.1:8080/v1" \
  --model "Qwen3.5-9B-Q5_K_M.gguf" \
  --dry-run
```

### Live autoplay（完整玩家回合）

进入一场真实战斗并确认 bridge 允许写入后，可执行一整回合的连续自动打牌：

```bash
python tools/run_llm_autoplay.py \
  --bridge-base-url "http://127.0.0.1:17654" \
  --base-url "http://127.0.0.1:8080/v1" \
  --model "Qwen3.5-9B-Q5_K_M.gguf" \
  --max-actions-per-turn 12
```

常用参数：

- `--dry-run`：只做模型决策，不发送 `/apply`
- `--trace-dir`：指定 trace 输出目录
- `--max-steps`：限制整次 runner 的最大决策步数
- `--max-actions-per-turn`：限制当前玩家回合内最多执行多少个动作
- `--no-auto-end-turn-when-only-end-turn`：只剩 `end_turn` 时不自动点回合结束，而是直接停止
- `--no-stop-after-player-turn`：关闭“打完整个玩家回合就退出”，继续沿用旧的跨窗口调试流程
- `--policy-timeout-seconds`：限制单步模型调用超时

### Live autoplay（整场战斗）

如需从当前玩家回合一路打到战斗结束、处理 reward/map，并尝试接回下一场战斗，可显式启用 battle 模式：

```bash
python tools/run_llm_autoplay.py \
  --bridge-base-url "http://127.0.0.1:17654" \
  --base-url "http://127.0.0.1:8080/v1" \
  --model "Qwen3.5-9B-Q5_K_M.gguf" \
  --battle-mode \
  --reward-mode safe-default \
  --map-mode safe-default \
  --stop-after-next-combat \
  --max-turns-per-battle 12 \
  --max-total-actions 48 \
  --wait-for-next-player-turn-seconds 30 \
  --transition-timeout-seconds 15
```

battle 模式下，runner 会在敌方回合和动画窗口持续轮询，直到：

- 进入 `reward`、`map`、过渡等待等跨窗口状态并继续推进
- 命中 `next_combat_entered`、`map_phase_reached`、`reward_phase_reached` 等显式停止边界
- 命中 `max_turns_per_battle`、`max_total_actions`
- 等待下一玩家回合或 reward/map 过渡超时
- 模型或 bridge 失败中断

新增常用参数：

- `--battle-mode`：启用整场战斗模式，等价于关闭 `stop_after_player_turn`
- `--reward-mode`：reward 策略，可选 `halt`、`skip`、`skip-only`、`safe-default`、`llm`
- `--map-mode`：map 策略，可选 `halt`、`safe-default`、`llm`
- `--stop-after-next-combat`：一旦重新进入下一场战斗就停止，便于验证跨窗口链路
- `--max-turns-per-battle`：限制整场战斗最多完成多少个玩家回合
- `--max-total-actions`：限制整场战斗最多提交多少个动作
- `--max-consecutive-failures`：限制连续失败预算
- `--wait-for-next-player-turn-seconds`：等待下一玩家回合的超时
- `--transition-timeout-seconds`：等待 reward/map/房间切换的超时
- `--poll-interval-seconds`：敌方回合 / 动画窗口的轮询间隔
- `--max-non-combat-steps`：限制 reward/map/transition 等非战斗步骤预算
- `--unknown-window-fuse`：未知窗口连续出现多少次后熔断停止

每次运行都会输出 `RunSummary`，并在 `trace_dir` 下保存 JSONL trace。回合级结果重点看：

- `turn_completed`：是否正常打到本回合停止边界
- `actions_this_turn`：本回合已执行动作数
- `ended_by`：最终停止原因，如 `auto_end_turn`、`phase_changed`、`max_actions_per_turn`

battle 模式下再重点看：

- `battle_completed`：是否真正打完当前战斗
- `turns_completed`：已经完成的玩家回合数
- `total_actions`：整场战斗累计提交动作数
- `current_turn_index`：当前观测到的玩家回合索引
- `reward_actions_taken` / `map_actions_taken`：reward 与 map 阶段已提交动作数
- `non_combat_steps`：本次运行累计经过多少个非战斗步骤
- `next_combat_entered`：是否成功重新接回下一场战斗

单步 trace 至少包含：

- 当前 `snapshot`
- 当前 `legal_actions`
- 模型输出的 `action_id` / `reason` / `halt`
- 原始模型响应文本 `raw_response_text`
- bridge 回执或 dry-run 结果

多步回合模式下，每条 trace 还会额外记录：

- `step_index`
- `actions_this_turn`
- `phase_kind` / `step_kind`
- `transition_elapsed_seconds`
- `is_final_step`
- `stop_reason`

## 当前进度

目前仓库已经能够：

- 在真实 STS2 进程中挂载 bridge
- 获取地图、战斗、奖励等窗口阶段的状态
- 为后续 Agent 或大模型接入提供标准化的状态和动作数据

后续会继续补齐更多游戏字段、扩大动作执行覆盖率，并把大模型决策接到现有 bridge 之上。

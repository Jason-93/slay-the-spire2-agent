## Why

当前 bridge 与 agent 已经能完成基础的 live autoplay，但战斗观测仍然过于瘦身：手牌基本只有 `name/cost/playable`，敌人基本只有 `hp/block/intent`，缺少卡牌描述、结构化意图、powers 与可支撑长期规划的 run-level 信息。结果是大模型经常只能依赖卡名猜效果、依赖模糊 intent 盲打，难以做出稳定的战术决策，更无法自然扩展到牌库规划、路线规划与怪物机制百科。

现在推进 rich runtime state schema，可以先解决“看不清局面”的问题，同时为后续的派生语义层、静态知识层与更强策略 agent 预留稳定扩展点，避免后面反复破坏协议。

## What Changes

- 扩展 mod/runtime 导出的战斗状态 schema：在玩家、手牌、敌人对象中增加更丰富且可选的结构化字段，如卡牌描述、升级态、目标类型、traits、结构化敌方 intent、powers 等。
- 为 bridge 快照引入可扩展的 `run_state` 层，逐步承载 `act/floor/room/map` 等整局规划所需事实，并保持与当前 `combat/reward/map/terminal` 决策窗口兼容。
- 明确区分运行时事实、派生语义与静态知识锚点，优先在 snapshot 中保留 `canonical_*`/稳定标识与结构化原始字段，便于未来外挂卡牌/怪物百科，而不是把百科硬编码进 live payload。
- 更新 Python 侧 models、HTTP bridge 解析与 LLM snapshot 摘要，使 agent 能消费 richer state，同时保持旧字段向后兼容。
- 增加 fixture / unit / live validation 覆盖，确认 richer state 在 fixture 与 in-game runtime 下都能稳定导出，并且缺失字段时不会破坏现有 autoplay。

## Capabilities

### New Capabilities
- `rich-runtime-state-schema`: 定义面向 agent 的分层 runtime state schema，包括 richer combat state、run_state 与知识锚点扩展约定。

### Modified Capabilities
- `mod-state-export`: 调整 mod 导出的状态快照要求，使其必须支持更丰富的卡牌、敌人与整局状态字段。
- `game-bridge`: 调整 bridge 快照契约，使其能向上层稳定暴露 richer runtime state，并处理可选字段的兼容性。
- `llm-autoplay-runner`: 调整 runner 对 snapshot 的消费要求，使其能够把 richer state 提供给策略层，并保持旧行为可回退。

## Impact

- 受影响代码主要包括 `mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs`、`mod/Sts2Mod.StateBridge/Contracts/*.cs`、`src/sts2_agent/models.py`、`src/sts2_agent/bridge/http.py`、`src/sts2_agent/policy/llm.py`。
- 需要扩展 fixture、Python 单元测试、mod 侧测试与至少一次 live runtime 验证，覆盖 richer card/enemy/run state 的导出质量。
- 会引入协议字段扩展，但应采用追加式、可选字段策略，避免破坏现有 bridge/runner 使用方。

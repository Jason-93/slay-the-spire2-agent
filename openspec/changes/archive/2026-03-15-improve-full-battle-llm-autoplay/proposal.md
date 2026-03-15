## Why

当前 `llm-autoplay-runner` 已经能在理想路径上打完整场战斗，但真实 live 对局里仍然容易被回合切换、短暂空动作窗口、额外选牌子流程和模型“忘记上一手发生了什么”打断。结果是 battle autoplay 虽然可用，却还不够稳定，难以连续复现、评估和迭代大模型策略质量。

现在继续完善很合适：bridge 的状态质量、reward/map 衔接和 battle loop 都已经具备基础能力，下一步应该把重点放到“整场战斗稳定跑完”的上下文组织、恢复策略和验证闭环上，而不是继续依赖人工盯盘补救。

## What Changes

- 为 battle autoplay 增加 battle 级上下文摘要，向模型补充最近动作、最近 bridge 回执、当前回合索引、等待/恢复状态和额外选牌窗口语义。
- 强化 orchestrator 的恢复逻辑，对 `stale_action`、临时空 legal actions、回合切换窗口、额外选牌窗口和可恢复拒绝结果执行有限次重观测与重试，而不是立即失败。
- 收紧 `chat-completions` 决策契约，要求模型输出对 targeted action 更稳定的结构化字段，并保留可诊断的置信度/恢复线索。
- 扩展 live validation 和 battle artifacts，增加“多回合整场战斗 autoplay 冒烟”的可回放结果，便于评估稳定性提升。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `autoplay-orchestrator`: 从“能跨回合运行”提升为“能维护 battle 级上下文并对可恢复竞争态执行有界恢复”。
- `llm-autoplay-runner`: 从“逐步调用模型做动作选择”提升为“向模型提供 battle 级摘要，并把恢复态、额外选牌态和回合推进态纳入运行语义”。
- `chat-completions-llm-provider`: 调整模型输入/输出契约，补充 battle 级上下文和更稳定的结构化决策字段。
- `live-apply-validation`: 增加整场战斗多回合 smoke validation，记录 battle 级成功率、停止原因和恢复路径 artifacts。

## Impact

- 影响 Python 侧 `AutoplayOrchestrator`、LLM policy/provider、trace schema、CLI 调试入口与 battle smoke 脚本。
- 影响测试与验证，需增加 battle 级恢复、上下文摘要、额外选牌窗口和 live smoke artifacts 的覆盖。
- 不要求新增 bridge HTTP 端点，但会更依赖现有 richer runtime state、selection metadata 与动作回执诊断字段。

## Why

当前系统已经能在真实 STS2 战斗中完成“单步动作”和“完整玩家回合”两级 autoplay，证明 bridge、模型调用和写入闭环可用。但如果每回合都要人工重新启动 runner，就还不能形成真正可观察、可评估的大模型自动打牌体验，也无法稳定衡量整场战斗层面的策略质量与故障恢复能力。

现在推进“整场战斗 autoplay”正合适：一方面 `end_turn` 推进链路和回合级 trace 已经打通，另一方面 live 联调已经暴露出 `stale_action`、伪 legal action、回合切换等典型问题，适合进一步把 runner 抬升到“跨回合、直到战斗结束或命中安全边界”的执行语义。

## What Changes

- 将现有 `llm-autoplay-runner` 从“完整玩家回合 autoplay”扩展为“整场战斗 autoplay”，支持跨多个玩家回合持续运行。
- 增加 battle 级停止条件与安全边界，例如最大回合数、最大总动作数、连续失败预算、可选的回合间暂停或人工接管阈值。
- 扩展 trace 与 `RunSummary`，补充 battle 级统计字段，例如已完成回合数、总动作数、终止原因、战斗是否结束、是否中途交还控制权。
- 更新 CLI 与文档，提供“打完整场战斗”的调试入口，并记录至少一次真实 live battle 冒烟结果。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `llm-autoplay-runner`: 将 requirement 从“支持单回合连续决策”扩展为“支持跨多个回合连续决策直到战斗结束或触发 battle 级停止条件”

## Impact

- 影响 Python 侧 `AutoplayOrchestrator`、`LiveAutoplayConfig`、CLI、trace/summary 数据结构与测试。
- 影响真实联调流程，需要新增 battle 级 smoke artifacts 与文档说明。
- 不要求新增 bridge HTTP 协议，但会更依赖现有 runtime 状态推进、phase/turn 识别与错误恢复质量。

## Context

当前仓库已经具备 battle 级 autoplay 主路径：runner 能在 `combat` 中跨多个玩家回合连续执行，bridge 也能导出 richer runtime state、reward/map 衔接与额外选牌动作。但 live 实测仍暴露几个稳定性问题：模型只看当前快照时容易忘记上一手动作是否刚被拒绝、刚结束回合还是刚进入额外选牌；短暂的空 action 窗口、动画窗口或 `stale_action` 也会让 battle autoplay 过早中断。

因此这次设计不再追求新增更多桥接字段，而是把现有 battle loop 收敛成“有 battle 记忆、能做有限恢复、可解释可验证”的执行模型。重点在 Python 侧 orchestrator / provider / validation，而不是再扩展 mod 协议面。

## Goals / Non-Goals

**Goals:**
- 提升 LLM 整场战斗 autoplay 在真实 live battle 中的稳定性，减少因短暂竞争态或上下文丢失导致的中断。
- 为模型输入补充 battle 级短期记忆，包括最近动作、最近失败、当前等待态、额外选牌态和回合推进摘要。
- 为 orchestrator 增加有界恢复策略，使可恢复错误尽量在本地吸收，而不是立即终止 battle。
- 产出可比对的 battle 级 artifacts，便于后续评估“是否真的更稳定了”。

**Non-Goals:**
- 不在本次 change 中解决长期牌库规划、敌人百科知识库或高阶策略质量问题。
- 不扩展到整局 run 托管；reward/map/菜单只作为 battle 前后衔接背景，不是主目标。
- 不引入新的远程服务或复杂队列系统，仍保持本地 CLI + bridge + OpenAI 兼容接口。

## Decisions

### 1. 在 orchestrator 内维护 battle-scoped memory，而不是把完整历史原样喂给模型

执行核心保留在现有 `AutoplayOrchestrator`。新增一个 battle 级轻量上下文对象，记录：
- 最近若干步的合法动作摘要与最终选中动作
- 最近一次 bridge 回执与失败原因
- 当前 battle 的回合索引、总动作数、连续恢复次数
- 当前是否处于等待玩家回合、额外选牌、transition 或 recovery 模式

向模型暴露的是压缩后的 battle summary，而不是完整 trace 原文。这样可以控制 token 开销，并让模型看到“刚才发生了什么”这个最关键的短期记忆。

备选方案是把最近 N 条完整 trace 直接拼进 prompt，但这会显著增大上下文长度，也会把很多无关字段重复暴露给模型。

### 2. provider 输出契约补充 recovery-friendly 结构字段，但仍以合法 action_id 为唯一执行入口

`chat-completions-llm-provider` 继续要求模型选择当前 legal set 中的 `action_id`，避免脱离 bridge 合法集合胡乱构造动作。同时补充以下字段：
- `target_id`：targeted action 时显式返回
- `confidence`：模型对本次动作把握度的离散或数值表达
- `reason`：简短决策理由
- `halt`：显式放弃执行

其中真正执行仍以 `action_id` + 现有 legal action params 为准，避免引入新的执行分支；新增字段主要用于校验、日志和 battle 级恢复提示。

备选方案是让模型直接返回完整 action payload，但这会放大协议耦合，也更容易因为 params 漂移导致失败。

### 3. 可恢复错误采用“重观测 -> 约束化重试 -> 达预算后中断”的三段式恢复

对以下情况视为可恢复：
- `stale_action`
- 当前 decision 短暂没有可用 legal action，但仍处于 `combat`
- 刚从 `end_turn`、额外选牌、动画窗口切回玩家态
- 模型返回了当前 legal set 之外的动作，但 legal set 本身仍稳定

恢复步骤统一为：
1. 重新拉取最新 `snapshot/actions`
2. 将上一次失败原因压缩进 battle summary
3. 在限定预算内重新请求模型或等待下一次稳定窗口

如果同类恢复连续超预算，则以明确 stop reason 中断，而不是无限重试。

### 4. battle smoke validation 单独记录“恢复质量”，而不只看最终是否打赢

整场战斗 autoplay 的价值不只是最终完成战斗，还要知道过程中是否频繁靠恢复机制硬撑。因此 live validation artifacts 除现有结果外，还增加：
- recoverable error 次数
- recovery success 次数
- recovery stop reason
- 最近 battle summary / 最近失败摘要

这样后续可以区分“真正稳定跑完”和“虽然跑完但恢复次数很多”的差别。

## Risks / Trade-offs

- [Risk] battle summary 设计不当，可能把 prompt 变长但信息增益有限 -> Mitigation：只保留最近少量高价值字段，并通过 trace 对比持续收敛。
- [Risk] 恢复逻辑过强会掩盖真正的 bridge 或策略缺陷 -> Mitigation：所有恢复都要落盘，且超过预算后必须显式失败。
- [Risk] `confidence` 等新增字段可能提升模型输出复杂度 -> Mitigation：保持字段最小化，执行仍只依赖 `action_id` / `target_id` / `halt`。
- [Risk] live smoke validation 更长、更脆弱 -> Mitigation：区分 discovery、dry-run 和真实 smoke，默认保守设置 battle 级预算。

## Migration Plan

1. 先补 battle summary / provider contract / trace schema，不改 battle loop 主控制流。
2. 再把恢复状态机接入 orchestrator，对可恢复错误改为有界重试。
3. 增加 battle 级测试与 live smoke artifacts，确认恢复路径和停止原因可诊断。
4. 更新 CLI / README，使调试入口能显式开启或关闭 battle recovery 语义。

回滚方式：
- 若 battle summary 或恢复逻辑不稳定，可保留旧的严格停止模式作为配置开关，快速退回“遇到竞争态立即中断”的行为。

## Open Questions

- `confidence` 最终采用数值区间还是有限枚举更利于不同模型稳定输出。
- 是否需要把“上一手动作的预期结果”也纳入模型输出，以便 battle trace 对比模型理解与实际结果差异。
- battle summary 是否要对 reward/map 过渡窗口保留极小摘要，为未来 run-level autoplay 铺路。

## Context

当前仓库已经具备 live bridge、battle autoplay、reward/map 衔接、HUD 状态展示和 battle 级 trace，但真实对局里仍然频繁出现 `rejected`、`stale_action`、`selection_window_changed`、`not_player_turn` 或“请求 accepted 但很快被下一次状态推翻”的情况。现象上看像是模型“很蠢”，但实际上有相当一部分失败来自提交时机不稳、窗口切换边界不明确、重复状态生命周期刷写，以及验证口径还不能很好区分“策略错误”和“runtime 时序错误”。

这次变更的重点不是继续扩充更多状态字段，而是把现有状态、动作和 battle loop 组织得更保守、更可恢复、更可诊断，让 live autoplay 在真实 battle 中减少无谓 reject，并让 reject 真正变成可以持续优化的指标。

## Goals / Non-Goals

**Goals:**
- 在不牺牲现有 battle autoplay 能力的前提下，降低 live `/apply` 的 reject 频率。
- 在动作提交前增加稳定窗口判定和本地保护，减少明显高风险提交。
- 将 reject 分成“可恢复”和“不可恢复”两类，并为可恢复 reject 提供有界恢复路径。
- 让 HUD、trace 与 live validation 能明确展示 reject 的来源、恢复过程和最终影响，便于后续比较优化前后差异。

**Non-Goals:**
- 不在本次变更中追求更强的大模型策略质量，例如长期牌库规划或敌人百科推理。
- 不新增新的 bridge 远程服务或复杂消息队列；仍沿用当前本地 HTTP bridge。
- 不改变 legal action 作为唯一执行来源的基本契约；模型仍只能从当前 legal set 中做选择。

## Decisions

### 1. 在 orchestrator 内增加 pre-submit gate，而不是把 reject 全部留给 `/apply`

执行前增加一层统一的“提交门槛”检查，至少覆盖：
- 当前 phase 是否仍为可执行 phase
- `current_side` 是否仍允许玩家动作
- `window_kind` 是否落在已知可提交窗口
- 当前 decision 是否在最近一次稳定观测之后没有明显漂移
- 目标动作是否与 selection / transition / pending end-turn 状态冲突

这层 gate 的目标不是替代 bridge 的合法性校验，而是拦住已知高风险提交。这样可以把“本地已知不该发的动作”直接转成等待、重观测或恢复，而不是先制造一次 reject 再处理。

备选方案是继续完全依赖 `/apply` 返回 reject 作为唯一真相。这样实现简单，但 reject 率会偏高，也更难区分是模型选错还是 runtime 窗口本来就不稳。

### 2. reject 采用统一分类表，并绑定恢复策略

把 live 失败统一映射到一组稳定类别：
- `recoverable_stale`: 如 `stale_action`、`selection_window_changed`
- `recoverable_timing`: 如 `not_player_turn`、短暂空 legal actions、transition wait
- `invalid_policy_decision`: 模型动作不在 legal set、缺目标、参数不合法
- `hard_runtime_reject`: bridge 明确拒绝且不适合自动恢复

每一类都绑定默认动作：
- 重新观测
- 等待窗口稳定
- 重新请求模型
- 立即停止并落盘

这样可以避免当前“所有 reject 都像同一件事”的问题，也方便后续在 validation 中直接统计各类 reject 的占比。

### 3. 历史 HUD 只保留“决策条目”，不保留同一条决策的全部状态噪声

HUD 现在已经有滚动历史，但如果 `planned -> submitted -> accepted` 全部展开，会迅速淹没真正有价值的 `detail`。因此历史层采用“同一决策合并”的策略：
- `thinking` 单独保留，表示模型正在分析
- 具有同一 `phase/action_label/reason/detail/turn/step` 的状态更新合并为一条
- 最终展示该条决策的最新状态，同时保留摘要和思路

这样玩家看到的是“这一步最后发生了什么、理由是什么”，而不是低价值状态刷屏。

### 4. live validation 新增 reject-rate artifacts，而不仅看 battle 是否完成

仅看 `battle_completed` 无法判断系统是否真的更稳定。validation 需要额外记录：
- reject 总数
- recoverable reject 总数
- recovery 成功次数
- 各 reject 分类计数
- battle stop reason
- 最近一次 reject 的窗口与动作摘要

后续比较时，可以把“完成战斗但 reject 很多”与“完成战斗且 reject 明显下降”区分开来。

## Risks / Trade-offs

- [Risk] pre-submit gate 过于保守，可能减少 reject 的同时也错过本可成功的动作窗口 -> Mitigation：将 gate 结果写入 trace，并允许通过配置逐步放宽。
- [Risk] reject 分类不准确会误导恢复策略 -> Mitigation：保留原始 bridge 错误码、窗口元数据和分类结果，便于对照修正。
- [Risk] HUD 历史合并后，某些调试场景想看完整生命周期细节 -> Mitigation：trace 仍保留完整 bridge_result 与状态推进，HUD 只做高价值摘要。
- [Risk] validation 指标变多后结果更复杂 -> Mitigation：提供稳定的汇总字段，把 reject 统计放进单独 artifacts 文件，避免主结果文件过载。

## Migration Plan

1. 先补 OpenSpec 约束，明确 reject 分类、pre-submit gate、HUD 历史语义和 validation 指标。
2. 在 Python 侧实现提交前 gate、reject 分类和恢复策略，并补单元测试。
3. 在 mod/HUD 侧继续收敛历史展示语义，确保同一决策不会被低价值状态淹没。
4. 扩展 live validation artifacts，用相同 battle 场景比较 reject 总数和恢复成功率。
5. 若新策略导致误判过多，可先保留旧路径作为配置回退。

## Open Questions

- `recoverable_timing` 是否需要再细分为“等待玩家回合”和“selection/transition 切换”两类，以便后续做不同等待时长。
- validation 是否要输出一个统一的 `reject_rate` 百分比字段，还是保留原始计数由后处理脚本计算。
- 是否需要把“模型输出耗时”也纳入 reject 诊断，以区分慢模型导致的 stale 与普通窗口切换 reject。

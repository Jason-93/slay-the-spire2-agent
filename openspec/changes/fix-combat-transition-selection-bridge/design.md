## Context

当前 live battle 已能从玩家回合打到 reward，但实测仍有两类稳定性缺口：一是在回合切换边界，`/actions` 可能短暂暴露已经过期的玩家动作，随后 `/apply` 返回 `409 rejected`；二是部分卡牌会触发战斗内二级选择流程，例如“消耗 1 张牌”“弃 1 张牌后继续结算”，bridge 目前仍把它们当成普通 `play_card` 处理，导致 agent 无法继续完成后续选择。这个问题横跨 runtime 状态导出、动作执行、Python runner 的窗口识别与 live 验证脚本，因此需要单独设计。

## Goals / Non-Goals

**Goals:**
- 明确区分 `player_turn`、`enemy_turn`、`combat_transition` 与战斗内额外选牌窗口，减少回合切换时的过期动作暴露。
- 为战斗内二级选牌流程提供稳定 schema：可识别的窗口种类、可执行 legal actions、明确的 apply 失败语义。
- 让 runner 能把“打出一张会触发选牌的卡”和“在后续窗口里选一张牌”视为连续决策，而不是 `play_rejected` 或无穷重试。
- 保持 fail-safe：无法稳定识别的额外选择窗口宁可保守降级，也不导出误触动作。

**Non-Goals:**
- 不在这次变更里覆盖所有事件、商店、遗物弹窗等非战斗多选窗口。
- 不尝试一次性支持所有复杂多阶段卡牌效果；优先覆盖“从当前手牌/可见卡牌集合中选择一张继续结算”的主路径。
- 不改变 LLM policy 的高层策略逻辑，只补足其可消费的 bridge 语义与最小 runner 适配。

## Decisions

### 决策 1：将回合切换抖动建模为显式窗口，而不是仅靠 apply 重试兜底
- 方案：在 mod 侧继续强化 `window_kind`，至少保证 `enemy_turn`、`combat_transition`、`combat_card_selection` 这类窗口可区分；当窗口不是稳定玩家决策态时，不导出普通 `play_card` / `end_turn`。
- 原因：单纯依赖 `/apply` 返回 `stale_action` 或 `not_player_turn` 只能止损，不能阻止 runner 与 LLM 在错误时间点做决策。
- 备选方案：维持当前导出，仅在 `/apply` 端增强拒绝语义。放弃原因是仍会制造大量无效 LLM 调用和 trace 噪音。

### 决策 2：把额外选牌动作建模为新的 combat-selection capability
- 方案：为战斗内二级选择引入独立 capability，由 bridge 在 `phase="combat"` 下导出额外子窗口与 legal actions，例如 `choose_combat_card`、`cancel_combat_selection`（仅在规则允许时）。
- 原因：这类窗口与普通出牌不同，输入对象不是“打出哪张牌”，而是“对当前待决效果选择一张牌”；如果继续复用 `play_card`，会混淆实例定位与执行语义。
- 备选方案：复用 `choose_reward` 或在 `play_card` 参数里塞更多字段。放弃原因是语义不清，且不利于未来扩展到弃牌/回收/选择目标牌等更多战斗内选择。

### 决策 3：apply 执行分两段校验：决策窗口校验 + 运行时二次确认
- 方案：`InGameRuntimeCoordinator` 先依据当前导出的 legal action 集校验动作，再在实际执行前复查当前窗口是否仍匹配该 action 所属子窗口；若窗口已变化，返回 `stale_action` 或 `selection_window_changed`。
- 原因：回合切换和二级选牌都存在“导出时合法、执行时已变化”的天然竞争，需要明确拒绝原因。
- 备选方案：直接执行 runtime handler，由底层失败统一映射为 `play_rejected`。放弃原因是诊断粒度太粗，难以区分真正不可打与窗口切换。

### 决策 4：先覆盖可见卡牌选择，再逐步扩展到更复杂选择集合
- 方案：首批支持从当前手牌、弃牌堆可见条目或 bridge 已能稳定实例化的卡牌集合里选择单张卡；对不可稳定枚举的隐藏集合仅暴露过渡态与日志，不导出冒险动作。
- 原因：这样可以尽快打通 `True Grit` 一类真实战斗阻塞点，同时控制反射与执行复杂度。
- 备选方案：一次性抽象任意选择源。放弃原因是当前 STS2 runtime 反射路径尚不稳定，易引入大量伪动作。

## Risks / Trade-offs

- [Risk] 额外选牌窗口的 runtime 节点结构在不同卡牌/版本间不完全一致 -> Mitigation：先围绕已观测到的常见选择容器实现多路径探测，并把探测来源写入 diagnostics。
- [Risk] 更严格的窗口过滤可能让某些短暂可操作时机被保守隐藏 -> Mitigation：优先保证不误导出动作，同时保留日志和 `window_kind` 以便后续微调。
- [Risk] 新动作类型会要求 Python runner 与验证脚本同步适配 -> Mitigation：在同一变更里补齐 bridge client 解析、runner safe-action 过滤与 live validation 脚本。
- [Risk] LLM 仍可能在窗口刚切换时基于旧 snapshot 输出动作 -> Mitigation：保留 apply 端的 `stale_action`/`selection_window_changed` 拒绝，并让 runner 在这些错误上刷新 snapshot 后重试。

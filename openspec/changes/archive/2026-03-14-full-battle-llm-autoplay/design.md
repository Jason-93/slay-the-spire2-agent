## Context

当前 `llm-autoplay-runner` 已经支持“同一玩家回合内连续决策”，并且在真实 STS2 战斗中完成了从出牌到自动 `end_turn` 的闭环验证。mod 侧也已经修复 `end_turn` accepted 但状态不推进的问题，说明 battle 内的状态推进链路已经基本可信。

但现有 runner 仍以“当前玩家回合”为执行边界：一旦 `end_turn` 成功或 phase 切走，就立即退出。对于用户真正关心的“整场战斗能不能自动打完”，现状仍需要在每个玩家回合之间人工重启一次 runner，无法连续观察敌方回合、下一玩家回合、战斗结束和奖励出现等完整 battle 生命周期。

本次设计目标是在不扩展 bridge HTTP 协议的前提下，把执行语义提升为“跨多个玩家回合，持续到战斗结束或命中 battle 级安全边界”。核心依赖仍是现有 `snapshot.phase`、`metadata.current_side`、`metadata.round_number`、legal actions 与 `POST /apply` 回执。

## Goals / Non-Goals

**Goals:**
- 支持在同一场 `combat` 中跨多个玩家回合持续 autoplay，直到战斗结束或触发 battle 级停止条件。
- 在敌方回合、动画窗口或暂时不可操作阶段保持“等待并重新观察”，而不是立即退出。
- 增加 battle 级统计与 trace 字段，至少能回答“打了几个回合”“总共执行了多少动作”“最终为何退出”“是否真正打完战斗”。
- 暴露 battle 级安全参数，例如最大回合数、最大总动作数、敌方回合等待超时、连续失败预算。

**Non-Goals:**
- 不扩展到整局 run、跨战斗地图选择、奖励选择或事件选择的全自动托管。
- 不在本次 change 中解决模型策略质量，例如卡序规划、敌人意图理解或长程资源管理。
- 不引入新的外部编排服务或远程队列；仍沿用本地 CLI + bridge + model endpoint 结构。

## Decisions

### 1. 在现有 orchestrator 上加 battle loop，而不是单独新建一个 runner

保留 `AutoplayOrchestrator` 作为唯一执行核心，在其内部把“单回合 loop”抬升为“battle loop + player-turn loop”两层语义：

- battle 仍处于 `combat` 时保持运行
- `metadata.current_side == "Player"` 时进入玩家决策分支
- 非玩家侧时不调模型，只轮询状态直到重新进入玩家侧或战斗结束

这样可以最大化复用当前 trace、stale 重试、合法动作过滤和 CLI 接口，避免把 battle 模式实现成第二套并行代码路径。

备选方案：
- 新建 `BattleAutoplayRunner`：概念更干净，但会复制 orchestrator、CLI、summary、测试与 trace 逻辑，维护成本更高。

### 2. 将“战斗结束”定义为离开 combat 决策域，而不是必须击杀敌人后进入 terminal

对整场战斗 autoplay 来说，正常完成条件应优先识别“当前战斗 encounter 已结束”，而不要求整个游戏 run 终止。因此 battle 完成判定采用以下优先级：

- `snapshot.terminal = true`
- `snapshot.phase != "combat"`，例如进入 `reward`
- `combat` 仍在，但 bridge 已明确暴露非战斗窗口或无可恢复的终止状态

这保证 runner 在战斗打完进入奖励时就能正常退出，而不是误以为要继续托管奖励窗口。

### 3. 引入 battle 级安全预算，并保留回合级预算

现有 `max_steps` 和 `max_actions_per_turn` 只能限制单回合执行。为避免整场战斗模式长时间失控，新增 battle 级预算：

- `max_turns_per_battle`
- `max_total_actions`
- `max_consecutive_failures`
- `wait_for_next_player_turn_seconds`

其中：
- 回合内仍用 `max_actions_per_turn`
- 跨回合则累计 `turns_completed` 与 `total_actions`
- 对 `stale_action` 这类可恢复竞争态不立即失败，但会进入连续失败预算

### 4. 敌方回合与动画窗口采用“观察等待”，不视为异常

`end_turn` 成功后会出现敌方回合、攻击动画、抽牌结算等短暂不可决策窗口。这些窗口既不是玩家回合完成后的退出条件，也不应该被算作错误。

因此 runner 在 battle 模式下会：

- 当 `phase == "combat"` 且 `current_side != "Player"` 时进入等待
- 按固定 poll 间隔重新读取 `snapshot/actions`
- 当重新观测到 `current_side == "Player"` 时恢复模型决策
- 若等待超时则以明确原因退出，如 `next_player_turn_timeout`

### 5. 扩展 summary 与 trace 到 battle 级别

`RunSummary` 与 trace 除保留回合级字段外，再增加：

- `battle_completed`
- `turns_completed`
- `total_actions`
- `current_turn_index`
- `ended_by`

trace 每步增加 battle 维度标记，例如：

- `turn_index`
- `total_actions`
- `waiting_for_player_turn`
- `battle_stop_reason`

这样后续可以区分“某个玩家回合内的动作序列”和“整场战斗跨回合的状态推进”。

## Risks / Trade-offs

- [敌方回合 / 动画窗口判断不稳定] → 优先依赖 `metadata.current_side`、`round_number` 与 `phase` 组合，而不是只看 legal actions。
- [长战斗导致 runner 持续占用较久] → 增加 battle 级预算和等待超时，默认保持保守。
- [`stale_action` 在 live 模式仍会频繁出现] → 保留可恢复重试，但纳入连续失败预算，避免无限重试。
- [奖励窗口出现后是否立即退出存在语义歧义] → 明确本 change 以“战斗结束即退出”为准，不托管 reward/map。
- [更多摘要字段可能影响旧脚本] → 采取只增不删策略，保留现有字段语义。

## Migration Plan

1. 先扩展 orchestrator 配置和 battle 级 summary/trace 字段。
2. 再实现 battle loop：玩家回合决策、敌方回合等待、battle 完成判定。
3. 更新 CLI 参数和测试，覆盖跨回合推进、等待恢复、预算停止等路径。
4. 在真实 battle 中完成一次“从首个玩家回合开始到进入奖励窗口”为止的冒烟，并记录 artifacts。

回滚方式：
- 若 battle 模式不稳定，可把 CLI 默认仍保持 `stop_after_player_turn=true`，只把整场战斗模式作为显式开关保留。

## Open Questions

- 首版 battle 模式是否默认在进入 `reward` 后立即退出，还是允许未来扩展为“自动跳过奖励并继续 run”。
- `stale_action` 是否应区分为“live 正常竞争态”与“bridge 质量问题”，并单独统计。
- 是否需要在 battle 模式下加入可选的每回合日志摘要，方便长战斗实时观察。

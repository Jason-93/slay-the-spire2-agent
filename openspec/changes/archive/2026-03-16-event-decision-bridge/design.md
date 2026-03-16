## Context

当前系统已经能在 combat、reward、map、menu 四类窗口上完成“导出状态 -> 枚举 legal actions -> `/apply` 执行 -> runner 连续推进”的闭环，但 event 房间仍是缺口。实际 live 运行中，进入事件后经常出现三类问题：一是 runtime phase 误判，把 event 临时挂成 `combat` 或 `combat_transition`；二是外部看不到事件正文与可选项，只能停下交还人工；三是即使能识别到界面，也没有对应 action handler，runner 无法继续推进到 map 或后续战斗。

这次改动会同时跨 C# mod 与 Python runner，因此需要一个统一的 event 决策窗口模型，避免继续把事件硬塞进 reward 或 map 的既有语义里。

## Goals / Non-Goals

**Goals:**
- 为 live runtime 增加稳定的 `phase=event` / `window_kind=event_choice|event_continue|event_transition` 识别。
- 为 event 导出足够的结构化信息，至少包含标题、正文、可选项、选项可用性与诊断来源。
- 为 event 新增 legal actions 与 `/apply` 映射，支持选项点击和事件收尾继续。
- 让 LLM runner / orchestrator 能在 event 窗口继续自动决策，并在事件结束后恢复 run-flow。
- 增加可复盘的日志、trace 与测试，便于 live 排查。

**Non-Goals:**
- 不在本次引入完整的事件百科、长期收益评估或跨事件记忆系统。
- 不尝试覆盖所有潜在特殊事件动画，只先覆盖“可点击选项 + 继续按钮”的主路径。
- 不新增外部数据库依赖；事件说明仍优先依赖游戏 runtime 文本。

## Decisions

### 1. 使用独立 `event` phase，而不是复用 `reward`

事件在语义上与奖励不同：它可能包含代价、分支、后续继续按钮，以及“不显示奖励列表但仍可继续”的收尾状态。继续复用 `reward` 会让 runner 的策略提示、默认动作与 stop reason 变得混乱。因此在 live snapshot 中直接导出 `phase=event`，并用 `metadata.window_kind` 区分 `event_choice`、`event_continue`、`event_transition`。

备选方案：
- 复用 `reward`：实现成本低，但会污染已有 reward 语义，并让模型难以区分“奖励拿牌”和“事件选项”。
- 复用 `map`：不符合事实，且无法表达事件正文与继续动作。

### 2. 事件正文与选项先放入 `metadata` 的结构化字段

为了避免一次性重构整个 snapshot 顶层 schema，本次优先在 `snapshot.metadata` 中新增稳定的 event 字段，例如 `event_title`、`event_body`、`event_options`、`event_option_count`、`event_continue_available`。Python 侧在 policy summary 中将这些字段提炼为模型可读输入。

备选方案：
- 新增顶层 `event` 对象：长期更整洁，但会同时改动 contracts、fixtures、parser、tests，当前推进成本更高。
- 仅导出纯文本 diagnostics：太弱，不足以支撑 agent 选项决策。

### 3. 新增专用 action type：`choose_event_option` 与 `continue_event`

event 动作与 reward/map/combat 现有动作不等价，需要明确分开。`choose_event_option` 通过 `params.option_index` 绑定当前可见选项，`continue_event` 用于“继续/离开/确认”类单按钮收尾动作。这样 `/apply` 可保持实例级校验，runner 也能在 prompt 中明确当前窗口的动作集合。

备选方案：
- 复用 `choose_reward` / `advance_reward`：名字和语义都不准确，且会让现有 reward 默认策略误伤事件分支。

### 4. event 检测优先基于 room/screen/object 组合信号，而不是单一 overlay

事件窗口可能出现在 `EventRoom`、专用 event screen、或带继续按钮的结尾画面中。实现上优先组合 `current_room_type`、可见 screen 类型、按钮树、文本节点与可点击项数量进行分析，并在 metadata 中输出 detection source。这样即使某个字段在版本变化后失效，也更容易降级和定位。

备选方案：
- 仅靠 overlay top screen：实现简单，但对版本和特殊事件太脆弱。

## Risks / Trade-offs

- [Risk] event 运行时对象命名可能因版本变化而不稳定 -> Mitigation：保留多套候选字段 / 方法名，并把 detection source 与失败阶段写入日志。
- [Risk] 某些事件存在二次确认、隐藏条件或异步动画，导致按钮瞬时不可点 -> Mitigation：引入 `event_transition` 过渡态与受控重试，而不是立即误判失败。
- [Risk] LLM 仍可能对事件收益理解较差 -> Mitigation：先保证正文、选项文本和限制条件完整暴露，再补充基础规则提示与 trace 复盘。
- [Risk] metadata 承载 event 结构会让 schema 不如顶层字段直观 -> Mitigation：字段命名保持稳定，并在后续若 event 能力继续扩展时再考虑独立顶层对象。

# event-decision-bridge Specification

## Purpose
定义 event 房间的结构化状态导出与继续、离开、选择选项等动作桥接语义，确保 agent 能在 run 内稳定处理事件界面决策。
## Requirements
### Requirement: event 窗口必须导出结构化状态与正文语义
当玩家进入 run 内 event 房间且界面存在可读事件内容时，bridge MUST 将当前窗口导出为 `snapshot.phase="event"`，并在稳定字段中暴露 event 的标题、正文、选项摘要与窗口诊断。bridge MUST 区分至少三类 event 子窗口：可选项窗口、继续/离开窗口、以及短暂过渡窗口。

#### Scenario: event 选项窗口导出标题、正文与选项
- **WHEN** 当前 run 位于 event 房间，界面可见事件标题、正文和一个或多个可点击选项
- **THEN** `snapshot.phase` MUST 等于 `event`
- **THEN** `snapshot.metadata.window_kind` MUST 标记为 `event_choice` 或等效稳定值
- **THEN** `snapshot.metadata` MUST 提供 `event_title`、`event_body` 与 `event_options`

#### Scenario: event 收尾窗口导出 continue 语义
- **WHEN** 当前事件正文已经结算完毕，只剩“继续/离开/确认”之类的收尾按钮
- **THEN** `snapshot.phase` MUST 仍等于 `event`
- **THEN** `snapshot.metadata.window_kind` MUST 标记为 `event_continue` 或等效稳定值
- **THEN** `snapshot.metadata.event_continue_available` MUST 标记为 true

#### Scenario: event 过渡中保持 fail-safe
- **WHEN** 当前事件界面正在动画切换、按钮树尚未稳定，或 runtime 只能确认处于 event 但暂时拿不到可点击项
- **THEN** bridge MUST 返回可序列化的 `snapshot`
- **THEN** `snapshot.metadata.window_kind` MUST 标记为 `event_transition` 或等效过渡值
- **THEN** bridge MUST NOT 伪造 `choose_event_option` 或 `continue_event` legal actions

### Requirement: event 窗口必须导出稳定 legal actions
当 `snapshot.phase="event"` 时，bridge MUST 基于当前真实可交互控件导出 event 专用 legal actions。对于选项型事件，bridge MUST 使用 `choose_event_option` 绑定当前可见选项索引；对于收尾按钮，bridge MUST 使用 `continue_event` 表示继续推进。若某个选项当前不可点击，bridge MUST 明确降级而不是盲目暴露为可执行动作。

#### Scenario: 每个可点击事件选项生成 choose_event_option
- **WHEN** 当前 event 窗口存在多个可点击选项
- **THEN** `actions` MUST 为每个可点击选项生成一个 `type="choose_event_option"` 的 legal action
- **THEN** 每个 action 的 `params.option_index` MUST 与 `snapshot.metadata.event_options` 的顺序一致
- **THEN** action `label` MUST 使用玩家可读的选项文本或稳定 fallback 文本

#### Scenario: 继续按钮生成 continue_event
- **WHEN** 当前 event 窗口只存在一个“继续/离开/确认”之类的可点击收尾按钮
- **THEN** `actions` MUST 至少包含一个 `type="continue_event"` 的 legal action
- **THEN** 该 action 的 `label` MUST 为当前按钮文本或等效可读文本

#### Scenario: 不可点击选项不得伪装为可执行动作
- **WHEN** 某个事件选项因条件不足、动画中或运行时不可点击而不能真实执行
- **THEN** bridge MUST NOT 将其导出为可执行的 `choose_event_option`
- **THEN** bridge MUST 在 `snapshot.metadata` 或日志中留下对应 diagnostics

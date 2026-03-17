## ADDED Requirements

### Requirement: event 选项必须导出结构化说明与 glossary 词条
当 `snapshot.phase="event"` 且当前窗口为 `event_choice` 时，bridge MUST 为每个 `event_options` 条目导出稳定的结构化说明字段，而不是只返回面向展示的 `label`。该结构 MUST 至少允许调用方读取选项正文说明，以及从选项文本中识别出的关键术语 glossary anchors。对于“锋利”“附魔”或等效 event 词条，bridge MUST 优先复用游戏 runtime hover / localization 的真实说明文本；若当前 runtime 无法提供 hover，bridge MUST 显式降级为空 hint 或缺失 glossary 条目，并在日志中留下缺口诊断，而不是伪造手写说明。

#### Scenario: event 选项包含可 hover 的附魔词条
- **WHEN** 当前 event 选项文本中出现“锋利2”或等效可在游戏内 hover 查看说明的术语
- **THEN** 对应 `event_options` 条目 MUST 导出该术语的 glossary anchor
- **THEN** glossary `hint` MUST 优先使用游戏 runtime / localization 中的真实说明文本

#### Scenario: event 选项为模型提供独立于 label 的说明字段
- **WHEN** 外部 agent 读取 `snapshot.metadata.event_options`
- **THEN** 每个 option MUST 提供可直接消费的结构化说明字段，例如 `description` 或等效稳定字段
- **THEN** 调用方 MUST 不需要自行从多行 `label` 中拆分正文与词条

#### Scenario: event 词条缺少 hover 时安全降级
- **WHEN** 某个 event 选项中的高亮术语当前无法从 runtime 读取到真实 hover 说明
- **THEN** bridge MUST 返回空 `hint`、缺失 glossary 或等效安全降级结果
- **THEN** bridge MUST 在日志中记录该术语、事件上下文与缺失原因

### Requirement: event 选项 glossary 语义必须在 snapshot 与 legal actions 中保持一致
当 bridge 为 event 窗口导出 `choose_event_option` legal actions 时，action metadata MUST 与 `snapshot.metadata.event_options` 复用同一套 option 说明语义。若某个选项在 snapshot 中已经解析出 glossary anchors、说明文本或关键词，bridge MUST 在对应 action metadata 中导出一致的字段含义，避免调用方在展示层和执行层读到冲突信息。

#### Scenario: choose_event_option 复用相同 option 说明结构
- **WHEN** bridge 为当前 event 选项生成 `choose_event_option` legal action
- **THEN** 该 action metadata MUST 包含与对应 `event_options` 一致的说明字段与 glossary 信息
- **THEN** 调用方 MUST 能仅依赖 action metadata 或 snapshot 任一来源理解该选项语义

#### Scenario: snapshot 与 actions 不得对同一词条给出冲突 hint
- **WHEN** 某个 event 选项 glossary 已在 snapshot 中解析出真实 hint
- **THEN** 对应 `choose_event_option` metadata MUST 复用同一 hint 或等价文本
- **THEN** bridge MUST NOT 出现 snapshot 已有真实说明、但 action metadata 回退为空或不同手写说明的冲突状态

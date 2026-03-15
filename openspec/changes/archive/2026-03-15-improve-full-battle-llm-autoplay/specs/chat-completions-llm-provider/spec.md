## ADDED Requirements

### Requirement: chat-completions provider 必须支持 battle 级上下文输入
provider MUST 能将 battle-scoped context 编码进模型输入，至少覆盖最近动作、最近 bridge 回执、当前回合索引、累计动作数、等待态 / recovery 态，以及额外选牌窗口语义。该上下文 MUST 与当前 `snapshot`、`legal actions` 一起发送，帮助模型理解“当前这一手是在什么 battle 语义下做的”。

#### Scenario: 使用 battle summary 构造模型请求
- **WHEN** runner 在 battle 中请求 provider 做一次新决策
- **THEN** 请求消息 MUST 同时包含当前 observation 与 battle 级摘要
- **THEN** battle 级摘要 MUST 不要求调用方手工拼接自由文本

### Requirement: chat-completions provider 必须解析更稳定的结构化决策字段
provider MUST 要求模型返回至少 `action_id`、`target_id`、`reason`、`halt` 与 `confidence` 字段；其中无目标动作时 `target_id` MAY 为空。若模型返回缺失结构字段或字段类型不合法，provider MUST 将其视为解析失败，而不是隐式猜测补齐。

#### Scenario: targeted action 返回显式 target_id
- **WHEN** 当前 legal set 中的候选动作需要目标
- **THEN** provider MUST 期待模型显式返回 `target_id`
- **THEN** 上层 MUST 能据此判断模型是否真的理解了目标选择，而不是只返回模糊动作意图

#### Scenario: confidence 字段缺失时视为无效输出
- **WHEN** 模型返回 JSON，但缺少 `confidence` 或该字段类型错误
- **THEN** provider MUST 返回结构化 parse error
- **THEN** 上层 MUST NOT 直接把该响应当成有效动作提交给 bridge

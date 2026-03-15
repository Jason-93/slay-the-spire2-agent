# chat-completions-llm-provider Specification

## Purpose
定义 Python 侧对 OpenAI 兼容 `chat/completions` 接口的模型接入约束，确保 STS2 agent 可以稳定请求本地或远程大模型，并把响应解析为可执行的结构化动作决策。
## Requirements
### Requirement: chat-completions provider 必须支持 OpenAI 兼容接口配置
系统 MUST 提供一个可配置的 `chat-completions-llm-provider`，能够向 OpenAI 兼容的 `POST /v1/chat/completions` 端点发送非流式请求。provider MUST 支持至少以下配置项：`base_url`、`model`、`api_key`、`timeout_seconds`、`temperature` 与 `max_tokens`，并允许 `api_key` 为空以兼容本地调试服务。

#### Scenario: 使用本地兼容接口发起请求
- **WHEN** 调用方将 `base_url` 配置为 `http://127.0.0.1:8080/v1` 且提供有效 `model`
- **THEN** provider MUST 向 `http://127.0.0.1:8080/v1/chat/completions` 发起请求
- **THEN** 请求体 MUST 包含 `model` 与 `messages`

#### Scenario: 未配置 api_key 也能兼容本地服务
- **WHEN** 调用方未提供 `api_key`
- **THEN** provider MUST 仍可构造请求
- **THEN** provider MUST NOT 因缺少 `Authorization` 头而在本地校验阶段直接失败

### Requirement: chat-completions provider 必须返回结构化动作决策
provider MUST 将当前决策上下文编码为模型输入，并要求模型输出一个可解析的 JSON 结果。解析后的最小结果 MUST 包含 `action_id`、`reason` 与 `halt` 字段；当模型选择放弃执行时，provider MUST 允许 `halt=true` 且 `action_id=null`。

#### Scenario: 模型返回合法 JSON 决策
- **WHEN** 模型响应正文包含可解析 JSON，且带有 `action_id`、`reason`、`halt`
- **THEN** provider MUST 产出可供 `Policy` 使用的结构化决策对象
- **THEN** 决策对象 MUST 保留原始文本或解析元数据，便于 trace 落盘

#### Scenario: 模型明确要求停止
- **WHEN** 模型返回 `{"action_id": null, "reason": "...", "halt": true}`
- **THEN** provider MUST 将该结果解释为中止当前自动打牌步骤
- **THEN** 上层 orchestrator MUST 能据此安全停止，而不是继续猜测动作

### Requirement: chat-completions provider 必须对响应异常给出可诊断错误
当网络请求失败、响应超时、响应结构缺失或 JSON 无法解析时，provider MUST 返回明确的错误状态或抛出带错误码的异常，供上层决定重试或中断。provider MUST NOT 在无法确认动作的情况下返回伪造的 `action_id`。

#### Scenario: HTTP 请求超时
- **WHEN** chat completions 请求在 `timeout_seconds` 内未完成
- **THEN** provider MUST 返回或抛出明确的 timeout 错误
- **THEN** 错误信息 MUST 能被 trace 记录为模型侧失败原因

#### Scenario: 响应不是可解析 JSON
- **WHEN** provider 从 `choices[0].message.content` 读取到的文本不是合法 JSON
- **THEN** provider MUST 返回或抛出 parse error
- **THEN** 上层 MUST NOT 继续提交任何动作到 bridge

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


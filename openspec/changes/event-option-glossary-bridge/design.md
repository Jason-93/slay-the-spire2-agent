## Context

当前 event bridge 已能导出标题、正文和选项文本，但 `event_options` 基本仍是面向 UI 的 `label` 拼接结果。像“选择一张攻击牌附魔：锋利2”这类选项，模型只能看到“锋利2”字样，却拿不到游戏 hover 中对应的真实说明，因此很难比较收益与风险。

仓库里已经为 cards、relics、potions、enemies 建立了 glossary / description 提取路径，并且约束了“优先取 runtime 原文、缺失时记录日志而不是伪造说明”的方向。event 选项适合复用这套模式，但它的文本来源更分散：既可能来自按钮文案，也可能来自按钮内部高亮词条或 hover tip。

## Goals / Non-Goals

**Goals:**
- 让 `event_options` 为模型提供可直接消费的结构化说明，而不只是一段多行 `label`
- 为 event 选项中的关键术语导出 glossary anchors 与 hover hint，优先复用游戏 runtime 真实文本
- 让 `snapshot.metadata.event_options` 与 `choose_event_option` action metadata 使用一致的 option 说明语义
- 缺少 hover 时保留可观测日志，避免对外暴露伪造的词条说明

**Non-Goals:**
- 不在这次变更中扩展所有 event 全量百科或剧情知识库
- 不修改 event 基础动作类型，仍沿用 `choose_event_option` / `continue_event`
- 不要求为每个 event 选项都生成复杂 card preview；本次仅补齐 option 自身可解释文本与 glossary

## Decisions

### 1. 扩展 event option 公共 schema，而不是让调用方从 `label` 二次解析

为 `snapshot.metadata.event_options[]` 增加面向 agent 的结构化字段，例如 `description`、`glossary`、`keywords` 或等效稳定字段，并让 `choose_event_option` metadata 复用同一语义。这样模型读取 event 决策时不必自己拆分 `label` 中的换行、高亮和词条。

备选方案是继续只暴露 `label`，由 Python 客户端或模型提示词自己解析“锋利2”等词条；但这会把游戏语义提取逻辑分散到客户端，且无法拿到 hover 原文，因此不采用。

### 2. 复用 runtime hover / localization 提取链路，优先取游戏真实词条说明

实现上优先从 event option 关联的 tooltip / hover 数据中提取标题与说明；若 event 选项引用了已有 glossary term，则直接复用现有 glossary 规范。只有在 runtime 明确拿不到 hover 时才降级为空 hint，并记录日志说明缺口来源。

备选方案是维护一份 event 词条手写表，但这会再次引入语言漂移和重复维护成本，因此仅保留日志告警，不把手写说明作为默认对外协议。

### 3. 保持向后兼容：保留 `label`，新增字段全部追加

现有调用方已经依赖 `label` 直接展示 event 选项，因此这次变更不替换旧字段，而是在 option 对象与 action metadata 中追加结构化说明字段。老客户端仍可继续工作，新客户端与模型可以逐步切换到更可靠的字段。

## Risks / Trade-offs

- [不同 event 的 tooltip 来源不一致] -> 先统一抽象成“option glossary extraction”流程，对识别失败的分支输出诊断日志，避免静默丢失
- [部分词条只有按钮高亮、没有可读 hover] -> 对外返回空 `hint` 或空 glossary，并在日志中标记 missing runtime hint
- [option metadata 与 action metadata 不一致] -> 复用同一个 option DTO 组装路径，避免 snapshot 与 actions 各自拼装
- [字段追加后 JSON 体积增大] -> 仅为当前 event 可见选项导出必要字段，不引入额外百科载荷

## Context

当前 bridge 已经能够在部分 live runtime 场景中导出说明质量字段，但整体职责边界仍不够清晰：mod 端负责一部分真实值提取，Python 端仍保留模板识别、兼容摘要与局部兜底。同时协议里还存在 `description`、`description_rendered`、`description_raw` 等重叠字段，增加了消费方理解成本。

这次变更的核心不是简单“把字符串替换搬家”，而是把说明解析收敛为 mod 端的稳定能力，并顺手清理协议冗余：runtime bridge 直接面向游戏对象、LocString 和动态变量，输出最终说明与必要诊断；客户端只消费这些结果，不再做历史兼容。

## Goals / Non-Goals

**Goals:**
- 明确 mod 端是说明解析的唯一主责任方，客户端不再承担核心 description render 逻辑。
- 收敛卡牌、powers 及后续可扩展实体的说明字段语义，保留一个 canonical `description` 字段和必要 diagnostics。
- 为解析失败、模板残留、版本差异提供服务端 diagnostics，保证 agent 侧仍能安全消费。
- 让 live validation 与 policy 摘要能够验证“服务端已解析”与“仅模板回退”的区别。

**Non-Goals:**
- 本次不构建完整的怪物机制百科或长期牌库规划知识库。
- 本次不承诺一次覆盖所有游戏对象的完整说明链路，优先覆盖高频决策实体。
- 本次不保证对旧协议做向后兼容；允许直接调整字段定义。

## Decisions

### 决策一：以 mod runtime 为 description truth source
由 `Sts2RuntimeReflectionReader` 统一负责真实描述解析。优先读取 runtime 已存在的 rendered 文本；若 runtime 仅提供模板，则在 mod 端结合 `LocString.Variables`、`DynamicVars`、显式数值字段完成替换并导出结果。

备选方案是继续允许 Python 侧根据 `description_vars` 做二次渲染，但这会让不同客户端重复实现模板规则，并放大多语言与富文本差异，因此不选。

### 决策二：使用单一 canonical `description` 字段，对外移除重复说明字段
对外协议以 `description` 作为最终、可直接消费的说明文本；`description_rendered` 这类重复字段从公共 schema 中移除。若需要诊断模板来源或解析路径，统一通过 `description_quality`、`description_source`、`description_vars` 和 metadata 承载，而不是再保留一套平行文本字段。

备选方案是继续同时保留 `description`、`description_rendered`、`description_raw`，但这会让客户端持续依赖历史语义，因此不选。

同时，对外 `description` 中的 glossary 高亮统一转换为 Markdown 风格的 `**词条**`。这样 agent、调试脚本和日志文件都能直接消费，不必理解游戏内部 `[gold]...[/gold]`、`[blue]...[/blue]` 等富文本标签。

### 决策三：客户端仅做严格消费，不保留历史兼容读取
Python bridge / policy 按新的 mod 协议直接读取 `description` 与 diagnostics，不再保留 `description_rendered` / `description_raw` 的兼容拼接逻辑。若服务端未给出所需字段，直接视为 bridge 缺陷并通过测试暴露。

## Risks / Trade-offs

- [运行时反射路径继续变化] -> 将解析逻辑拆成“runtime rendered / loc string / numeric members / diagnostics”多层回退，并补充 live artifacts。
- [mod 端职责变重] -> 通过统一字段语义减少多个客户端重复实现，总体维护成本更低。
- [不同实体的 description 容器不一致] -> 先抽象通用解析管线，再逐步接入 relics、potions 等实体。
- [直接删掉兼容字段会带来一次性改动面] -> 同步更新 contracts、fixtures、Python bridge 与 tests，在同一 change 内完成切换。

## 1. Schema 与 fixture 对齐

- [x] 1.1 更新 C# contracts、Python models 与 decode 逻辑，把 `snapshot.player.relics` 从字符串数组升级为结构化 relic 对象列表
- [x] 1.2 更新 fixture provider 与相关测试数据，为 relic 补充 `name`、`description`、`canonical_relic_id` 或等效字段
- [x] 1.3 检查 policy / runner /摘要逻辑中对 relic 字符串数组的假设，并切换到新 schema

## 2. Runtime relic 提取

- [x] 2.1 在 `Sts2RuntimeReflectionReader` 中新增结构化 relic 提取逻辑，替换当前 `ExtractLabels(...player.relics...)` 的纯字符串导出
- [x] 2.2 优先从 relic 模型、hover tip、`Description`、`SmartDescription`、localization 等 runtime 来源解析 canonical `description`
- [x] 2.3 为无法稳定解析 description 的 relic 保留 fail-safe 降级与日志 diagnostics，同时避免公开排障字段泄漏到客户端

## 3. 验证

- [x] 3.1 补充 Python / fixture 回归测试，确认 `snapshot.player.relics` 已变为结构化对象且 description 语义稳定
- [x] 3.2 补充 live validation 或现有验证脚本断言，检查 relic name / description 在真实 runtime 中可读
- [x] 3.3 用一次真实 STS2 运行时联调验证常见 relic（如 `燃烧之血`）能够导出 description，并记录 artifacts

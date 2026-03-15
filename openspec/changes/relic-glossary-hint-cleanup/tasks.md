## 1. relic glossary 提取清理

- [ ] 1.1 在 `Sts2RuntimeReflectionReader` 的 relic 提取路径中增加 glossary post-process，过滤与 relic 自身说明重复的 glossary 项
- [ ] 1.2 调整 relic glossary hint 的质量判定，过滤 `hint` 为空、`missing_hint`、模板残留或等效低价值 fallback 条目
- [ ] 1.3 为被过滤的 relic glossary 项补充日志 / diagnostics，便于定位是重复过滤、空 hint 还是模板 fallback

## 2. 真实 hint sourcing 与回归验证

- [ ] 2.1 优化 relic 二级 glossary（如 `格挡`、`升级`、`遗物`）的真实 hint sourcing，优先使用 hover tip、模型说明或 localization 的已渲染文本
- [ ] 2.2 更新 fixture / Python / validation 断言，确认 `snapshot.player.relics[].glossary` 不再暴露重复、空 hint 或模板化条目
- [ ] 2.3 用一次真实 STS2 runtime 联调验证 `永冻冰晶`、`燃烧之血` 等 relic 的 glossary 已去重且 hint 质量稳定，并记录 artifacts

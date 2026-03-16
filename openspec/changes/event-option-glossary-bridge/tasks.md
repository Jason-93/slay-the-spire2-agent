## 1. Event 选项说明提取

- [ ] 1.1 梳理 `mod/Sts2Mod.StateBridge/` 中 event option 现有文本来源，定位按钮文案、高亮词条与 hover / tooltip 的可读入口
- [ ] 1.2 为 event option 增加统一的结构化说明 DTO，至少覆盖 `description`、`glossary` 与稳定关键词字段，并保留现有 `label`
- [ ] 1.3 实现 event option glossary 提取逻辑，优先复用 runtime hover / localization 文本，缺失时输出日志诊断而不是伪造 hint

## 2. Bridge 导出一致性

- [ ] 2.1 将新的 option 说明结构接入 `snapshot.metadata.event_options` 导出路径
- [ ] 2.2 将同一结构复用到 `choose_event_option` legal action metadata，确保 snapshot 与 actions 对同一 option 语义一致
- [ ] 2.3 针对“锋利2”或等效带附魔词条的 event 选项补充可复现样例或调试夹具，验证对外 JSON 不再只剩纯文本 label

## 3. 验证与回归

- [ ] 3.1 增加或更新 event bridge 相关测试，覆盖 glossary 成功提取、缺失 hover 安全降级、snapshot/actions 一致性
- [ ] 3.2 运行 OpenSpec 校验与相关本地验证脚本，确认新增字段不会破坏现有 event 决策流程
- [ ] 3.3 补充必要文档或调试说明，说明 event option glossary 字段的读取方式与日志定位方法

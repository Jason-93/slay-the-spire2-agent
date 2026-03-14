## 1. 服务端说明解析职责收敛

- [ ] 1.1 盘点当前 cards、powers、relics、potions 的 description 导出路径，标记哪些仍依赖客户端侧模板识别或补渲染。
- [ ] 1.2 重构 `Sts2RuntimeReflectionReader` 的说明解析入口，统一由 mod 端输出 canonical `description`、`description_quality`、`description_source` 与 `description_vars`。
- [ ] 1.3 删除公共 schema 中重复或历史兼容的说明字段，把 glossary 富文本统一规范为 `**词条**`，并为无法完全解析的实体补充一致的 `template_fallback` / `partial` diagnostics。

## 2. 快照与动作协议统一

- [ ] 2.1 更新 contracts、window extractors 与 fixture provider，确保 snapshot 与 action preview 共享同一套说明字段语义。
- [ ] 2.2 为 powers 之外的后续可扩展实体预留统一说明导出入口，避免每类对象单独实现质量字段协议。
- [ ] 2.3 校正 Python bridge / policy 的消费逻辑，移除客户端 description render 与历史兼容读取分支，改为严格消费新的 mod 协议。

## 3. 验证与联调

- [ ] 3.1 补充 mod 单元测试，覆盖“runtime 已解析”“mod 端补解析”“模板回退”三类说明结果。
- [ ] 3.2 补充 Python 侧测试，确认 agent 摘要直接消费 canonical `description` 与 diagnostics，并在缺少旧字段时仍正常工作。
- [ ] 3.3 运行 fixture、`validate_mod_bridge.py` 与至少一次真实 STS2 live validation，记录 artifacts 证明说明解析完全由 mod 端负责且公共 schema 已完成收敛。

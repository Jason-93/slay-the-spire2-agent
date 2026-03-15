## 1. potion 文本提取与过滤

- [x] 1.1 在 `Sts2RuntimeReflectionReader` 的药水提取路径中梳理 canonical `description` sourcing，避免将模板化 hover tip 直接作为最终药水说明返回。
- [x] 1.2 为 potion glossary 增加 post-process 过滤，去掉空 hint、`missing_hint`、模板占位残留、与药水自身名称或自身说明重复的条目。
- [x] 1.3 为被过滤或降级的 potion glossary 条目补充日志诊断，记录药水标识、对象路径、来源与过滤原因。

## 2. bridge 契约与验证收口

- [x] 2.1 更新相关 contracts / fixtures / snapshot 断言，确认 `snapshot.player.potions[].glossary` 只保留高质量术语说明。
- [x] 2.2 扩展 `tools/validate_live_apply.py` 与对应测试，新增 potion glossary 的质量审计与失败原因输出。
- [x] 2.3 补充或更新 Python / C# 测试，覆盖“模板化药水说明回退”“identity glossary 去重”“低质量 hint 过滤后仍保持 snapshot 可用”。

## 3. 联调与回归验证

- [x] 3.1 运行 `dotnet build mod/Sts2Mod.StateBridge.sln`、`$env:PYTHONPATH='src'; python -m unittest discover -s tests -v`，确认文本清理未破坏现有 bridge 行为。
- [x] 3.2 用真实 STS2 runtime 对包含 `肌肉药水` 或等效动态描述药水的快照做一次 live 验证，确认不再暴露模板化 potion glossary。
- [x] 3.3 记录本次 live validation artifacts（`tmp/live-apply-validation/20260315-141009`、`tmp/sts2-debug/sts2-runtime-1773554954.log`），便于后续 archive。

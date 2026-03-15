## 1. enemy 文本规范化与去噪

- [ ] 1.1 在 `Sts2RuntimeReflectionReader` 的 enemy 导出路径中清理 `intent` / `intent_raw` / `move_name` / `move_description` 的富文本残留与展示性 markup。
- [ ] 1.2 增加 `move_name` 去重/抑制逻辑，避免仅重复数值意图、通用 intent 标签或纯 UI 展示文本继续暴露给客户端。
- [ ] 1.3 调整 enemy `keywords` / `traits` / `move_glossary` 的提取与过滤，去掉 `POWER.*`、类型名、canonical id 或等效内部 token。
- [ ] 1.4 为 `enemy.powers[].glossary` 增加 post-process 过滤，去掉与 power 本体名称/说明重复、空 hint、`missing_hint` 与模板残留条目。

## 2. 契约收口与测试覆盖

- [ ] 2.1 更新 fixture、contracts 导出断言与 C# tests，覆盖“多段攻击富文本 intent 规范化”“重复 move_name 抑制”“内部 keyword 过滤”“enemy power glossary 去重”。
- [ ] 2.2 扩展 `tools/validate_live_apply.py` 与 Python tests，新增 enemy richer fields 与 enemy power glossary 的质量审计与失败原因输出。
- [ ] 2.3 为被过滤或降级的 enemy 字段补充日志 / diagnostics，记录 enemy 标识、字段路径、来源与过滤原因。

## 3. 验证与联调

- [ ] 3.1 运行 `dotnet build mod/Sts2Mod.StateBridge.sln`、`dotnet test mod\\Sts2Mod.StateBridge.Tests\\Sts2Mod.StateBridge.Tests.csproj --no-restore`、`$env:PYTHONPATH='src'; python -m unittest discover -s tests -v`，确认 enemy 文本清理未破坏现有 bridge 行为。
- [ ] 3.2 用真实 STS2 runtime 对 `墨宝`、`蛇行扼杀者` 或等效敌人做一次 live 验证，确认不再暴露富文本 `intent`、重复 `move_name` 和内部 `keywords`。
- [ ] 3.3 记录本次 live validation artifacts 与典型 enemy 快照，便于后续 archive 与回归对比。

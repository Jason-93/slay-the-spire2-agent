## 1. 契约与 schema 调整

- [x] 1.1 在 C# runtime contracts 与 Python models 中新增 `PotionView`（或等效对象），并将 `player.potions` 升级为结构化列表。
- [x] 1.2 在玩家状态中补充 `potion_capacity` 字段，并同步更新 JSON decode / encode / fixture schema。
- [x] 1.3 调整 `use_potion` legal action metadata，使其能稳定关联对应药水对象或预览信息。

## 2. mod runtime 药水提取

- [x] 2.1 在 `Sts2RuntimeReflectionReader` 中补齐 live runtime 药水读取路径，稳定提取药水名称、说明、知识锚点与 glossary。
- [x] 2.2 补齐药水栏容量读取逻辑，并在读取失败时提供稳定 fallback，而不影响整份快照构建。
- [x] 2.3 将结构化药水信息接入 `snapshot.player` 与 `use_potion` action metadata 导出。

## 3. Python 消费与策略摘要

- [x] 3.1 更新 Python bridge / client / dataclass 解析，兼容新的结构化药水对象与 `potion_capacity`。
- [x] 3.2 更新 LLM snapshot summary / trace 输出，让大模型能直接看到药水说明与药水栏上限。
- [x] 3.3 如有基于旧 `list[str]` 的调用点，统一迁移到新 potion schema，避免隐式类型错误。

## 4. 测试与验证

- [x] 4.1 更新或新增 C# 单元测试，覆盖“药水对象导出”“说明缺失时保守降级”“药水栏容量导出”。
- [x] 4.2 更新 Python 单元测试与 fixtures，覆盖结构化药水 decode、policy summary 与 `use_potion` metadata。
- [x] 4.3 运行 `dotnet test mod\\Sts2Mod.StateBridge.Tests\\Sts2Mod.StateBridge.Tests.csproj --no-restore`、`$env:PYTHONPATH='src'; python -m unittest discover -s tests -v`，并记录 live/fixture 验证结果。

## 1. 最终描述解析链路

- [x] 1.1 梳理 `Sts2RuntimeReflectionReader` 当前 cards description 的读取顺序，明确 `GetDescriptionForPile(...)`、`GetDescriptionForUpgradePreview()` 与现有 `RenderedDescription` / 模板 fallback 的接入点
- [x] 1.2 实现统一的 card description resolver，优先调用游戏最终描述 API，并在内部记录 source、context 与 fallback 阶段
- [x] 1.3 为 hand、draw、discard、exhaust 与 preview 定义稳定的 description context / `PileType` 映射，并补齐安全回退

## 2. 导出路径整合

- [x] 2.1 将 `snapshot.player.hand[]` 的 `description` 切换到新的 canonical resolver
- [x] 2.2 将 `draw_pile_cards`、`discard_pile_cards`、`exhaust_pile_cards` 与 `actions[].metadata.card_preview` 统一切换到同一条 resolver 链路
- [x] 2.3 确保公共 schema 继续只暴露单个 `description`，把解析质量、来源与变量等诊断信息留在日志或内部 diagnostics

## 3. 回归测试与 live 验证

- [x] 3.1 补充 `TRUE_GRIT`、升级预览与条件模板残留的回归测试，确认对外 description 不再暴露 `IfUpgraded` 等 DSL
- [x] 3.2 补充 hand / piles / `card_preview` 一致性与 fallback 行为测试，确认最终描述 API 不可用时仍可稳定返回
- [x] 3.3 在真实 STS2 运行时执行一次 live 验证，确认 snapshot / actions 优先输出游戏最终 description，并通过日志可定位 fallback 原因

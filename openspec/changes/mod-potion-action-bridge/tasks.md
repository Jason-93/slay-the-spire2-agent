## 1. mod 端药水动作执行

- [ ] 1.1 在 `Sts2RuntimeReflectionReader.ExecuteAction(...)` 中接入 `use_potion` 分支，并新增独立的 `ExecuteUsePotion(...)` 运行时处理路径。
- [ ] 1.2 基于 `potion_index`、`canonical_potion_id` 与当前 live 药水栏实现药水实例重定位与一致性校验，返回结构化 `stale_action` / `invalid_action` / `target_required` 等失败语义。
- [ ] 1.3 为药水执行补充 queue-stage、`runtime_handler`、槽位索引与失败阶段 diagnostics，确保真实执行与失败路径都可复盘。

## 2. fixture 与 live 验证

- [ ] 2.1 更新 fixture provider 或相关测试支撑，使 `use_potion` 不再停留在 `unsupported_action`，并补充药水动作成功/失败回执覆盖。
- [ ] 2.2 扩展 `tools/validate_live_apply.py` 或新增药水专项验证脚本，记录药水执行前后 `player.potions[]`、apply 请求/回执与推进证据 artifacts。
- [ ] 2.3 在真实游戏进程中完成至少一次 `use_potion` live 冒烟，确认药水动作被接受且状态发生可观察推进。

## 3. Python 侧联动收尾

- [ ] 3.1 在确认 mod 端支持后，移除或放宽当前 runner 对 `use_potion` 的保守过滤，并补充相应单元测试。
- [ ] 3.2 更新 `README.md` / `README.zh.md` 或 `docs/`，说明当前药水动作支持范围、已知限制与 live 调试方式。

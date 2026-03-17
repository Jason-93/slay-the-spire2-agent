## 1. 收敛商店 snapshot 协议

- [ ] 1.1 梳理当前 `shop_offers`、嵌套 preview 与离店字段的实际导出结构，明确需要保留和删除的公共字段
- [ ] 1.2 调整 mod 侧商店 contract / provider，把 `snapshot.metadata.shop_offers[]` 收敛为统一 canonical offer 结构，并补齐 `purchasable` 与 `unavailable_reason` 语义
- [ ] 1.3 规范商店公共文本字段，移除 `BackButton` 等底层 UI 命名在用户向 schema 中的直接暴露

## 2. 收敛商店 action 协议与执行锚点

- [ ] 2.1 调整商店 legal actions 的 `params` 与 metadata，只保留 `offer_id`、价格、类型等执行锚点和最小上下文
- [ ] 2.2 更新 `/apply` 的商店目标重定位与校验逻辑，确保轻量动作协议下仍能安全拒绝 stale / drift 场景
- [ ] 2.3 同步更新 Python bridge 消费层、fixture 解析与任何依赖旧 preview 结构的策略代码

## 3. 验证与文档同步

- [ ] 3.1 更新商店相关测试、fixture 与校验脚本，覆盖 canonical offer、不可购买原因、离店动作标签与轻量 metadata
- [ ] 3.2 运行商店相关验证（至少包括 Python 单测、bridge 校验与一次 live shop smoke test），确认 snapshot / actions 新结构可用
- [ ] 3.3 补充 README / docs / OpenSpec 说明，记录商店 canonical 结构与动作读取约定

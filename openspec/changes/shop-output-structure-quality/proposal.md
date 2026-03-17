## Why

当前商店 bridge 已经能导出 `phase=shop`、商品列表与真实购买动作，但对外 JSON 结构仍然存在质量问题：同一商品信息在 `shop_offers`、action metadata、嵌套 preview 中重复出现，部分字段命名与其他 phase 不完全一致，还夹带调试导向或 UI 导向的值，增加了 agent / LLM 的消费复杂度。随着商店已经进入 live 自动流程，当前最需要的是把商店协议收敛成更稳定、精简、可扩展的输出结构，而不是继续在客户端做额外兜底。 

## What Changes

- 收敛 shop snapshot 的公共输出结构，减少重复嵌套字段，明确哪些字段是对外契约、哪些仅保留在日志中。
- 统一 shop offer 在 `snapshot.metadata.shop_offers` 与 legal action metadata 中的语义，避免同一商品在不同位置出现不一致或过度重复的结构。
- 规范商店动作参数与元数据，只保留执行锚点和决策必需信息，移除对客户端无价值的冗余展示字段。
- 为商店服务项、不可购买原因、离店动作等边界情况定义更清晰的结构约束，提升后续 LLM 与调试工具的可读性。

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `mod-state-export`: 调整 shop snapshot 中 `shop_offers` 的公共导出契约，要求更精简且语义一致。
- `shop-decision-bridge`: 调整商店 legal actions 与 `/apply` 相关元数据结构，减少重复字段并固定动作锚点语义。

## Impact

- 受影响代码主要在 `mod/Sts2Mod.StateBridge/Providers/`、`mod/Sts2Mod.StateBridge/Contracts/`、`src/sts2_agent/bridge/`、`src/sts2_agent/policy/`、`tools/` 与 `tests/`。
- 对外协议会修改 shop offer / action metadata 的字段组织方式，调用方需要跟随新的精简结构读取商店信息。
- 相关文档、fixture 校验与 live 验证脚本需要同步更新，确保商店场景的输出质量可以稳定回归。

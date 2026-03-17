## Why

当前 bridge 已能覆盖 combat、reward、map、event 等关键窗口，但在商店场景里仍缺少结构化状态与可执行动作，导致 autoplay 一旦进入商店就只能停下或依赖人工接管。随着 live 自动推进已经能够稳定跑到商店前后，补齐 shop 场景已成为继续打通整局流程与提升 LLM 决策质量的必要缺口。

## What Changes

- 为 mod 增加 shop 场景识别，导出商店窗口的结构化 snapshot 与合法 actions。
- 为 shop 商品、移牌服务与离开商店动作定义统一的公共协议，供外部 agent / LLM 直接消费。
- 让 `/apply` 支持商店内购买、移除卡牌、跳过/离开等真实动作，并保持 stale-action 与窗口漂移校验。
- 扩展 autoplay orchestrator，使其能够在 shop phase 中等待稳定窗口、调用 policy、执行安全默认策略或显式 halt。
- 为 live 调试与验证脚本补充 shop 相关 fixture / smoke validation，便于后续整局自动化回归。

## Capabilities

### New Capabilities
- `shop-decision-bridge`: 定义 shop 场景的状态导出、合法动作与可执行控制协议。

### Modified Capabilities
- `mod-state-export`: 将统一状态快照覆盖范围扩展到 `shop` phase，并补充商店窗口元数据与商品信息。
- `autoplay-orchestrator`: 扩展 orchestrator 对 shop phase 的稳定窗口等待、策略调用与自动推进语义。

## Impact

- 受影响代码主要位于 `mod/Sts2Mod.StateBridge/Providers/`、`mod/Sts2Mod.StateBridge/Extraction/`、`src/sts2_agent/orchestrator.py`、`src/sts2_agent/policy/llm.py`、`tools/` 与 `tests/`。
- 外部协议会新增 `shop` 相关 snapshot metadata、商品/服务结构以及对应 action types。
- live autoplay、验证脚本与后续整局 LLM 实跑将能覆盖商店这一关键非战斗场景。

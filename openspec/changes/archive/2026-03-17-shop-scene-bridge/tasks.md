## 1. Shop 状态导出

- [x] 1.1 在 mod runtime reader 中识别商店主窗口，导出 `phase=shop` 与稳定的 `window_kind` / detection metadata
- [x] 1.2 设计并实现 shop offers 的公共结构，覆盖卡牌、遗物、药水与移牌服务的名称、价格、类别、可购买性与说明文本
- [x] 1.3 为 fixture provider 增加 shop snapshot 场景，覆盖可购买、金币不足、药水栏已满与离开商店等情况

## 2. Shop 动作与 apply

- [x] 2.1 在 legal actions 中新增商店动作类型：购买卡牌、购买遗物、购买药水、移除卡牌、离开商店
- [x] 2.2 为商店动作建立稳定锚点与执行前校验，处理索引漂移、目标消失、金币不足与服务失效
- [x] 2.3 在 `/apply` 执行链路中接入真实 shop action，并补充成功 / stale / not_affordable 等返回语义

## 3. Autoplay 与策略集成

- [x] 3.1 为 orchestrator 增加 `shop_mode` 配置，并支持 `halt`、`safe-default`、`llm`
- [x] 3.2 将 shop phase 纳入稳定窗口等待、trace、reject recovery 与 step kind 分类逻辑
- [x] 3.3 扩展 LLM policy 的 snapshot / action 摘要，让模型可基于 shop offers 与玩家金币做决策

## 4. 验证与文档

- [x] 4.1 为 Python 单测补充 shop snapshot、shop actions、shop_mode 与 reject recovery 覆盖
- [x] 4.2 增加 shop live/fixture 验证脚本或扩展现有验证脚本，覆盖购买、离开与窗口漂移
- [x] 4.3 更新 README / docs 中的 shop 场景说明、调试命令与 autoplay 使用方式

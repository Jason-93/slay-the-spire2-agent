## ADDED Requirements

### Requirement: Shop bridge MUST 导出可执行的商店动作集合
系统 MUST 在商店主窗口导出与当前商店状态一致的合法动作集合，至少覆盖购买卡牌、购买遗物、购买药水、移除卡牌（若可用）以及离开商店。每个动作 MUST 带有稳定的 `action_id`、动作 `type`、目标标识与必要参数，供外部 agent 直接执行。

#### Scenario: 商店主窗口存在多个可购买对象
- **WHEN** 玩家进入可交互的商店主界面，且当前存在卡牌、遗物、药水或服务项
- **THEN** bridge MUST 返回对应的 shop legal actions，而不是把商店退化成空动作窗口
- **THEN** 每个购买动作 MUST 能区分其购买对象类型与目标标识

#### Scenario: 离开商店始终作为合法动作暴露
- **WHEN** 玩家位于可离开的商店窗口
- **THEN** bridge MUST 导出 `leave_shop` 或等效离开动作
- **THEN** 外部调用方 MUST 不需要通过伪造 map/event 动作才能离开商店

### Requirement: Shop bridge MUST 为 `/apply` 提供安全的商店动作执行语义
系统 MUST 支持通过 `/apply` 执行商店动作，并在执行前重新解析当前商店窗口，校验目标商品、服务或离开按钮仍与原始动作匹配。若窗口已变化、目标已售出、金币不足或服务不可用，bridge MUST 返回明确拒绝，而不是执行错误购买。

#### Scenario: 合法购买动作被接受
- **WHEN** 外部调用方提交当前商店窗口中的一个合法购买动作，且玩家仍满足金币与容量约束
- **THEN** `/apply` MUST 接受该动作并触发真实购买
- **THEN** 后续 snapshot MUST 反映金币、商品可见性或库存状态的变化

#### Scenario: 购买前商店窗口已经漂移
- **WHEN** 外部调用方提交的商店动作所对应目标已在当前窗口中消失、变价或索引漂移
- **THEN** bridge MUST 返回 `stale_action`、`selection_window_changed` 或等效拒绝结果
- **THEN** bridge MUST NOT 把该旧动作误执行到新的商店目标上


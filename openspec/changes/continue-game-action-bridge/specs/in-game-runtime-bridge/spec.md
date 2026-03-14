## ADDED Requirements

### Requirement: 继续/确认按钮必须导出 continue_game legal action
当当前窗口存在明确的“继续/前进/确认（Proceed/Continue/OK）”类按钮，并且该按钮用于推进 run 的流程而不构成多选策略决策时，bridge MUST 生成 `type="continue_game"` 的 legal action。该 action MUST 具备可读 `label`，并 SHALL 在 `metadata` 中提供用于诊断的探测来源与目标控件信息（例如按钮文本、节点类型、字段路径或候选命中规则）。

#### Scenario: 奖励链路结束后出现 Proceed 时导出 continue_game
- **WHEN** 玩家已完成奖励链路的选择步骤，界面出现“Proceed/Continue”按钮用于返回地图或进入下一节点
- **THEN** `actions` MUST 包含 `type="continue_game"` 的 legal action
- **THEN** 该 action 的 `label` MUST 与玩家可见按钮文本一致或等效可读
- **THEN** `metadata` MUST 包含 `continue_detection_source` 或等效字段用于诊断

#### Scenario: 单按钮确认弹窗出现时导出 continue_game
- **WHEN** 当前为确认/提示弹窗，且只有一个用于关闭/确认的按钮（例如 OK/Confirm）
- **THEN** `actions` MUST 包含 `continue_game`
- **THEN** bridge MUST NOT 伪造 reward/map/combat 的策略动作来替代该确认操作

#### Scenario: 多选项窗口不得错误导出 continue_game
- **WHEN** 当前窗口包含两个或更多个互斥的可选项（例如事件选项、多个奖励按钮、商店购买列表等），需要策略决策才能推进
- **THEN** bridge MUST NOT 将其中任意一个选项简化为 `continue_game`
- **THEN** 若窗口同时存在继续按钮与策略选项，bridge MUST 仅在继续按钮语义明确且不会跳过未决策步骤时才生成 `continue_game`，否则 MUST 省略该动作并在 `metadata` 中解释原因


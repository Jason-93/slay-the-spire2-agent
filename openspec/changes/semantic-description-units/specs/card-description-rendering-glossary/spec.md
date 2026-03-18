## ADDED Requirements

### Requirement: 描述渲染链路 MUST 基于变量语义做最小单位补全
系统 MUST 在 description 渲染过程中识别动态变量的语义类型，例如 `energy`、`gold`、`cards` 或等效单位语义。当最终文本仍保留裸数字或非文本图标占位时，bridge MUST 在不改变原始效果含义的前提下做最小补全，使输出可直接被 agent 理解。

#### Scenario: 变量语义可从运行时对象可靠解析
- **WHEN** 某个 description 变量可以从占位符名、成员别名、动态方法或对象上下文中可靠识别为特定语义
- **THEN** bridge MUST 使用该语义补全最终文本中的缺失单位
- **THEN** bridge MUST NOT 仅因为数值存在就盲目追加单位

#### Scenario: 变量语义无法可靠确定
- **WHEN** description 中存在动态数字，但 bridge 无法可靠判断它代表金币、能量、张数或其他语义
- **THEN** bridge MUST 保留当前可解析文本，而不是做猜测性的单位补全
- **THEN** bridge MUST 记录诊断日志，便于后续补充新的语义来源

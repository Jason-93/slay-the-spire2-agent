## Why

当前 event 选项虽然能导出 `label`，但像“锋利2”这类关键附魔词条只以纯文本出现，agent 无法读取游戏 hover 中的真实说明，导致模型在事件抉择时缺少效果语义，只能靠字面猜测。现在 bridge 已经为卡牌、遗物、药水和敌人逐步补齐 glossary，这一缺口会直接影响 event 决策质量，适合继续补齐。

## What Changes

- 为 `event_choice` 窗口中的 `event_options` / `choose_event_option` 导出结构化 glossary 信息，而不只返回纯文本 `label`
- 优先复用游戏 runtime hover / localization 中的真实词条说明，覆盖类似“锋利”“附魔”等 event 选项中的关键术语
- 为 event 选项补充可供模型直接消费的 option-level 描述字段，避免调用方只能自行从多行 `label` 中拆词
- 对缺失 hover 的词条增加日志诊断与安全降级，避免把手写 fallback 伪装成游戏原始说明

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `event-decision-bridge`: 扩展 event 选项导出协议，为选项文本中的关键术语补充 glossary anchors、hover hint 与更稳定的结构化描述字段

## Impact

- 影响 `mod/Sts2Mod.StateBridge/` 中 event 窗口状态提取、option metadata 组装与 glossary 解析逻辑
- 影响本地 HTTP bridge 的 `snapshot` / `actions` 中 event option JSON 结构
- 需要补充相关验证与日志，确保缺失词条时能明确定位而不误导模型

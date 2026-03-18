## Why

当前 bridge 已经能够从游戏运行时或模板中恢复大部分说明文本，但在商店等场景仍会出现仅输出裸数字的问题，例如 `增加25。` 或 `获得2。`。这类描述对人类和大模型都不够可解释，会直接削弱商店决策、事件决策与后续知识扩展的质量。

## What Changes

- 为运行时描述渲染链路补充“变量语义”层，区分数值代表的是 `gold`、`energy`、`cards` 等语义单位，而不是只返回纯数字。
- 为商店服务说明增加语义化单位补全，在游戏原始渲染缺少单位时，输出对 agent 更可读的描述，例如 `增加25金币。`。
- 为卡牌、遗物、药水等说明对象统一复用语义化渲染后处理，优先依赖游戏运行时信息与变量来源，避免按单条中文文案硬编码替换。
- 增加诊断与约束，确保补全逻辑仅在确定语义时生效，避免错误地为无单位数值追加说明。

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `shop-decision-bridge`: 商店商品与服务描述需要输出带明确语义单位的可读说明，避免价格变化或收益数值只剩裸数字。
- `card-description-rendering-glossary`: 描述渲染链路需要支持基于变量语义的单位补全与运行时归一化，而不仅仅做占位符替换和 glossary 提取。

## Impact

- 影响 `mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs` 的描述提取、变量解析与渲染后处理逻辑。
- 影响 shop snapshot、卡牌/遗物/药水说明文本以及相关 live/fixture 验证用例。
- 不引入新的外部依赖，也不改变 `/apply` 协议；主要是提升 snapshot 文本质量与 agent 可解释性。

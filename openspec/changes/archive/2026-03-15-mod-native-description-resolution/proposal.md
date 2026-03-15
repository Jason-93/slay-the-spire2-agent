## Why

当前卡牌与 powers 的说明文本虽然已经能在部分场景解析出真实数值，但整体链路仍混合了 mod 端导出、Python 端兼容摘要和客户端侧兜底渲染。这样的职责划分会让不同调用方看到的说明语义不一致，也让协议里长期保留了 `description` / `description_rendered` / `description_raw` 这类重复字段。

现在需要把“说明文本解析”完全收敛到 mod 端：由游戏内 runtime 直接导出最终可读描述与必要诊断，客户端只消费结果，不再承担任何核心渲染职责，也不再为历史兼容保留冗余字段。

## What Changes

- **BREAKING** 将卡牌、powers、relics、potions 等说明类文本的最终解析职责完全下沉到 mod runtime bridge。
- **BREAKING** 收敛说明字段协议，移除重复或历史兼容字段，仅保留最终对外需要的 canonical description 与必要 diagnostics。
- **BREAKING** 对外 `description` 中的 glossary 词条统一改为 `**词条**` 标记，而不是保留游戏内部 `[gold]...[/gold]` 等富文本标签。
- 为无法直接解析的文本增加服务端诊断与降级约束，确保客户端只需展示或消费结果，而不是自行猜测。
- 梳理 Python bridge / policy / live validation 的职责边界，移除客户端侧 description render 与兼容拼接逻辑。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `in-game-runtime-bridge`: 调整 live runtime bridge 对说明文本的导出约束，要求由 mod 端直接给出最终可读描述，并允许移除重复兼容字段。
- `mod-state-export`: 调整统一状态快照的文本字段语义，要求结构化快照仅保留必要说明字段与诊断信息。

## Impact

- 受影响代码主要位于 `mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs`、状态导出 contracts、window extractors 与对外 JSON schema。
- Python 侧会影响 `src/sts2_agent/bridge/`、`src/sts2_agent/policy/` 与 live validation 脚本，需要删掉冗余 description 兼容读取。
- 需要补充真实 runtime 验证样例，覆盖卡牌、powers 以及后续可扩展到 relics / potions 的说明解析链路。

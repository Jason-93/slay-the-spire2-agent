## MODIFIED Requirements

### Requirement: Bridge 暴露当前决策快照
系统 MUST 暴露当前 Slay the Spire 2 决策窗口的结构化快照，至少包含会话元数据、阶段元数据、玩家可见状态、敌人可见状态、牌区摘要、遗物、药水以及终局标记。对于 combat 相关快照，bridge MUST 进一步稳定暴露 richer runtime state，包括可选的卡牌描述、升级态、目标类型、traits、结构化敌方 intent、玩家/敌方 powers 与最小 `run_state` 规划上下文；bridge MUST 保持现有基础字段语义不变，并允许 richer 字段缺失时兼容退化。

#### Scenario: 在玩家回合中请求 richer combat snapshot
- **WHEN** agent 在一场进行中的战斗里、玩家可行动阶段请求当前决策快照
- **THEN** bridge 返回该最新决策窗口的单个结构化快照，并包含足以选择合法动作的基础状态与已支持 richer state 字段
- **THEN** agent 即使遇到部分 richer 字段缺失，也仍能基于保底字段继续读取与决策

## ADDED Requirements

### Requirement: Bridge 必须为知识层扩展保留稳定锚点
系统 MUST 在卡牌、敌人或等效对象上保留可供上层知识系统消费的稳定锚点，例如 `canonical_*_id` 或等效标识，并与 live action 所需的实例标识分离。bridge MAY 在第一阶段对暂时无法解析的锚点返回空值，但协议 MUST 允许这些字段稳定存在。

#### Scenario: 上层策略同时需要实例动作与静态知识映射
- **WHEN** 上层策略既要提交某张具体手牌的动作，又要查询该卡牌的长期知识标签
- **THEN** bridge 返回的对象 MUST 能区分运行时实例标识与稳定知识锚点
- **THEN** 上层调用方 MUST 不需要依赖卡名字符串推断二者关系

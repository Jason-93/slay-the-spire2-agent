## ADDED Requirements

### Requirement: live validation 必须支持多回合整场战斗 autoplay 冒烟
系统 MUST 提供面向整场战斗 LLM autoplay 的 live smoke validation，至少能覆盖一个包含多个玩家回合的真实 battle，并记录 battle 是否完成、总动作数、回合数、恢复次数、停止原因以及关键 battle artifacts。若 smoke 过程中发生可恢复竞争态，artifacts MUST 能区分“已恢复”与“最终失败”。

#### Scenario: 多回合 battle smoke 成功完成
- **WHEN** live validation 成功从 battle 首个玩家回合运行到战斗结束离开 `combat`
- **THEN** artifacts MUST 记录 `battle_completed=true`
- **THEN** artifacts MUST 同时记录回合数、总动作数与是否发生过 recovery

#### Scenario: battle smoke 因恢复预算耗尽失败
- **WHEN** live validation 在 battle 中连续命中可恢复竞争态但最终未能恢复
- **THEN** 结果 MUST 标记为非成功
- **THEN** artifacts MUST 记录最近失败原因、恢复尝试次数与 battle stop reason

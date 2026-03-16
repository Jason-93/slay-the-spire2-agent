## MODIFIED Requirements

### Requirement: live validation 必须支持多回合整场战斗 autoplay 冒烟
系统 MUST 提供面向整场战斗 LLM autoplay 的 live smoke validation，至少能覆盖一个包含多个玩家回合的真实 battle，并记录 battle 是否完成、总动作数、回合数、恢复次数、停止原因以及关键 battle artifacts。若 smoke 过程中发生可恢复竞争态，artifacts MUST 能区分“已恢复”与“最终失败”。对于 live 时序问题，validation MUST 额外审计稳定窗口门控结果，并把“错误 `end_turn`”视为明确失败：若某步提交 `end_turn` 时，同一稳定玩家窗口内仍存在 `play_card`、`choose_combat_card`、`use_potion` 或等效高价值动作，则该次 smoke MUST 判为失败，而不是静默通过。

#### Scenario: 多回合 battle smoke 成功完成
- **WHEN** live validation 成功从 battle 首个玩家回合运行到战斗结束离开 `combat`
- **THEN** artifacts MUST 记录 `battle_completed=true`
- **THEN** artifacts MUST 同时记录回合数、总动作数、是否发生过 recovery，以及稳定窗口 gate 统计

#### Scenario: battle smoke 因恢复预算耗尽失败
- **WHEN** live validation 在 battle 中连续命中可恢复竞争态但最终未能恢复
- **THEN** 结果 MUST 标记为非成功
- **THEN** artifacts MUST 记录最近失败原因、恢复尝试次数、gate 状态与 battle stop reason

#### Scenario: validation 发现错误 `end_turn`
- **WHEN** smoke trace 或 validation artifacts 显示某次提交了 `end_turn`，但同一稳定玩家窗口内仍存在可提交的 `play_card`、`choose_combat_card`、`use_potion` 或等效高价值动作
- **THEN** validation MUST 将该次运行判定为失败
- **THEN** artifacts MUST 记录对应 step 的 observation、legal actions、policy output、gate 结果与错误原因

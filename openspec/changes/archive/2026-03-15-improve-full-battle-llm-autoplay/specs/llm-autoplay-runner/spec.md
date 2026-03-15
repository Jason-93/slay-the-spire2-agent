## ADDED Requirements

### Requirement: runner 必须向模型提供 battle 级摘要而不只提供当前快照
在整场战斗 autoplay 模式下，runner MUST 在当前 `snapshot` 与 `legal actions` 之外，向策略层补充 battle 级摘要，至少覆盖最近动作、最近 bridge 结果、当前回合索引、当前 battle 的累计动作数、等待态 / 过渡态 / 额外选牌态，以及最近一次可恢复失败信息。该摘要 MUST 保持简洁并可重复序列化到 trace。

#### Scenario: battle 中途再次进入玩家回合
- **WHEN** runner 在敌方回合等待后重新回到玩家回合并再次调用模型
- **THEN** 模型输入 MUST 能看到 battle 已进行到第几个玩家回合
- **THEN** 模型输入 MUST 能看到最近一次等待或恢复发生了什么

#### Scenario: 进入额外选牌窗口时保持上下文连续
- **WHEN** runner 在 battle 中因打牌效果进入 `choose_combat_card` 或等效额外选牌窗口
- **THEN** 模型输入 MUST 明确标识当前不是普通出牌选择，而是额外选牌子决策
- **THEN** battle 摘要 MUST 保留导致该窗口出现的上一手动作线索

### Requirement: runner 必须把 battle 级恢复结果写入 trace 与 summary
runner MUST 在 trace 与最终摘要中记录每次可恢复竞争态、恢复是否成功、恢复后重新执行的动作，以及 battle 最终是正常完成还是因恢复预算、等待超时、模型连续失败等原因中断。

#### Scenario: battle 正常完成且曾发生恢复
- **WHEN** runner 在同一场战斗中至少经历一次恢复，但最终仍成功离开 `combat`
- **THEN** trace MUST 能标出恢复发生的步骤与后续恢复成功的动作
- **THEN** summary MUST 能区分“battle_completed=true”与“期间发生过 recovery”

#### Scenario: battle 因恢复失败而停止
- **WHEN** runner 多次恢复后仍无法重新得到稳定决策窗口
- **THEN** summary MUST 记录 battle 未完成
- **THEN** stop reason MUST 明确反映是恢复链路失败，而不是普通 halt

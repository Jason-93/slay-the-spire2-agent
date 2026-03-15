## ADDED Requirements

### Requirement: live validation 必须支持 use_potion 的真实 apply 冒烟
系统 MUST 提供一条面向真实游戏进程的 `use_potion` apply 冒烟路径，用于验证药水动作不仅在 `actions` 中可见，而且能够通过 `/apply` 被真实执行并推动 live 状态前进。该验证流程 MUST 输出可复盘 artifacts，并区分“药水动作不可用”“请求被拒绝”“请求被接受但状态未推进”三类结果。

#### Scenario: 发现可执行药水动作并完成真实验证
- **WHEN** 当前 live `snapshot.phase` 允许使用药水，且 `/actions` 中存在至少一个 `use_potion`
- **THEN** 验证流程 MUST 能选择一个候选药水动作并生成真实 `POST /apply` 请求
- **THEN** 若 bridge 返回接受且药水槽位、`decision_id`、legal actions 或玩家状态出现与药水效果一致的推进，流程 MUST 将结果标记为成功

#### Scenario: 当前没有药水动作时返回非执行结果
- **WHEN** 当前 live 窗口不存在 `use_potion` legal action
- **THEN** 验证流程 MUST 返回明确的未执行结果
- **THEN** artifacts MUST 记录当前 phase、候选筛选原因与当前动作集合摘要

### Requirement: use_potion 验证 artifacts 必须记录药水前后状态
当 live validation 对 `use_potion` 发起真实写入时，artifacts MUST 额外记录药水执行前后的 `player.potions[]`、候选动作 metadata、apply 请求/回执，以及用于判断状态推进的证据字段，便于后续回放与排障。

#### Scenario: 药水执行成功后 artifacts 包含前后对比
- **WHEN** 某次 `use_potion` 验证完成
- **THEN** artifacts MUST 记录执行前后的 `snapshot.player.potions[]`
- **THEN** artifacts MUST 记录候选 `potion_preview`、请求参数与返回的 `runtime_handler`
- **THEN** 结果文件 MUST 明确写出成功或失败的推进证据

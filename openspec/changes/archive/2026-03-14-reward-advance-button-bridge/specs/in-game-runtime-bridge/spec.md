## ADDED Requirements

### Requirement: reward 收尾前进窗口必须导出可执行动作
当奖励链路已经没有可领取奖励，但界面仍停留在需要玩家点击“前进/继续”后才能进入地图的窗口时，bridge MUST 将该窗口导出为 reward 链路中的可区分子窗口，并提供至少一个可执行 legal action，使外部 agent 能显式推进到地图，而不是停留在空 reward 窗口。

#### Scenario: 普通奖励收尾后出现前进按钮
- **WHEN** 玩家已经领完当前奖励，界面显示“前进/继续”按钮，且点击后才会进入地图
- **THEN** `snapshot.phase` MUST 仍可保持为 `reward` 或等效 reward 链路 phase
- **THEN** `metadata.window_kind` MUST 标记为可区分的 reward 收尾子窗口，而不是继续复用空 `reward_choice`
- **THEN** `actions` MUST 至少包含一个可执行的前进/继续 legal action

#### Scenario: 空 reward 窗口不得再被导出为可交互状态
- **WHEN** 当前 `reward_count=0`，且界面实际上处于“前进/继续”窗口
- **THEN** bridge MUST NOT 导出 `rewards=[]` 且 `actions=[]` 的稳定空 reward 窗口作为最终结果
- **THEN** bridge MUST 要么导出 continue/advance 动作，要么显式标记为短暂过渡态并附带 diagnostics

### Requirement: reward 收尾到 map 的推进信号必须可诊断
bridge MUST 在 reward 收尾、提交前进动作、进入地图三个阶段导出稳定的 metadata / diagnostics，便于 runner 与 live 验证脚本判断当前卡在“未点前进”“前进已提交等待切图”还是“已经进入 map”。

#### Scenario: 前进动作提交后进入房间过渡
- **WHEN** 外部通过 `/apply` 成功提交 reward 收尾前进动作
- **THEN** action response metadata MUST 标记这是 reward continue/advance 语义
- **THEN** 后续 `snapshot` 或 metadata MUST 能区分房间过渡中与地图已就绪两种状态

#### Scenario: 地图出现后不再保留 reward 收尾语义
- **WHEN** 地图已经出现并可选择下一个节点
- **THEN** `snapshot.phase` MUST 推进为 `map`
- **THEN** `metadata.window_kind` MUST 不再保留 reward 收尾子窗口标记
- **THEN** `actions` MUST 导出 `choose_map_node` legal actions

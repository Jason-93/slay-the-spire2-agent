## ADDED Requirements

### Requirement: runner 必须处理 reward 收尾前进动作
当 reward 链路进入“前进/继续”按钮窗口时，runner MUST 将其视为 reward 链路中的可执行步骤，而不是把它误判为空 reward 或异常卡死。只要 bridge 已导出对应 legal action，runner MUST 能提交该动作并继续等待地图出现。

#### Scenario: reward 收尾窗口存在 continue/advance 动作
- **WHEN** `snapshot.phase=reward`，且 metadata 表示 reward 收尾子窗口，`actions` 中存在 continue/advance 对应 legal action
- **THEN** runner MUST 优先执行该动作，而不是因 `rewards=[]` 或空策略空间而停止
- **THEN** 提交动作后 runner MUST 继续推进到 `map` 或房间过渡状态

#### Scenario: reward 收尾窗口没有动作时视为 bridge 异常
- **WHEN** runner 观察到 reward 收尾窗口，但 `actions=[]` 持续存在并超过安全等待预算
- **THEN** runner MUST 将该情况记录为 bridge/phase 导出异常
- **THEN** 运行结果与 trace MUST 能明确区分这类失败，而不是只输出泛化的 `transition_timeout`

### Requirement: live 验证必须覆盖 reward continue 到 map 链路
系统 MUST 提供自动化验证路径，能够在真实游戏运行时覆盖“奖励收尾 -> 点击前进/继续 -> 进入地图”这一链路，并把空 reward、前进动作提交、地图出现等关键节点写入 artifacts。

#### Scenario: live 验证成功进入地图
- **WHEN** 游戏处于 reward 收尾窗口，且 bridge 允许写入
- **THEN** 验证脚本 MUST 能识别并提交 continue/advance 动作
- **THEN** artifacts MUST 记录动作提交前后快照与最终进入 `map` 的结果

#### Scenario: live 验证发现空 reward 卡死
- **WHEN** 游戏停留在 `phase=reward` 且 `reward_count=0`、`actions=[]` 的状态超过阈值
- **THEN** 验证脚本 MUST 将该情况判定为失败
- **THEN** artifacts MUST 记录最后一个 reward 子窗口、最后一次动作与超时前的 diagnostics

# live-apply-validation Specification

## Purpose
TBD - created by archiving change validate-live-apply-autoplay. Update Purpose after archive.
## Requirements
### Requirement: 系统必须提供真实游戏内的受控 apply 验证流程
系统 MUST 提供一条面向真实 STS2 进程的 `live-apply-validation` 流程，能够读取当前 `health`、`snapshot` 与 `actions`，选择一个当前合法且可执行的动作，并在满足安全前提时发起 `POST /apply` 请求。该流程 MUST 与现有 bridge HTTP 协议保持一致，不得依赖仅在 fixture 模式存在的假数据路径。

#### Scenario: 在 live 战斗窗口发现可执行动作
- **WHEN** bridge 已连接到真实游戏进程，当前 `snapshot.phase` 为 `combat`，且 `/actions` 中存在一个结构化可执行动作
- **THEN** 验证流程 MUST 能读取该动作的 `action_id`、`action_type` 与 `params`
- **THEN** 验证流程 MUST 生成一份待执行候选动作说明

#### Scenario: 当前没有安全候选动作时不强行出牌
- **WHEN** 当前 live 窗口中不存在满足验证策略的候选动作
- **THEN** 验证流程 MUST 返回明确的未执行结果
- **THEN** 结果 MUST 说明当前 phase、候选筛选原因或缺失条件

### Requirement: 写入验证必须受显式安全开关约束
系统 MUST 默认以只读 discovery 方式运行 live 验证。只有当调用者显式进入 apply 模式，且 bridge 写入能力已通过 `STS2_BRIDGE_ENABLE_WRITES=true` 或等效机制开启时，验证流程才可提交真实 `POST /apply` 请求。若安全前提不满足，流程 MUST 拒绝执行写入并返回明确原因。

#### Scenario: 未开启写入能力时拒绝真实 apply
- **WHEN** 调用者请求执行真实写入，但当前环境未显式开启 bridge 写入能力
- **THEN** 验证流程 MUST 拒绝发送 `POST /apply`
- **THEN** 结果 MUST 明确标记为安全拒绝，而不是伪造成功

#### Scenario: discovery 模式只读取不写入
- **WHEN** 调用者以默认 discovery 模式运行验证流程
- **THEN** 流程 MUST 只调用只读端点，如 `/health`、`/snapshot`、`/actions`
- **THEN** 流程 MUST NOT 修改 live 游戏状态

### Requirement: 成功验证必须同时确认请求回执与状态推进
系统 MUST 将 live `POST /apply` 验证定义为“请求被接受且状态发生可观察推进”的双条件校验。验证流程 MUST 在收到 `accepted` 或等效成功回执后，继续轮询新的 `snapshot` 或 `actions`，确认 `decision_id`、phase、手牌、能量或 legal actions 至少有一项发生与该动作一致的变化；否则 MUST 返回 `inconclusive`、`failed` 或等效非成功结论。

#### Scenario: 真实出牌后进入新的决策上下文
- **WHEN** 验证流程对当前 live `decision_id` 提交一个合法动作，且 bridge 返回请求已接受
- **THEN** 流程 MUST 继续等待并读取新的 live 状态
- **THEN** 若新的 `decision_id` 已变化或原动作已不再合法，流程 MUST 将本次验证标记为成功

#### Scenario: 请求被接受但状态长时间不变
- **WHEN** bridge 返回请求已接受，但在验证超时窗口内 live `snapshot` 与 `actions` 没有出现可观察推进
- **THEN** 验证流程 MUST NOT 将结果标记为成功
- **THEN** 结果 MUST 明确区分为 `inconclusive`、超时或等效诊断状态

### Requirement: 验证流程必须输出可复盘的结构化 artifacts
系统 MUST 为每次 live 验证生成独立的结构化 artifacts，至少记录执行前状态、候选动作、实际请求、回执、执行后状态与最终结论。artifacts MUST 使用 UTF-8 无 BOM 编码，便于中文诊断信息与后续自动化消费。

#### Scenario: 单次验证生成完整结果目录
- **WHEN** 调用者完成一次 discovery 或 apply 验证流程
- **THEN** 系统 MUST 生成一个按时间或运行标识隔离的结果目录
- **THEN** 目录 MUST 至少包含验证前后快照、动作请求/响应以及汇总结论文件

#### Scenario: 验证失败时仍保留诊断材料
- **WHEN** live 验证因环境、网络、协议校验或状态超时而失败
- **THEN** 系统 MUST 仍输出已收集到的诊断 artifacts
- **THEN** 结果文件 MUST 包含失败阶段、失败原因与关键上下文

### Requirement: live validation 必须审计 enemy richer fields 的文本质量
系统 MUST 在 `live-apply-validation` 或等效验证流程中审计 `snapshot.enemies[]` 的 richer fields 质量，至少覆盖 enemy `intent` / `move_name` / `move_description` 中的富文本残留、重复意图展示，`keywords` 中的内部 id 泄漏，以及 `powers[].glossary` 中重复本体说明或低质量 glossary 条目。若发现上述低质量 enemy 字段，验证结果 MUST 标记为失败、`inconclusive` 或等效非成功结论，而不得静默通过。

#### Scenario: 验证发现 enemy 富文本 intent 残留
- **WHEN** live snapshot 中某个 enemy 的 `intent` 或 `move_name` 仍包含 `[font_size]`、`[/font_size]` 或等效 UI markup
- **THEN** 验证流程 MUST 将该结果标记为非成功
- **THEN** artifacts MUST 记录对应 enemy 路径、字段名与失败原因

#### Scenario: 验证发现 enemy keywords 泄漏内部 id
- **WHEN** live snapshot 中某个 enemy 的 `keywords` 仍包含 `POWER.*`、类型名或等效内部 token
- **THEN** 验证流程 MUST 将其识别为低质量 enemy 字段
- **THEN** 结果 MUST 明确区分这是 keyword 泄漏问题，而不是普通文本缺失

#### Scenario: 验证发现 enemy power glossary 重复本体说明
- **WHEN** live snapshot 中某个 enemy power 的 `glossary` 仍包含重复 power 名称、重复 power description、空 hint、`missing_hint` 或模板化条目
- **THEN** 验证流程 MUST 将该结果标记为非成功
- **THEN** artifacts MUST 记录对应 enemy 路径、power 路径、glossary_id 与失败原因

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

### Requirement: live validation 必须输出 reject 分类与恢复质量 artifacts
系统 MUST 在 live validation、battle smoke validation 或等效真实运行验证中输出 reject 与恢复质量 artifacts，至少记录 reject 总数、按分类统计、恢复尝试次数、恢复成功次数、最终 stop reason，以及最近一次 reject 的上下文摘要。若 battle 虽然完成但 reject 仍然很多，结果 artifacts MUST 能明确体现这一点。

#### Scenario: battle 完成但 reject 仍被单独统计
- **WHEN** 某次 live battle validation 最终成功完成战斗，但过程中发生过 reject 或恢复
- **THEN** artifacts MUST 记录 reject 总数与恢复成功次数
- **THEN** 调用方 MUST 能区分“正常完成且无 reject”与“完成但依赖多次恢复”

#### Scenario: validation 因 reject 链路失败而终止
- **WHEN** 某次 live validation 因 reject 连续发生、恢复预算耗尽或等效拒绝链路失败而停止
- **THEN** 结果 MUST 记录 reject 分类汇总、恢复次数与最终 stop reason
- **THEN** diagnostics MUST 包含最近一次 reject 的 phase、window 或等效上下文摘要

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


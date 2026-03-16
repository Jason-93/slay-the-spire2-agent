## Context

当前 live orchestrator / runner 已支持 battle 级自动打牌、reject 恢复与 trace 落盘，但 pre-submit gate 仍把 rebase 当成主要恢复手段。对于 `play_card` 这类高约束动作，有限 rebase 还能缓解轻微漂移；但 `end_turn`、`use_potion` 这类低信息动作一旦跨回合或跨子窗口复用，就容易把旧策略意图错误投射到新状态。现有 trace 已证明：模型在旧窗口判断“手牌空、能量为 0，可以结束回合”，而提交时 observation 已变成新玩家回合，仍被 rebase 成新的 `end_turn` 并成功送出。

因此，本次修复的核心不是“让 rebase 更聪明”，而是把 live 自动打牌流程改成：先等待状态稳定，再请求模型；提交前若发现窗口已变，就回到重观测与重新决策，而不是继续赌旧动作可复用。

## Goals / Non-Goals

**Goals:**
- 在 live `combat` 中，以稳定决策窗口作为调用 policy 的前提条件。
- 收紧 pre-submit gate / rebase，使 `end_turn`、`use_potion` 不再跨窗口、跨回合或跨子选择窗口复用。
- 当窗口在模型响应后发生漂移时，runner 能执行 reobserve -> restabilize -> redecide，并把过程写入 trace / summary。
- 在 live smoke validation 中把“错误结束回合”识别为明确失败。

**Non-Goals:**
- 不修改 mod / bridge 协议，也不新增必须依赖的 runtime 字段；实现仅基于现有 `phase`、`window_kind`、`current_side`、`round_number`、`selection_kind` 与 legal actions。
- 不追求消灭所有 `stale_action`；允许对 harmless drift 保留严格受限的 rebase。
- 不改变模型提示词的主策略，只修正 live 状态门控与提交时序。

## Decisions

1. **以稳定窗口而不是单次快照作为决策输入前提**
   - 在 live `combat` 中，runner / orchestrator 进入决策前，必须连续获取到满足稳定条件的窗口：关键 metadata 一致，legal actions 不再明显抖动，并且不处于过渡态 / 等待态。
   - 若窗口未稳定，则继续轮询、等待或进入恢复路径，而不是提前调用 policy。
   - trace 中记录稳定判定结果，例如 `gate_status=waiting_stable_window`、`gate_reason=window_drift`。

2. **把 rebase 收缩为同稳定窗口内的窄兜底**
   - 仅当旧动作与新 observation 仍属于同一稳定窗口，且动作类型具备足够强的实例锚点时，才允许 rebase；例如 `play_card`、`choose_combat_card` 仍可在同窗口内做受限重匹配。
   - `end_turn`、`use_potion` 不允许跨稳定窗口 rebase；一旦 `round_number`、`window_kind`、`selection_kind` 或 legal action 形态发生关键变化，必须作废旧决策并重新请求模型。
   - 若 gate 发现旧动作只在语义上“还能点”，但缺少同窗口证据，则优先 redecide，而不是继续提交。

3. **runner 负责窗口漂移后的重决策闭环**
   - 当模型返回动作后、提交前发现窗口已变化，runner 应执行 reobserve -> restabilize -> redecide，而不是把这类情况直接记成 hard reject。
   - trace 与 summary 需要区分：正常通过、稳定后重决策、同窗口安全 rebase、不可恢复漂移中断。
   - battle 上下文要保留最近一次 gate 失败原因，避免模型连续在同类不稳定窗口上误判。

4. **live validation 把错误 `end_turn` 视为真实失败**
   - 在 full-battle / smoke validation 中，若某步提交 `end_turn` 时同一稳定玩家窗口内仍存在 `play_card`、`choose_combat_card`、`use_potion` 或等效高价值动作，验证必须判为失败。
   - artifacts 要保存对应 step 的 observation、legal actions、policy output、gate 结果与最终提交动作，便于复盘时直接定位“为何提前结束回合”。

## Risks / Trade-offs

- **[Risk]** 稳定窗口等待过严，可能增加 battle 决策延迟。  
  **Mitigation:** 使用有界轮询与超时；区分等待稳定与真正卡死，并把等待耗时写入 trace。

- **[Risk]** 收紧 rebase 后，部分原本可自动恢复的轻微漂移会转成重新决策。  
  **Mitigation:** 保留同稳定窗口内的实例级 rebase，仅禁止高风险低信息动作跨窗口复用。

- **[Risk]** 仅靠现有 metadata 可能仍存在边缘误判。  
  **Mitigation:** 联合 `phase`、`window_kind`、`current_side`、`round_number`、`selection_kind` 与 legal actions 共同判定，并在日志 / trace 中保留完整门控证据。

- **[Trade-off]** 增加 gate / trace 复杂度。  
  **Mitigation:** 让复杂度集中在 orchestrator / runner 内部，外部 bridge 协议与策略接口保持不变。

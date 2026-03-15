## Context

当前仓库已经能在 live runtime 中稳定导出药水观察语义：`snapshot.player.potions[]` 包含名称、说明、`canonical_potion_id`，`actions` 里也会生成 `type="use_potion"` 的 legal action，并带有 `potion_index` 与 `potion_preview`。但 `ExecuteAction(...)` 仍未把 `use_potion` 映射到真实运行时处理器，导致真实 battle autoplay 一旦选择药水，就会在 mod 端得到 `unsupported_action`。

这次 change 的重点不是扩展新的协议字段，而是把现有药水观察语义接到真实执行链路：让 `use_potion` 和 `play_card`、`choose_reward` 一样进入受控队列、在游戏线程消费、返回可诊断结果，并补上 live 验证闭环。

## Goals / Non-Goals

**Goals:**
- 让 mod 端真实支持 `use_potion` 动作执行，而不是仅导出 legal action。
- 保持 `snapshot.player.potions[]`、`actions[].metadata.potion_preview` 与 `/apply use_potion` 的参数语义一致。
- 为药水动作提供可恢复、可诊断的失败语义，便于 runner 后续安全放开药水动作。
- 补上一条真实 live 验证路径，证明药水动作不仅“被接受”，而且能推动游戏状态前进。

**Non-Goals:**
- 本次不扩展面向目标的药水使用（例如需要显式选择敌人/友方目标的药水）到全覆盖；若运行时发现需要目标而当前协议未提供，优先返回结构化拒绝。
- 不在本次 change 中处理药水策略质量、何时该用药水或长期资源规划问题。
- 不修改 Python 侧 LLM prompt 的药水策略表达，只聚焦 mod 执行能力与验证闭环。

## Decisions

### 1. 继续复用现有 `use_potion` legal action 参数，而不是引入新的动作类型

执行入口继续使用现有 `type="use_potion"`，并优先依赖 `params.potion_index`、`params.canonical_potion_id` 与当前 live 药水栏做实例匹配。这样可以保持协议面最小变化，也能直接复用已经存在的 `potion_preview` 观察语义。

备选方案是新增 `drink_potion`、`throw_potion` 等更细分动作类型，但当前 bridge 还没有稳定覆盖所有药水子语义，过早拆分会扩大协议耦合面。

### 2. 受控执行仍走现有 action queue，并把药水映射封装为独立 runtime handler

`use_potion` 将和 `play_card` 一样，先经 `/apply` 校验，再进入 in-game queue，由游戏线程在安全调度点消费。mod 端新增独立 `ExecuteUsePotion(...)` 路径，负责：
- 校验当前仍处于允许使用药水的窗口；
- 通过 `potion_index` 与当前槽位实例重新定位药水；
- 解析并调用游戏内实际的“使用药水”入口；
- 产出 `runtime_handler`、阶段 metadata 与错误码。

这样可以把药水动作的反射匹配、失败诊断与其他动作隔离开，避免把 `ExecuteAction(...)` 继续堆成更大的条件分支。

### 3. 优先支持“无目标即可直接生效”的药水；需要目标的药水先显式拒绝

当前 bridge 协议中的 `use_potion` legal action 没有目标参数，因此第一阶段实现以“当前可直接使用、无需额外目标”的药水为主。若运行时发现某瓶药水实际需要目标，mod 端应返回 `runtime_incompatible`、`target_required` 或等效结构化错误，而不是猜测目标或静默失败。

备选方案是在这次 change 同时扩展药水 target 语义，但这会牵涉 `actions` schema、policy、runner、bridge client 与测试矩阵，范围过大。

### 4. live 验证优先新增药水专项冒烟，而不是把现有 apply 脚本做成复杂的通用策略机

现有 `tools/validate_live_apply.py` 更偏向“在当前窗口找一个安全动作试一下”。药水动作的候选条件和成功判据更特殊：要确认药水栏变化、药水不再可用、或战斗资源发生符合药水效果的推进。因此本次更适合新增或显式扩展一条药水专项验证路径，输出专门 artifacts，而不是把现有脚本的默认候选逻辑变得过于复杂。

## Risks / Trade-offs

- [Risk] 游戏内药水调用入口存在版本差异，反射路径不稳定 -> Mitigation：按多条候选成员/方法做探测，并在失败时返回结构化 `runtime_incompatible` 与 `runtime_handler` diagnostics。
- [Risk] 某些药水实际需要目标或额外 UI 交互，当前协议无法直接表达 -> Mitigation：第一阶段只承诺支持无目标直接使用药水，其他情况显式拒绝并记录日志。
- [Risk] 药水使用成功但状态推进信号不明显，live 验证容易误判 -> Mitigation：把“药水槽位减少、原 action 不再合法、资源/状态发生变化”作为组合判据写入 artifacts。
- [Risk] runner 后续放开药水动作后，可能增加模型的低质量资源浪费 -> Mitigation：本 change 只提供执行能力；策略放开可以后续单独控开关或通过 prompt 收敛。

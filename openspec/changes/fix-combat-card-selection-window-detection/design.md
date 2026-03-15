## Context

当前 mod 已经具备战斗额外选牌窗口的基础识别链路，例如 `GetCombatCardSelectionScreen(...)`、`TryBuildCombatSelectionContext(...)` 与 `ExecuteChooseCombatCard(...)`，但 live 实测表明某些真实覆盖层类型，例如 `NChooseACardSelectionScreen`，出现时识别链路没有稳定命中，最终仍回落到 `window_kind=player_turn`，并继续导出普通 `play_card` / `end_turn`。这会让外部 runner 误以为仍在常规出牌窗口，导致自动对局在选牌界面卡死。

这个问题同时影响 mod 侧窗口语义、`/snapshot` 与 `/actions` 的对外契约，以及上层 autoplay / LLM 验证稳定性。修复必须以 mod 为主，而不是在 Python runner 侧继续追加特判，否则会把真实 live UI 语义和 bridge 语义进一步拉开。

## Goals / Non-Goals

**Goals:**
- 让 in-game runtime 在战斗额外选牌覆盖层出现时稳定识别为 `combat_card_selection`。
- 让 `actions` 与当前窗口严格一致：选牌窗口只导出 `choose_combat_card` / `cancel_combat_selection` 或等效动作。
- 为识别链路补充足够 diagnostics，便于后续定位新覆盖层类型、prompt 缺失或 hook 变化。
- 补充回归验证，覆盖这次 live 暴露出来的真实窗口类型。

**Non-Goals:**
- 不在这次变更中扩展新的 reward 选牌语义。
- 不重写整个 runtime 反射框架，只修复战斗选牌窗口的识别优先级、判定条件与导出语义。
- 不在 Python orchestrator 侧通过临时猜测去绕过 mod 识别错误。

## Decisions

1. **优先修 mod 侧窗口判定，而不是在 runner 侧打补丁。**
   - 原因：当前问题的根因是 live bridge 错把覆盖层导成普通 `player_turn`，属于协议语义错误。若只在 runner 中根据 `overlay_top_type` 猜测，会导致 bridge、测试与调用方看到的动作集合不一致。
   - 备选方案：在 Python 侧检测 `overlay_top_type` 后拦截普通动作。该方案只能止损，不能让 `/actions` 暴露真实可执行动作，因此不采用作为主方案。

2. **将 combat selection 识别链路改为“覆盖层优先、玩家手牌选择并列兜底”。**
   - 原因：live 现场已经证明某些选择界面是独立 overlay，而不是完全挂在 `NPlayerHand` 上；只依赖 `IsInCardSelection`、prompt 文本或 hand 内部状态会漏判。
   - 具体做法：优先检查 `overlay_top_type` / `overlay_top` 是否命中可疑 card selection screen，再回退到 player hand selection；同时继续保留 reward screen 排除条件与 live enemy 检查，避免把 reward / deck view 误判成 combat selection。
   - 备选方案：继续依赖 prompt 文本关键字。该方案对无 prompt、prompt 未本地化或字段变更不稳，因此只保留为辅助手段。

3. **一旦识别为 `combat_card_selection`，普通玩家动作必须被覆盖，不允许并存。**
   - 原因：并存导出会让外部策略层误提交 `play_card` / `end_turn`，而当前游戏真实可交互窗口并不接受这些动作。
   - 备选方案：保留普通动作并在 metadata 中加提示。该方案仍然会让调用方误用，不满足“actions 与当前窗口一致”的要求。

4. **增加面向识别链路的 diagnostics 与回归测试。**
   - 原因：这类问题容易在游戏版本升级或节点类型变更后复发，仅靠一次 live 通过不足以防回归。
   - 具体做法：在 metadata / 日志中保留 `overlay_top_type`、selection 来源、回退路径、过滤原因；并增加针对 `NChooseACardSelectionScreen` 风格覆盖层的最小单测或夹具验证。

## Risks / Trade-offs

- **[Risk]** overlay 类型放宽后误把 reward、deck、shop 等卡牌界面识别成 combat selection  
  **Mitigation:** 继续保留 `IsRewardScreenObject(...)`、live enemies 存活检查、select hook 检查与 prompt/choice 交叉验证。

- **[Risk]** 某些选择界面没有 prompt，或 hook 名称与当前反射假设不一致  
  **Mitigation:** 允许类型提示与 choice 结构共同判定，并在 diagnostics 中记录未命中的原因，便于后续补型。

- **[Risk]** 只修识别，不修验证，未来仍可能静默退化  
  **Mitigation:** 同步补充 fixture、单测与 live smoke，确保 `window_kind` 与 `actions` 一起回归。

- **[Trade-off]** 更严格地屏蔽普通动作可能暴露更多“无动作窗口”  
  **Mitigation:** 这是正确暴露 live 状态的代价，后续 runner 可以基于明确语义恢复，而不是在错误动作集合上重复提交。

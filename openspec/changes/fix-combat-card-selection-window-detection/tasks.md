## 1. Combat selection 识别修复

- [x] 1.1 审查 `Sts2RuntimeReflectionReader` 中 `GetCombatCardSelectionScreen(...)`、`LooksLikeCombatCardSelectionScreen(...)` 与 overlay 判定链路，定位 `NChooseACardSelectionScreen` 未命中的具体条件
- [x] 1.2 调整战斗选牌窗口识别优先级，确保独立 overlay card selection screen 出现时优先导出 `window_kind=combat_card_selection`
- [x] 1.3 补充或放宽 combat selection 命中条件，使其不再仅依赖 prompt 文本或 `NPlayerHand` 选择态

## 2. 动作导出与 diagnostics 收敛

- [x] 2.1 在识别为 `combat_card_selection` 时，仅导出 `choose_combat_card` / `cancel_combat_selection` 或等效动作，不再并存普通 `play_card` / `end_turn`
- [x] 2.2 补充 `selection_kind`、`selection_prompt`、`overlay_top_type`、识别来源或等效 diagnostics，便于 runner 判断当前窗口
- [x] 2.3 为识别失败、过滤回退或 hook 缺失增加日志与 diagnostics，便于排查后续新增覆盖层类型

## 3. 回归验证

- [x] 3.1 增加最小单测或 fixture，覆盖独立 overlay card selection screen 被正确识别为 `combat_card_selection` 的场景
- [x] 3.2 增加回归验证，确认该窗口下 `/actions` 只返回 combat selection 对应动作，不再暴露普通玩家动作
- [x] 3.3 运行一次 live 验证，确认当前真实卡住的选牌界面能够被 mod 正确识别并继续推进

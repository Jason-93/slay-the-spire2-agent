## 1. combat 窗口导出与时序收紧

- [ ] 1.1 在 `Sts2RuntimeReflectionReader` 中补齐回合切换检测，稳定区分 `player_turn`、`enemy_turn`、`combat_transition`，并避免在非稳定玩家回合导出普通 `play_card` / `end_turn`。
- [ ] 1.2 为战斗窗口 metadata 补充过渡态诊断字段（如 `transition_kind`、`current_side`），并在必要时输出抑制原因，便于 runner 判断当前不可提交动作。
- [ ] 1.3 增加对应 C# 单元测试与 fixture，覆盖 end turn 后等待敌方结算、敌方回合、回合重新回到玩家回合的导出行为。

## 2. 战斗内额外选牌窗口建模

- [ ] 2.1 在 runtime 反射层识别战斗内额外选牌窗口，导出 `combat_card_selection`（或等效）窗口种类、`selection_kind`、来源卡牌等 metadata。
- [ ] 2.2 为当前可选牌集合生成 `choose_combat_card` legal actions，并在规则允许时导出 `cancel_combat_selection`；动作参数必须能稳定定位到被选中的卡牌实例。
- [ ] 2.3 为额外选牌窗口补齐状态导出测试，覆盖“可选卡牌列表正常导出”“不可取消时不生成 cancel”“窗口变化时动作失效”三类场景。

## 3. apply 执行与错误语义

- [ ] 3.1 在 `InGameRuntimeCoordinator` / apply 执行路径中增加回合切换与选择窗口漂移的二次校验，返回 `not_player_turn`、`selection_window_changed`、`stale_action` 等可恢复错误码。
- [ ] 3.2 实现 `choose_combat_card` 与 `cancel_combat_selection` 的真实执行映射，确保额外选牌动作能驱动 live 结算推进。
- [ ] 3.3 为 apply 回执增加最小诊断字段，区分“窗口已切换”“动作仍合法但执行失败”“目标牌已不再可选”等失败阶段。

## 4. Python runner 与 live 验证

- [ ] 4.1 在 Python bridge client / models 中补齐新窗口种类与新动作类型的解析，避免未知 action type 破坏 runner。
- [ ] 4.2 调整 live autoplay / 验证脚本的 safe-action 逻辑：在 `enemy_turn`、`combat_transition` 停止普通出牌；在 `combat_card_selection` 进入额外选牌决策分支。
- [ ] 4.3 新增或扩展 live/fixture 验证脚本，实测覆盖“跨回合无多余 409 rejected”与“打出需要选牌的卡后可继续完成选择并推进战斗”。

## 5. 文档与回归验证

- [ ] 5.1 更新相关文档或说明，记录新的 `window_kind`、`choose_combat_card` / `cancel_combat_selection` 语义与常见失败码。
- [ ] 5.2 运行 `dotnet test mod\Sts2Mod.StateBridge.Tests\Sts2Mod.StateBridge.Tests.csproj --no-restore`、`$env:PYTHONPATH='src'; python -m unittest discover -s tests -v` 以及针对 live bridge 的专项验证，确认变更可进入 apply 阶段。

## 1. battle 级 orchestrator 语义

- [ ] 1.1 扩展 `AutoplayOrchestrator` 配置，增加 battle 级参数，如最大回合数、最大总动作数、连续失败预算、下一玩家回合等待超时与 poll 间隔。
- [ ] 1.2 将现有单回合执行模型提升为 battle loop：在 `combat` 内跨多个玩家回合持续运行，玩家回合时调模型，非玩家回合时等待并重新观测。
- [ ] 1.3 扩展 `RunSummary` 与 trace，增加 `battle_completed`、`turns_completed`、`total_actions`、当前回合索引、battle 停止原因等字段。

## 2. 停止条件与恢复策略

- [ ] 2.1 实现 battle 完成判定：覆盖 `snapshot.phase != "combat"`、`snapshot.terminal = true`、战斗结束进入奖励窗口等路径。
- [ ] 2.2 实现 battle 级安全边界：覆盖最大回合数、最大总动作数、下一玩家回合等待超时、连续失败超过预算等停止原因。
- [ ] 2.3 在 battle 模式下保留并适配现有恢复逻辑，包括 `stale_action` 重试、伪 legal action 过滤、只剩 `end_turn` 自动结束当前回合。

## 3. CLI 与测试

- [ ] 3.1 更新 `src/sts2_agent/live_autoplay.py` 与 `tools/run_llm_autoplay.py`，暴露 battle 模式与 battle 级安全参数，并在输出中体现 battle 级摘要。
- [ ] 3.2 增加单元测试，覆盖跨两个玩家回合连续执行、敌方回合等待恢复、等待超时停止、最大回合数/最大总动作数停止等路径。
- [ ] 3.3 补充 CLI / 集成级测试，确认 battle 参数覆盖、battle trace 字段与摘要字段可用，同时保持现有单回合模式兼容。

## 4. 真实联调与文档

- [ ] 4.1 更新 `README.md` 或 `docs/`，说明如何运行“整场战斗 autoplay”、battle 级安全参数以及与单回合模式的区别。
- [ ] 4.2 在真实 STS2 战斗窗口完成至少一次从首个玩家回合开始，到战斗结束进入 `reward` 或等效结束窗口为止的 battle autoplay 冒烟，并记录动作序列、回合统计、停止原因与结果 artifacts。

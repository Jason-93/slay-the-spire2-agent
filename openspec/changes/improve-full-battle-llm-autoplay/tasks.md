## 1. battle 上下文与模型契约

- [ ] 1.1 为 battle autoplay 增加 battle-scoped context 数据结构，汇总最近动作、最近 bridge 回执、当前回合索引、累计动作数、等待态 / recovery 态与额外选牌态。
- [ ] 1.2 更新 `chat-completions` prompt builder 与响应 schema，要求模型返回 `action_id`、`target_id`、`reason`、`halt`、`confidence`，并保留 battle summary 输入。
- [ ] 1.3 扩展 trace / summary 序列化，确保 battle context、恢复次数、最近失败和 stop reason 可稳定落盘。

## 2. orchestrator 恢复与 battle 稳定性

- [ ] 2.1 在 `AutoplayOrchestrator` 中实现 battle 级恢复流程：覆盖 `stale_action`、临时空 legal actions、等待玩家回合恢复与额外选牌窗口切换。
- [ ] 2.2 为 recovery 增加有界预算、分类 stop reason 与恢复统计，避免 battle autoplay 无限重试。
- [ ] 2.3 调整 battle loop 的策略调用时机，确保等待态、transition 态和额外选牌态都能携带正确的 battle context 进入下一次决策。

## 3. 测试、验证与文档

- [ ] 3.1 增加单元测试，覆盖 battle summary 构造、provider 新字段解析、recovery 成功/失败路径与额外选牌上下文连续性。
- [ ] 3.2 扩展 live battle smoke validation 或新增脚本，记录 battle 完成度、回合数、总动作数、恢复次数与停止原因 artifacts。
- [ ] 3.3 更新 `README.md` / `docs/`，说明新的 battle autoplay 调试方式、provider 输出约束和 recovery 相关安全参数。

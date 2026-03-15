## 1. Reject 分类与提交流程收敛

- [x] 1.1 在 Python 侧为 live `/apply` 失败建立统一 reject 分类表，并保留原始 bridge 错误码与分类结果
- [x] 1.2 为 `AutoplayOrchestrator` 增加 pre-submit gate，拦截非玩家操作态、transition 与已知不稳定窗口
- [x] 1.3 将可恢复 reject 接入“重观测 -> 等待/重试 -> 达预算停止”的统一恢复路径

## 2. Runner 与 trace 诊断增强

- [x] 2.1 扩展 `RunSummary`、trace 或等效 diagnostics，记录 reject 次数、恢复次数、分类汇总与最终 stop reason
- [x] 2.2 在 live runner 与 battle smoke 脚本中输出 reject-rate artifacts，区分“完成战斗”与“完成但 reject 很多”
- [x] 2.3 为 battle 级验证补充针对 recoverable reject、hard reject 与 gate 拦截的单元测试/集成测试

## 3. HUD 历史与可观察性优化

- [x] 3.1 调整 `/agent-status` 历史语义，使同一条决策的生命周期更新合并为单条历史记录
- [x] 3.2 让 HUD 历史区稳定展示每条决策的摘要与思路，并避免被低价值状态刷屏淹没
- [x] 3.3 补充 mod 侧测试或最小回归验证，确认 session 切换、stale 与历史清空行为正确

## 4. Live 回归验证

- [x] 4.1 设计一组固定 live battle 回归步骤，用于比较优化前后 reject 总数与恢复成功率
- [x] 4.2 运行一次真实 LLM autoplay 回归，确认 HUD、trace 与 validation artifacts 能同时反映 reject 改善情况
- [x] 4.3 更新相关文档或调试说明，写清 reject 分类、恢复预算和观察指标的解读方式

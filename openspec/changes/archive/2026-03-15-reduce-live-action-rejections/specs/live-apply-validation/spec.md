## ADDED Requirements

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

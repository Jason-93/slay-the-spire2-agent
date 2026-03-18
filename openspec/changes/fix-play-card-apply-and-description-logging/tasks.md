## 1. 修正 play_card 执行语义

- [ ] 1.1 审查并调整 `Sts2RuntimeReflectionReader` 中的 `play_card` 执行顺序，优先接入直接运行时出牌入口，UI 拖拽链路仅保留为 fallback。
- [ ] 1.2 为 `play_card` 增加状态推进校验，确保 accepted 仅在 `decision_id`、`state_version`、手牌/能量/窗口等 live 信号发生推进时返回。
- [ ] 1.3 为“已消费但未生效”的 `play_card` 回执补充结构化 diagnostics，例如 `queue_stage`、`runtime_handler` 与失败阶段。

## 2. 清理 description 热路径异常

- [ ] 2.1 审查战斗额外选牌窗口识别与相关启发式，移除会直接触发格式化的危险 `Description` 访问，改用安全文本来源或保守降级。
- [ ] 2.2 为 description 格式化失败补充日志降级路径，保证 `snapshot`、`actions` 与窗口识别不会因单条文本异常而中断。
- [ ] 2.3 收敛重复的本地化格式化报错，确保默认日志聚焦失败与降级，而不是在热路径中持续刷同类异常。

## 3. Live 验证

- [ ] 3.1 在真实游戏内手动验证一次 `/apply play_card`，确认 accepted 后 live 状态确实推进。
- [ ] 3.2 验证战斗中的额外选牌窗口仍能被稳定识别，且不会再因 description 访问刷出高频格式化错误。
- [ ] 3.3 运行至少一轮 live autoplay 复测，确认不再因假成功 `play_card` 卡死，并记录剩余已知问题。

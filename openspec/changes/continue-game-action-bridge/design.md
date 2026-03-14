## Context

当前仓库通过 STS2 游戏内 mod 暴露 `health`、`snapshot`、`actions` 与 `POST /apply`，使外部 agent 可以在受控线程上下文中读取状态并执行动作。目前核心决策（combat 打牌、map 选点、reward 选择/跳过与选牌二级界面）已经可用，但自动化测试与端到端对局仍会频繁卡在一些“无策略含义、只需要点击一次就能推进流程”的界面上，例如：

- 奖励链路结束后的“前进/继续（Proceed/Continue）”
- 单按钮确认弹窗（OK/Confirm）
- 过渡提示页或说明页的关闭

这些界面不适合被建模为 reward/map/combat 的策略动作，但缺失稳定的推进动作会导致自动化用例无法闭环，必须人工点击。

约束：
- 协议增量尽量小，避免引入新的 phase。
- 动作执行必须走现有受控队列与主线程消费逻辑，避免在 HTTP 线程直接触碰游戏对象。
- 输出文档使用 UTF-8 无 BOM，正文简体中文。

## Goals / Non-Goals

**Goals:**
- 在 `actions` 中引入可复用的 `continue_game` legal action，用于表示“当前存在明确的继续/确认按钮，点击可推进流程”。
- 在 in-game runtime 中稳定识别可点击的 continue/confirm/proceed 控件，并导出可诊断的 metadata。
- 在 `POST /apply` 中实现 `continue_game` 的真实执行映射（点击对应控件），并提供可诊断回执。
- 提供最小的 fixture 与 live 冒烟脚本，便于自动化测试稳定复现并验证推进成功。

**Non-Goals:**
- 不在本变更中实现“所有事件/商店/战斗后分支”的完整覆盖；优先覆盖最常见的单按钮推进点。
- 不引入新的外部依赖或复杂的 UI 识别（例如图像识别）；仍以反射与节点探测为主。
- 不在本变更中定义新的策略层（何时点 continue），仅提供能力与回执，策略由上层 orchestrator/runner 决定。

## Decisions

### 1) 引入通用动作 `continue_game`，而不是为每个窗口创建独立 action type

选择新增 `type="continue_game"`（无 params 或仅保留可选诊断 params），统一表达“推进到下一步”。这样可以显著降低协议复杂度，并适配未来更多单按钮推进点。

备选方案：为 reward proceed、弹窗确认等分别引入 `proceed_reward`、`confirm_dialog` 等 action type。缺点是协议膨胀，且上层策略需要知道窗口细节。

### 2) continue 检测采用“候选控件探测 + 交互性校验 + 保守导出”三段式

实现上在 `Sts2RuntimeReflectionReader` 中增加 `TryBuildContinueAction(...)`：
- 候选控件探测：优先从 overlay/top screen 与当前 run node 中查找已知“继续/确认/前进”类型的节点或按钮集合（通过类型名、字段名、常见方法签名等反射信号）。
- 交互性校验：要求控件可见、可点击且当前不处于禁用态；同时提取用户可读文本作为 `actions[].label`。
- 保守导出：仅在当前窗口不存在“需要策略选择的多选项”时生成 `continue_game`。例如有多个 reward 选项/事件选项时，不应错误地把 continue 当作主动作。

诊断信息放入 metadata（例如 `metadata.continue_button_text`、`metadata.continue_detection_source`、`metadata.continue_target_type`），避免污染主字段。

### 3) 执行映射使用“提交时校验 decision_id + 执行时重新解析目标控件”

为降低 stale UI 风险，`POST /apply` 的 `continue_game` 处理流程：
- 提交阶段：沿用现有 `decision_id` 与 legal actions 校验，确保只执行当前窗口导出的动作。
- 执行阶段：在游戏主线程消费动作队列时重新解析 continue 目标控件（同一探测逻辑），并调用其 click/activate 方法。
- 回执：返回 `runtime_handler`（例如 `continue_button.Click`）、以及失败时的 `runtime_incompatible`/`stale_action`/`not_clickable` 等原因，便于上层恢复。

备选方案：在 action params 中携带反射路径或对象 id 并直接执行。缺点是实现复杂，且容易跨帧失效。

## Risks / Trade-offs

- [游戏版本变更导致控件类型/字段名变化] → 通过多信号探测与 diagnostics 降低单点依赖，并在 live 冒烟脚本中尽早暴露不兼容。
- [误把“跳过/放弃”等危险按钮当作 continue] → 仅匹配白名单控件类型/文本关键词，并在有多选项窗口中禁用 continue_game 导出。
- [按钮短暂不可点击导致 apply 失败] → apply 返回结构化失败原因；上层可重试或等待下一帧窗口稳定后再提交。


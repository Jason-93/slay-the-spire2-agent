## ADDED Requirements

### Requirement: 战斗窗口识别不得依赖会触发格式化异常的不安全 description 读取
当 bridge 在 live combat 中识别额外选牌窗口、手牌选择窗口或其他战斗子窗口时，MUST 使用不会触发本地化格式化的安全文本来源，例如原始模板、缓存渲染文本、对象标识或其他低风险字段。bridge MUST NOT 仅为了窗口识别或诊断探测而直接访问可能抛出 `Localization formatting error` 的最终 `Description`。若安全文本来源不可用，bridge MUST 保守降级到过渡态、未知窗口或等效 fail-safe 结果，而不是抛异常、中断快照，或继续伪造普通玩家动作。

#### Scenario: 额外选牌窗口识别使用安全文本来源
- **WHEN** bridge 在 combat 中尝试判断当前是否处于额外选牌窗口，并需要读取候选卡牌的基本文本信息
- **THEN** bridge MUST 优先使用不会触发格式化执行的安全文本来源
- **THEN** `snapshot` 与 `actions` MUST 继续可序列化返回，而不是因 description 访问异常失败

#### Scenario: 安全文本来源不可用时保守降级
- **WHEN** 当前窗口识别所需的安全文本来源为空、缺失或不可解析
- **THEN** bridge MUST 降级为过渡态、未知窗口或等效 fail-safe 结果
- **THEN** bridge MUST NOT 因识别失败继续导出旧的 `play_card` 或其他高风险普通动作

### Requirement: description 格式化异常必须只进入日志诊断而不污染主流程
当 live runtime 中的 cards、powers 或其他说明对象在解析过程中触发本地化格式化异常时，bridge MUST 将该异常收敛到日志或本地 diagnostics，并继续使用安全 fallback 构建 `snapshot`、`actions` 或窗口识别结果。默认日志 SHOULD 聚焦失败与降级路径；bridge MUST NOT 因单条说明格式化异常持续刷屏、阻断自动对局，或让外部调用方承担额外恢复逻辑。

#### Scenario: 单张卡牌说明格式化失败时 snapshot 仍可返回
- **WHEN** 某张卡牌的说明文本因缺失 selector、变量或花括号闭合错误而触发格式化异常
- **THEN** bridge MUST 记录包含对象标识、字段来源与失败阶段的 warning 或等效诊断
- **THEN** `snapshot` MUST 仍然成功返回，并对该字段使用安全 fallback 或省略策略

#### Scenario: 窗口识别热路径不得因重复异常刷屏
- **WHEN** combat 窗口识别会在多个 tick 中反复接触同一批存在格式化问题的说明对象
- **THEN** bridge MUST 将异常收敛到日志诊断路径，而不是每次热路径访问都触发同类高频报错
- **THEN** 默认运行日志 MUST 以可排障为目标，不得被重复的同类 description 异常淹没

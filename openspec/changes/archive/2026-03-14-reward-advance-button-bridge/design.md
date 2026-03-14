## Context

当前 bridge 已能导出普通 reward、card reward selection、map 与 combat，但在真实游戏里，reward 链路并不是“选完最后一个奖励就立刻进入地图”。实际还会出现一个玩家可见的“前进/继续”按钮窗口，只有点击后才会跳到地图。现在 mod 侧把这个窗口继续识别为 `reward`，但同时导出 `rewards=[]`、`actions=[]`，runner 只能看到一个空 reward 窗口，既不能继续领奖，也不能前进到地图。

这个问题同时跨越 mod 状态识别、legal action 导出、runner 状态机和 live 验证脚本：如果只改 runner，仍然没有动作可点；如果只改 bridge 而不改 runner，autoplay 仍可能把该窗口当作异常空 reward。由于这是 `reward -> map` 过渡中的真实游戏窗口，需要先在设计上明确 phase、window_kind 与 action 语义。

## Goals / Non-Goals

**Goals:**
- 让 bridge 能稳定识别 reward 收尾“前进/继续”窗口，并导出至少一个可执行 legal action。
- 让 runner 能把该窗口视为 reward 链路的一部分，提交 continue/advance 动作后继续等待地图出现。
- 让 diagnostics 能区分“空 reward 但可继续前进”和“异常空窗口/识别失败”。
- 补充真实链路验证，至少覆盖 card reward -> reward continue -> map 这一段。

**Non-Goals:**
- 不在本次变更中扩展商店、事件、篝火等其他非战斗房间的动作导出。
- 不新增新的 HTTP 端点，优先复用现有 `snapshot`、`actions`、`apply` 协议。
- 不在本次变更中重做 reward 全量策略质量；目标是先保证“能继续前进”。

## Decisions

### 1. 将“前进/继续”视为 reward 链路的显式子窗口，而不是直接跳 phase
bridge 仍可保留 `snapshot.phase="reward"`，但必须通过 `metadata.window_kind`、`reward_subphase` 或等效 diagnostics 显式区分：普通奖励选择、card reward selection、reward advance screen。这样 runner 不需要猜“空 reward 是否正常”，而是可根据结构化子窗口决定下一步。

- 选择原因：当前 runner 已把 reward 当作跨窗口链路中的合法阶段，继续用 reward 子窗口扩展最小。
- 备选方案：直接把“前进”窗口导出为 `map`。问题是玩家实际上还没到地图，混淆 phase 语义。

### 2. “前进/继续”按钮通过 legal action 导出，而不是依赖纯过渡等待
mod 必须导出可执行动作，例如继续沿用 `choose_reward` 的收尾语义，或增加专门的 reward continue action；无论采用哪种形式，都必须出现在 `/actions` 中并能经 `/apply` 触发。runner 不应通过“空轮询直到 map”来赌界面自动前进。

- 选择原因：真实界面需要一次明确点击，必须作为动作导出。
- 备选方案：把该窗口当作 `transition_wait`，完全不导动作。问题是与真实 UI 不一致，也会导致 live 自动化卡死。

### 3. runner 对 reward 收尾窗口采用保守默认策略：优先前进
在 reward 已经领空、且 legal actions 中存在 continue/advance 对应动作时，runner 默认直接提交该动作，不再调用 LLM 做无意义选择。只有当窗口中同时存在多个真实奖励动作时，才保留既有 reward 决策模式。

- 选择原因：收尾窗口没有策略空间，默认前进最稳定。
- 备选方案：继续让 LLM 每次决定是否点击“前进”。问题是增加不必要的不确定性。

### 4. 用 live 验证脚本固化“空 reward 不应再出现”
验证脚本需要把“`phase=reward` 且 `reward_count=0` 且 `/actions=[]`”视为失败信号，并在 artifacts 中记录停在什么子窗口、最后一次动作是什么。这样下次联调能快速区分是按钮未导出、动作未生效，还是 phase 未推进。

- 选择原因：这次问题就是通过 live 实测暴露出来的，必须把它固化为回归检查。

## Risks / Trade-offs

- [Risk] 不同 reward 收尾窗口在反射层的节点类型可能不止一种。 → Mitigation：优先导出结构化 diagnostics，如 overlay type、button count、button label、handler source，并在测试中覆盖至少一种真实可复现路径。
- [Risk] 若复用现有 `choose_reward` 语义，可能让 reward 动作类型含义变宽。 → Mitigation：在 metadata 中明确标记 reward advance 子窗口与动作来源，确保 runner 与调试脚本可区分。
- [Risk] 某些情况下“前进”按钮可能短暂不可见，仍会出现短暂空窗口。 → Mitigation：runner 保留有限 `transition_wait`，但只把短暂等待作为例外，不再接受稳定停留在空 reward 窗口。
- [Risk] live 修复后可能暴露 map 进入后的下一层问题。 → Mitigation：本次变更的验证目标明确限定为“点掉前进按钮并进入地图”，后续再继续追下一段链路。

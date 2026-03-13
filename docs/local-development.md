# 本地开发说明

## 项目结构

- `src/sts2_agent/models.py`：协议模型，定义 observation、legal action、action result、trace 数据结构
- `src/sts2_agent/ids.py`：`session_id`、`decision_id`、`action_id`、`state_version` 的生成与校验
- `src/sts2_agent/bridge/base.py`：bridge 抽象接口与标准错误
- `src/sts2_agent/bridge/mock.py`：基于 fixture 的原型 bridge
- `src/sts2_agent/policy/`：策略接口与基线 policy
- `src/sts2_agent/orchestrator.py`：autoplay 编排逻辑
- `src/sts2_agent/fixtures/`：战斗、奖励、地图、终局等决策窗口 fixture
- `tests/`：协议与编排的回归测试

## Bridge 入口与适配方式

当前仓库提供的是 `MockGameBridge`，用于模拟 STS2 mod 的本地桥接能力。后续接入真实 mod 时，建议保留 `GameBridge` 抽象不变，只新增一个真实适配器，例如：

- `HttpGameBridge`：通过本地 loopback HTTP/JSON 调用 STS2 mod
- `NamedPipeGameBridge`：通过命名管道与 mod 通信

只要真实适配器实现以下方法，即可复用现有 orchestrator 与 policy：

- `attach_or_start()`
- `get_snapshot()`
- `get_legal_actions()`
- `submit_action()`
- `stop()`
- `reset()`

## 首个端到端运行流程

1. 运行测试：

```bash
python -m unittest discover -s tests -v
```

2. 在 Python 中运行一个原型 autoplay：

```python
from sts2_agent.bridge import MockGameBridge
from sts2_agent.orchestrator import AutoplayOrchestrator
from sts2_agent.policy import FirstLegalActionPolicy

bridge = MockGameBridge()
policy = FirstLegalActionPolicy()
orchestrator = AutoplayOrchestrator(bridge=bridge, policy=policy)
summary = orchestrator.run()
print(summary)
```

3. 查看输出 trace：

- 默认路径：`traces/<session_id>.jsonl`
- 每行一条决策记录，可直接用于回放、调试、评估

## 接入真实 STS2 mod 的下一步

- 按 `DecisionSnapshot` / `LegalAction` / `ActionSubmission` / `ActionResult` 的字段结构输出和消费 JSON
- 确保 mod 侧以 bridge 为合法动作真值源
- 对每个决策窗口生成稳定的 `decision_id` 与 `state_version`
- 在状态变化后拒绝过期动作，保持 fail-closed 行为

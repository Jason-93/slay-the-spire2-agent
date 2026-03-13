# 原型 bridge 校验记录

本次实现使用 `MockGameBridge` 作为原型 bridge，对 `game-bridge` 与 `autoplay-orchestrator` 契约进行首轮校验。

## 已覆盖的决策窗口

- `combat`：验证玩家回合中的 observation 提取与合法动作枚举
- `reward`：验证奖励选牌窗口的动作表达
- `map`：验证地图分支选择窗口的动作表达
- `terminal`：验证终局窗口无合法动作且 autoplay 正常结束

## 已验证的契约行为

- `DecisionSnapshot` 可以稳定输出 `session_id`、`decision_id`、`state_version`、`phase`
- `LegalAction` 为每个合法动作生成稳定 `action_id`
- bridge 会拒绝过期动作和不在合法集合中的动作
- orchestrator 能逐步读取 observation、调用 policy、提交动作并写入 trace
- bridge / policy 出错时，orchestrator 采用 fail-closed 中断

## 联调后确认的 schema 细节

- `decision_id` 必须和 `phase + state_version + session_id` 强绑定，否则过期动作很难稳定识别
- `action_id` 必须由 `decision_id + action_type + payload` 生成，避免同一窗口内动作冲突
- 非战斗窗口同样需要统一 observation 结构，不能因为字段较少就单独使用另一种返回格式
- `terminal` 必须作为显式布尔字段存在，不能仅靠 `phase == terminal` 推断
- trace 中除了 bridge 返回结果，还需要保留原 observation 与 legal action 集合，方便做离线问题定位

## 接入真实 mod 前的建议补充

- 增加 session token 或本地鉴权机制，限制非预期进程调用 loopback bridge
- 为目标选择、药水目标、事件选项补充更细粒度的 `target_constraints`
- 根据真实 STS2 mod 的数据结构补充更多 metadata 字段，但不要破坏核心契约

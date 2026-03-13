# 原型 bridge 校验记录

当前最小验证脚本为 `tools/validate_mod_bridge.py`，默认启动 `Sts2Mod.StateBridge.Host` 的 `fixture` 模式，并执行一轮读写闭环检查。

## 已覆盖的窗口

- `combat`
- `reward`
- `map`
- `terminal`

## 已验证的契约行为

- `GET /health` 能返回健康状态与兼容性元数据
- `GET /snapshot` 能为四类窗口返回稳定的 `decision_id` / `state_version`
- `GET /actions` 能返回当前 legal actions 集合
- `POST /apply` 能接受合法动作并推进到下一窗口
- 旧 `decision_id` 会被拒绝为 `stale_decision`
- `terminal` 窗口没有 legal actions

## 执行方式

```bash
dotnet build mod/Sts2Mod.StateBridge.sln
python tools/validate_mod_bridge.py
```

## 当前边界

- 该脚本仍基于 `fixture`，用于快速回归协议与写接口行为。
- 真实 `in-game-runtime` 仍建议按 `docs/sts2-mod-local-development.md` 中的手工流程联调。
- 若后续补充 `HttpGameBridge`，可直接复用本脚本中的请求顺序扩展为端到端 agent 验证。

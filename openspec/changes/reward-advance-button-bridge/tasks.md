## 1. Bridge 识别与动作导出

- [x] 1.1 在 `mod/Sts2Mod.StateBridge/Providers/Sts2RuntimeReflectionReader.cs` 中识别 reward 收尾“前进/继续”窗口，并为其设置可区分的 `window_kind` / diagnostics。
- [x] 1.2 为 reward 收尾窗口导出可执行 legal action，并在 `/apply` 后返回可区分的 continue/advance metadata。
- [x] 1.3 调整 reward 完成到地图出现之间的 phase / metadata 推进逻辑，避免稳定导出 `rewards=[]` 且 `actions=[]` 的空 reward 窗口。

## 2. Runner 与验证链路

- [x] 2.1 在 `src/sts2_agent/orchestrator.py` 中补充 reward 收尾前进窗口的处理逻辑，优先执行 continue/advance 动作并继续等待地图出现。
- [x] 2.2 调整 live 验证脚本与相关 diagnostics，把空 reward 卡死视为失败，并覆盖 reward continue -> map 链路。
- [x] 2.3 如有必要，补充 trace / summary 字段，明确记录 reward 收尾窗口、前进动作提交与进入地图结果。

## 3. 测试与联调

- [x] 3.1 补充 C# 测试，覆盖 reward 收尾前进窗口识别、动作导出与地图推进语义。
- [x] 3.2 补充 Python 测试，覆盖 runner 对 reward continue/advance 动作的自动处理与失败分支。
- [x] 3.3 在真实游戏中完成至少一次 reward 收尾 -> 前进 -> map 的 live 验证，并整理 artifacts / 文档说明。

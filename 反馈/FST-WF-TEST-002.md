# FST AI 测试工作流 — 运行测试报告 #001

| 项目 | 值 |
|------|----|
| **报告编号** | FST-WF-TEST-002 |
| **测试日期** | 2026-07-17 ~ 2026-07-20 |
| **工作流 ID** | 20260717_124300 |
| **测试目标** | threadpool 模块 |
| **测试方式** | 手动触发 (`/test-analyze threadpool`) |
| **工作流版本** | integrate-workflow 分支 |
| **结论** | ⚠️ 流程可跑通，但存在 8 个问题需修复 |

---

## 一、执行概况

| 阶段 | 结果 | 耗时 |
|------|------|------|
| 步骤 0 环境检查 | ✅ 通过 | ~3 min |
| 步骤 1 变更检测 | ✅ 4 文件, 3 函数 | ~4 min |
| 步骤 2 影响分析 | ✅ 8 个唯一函数 | ~5 min |
| 步骤 3 测试评估 | ✅ 全部 new | ~5 min |
| 步骤 4 测试生成 | ✅ 20 文件 (含多次重试) | ~35 min |
| 步骤 5 编译修复 | ✅ 2 轮, 全部通过 | ~5 min |
| 步骤 6 测试执行 | ⚠️ 190/190 通过，但阻塞近 3 天 | ~84 min 活跃 |
| 步骤 6.5 失败分析 | ✅ 3 缺陷 | ~5 min |
| 步骤 7 覆盖率 | ⚠️ 数据未落地 | — |
| 步骤 8 覆盖率补充 | ⚠️ 2 轮，分支 75% 未达标 | — |
| 步骤 9 报告 | ❌ 报告全 0，数据未写入 | — |

**Token 消耗**: orchestrator 131,758 (含 30+ 子 Agent，总量不可聚合统计)
**总耗时**: ~2.5 小时活跃 + ~3 天阻塞（service bug 导致人工介入）

---

## 二、发现的问题

### P0 — 阻断性问题

#### P0-1: `test_results.json` 未写入 state 目录

| 项 | 内容 |
|----|------|
| **阶段** | 步骤 6 → 步骤 9 |
| **现象** | 报告生成时测试总数/通过/失败/跳过均为 0 |
| **根因** | orchestrator 执行了测试，但结果只存在于 SendMessage 内存中，从未落地为 `ai_workflow/state/test_results.json`。`report_generator.py` 第 44 行读取该文件失败，fallback 到 0 值 |
| **影响** | 报告完全不可用，丢失 190 条测试结果 |
| **修复建议** | orchestrator 步骤 6 末尾增加强制校验：`test_results.json` 不存在或 `total==0` → 重试 `test_runner.py --output` → 仍失败则暂停报告 |

#### P0-2: `coverage_report.json` 未写入 state 目录

| 项 | 内容 |
|----|------|
| **阶段** | 步骤 7 → 步骤 9 |
| **现象** | 报告覆盖率全 0%（语句 0%、分支 0%），尽管原始 `.gcda` 文件和 `coverage.info` 已生成 |
| **根因** | 同 P0-1。`coverage.py` 可能只采集了原始数据，没有生成 `--output` 指定的结构化 JSON；或 orchestrator 未调用该步骤 |
| **证据** | `ai_workflow/state/coverage/` 下存在 `coverage.info` + `.gcda` 文件，但 `ai_workflow/state/coverage_report.json` 不存在 |
| **影响** | 覆盖率数据完全丢失（实际语句 100%、分支 75%） |
| **修复建议** | 同 P0-1，步骤 7 末尾校验 `coverage_report.json` 存在且非空 |

#### P0-3: PostToolUse Hook 静默失败

| 项 | 内容 |
|----|------|
| **阶段** | 任何 Edit/Write 到 service/*.cpp/.h |
| **现象** | 编辑 `task_queue.cpp` 后，hook 不创建 `trigger.flag`，不弹出 `/test-analyze` 建议 |
| **根因** | `settings.json` hook 脚本引用了 `$TOOL_INPUT_FILE_PATH`，该变量不存在于 Claude Code hook 环境。变量展开为空 → grep 不匹配 → `&&` 短路 → 静默失败 |
| **影响** | 自动触发机制完全失效 |
| **修复** | ✅ 已修复。改用 `$CLAUDE_TOOL_INPUT` (JSON) + python3 提取 `file_path` |

---

### P1 — 严重影响

#### P1-1: Orchestrator 步骤 6.5 遇到 service_bug 时误暂停

| 项 | 内容 |
|----|------|
| **阶段** | 步骤 6 → 步骤 6.5 |
| **现象** | 发现 `push()` 递归锁死锁（service_bug）后，orchestrator 暂停等待用户确认"是否修改 service 代码"，而非按 6.5 #3 规则生成报告后继续步骤 7 |
| **根因** | 三处指令冲突：<br>① 步骤 6.5 #3 规定 service_bug → 生成报告 → **继续步骤 7**<br>② 铁律 #5 规定 "遇阻即停…等待用户决策"<br>③ 禁止清单 #7 规定 "不确认不修改 service 代码"<br>Orchestrator 判断"死锁导致 80% 测试无法执行，继续覆盖率无意义"，铁律 #5 优先级高于 6.5 #3 |
| **影响** | 工作流暂停 ~3 天，需人工介入。正确的行为应该是生成报告后继续，不应阻塞 |
| **修复建议** | ① 步骤 6.5 #3 加显式豁免："此时 **不暂停**，生成报告后直接进入步骤 7"<br>② 铁律 #5 加例外条件："（service_bug 生成报告后除外）"<br>③ 或将禁止清单 #7 限定作用域（不覆盖 service_bug 报告流程） |

#### P1-2: CTest 粒度过细导致测试执行脆弱

| 项 | 内容 |
|----|------|
| **阶段** | 步骤 6 |
| **现象** | 204 个 CTest 测试（每个 gtest case 一个独立调用），导致：<br>① 死锁时 8 个进程同时卡住，CTest 无限等待<br>② 启动开销巨大（每个 case 启动一次二进制）<br>③ 无法按 suite 聚合结果 |
| **根因** | CMake 的 `gtest_discover_tests` 默认为每个 case 注册一个 CTest 测试。项目 20 个二进制 × 平均 ~10 case = 204 个 |
| **影响** | 测试执行脆弱，一个死锁阻塞全部；排查困难 |
| **修复建议** | ① 改为运行二进制级别（`./test_xxx --gtest_output=json`），20 个而非 204 个<br>② 或在 `test_runner.py` 中按二进制发现并运行，设置 per-binary 超时 |

---

### P2 — 中等问题

#### P2-1: test-generator Agent 生成代码含 3 个 test_bug

| 项 | 内容 |
|----|------|
| **阶段** | 步骤 4 → 步骤 6 |
| **问题用例** | ① `ClearPreservesPeakSize` — 峰值预期未考虑 `fillNormalQueue` 追加语义（队列累积 18 vs 预期 15）<br>② `clearQueue_PeakSizeOnlyIncreases` — 同上<br>③ `ConcurrentPushAndClear_*_NoCrash` — clear()/size() 间 TOCTOU 竞态 |
| **根因** | test-generator 只读了被测函数源码，未充分理解 test fixture 中 helper 函数（`fillNormalQueue`）的累积语义；并发测试中低估了 TOCTOU 窗口 |
| **影响** | 3 个误报失败，消耗步骤 6.5 分析资源 |
| **修复建议** | test-generator prompt 加约束："生成前先读 helper 函数（fill*）实现，理解 fixture 状态累积；并发测试用 atomic/barrier 保护竞态窗口" |

#### P2-2: 覆盖率补充循环 2 轮后仍未达标，但无法区分"不可达路径"和"测试不足"

| 项 | 内容 |
|----|------|
| **阶段** | 步骤 8 |
| **现象** | 分支覆盖率 75%（目标 80%），2 轮补充后无提升。orchestrator 判定剩余分支为"不可达异常路径"，记录警告后继续 |
| **根因** | `coverage-supplementer` 无法区分"代码可达但未测"和"代码不可达（异常退出路径）" |
| **影响** | 2 轮补充未提升覆盖率，属于浪费。但流程正确限制了上限退出 |
| **修复建议** | ① 补充前先由 analyzer 标记不可达分支，排除后重新计算目标值<br>② 或第二轮回退判定时，给出具体哪些分支被判断为不可达 |

---

### P3 — 轻微问题

#### P3-1: test-generator Agent 模型不可用时需多次重试

| 项 | 内容 |
|----|------|
| **阶段** | 步骤 4 |
| **现象** | `peakSize` 重试 3 次，`main` 重试 2 次，`TaskQueue::clear` 集成重试 1 次 |
| **根因** | 模型服务暂时不可用 |
| **影响** | 增加总耗时 ~15 分钟 |
| **修复建议** | 增加降级策略：主模型不可用 → 自动切换 fallback 模型重试 |

---

## 三、问题汇总

| 编号 | 严重度 | 类别 | 状态 | 标题 |
|------|--------|------|------|------|
| P0-1 | 🔴 P0 | 数据丢失 | ❌ 待修复 | `test_results.json` 未写入 state 目录 |
| P0-2 | 🔴 P0 | 数据丢失 | ❌ 待修复 | `coverage_report.json` 未写入 state 目录 |
| P0-3 | 🔴 P0 | 机制失效 | ✅ 已修复 | PostToolUse Hook 静默失败 |
| P1-1 | 🟠 P1 | 流程逻辑 | ❌ 待修复 | service_bug 时误暂停而非继续 |
| P1-2 | 🟠 P1 | 工程效率 | ❌ 待修复 | CTest 粒度过细 |
| P2-1 | 🟡 P2 | 生成质量 | ❌ 待修复 | test-generator 生成 3 个 test_bug |
| P2-2 | 🟡 P2 | 覆盖率 | ❌ 待修复 | 覆盖率补充无法排除不可达分支 |
| P3-1 | 🔵 P3 | 稳定性 | ❌ 待修复 | 模型不可用需多次重试 |

---

## 四、验证通过项

以下行为符合工作流预期，无需修改：

| 项 | 描述 |
|----|------|
| ✅ 编译修复循环 | 优先级排序有效，2 轮即修复全部错误 |
| ✅ 失败分析判定 | `ConcurrentMultipleStop` 正确判定为 service_bug（数据竞争），未被误判为 test_bug |
| ✅ 覆盖率补充循环上限 | 2 轮后正确停止，未无限循环 |
| ✅ Agent 分批评级 | 8 函数 × 3 类型分 3 批执行，流程受控 |
| ✅ service_bug_report 生成 | 2 个缺陷结构化输出，含代码位置、根因、修复建议 |

---

> 📅 报告生成: 2026-07-21 | 下次测试编号: FST-WF-TEST-003

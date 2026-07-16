---
name: test-analyze
description: AI驱动的C++测试分析工作流 — 分析代码变更影响，生成/改造测试，编译验证，覆盖率分析
argument: 可选的模块名（如 payment）或文件路径。不指定则自动检测 git diff 中的变更。
---

# /test-analyze — AI驱动的C++测试分析工作流

当你修改了 `service/` 下的 C++ 代码后，运行此命令启动完整的测试分析流程。

## 使用方法

```
/test-analyze                  # 自动检测 git diff 中的变更
/test-analyze payment          # 分析指定模块 payment
/test-analyze service/payment/transaction.cpp  # 分析指定文件
```

## 执行指令

**启动 test-orchestrator Agent 执行完整 10 步工作流：**

```
Agent({
  subagent_type: "test-orchestrator",
  description: "执行 FST 测试分析工作流",
  prompt: "用户参数: $ARGUMENTS。
触发方式: {如果 state/trigger.flag 存在则为 auto，否则为 manual}。
请严格按照 10 步工作流执行，每步完成后校验数据并向主对话报告进度。
遇到无法自动解决的问题时暂停，等待用户决策。"
})
```

**Agent 执行期间你的职责：**
1. 接收 Agent 通过 SendMessage 发来的进度报告，翻译给用户
2. Agent 暂停询问时，将问题清晰呈现给用户，等待用户输入后发送给 Agent（用 SendMessage）
3. Agent 完成时，向用户展示最终报告路径和关键摘要
4. **不要**在 Agent 执行期间自行执行工作流步骤（Agent 会全权处理）
5. **不要**在主对话中直接生成测试代码

## 相关命令

| 命令 | 用途 |
|------|------|
| `/test-analyze` | 完整 10 步工作流（含测试生成） |
| `/test-quick` | 快速验证（只跑已有测试 + 覆盖率，≤6 步） |
| `/test-coverage` | 只看覆盖率（≤4 步） |

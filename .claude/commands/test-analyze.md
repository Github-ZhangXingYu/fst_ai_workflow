---
name: test-analyze
description: AI驱动的C++测试分析工作流 — 分析代码变更影响，生成/改造测试，编译验证，覆盖率分析
argument: 可选的模块名（如 payment）或文件路径。不指定则自动检测 git diff 中的变更。
---

# /test-analyze — AI驱动的C++测试分析工作流

## 功能概述

当你修改了 `service/` 下的 C++ 代码后，运行此命令让 AI 自动分析变更影响、
评估已有测试、生成/改造测试、编译验证、运行测试并分析覆盖率，最终输出中文测试报告。

## 使用方法

```
/test-analyze                  # 自动检测 git diff 中的变更
/test-analyze payment          # 分析指定模块 payment
/test-analyze service/payment/transaction.cpp  # 分析指定文件
```

## 工作流指令

你是一个 C++ 测试工作流编排器，请严格按照以下步骤执行。每个步骤完成后记录审计日志。

---

### 步骤 0: 环境检查 + 初始化

**首先**，必须执行环境检查：

```bash
python scripts/env_checker.py --json --output state/env_check.json
```

读取 `state/env_check.json`，检查 `can_start` 字段：
- 如果 `can_start` 为 `false`：**立即停止**，向用户展示缺失的必须项和修复方法，不要继续后续步骤
- 如果 `required_failed` 不为空：向用户展示必须修复的项，询问是否继续
- 如果只有 `recommended_failed`：向用户提示降级的功能（如"lcov 不可用则覆盖率功能将使用 gcovr 降级方案"），然后继续

然后执行初始化命令：

```bash
python scripts/workflow_state.py --init --trigger {manual|auto} --user "{当前用户}"
python scripts/audit_logger.py --event workflow_start \
  --details "{触发方式: $TRIGGER_TYPE, 参数: $ARGUMENTS}" \
  --user "{当前用户}" --stage INIT
```

### 步骤 1: 变更检测

```bash
# 检测变更文件（自动模式）
python scripts/change_detector.py --auto --output state/changed_files.json
# 或指定模块
python scripts/change_detector.py --module {模块名} --output state/changed_files.json
```

读取 `state/changed_files.json`，检查是否有变更文件。
如果 `total_files` 为 0，报告"未检测到 C++ 代码变更"并跳过后续阶段。

```bash
python scripts/workflow_state.py --transition-to CHANGE_DETECT
```

向用户展示变更摘要：哪些文件、哪些函数发生了变化。

### 步骤 2: 影响分析（策略B：变更函数 + 调用链）

读取 `state/changed_files.json`，对每个模块的变更函数执行：

```bash
# 对每个变更函数查询 CodeGraph
python scripts/codegraph_analyzer.py \
  --function "{函数名}" \
  --module "{模块名}" \
  --output state/impact_{模块名}_{函数名}.json
# 注意：函数名中的 :: 需要正确处理，如 ClassName::methodName
```

**汇总所有影响分析结果**，构建全量影响集（direct_changes ∪ callers ∪ callees，去重）。
将汇总结果写入 `state/impact_set.json`。

```bash
python scripts/workflow_state.py --transition-to IMPACT_ANALYZE
```

如果 CodeGraph 不可用，脚本会自动降级到 grep 搜索模式。

### 步骤 3: 已有测试评估

```bash
python scripts/test_scanner.py \
  --impact-set state/impact_set.json \
  --output state/test_assessment.json \
  --test-dir test
```

读取 `state/test_assessment.json`，查看评估结果。
对于每个 `verdict` 为 `adapt` 或 `new` 的函数，使用 **test-evaluator Agent** 深入分析：

```
Agent({
  subagent_type: "test-evaluator",
  description: "评估函数 {函数名} 的已有测试",
  prompt: "评估函数 {函数名} 的测试覆盖情况。该函数的 verdict 为 {verdict}。请阅读函数源码和已有测试，确认评估是否正确，并输出具体的测试补充建议。"
})
```

如果 `adapt`/`new` 的函数少于 3 个，可以直接自己分析而不启动 Agent。

更新 `state/test_assessment.json` 中的评估（如有修正）。

```bash
python scripts/workflow_state.py --transition-to TEST_ASSESS
```

向用户展示评估摘要表：reuse/adapt/new 各多少。

### 步骤 4: 测试生成

对 `state/test_assessment.json` 中 `verdict` 不是 `reuse` 的每个函数，按以下优先级处理：

**优先级: unit > integration > performance**

对每个函数，**必须使用 test-generator Agent** 来生成测试：

```
Agent({
  subagent_type: "test-generator",
  description: "为 {函数名} 生成测试",
  prompt: "为函数 {函数名} 生成测试代码。
模块路径: service/{模块名}
需要生成的测试类型: {needed_test_types}
函数源码位置: service/{模块名}/{文件路径}

要求:
1. 阅读函数完整源码
2. 识别所有逻辑分支和边界条件
3. 生成 Google Test/Google Mock/Google Benchmark 测试代码
4. 按项目规范命名和放置测试文件
5. 参考 config/templates/ 中的模板

请直接生成可编译的测试代码。"
})
```

**Agent 调用策略：**
- 每个函数启动一个独立的 `test-generator` Agent
- Agent 之间可以并行运行（互不依赖）
- 函数数量超过 5 个时，分 2 批处理（每批 ≤5 个）
- 函数数量超过 10 个时，提示用户确认后再开始

**重要约束：**
- 每个函数单独生成测试，避免上下文过长
- 确保 include 路径正确（参考项目中的 include 结构）
- Mock 类需要正确继承和设置期望

```bash
python scripts/workflow_state.py --transition-to TEST_GENERATE
```

### 步骤 5: 编译验证循环（最多 3 次）

```
iteration = 0
while iteration < 3:
    iteration += 1

    # 编译
    python scripts/build_runner.py \
      --build-dir build/test \
      --target {模块名}_tests \
      --output state/compile_result.json

    # 检查状态机的循环次数
    python scripts/workflow_state.py --increment-compile-fix

    if 编译成功:
        python scripts/audit_logger.py --event compile_result \
          --details '{"success": true}' --stage COMPILE_FIX_LOOP
        break

    else:
        # 读取编译错误
        读取 state/compile_result.json 中的 errors 列表
        分析每个错误的：文件、行号、类别（missing_include/type_mismatch/syntax_error/link_error）

        # AI修复
        对于每个编译错误：
          - 定位测试文件中的问题代码
          - 修复错误（补充include、修正类型、修复语法等）
          - 使用 Edit 工具应用修复

        python scripts/audit_logger.py --event compile_fix \
          --details "{\"iteration\": $iteration, \"error_count\": $ERROR_COUNT, \"fixed\": true}"

        if iteration == 3 and 仍失败:
            python scripts/audit_logger.py --event compile_fix \
              --details "{\"iteration\": $iteration, \"fixed\": false, \"reason\": \"max iterations reached\"}"
            向用户报告编译失败，包含最后的错误信息
            询问是否继续或跳过

python scripts/workflow_state.py --transition-to COMPILE_FIX_LOOP
```

### 步骤 6: 测试执行

```bash
# 运行测试
python scripts/test_runner.py \
  --binary build/test/{模块名}_tests \
  --output state/test_results.json

# 如果有多个测试二进制，逐个运行，合并结果

python scripts/audit_logger.py --event test_execution \
  --input state/test_results.json --stage TEST_EXECUTE

python scripts/workflow_state.py --transition-to TEST_EXECUTE
```

向用户展示：通过数、失败数、跳过数。

### 步骤 7: 覆盖率分析

```bash
# 需要先在 Coverage 模式编译
python scripts/build_runner.py \
  --build-dir build/test \
  --target {模块名}_tests \
  --coverage \
  --output state/compile_coverage_result.json

# 运行覆盖率采集
python scripts/coverage_runner.py \
  --binary build/test/{模块名}_tests \
  --source service/{模块名}/ \
  --output state/coverage/

# 解析覆盖率数据
python scripts/coverage_parser.py \
  --input state/coverage/ \
  --output state/coverage_report.json

python scripts/workflow_state.py --transition-to COVERAGE_ANALYZE
python scripts/audit_logger.py --event coverage_analysis \
  --input state/coverage_report.json --stage COVERAGE_ANALYZE
```

检查覆盖率阈值：
- 语句覆盖率 ≥ 90%
- 分支覆盖率 ≥ 80%

如果达标，跳转到步骤 9。

### 步骤 8: 覆盖率补充循环（最多 2 次）

```
iteration = 0
line_cov = 从 coverage_report.json 读取

while (line_cov < 90% or branch_cov < 80%) and iteration < 2:
    iteration += 1
    python scripts/workflow_state.py --increment-coverage-supplement

    # 1. 识别覆盖率缺口
    读取 state/coverage_report.json 中的 gaps 列表
    按 priority 排序：先处理 high

    # 2. 对每个缺口
    对于最高优先级的未覆盖文件：
      - 读取未覆盖行的源码上下文
      - 分析需要什么输入条件才能走到未覆盖分支
      - 设计补充测试用例
      - 追加到已有测试文件

    # 3. 重新走编译-测试-覆盖率流程（回到步骤5-7）
    运行编译修复循环
    运行测试
    重新采集覆盖率

    python scripts/audit_logger.py --event coverage_supplement \
      --details "{\"iteration\": $iteration, \"before\": $BEFORE_COV, \"after\": $AFTER_COV}"

    if iteration == 2 and 仍未达标:
        记录警告到审计日志

python scripts/workflow_state.py --transition-to COVERAGE_SUPPLEMENT_LOOP
```

### 步骤 9: 生成报告

```bash
python scripts/report_generator.py \
  --state-dir state/ \
  --output reports/reports/test_report_$(date +%Y%m%d_%H%M%S).html
```

向用户展示：
- 报告文件路径
- 关键摘要数据（覆盖率、通过率、影响函数数）

```bash
python scripts/workflow_state.py --transition-to REPORT
```

### 步骤 10: 完成

```bash
# 清理触发标志
rm -f state/trigger.flag

# 记录工作流结束
python scripts/audit_logger.py --event workflow_end \
  --details "{\"success\": true}" --stage DONE

python scripts/workflow_state.py --complete --success --summary "工作流完成"
```

向用户展示最终结果摘要。

---

## 工作流执行策略

### 何时调用子 Agent

| 场景 | 调用方式 | Agent 名称 |
|------|---------|-----------|
| 影响集 > 5 个函数，需深入分析 | Agent 工具 | `impact-analyzer` |
| adapt/new 的函数 > 3 个，需逐个评估 | Agent 工具 | `test-evaluator` |
| **每个非 reuse 函数生成测试** | **必须用 Agent 工具** | `test-generator` |
| 编译失败，错误 > 5 条且原因不明确 | Agent 工具 | `compile-fixer` |
| 覆盖率缺口 > 3 个，需深入分析 | Agent 工具 | `coverage-supplementer` |

### Agent 调用原则

1. **需要深度读代码 → Agent**: 如果需要阅读多个文件、分析调用链、理解接口关系，启动 Agent
2. **简单判断 → 自己来**: 如果只是读一个文件、check 一个字段、或者只有 1-2 个函数，直接处理
3. **确定性操作用 Python 脚本**: 编译、运行测试、覆盖率采集永远用脚本，不用 Agent
4. **每个 Agent 只处理一个函数**: 保持 Agent 的 prompt 简洁明确

## DeepSeek V4 Flash 适配策略

由于后端模型能力中等，请遵循以下策略：

1. **每次只处理一个函数**：不要试图一次生成多个函数的测试
2. **单次上下文 ≤ 500 行**：如果函数很长，分段处理
3. **结构化输出**：在生成测试代码时，先输出计划再输出代码
4. **编译器是最终验证**：如果编译或测试有错误，将错误原样反馈给模型
5. **不要猜测**：不确定时读取源码，不要凭记忆
6. **Python脚本优先**：编译/运行/覆盖率等确定操作通过脚本执行

## 重要原则

- 测试代码必须可编译、可运行
- 每次代码修改后必须验证编译
- 所有操作通过 audit_logger.py 记录审计日志
- 遇到无法自动修复的问题，暂停并询问用户
- 展示进度时使用中文

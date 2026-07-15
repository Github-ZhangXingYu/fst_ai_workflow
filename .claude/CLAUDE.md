# FST AI测试工作流 — 项目规则

## 项目概述

FST（同花顺期货通）是一个 C++14 微服务后端项目，部署在内网 Linux 服务器上。
本项目提供了由 Claude Code 驱动的 AI 测试工作流框架。

## 技术栈

- **语言**: C++14
- **构建**: CMake 3.10+
- **测试**: Google Test (gtest), Google Mock (gmock), Google Benchmark
- **覆盖率**: gcov + lcov
- **静态分析**: clang-tidy
- **调用图**: CodeGraph
- **工作流脚本**: Python 3.8+

## 目录结构

```
fst/                              # 项目根目录（也是 git 仓库根目录）
├── .claude/                      # Claude Code 配置
│   ├── settings.json             # Hook 自动触发配置
│   ├── CLAUDE.md                 # 项目规则（本文件）
│   ├── commands/                 # Slash 命令（Skills）
│   └── agents/                   # 自定义子 Agent
├── scripts/                      # Python 确定性操作脚本
├── config/                       # 配置和模板
│   ├── workflow_config.json
│   └── templates/                # C++ 测试模板
├── state/                        # 工作流运行时状态
├── reports/                      # 输出报告和审计日志
├── service/                      # 微服务模块源码
│   └── <module>/
└── test/                         # 测试代码
    └── <module>/
        ├── unit/
        ├── integration/
        ├── performance/
        └── tools/
```

## 测试规则

1. **框架**: 所有测试必须使用 Google Test 框架编写
2. **Mock**: 集成测试中的外部依赖必须使用 Google Mock 模拟
3. **性能**: 性能测试使用 Google Benchmark
4. **命名规范**: 测试用例命名遵循 `<FunctionName>_<Scenario>_<ExpectedBehavior>` 格式
5. **文件头注释**: 每个测试文件必须包含文件头注释，说明测试目标和覆盖范围
6. **覆盖目标**: 语句覆盖率 ≥ 90%，分支覆盖率 ≥ 80%

## 测试分类

| 类型 | 目录 | 框架 | 说明 |
|-----|------|------|------|
| 单元测试 | `test/<模块>/unit/` | Google Test | 测试单个函数/类的独立行为 |
| 集成测试 | `test/<模块>/integration/` | Google Test + Mock | 测试组件间协作，Mock 外部依赖 |
| 性能测试 | `test/<模块>/performance/` | Google Benchmark | 测试关键路径的性能指标 |
| 测试工具 | `test/<模块>/tools/` | - | 测试辅助代码、Mock 实现 |

## AI 测试工作流规则

### 触发方式
1. **手动触发**: 运行 `/test-analyze [模块名|文件路径]`
2. **自动触发**: 修改 `service/` 下的 C++ 文件后，系统自动建议运行测试分析

### 工作流阶段
```
INIT → CHANGE_DETECT → IMPACT_ANALYZE → TEST_ASSESS → TEST_GENERATE
  → COMPILE_FIX_LOOP (≤3次) → TEST_EXECUTE → COVERAGE_ANALYZE
  → COVERAGE_SUPPLEMENT_LOOP (≤2次) → REPORT → DONE
```

### 循环控制
- **编译修复循环**: 最多 3 次迭代。第 3 次仍失败则暂停并报告用户
- **覆盖率补充循环**: 最多 2 次迭代。未达标则记录警告并继续

### 审计要求
- 所有工作流事件通过 `scripts/audit_logger.py` 记录到 `reports/audit/audit_log.jsonl`
- 每个事件包含: timestamp, user, event, stage, details, result

## 质量规则

1. 生成的测试代码必须可编译、可运行
2. 所有 Mock 对象必须正确设置期望
3. 测试用例必须覆盖: 正常路径、边界条件、错误路径
4. 性能测试必须包含基准数据并多次迭代
5. 生成的代码在应用前需要验证（检查语法基本正确性）

## 协作规则

- **确定性操作交给 Python**: 编译、运行测试、覆盖率采集等使用 Python 脚本
- **推理任务交给 AI**: 代码分析、测试设计、错误修复等使用 AI 判断
- **每个 AI 子任务聚焦单一目标**: 每次只处理一个函数或一个编译错误，避免上下文过长
- **遇到无法自动解决的问题**: 清晰地向用户报告错误并建议下一步操作

## 环境变量

| 变量 | 说明 | 默认值 |
|-----|------|--------|
| `CODEGRAPH_CMD` | CodeGraph CLI 命令 | `codegraph` |
| `FST_BUILD_DIR` | CMake 构建目录 | `build/test` |
| `FST_SERVICE_DIR` | 服务源码目录 | `service` |
| `FST_TEST_DIR` | 测试目录 | `test` |

---
name: test-coverage
description: FST 覆盖率分析 — 对指定模块重编译、运行测试并采集覆盖率，不生成任何测试
argument: 模块名（必填，如 payment）
---

# /test-coverage — 覆盖率分析

针对指定模块重新采集代码覆盖率数据。

## 使用方法

```
/test-coverage payment
```

## 执行指令

### 1. 环境检查
```bash
python ai_workflow/scripts/env_checker.py --json --output ai_workflow/state/env_check.json
```
如果 `can_start` = false，立即停止。

### 2. Coverage 模式编译
```bash
python ai_workflow/scripts/build_runner.py --build-dir build/test --target $ARGUMENTS\_tests --coverage --output ai_workflow/state/compile_coverage_result.json
```
编译失败 → 修复 → 重编译。最多 2 次。

### 3. 运行测试 + 采集覆盖率
```bash
python ai_workflow/scripts/coverage_runner.py --binary build/test/$ARGUMENTS\_tests --source service/$ARGUMENTS/ --output ai_workflow/state/coverage/
```

### 4. 解析并展示
```bash
python ai_workflow/scripts/coverage_parser.py --input ai_workflow/state/coverage/ --output ai_workflow/state/coverage_report.json --summary
```

向用户展示：
- 语句覆盖率 %（目标 ≥90%）
- 分支覆盖率 %（目标 ≥80%）
- 函数覆盖率 %
- 覆盖率缺口 Top-5
- HTML 报告位置（如已生成）

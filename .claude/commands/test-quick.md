---
name: test-quick
description: FST 快速测试 — 编译并运行已有测试 + 覆盖率分析。不生成新测试，适合日常迭代快速验证
argument: 模块名（如 payment）。不指定则自动检测变更模块
---

# /test-quick — 快速测试验证

当你只需验证代码改动没有破坏已有测试时使用。**不会生成新测试。**

## 使用方法

```
/test-quick          # 自动检测变更模块
/test-quick payment  # 指定模块
```

## 执行指令

按以下步骤执行（**不生成任何新测试代码**）：

### 1. 环境检查
```bash
python ai_workflow/scripts/env_checker.py --json --output ai_workflow/state/env_check.json
```
如果 `can_start` = false，立即停止并报告缺失项。

### 2. 变更检测
```bash
python ai_workflow/scripts/change_detector.py {--auto | --module $ARGUMENTS} --output ai_workflow/state/changed_files.json
```
如果 `total_files` = 0，报告"未检测到变更"并结束。

### 3. 编译测试

FST 编译惯例：`mkdir -p build && cd build && cmake .. <options> && make -j8 <target>`
测试二进制输出到 `product/bin/unittest/` 下。

先读 CMakeLists.txt 找到正确的 cmake 选项和测试 target 名，然后：

```bash
# --build-dir 是 build/，--cmake-options 传递 CMakeLists.txt 中的自定义选项
python ai_workflow/scripts/build_runner.py --build-dir build --target {make目标名} --output ai_workflow/state/compile_result.json
```

如果编译失败：分析错误 → 修复 → 重编译。最多 3 次。

### 4. 运行测试
```bash
# 测试二进制在 product/bin/unittest/ 下
python ai_workflow/scripts/test_runner.py --binary product/bin/unittest/{测试二进制名} --output ai_workflow/state/test_results.json
```

### 5. 覆盖率分析
```bash
python ai_workflow/scripts/build_runner.py --build-dir build --target {make目标名} --coverage --output ai_workflow/state/compile_coverage_result.json
python ai_workflow/scripts/coverage.py --binary product/bin/unittest/{测试二进制名} --source service/{模块名}/ --build-dir build --output ai_workflow/state/coverage_report.json
```

### 6. 展示结果摘要
向用户展示：
- 测试通过/失败/跳过数量
- 语句覆盖率 %
- 分支覆盖率 %
- 是否达标

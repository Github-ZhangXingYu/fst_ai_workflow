# ThreadPool 测试工作流 — 环境搭建记录

> 记录时间：2026-07-17  
> 机器环境：CentOS Stream 9 (x86_64)，离线→在线混合安装

---

## 一、初始状态

### 已就绪的必须工具

| 工具 | 版本 | 位置 | 说明 |
|------|------|------|------|
| python3 | 3.9.25 | `/usr/bin/python3` | 系统自带 |
| cmake | 3.31.8 | `/usr/bin/cmake` | 系统自带 |
| g++ | 11.5.0 | `/usr/bin/g++` | 系统自带，随 GCC 11.5.0 |
| git | 2.52.0 | `/usr/bin/git` | 系统自带 |
| make | 4.3 | `/usr/bin/make` | 系统自带 |
| gcov | 11.5.0 | `/usr/bin/gcov` | **随 g++ 捆绑安装，无需额外操作** |
| GTest | 1.15.2 | `build/lib/libgtest.a` | CMake FetchContent 自动下载编译 |
| node | 20.20.2 | `/usr/bin/node` | 系统已安装 |
| npm | 10.8.2 | `/usr/bin/npm` | 系统已安装 |

### 缺失的工具

| 工具 | 影响 | 缺失原因 |
|------|------|----------|
| lcov + genhtml | 🔴 覆盖率分析完全不可用 | 未安装，不在默认仓库 |
| clang-tidy | 🟡 静态分析跳过 | 未安装 |
| Google Benchmark | ⚪ 性能测试不可用 | 未安装 |
| codegraph | 🟡 调用图分析降级为 grep | 未安装，npm 包名变更 |
| GMock | 🟡 mock 库未编译 | CMakeLists.txt 中 `BUILD_GMOCK OFF` |

---

## 二、安装过程

### 前置：配置 EPEL 仓库

```bash
sudo dnf config-manager --set-enabled crb
sudo dnf install -y epel-release
```

CentOS Stream 9 默认不带 lcov 和 Google Benchmark，需要 EPEL（Extra Packages for Enterprise Linux）。

### 2.1 lcov + genhtml（覆盖率工具）

```bash
sudo dnf install -y lcov
```

- **版本**：1.14-6.el9
- **来源**：EPEL 仓库
- **包含**：`lcov` 和 `genhtml`（同一个包）
- **依赖链**：perl-JSON, perl-GD, gd, fontconfig, freetype 等 27 个包（总下载 5.5MB）
- **验证**：`lcov --version` → `LCOV version 1.14`

### 2.2 clang-tidy（静态分析）

```bash
sudo dnf install -y clang-tools-extra
```

- **版本**：22.1.3-1.el9
- **来源**：CentOS Stream 9 AppStream 仓库
- **依赖链**：llvm-libs → clang-libs → clang → clang-tools-extra，以及 gcc-toolset-15 等 26 个包（总下载 220MB）
- **验证**：`clang-tidy --version` → `LLVM version 22.1.3`

### 2.3 Google Benchmark（性能测试）

```bash
sudo dnf install -y google-benchmark google-benchmark-devel
```

- **版本**：1.8.5-9.el9
- **来源**：EPEL 仓库
- **库文件**：`/usr/lib64/libbenchmark.so`、`/usr/lib64/libbenchmark_main.so`
- **头文件**：`/usr/include/benchmark/benchmark.h`
- **验证**：`pkg-config --modversion benchmark` → `1.8.5`

### 2.4 codegraph（调用图分析）

```bash
npm install -g @colbymchenry/codegraph
```

- **版本**：1.4.1
- **来源**：npm 公网 registry
- **二进制**：`/usr/bin/codegraph`（全局 symlink）
- **为什么不用 `@codegraph-ai/cli`**：该包在 npm 公网上不存在，`env_checker.py` 中引用的包名已失效。`@colbymchenry/codegraph` 是功能等价的替代品（"Local-first code intelligence for AI agents"）。
- **验证**：`codegraph --version` → `1.4.1`

#### 项目索引初始化

```bash
codegraph init /home/zhangxingyu/projects7/threadpool
```

- 索引结果：14 文件、230 节点、399 边
- 索引数据存储在 `.codegraph/` 目录

### 2.5 GMock（启用编译）

**问题**：CMakeLists.txt 第 46 行设置了 `BUILD_GMOCK OFF`，导致 Google Mock 库未被编译，只有头文件可用。

**修改**：

```cmake
# 修改前
set(BUILD_GMOCK OFF CACHE INTERNAL "")

# 修改后
set(BUILD_GMOCK ON CACHE INTERNAL "")
```

**重新编译**：

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Debug -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
make -j8 -C build
```

**结果**：

```
build/lib/libgtest.a         (5.8M)   # 已存在
build/lib/libgtest_main.a    (106K)   # 已存在
build/lib/libgmock.a         (2.1M)   # 新编译
build/lib/libgmock_main.a    (111K)   # 新编译
```

---

## 三、脚本修改

### 3.1 修改原因

安装的 codegraph（v1.4.1）的 CLI 接口与 `codegraph_analyzer.py` 中硬编码的命令格式不兼容：

| 操作 | 脚本中的旧格式 | 实际 CLI 格式 |
|------|---------------|---------------|
| 查询调用者 | `codegraph query --callers <fn> --path <p>` | `codegraph callers <fn> -p <p> -j` |
| 查询被调用者 | `codegraph query --callees <fn> --path <p>` | `codegraph callees <fn> -p <p> -j` |
| 查询调用图 | `codegraph query --call-graph <fn> --path <p>` | 不存在，需要分别调用 callers + callees |

如果不修改，`_run_codegraph()` 会因为子命令不匹配返回 `None`，每次都走 grep 降级方案，codegraph 形同虚设。

### 3.2 修改内容

文件：`ai_workflow/scripts/codegraph_analyzer.py`

#### 修改 1：`query_callers()` 函数

```python
# 修改前
result = _run_codegraph(['query', '--callers', function_name,
                         '--path', search_path])
if result and 'callers' in result:
    return result['callers']

# 修改后
result = _run_codegraph(['callers', function_name,
                         '-p', search_path, '-j'])
if result:
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and 'callers' in result:
        return result['callers']
```

说明：
- `query --callers` 改为独立子命令 `callers`
- `--path` 改为 `-p`
- 新增 `-j` 获取 JSON 输出
- 兼容两种 JSON 格式：直接数组 `[{...}]` 或包装对象 `{"callers": [{...}]}`

#### 修改 2：`query_callees()` 函数

```python
# 修改前
result = _run_codegraph(['query', '--callees', function_name,
                         '--path', search_path])
if result and 'callees' in result:
    return result['callees']

# 修改后
result = _run_codegraph(['callees', function_name,
                         '-p', search_path, '-j'])
if result:
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and 'callees' in result:
        return result['callees']
```

修改方式与 `query_callers` 一致。

#### 修改 3：`query_call_graph()` 函数

```python
# 修改前
result = _run_codegraph(['query', '--call-graph', function_name,
                         '--path', search_path])
if result:
    return {
        'callers': result.get('callers', []),
        'callees': result.get('callees', [])
    }
return {
    'callers': query_callers(function_name, search_path),
    'callees': query_callees(function_name, search_path)
}

# 修改后
def query_call_graph(function_name: str, search_path: str) -> dict:
    return {
        'callers': query_callers(function_name, search_path),
        'callees': query_callees(function_name, search_path)
    }
```

说明：新版 codegraph 没有等价的 `--call-graph` 聚合查询，改为分别调用 callers 和 callees，然后再合并结果。旧的 `if result` 分支删除，简化逻辑。

---

## 四、最终状态

运行 `python3 ai_workflow/scripts/env_checker.py`：

```
============================================================
  FST AI 测试工作流 — 环境检查
============================================================

【必须工具】— 缺少则无法运行
----------------------------------------
  ✅ python3 — 运行工作流脚本
  ✅ cmake — 编译测试代码
  ✅ g++ (11.5.0) — C++14 编译器
  ✅ git — 检测代码变更

【项目检查】
----------------------------------------
  ✅ python_version (3.9.25)
  ✅ googletest
  ✅ compile_commands (位于 build/compile_commands.json)
  ✅ project_structure
  ✅ scripts

【推荐工具】— 缺少则部分功能降级
----------------------------------------
  ✅ lcov (1.14) — 代码覆盖率分析
  ✅ genhtml (1.14) — 生成覆盖率的 HTML 报告
  ✅ gcov (11.5.0) — 代码覆盖率数据采集
  ✅ clang-tidy (22.1.3) — C++ 静态分析
  ✅ codegraph (1.4.1) — C++ 调用图分析

【增强工具】— 缺少不影响核心功能
----------------------------------------
  ✅ gcovr — 覆盖率分析降级方案
  ✅ google-benchmark — 性能基准测试

  结论: ✅ 环境就绪，可以启动测试工作流
```

---

## 五、重要备注

1. **gcov 不需要单独安装**：它是 GCC 编译器套件的一部分，随 `g++` 自动安装，路径为 `/usr/bin/gcov`。

2. **codegraph 包名变更**：`env_checker.py` 中引用的 `@codegraph-ai/cli` 在 npm 公网上不存在，实际安装的是 `@colbymchenry/codegraph`。如果后续 `env_checker.py` 中 codegraph 检测失败，检查 `codegraph` 命令是否在 PATH 中即可，无需关心包名。

3. **codegraph 索引需要同步**：修改源码后，需运行 `codegraph sync` 更新索引（或 `codegraph init` 重建）。索引数据在 `.codegraph/` 目录。

4. **GMock 头文件始终可用**：即使 `BUILD_GMOCK OFF`，头文件也随 FetchContent 下载到了 `build/_deps/googletest-src/googlemock/include/`。改为 `ON` 是为了编译出 `libgmock.a` 和 `libgmock_main.a` 静态库，让集成测试能正确链接。

5. **Google Benchmark 的 CMakeLists.txt 未配置**：虽然系统已安装 benchmark 库（`/usr/lib64/libbenchmark.so`），但 CMakeLists.txt 中没有 `find_package(benchmark)` 或 `FetchContent` 声明。如果工作流需要编译性能测试，需要在 CMakeLists.txt 中添加：
   ```cmake
   find_package(benchmark REQUIRED)
   ```

6. **EPEL 仓库已永久配置**：通过 `epel-release` 包安装，后续 `dnf` 更新也会从 EPEL 拉取。

---

## 六、工作流试跑发现的问题

> 试跑时间：2026-07-17  
> 触发方式：`/test-analyze threadpool`（手动）  
> 工作流 ID：`20260717_040607`  
> 最终结果：48 个单元测试全部通过，行覆盖率 100%

### 6.1 意外收获：发现生产代码 Bug

工作流执行阶段 6（测试执行）时，所有调用 `push()` 的测试全部挂起。

**根因**：`service/threadpool/task_queue.cpp:13`，`push()` 在持有 `mutex_` 的情况下调用 `size()`，而 `size()` 内部又尝试 `lock_guard<std::mutex> lock(mutex_)`，对同一个非递归互斥锁重复加锁 → 死锁。

```cpp
// 问题代码
void TaskQueue::push(Task task, int priority) {
    std::lock_guard<std::mutex> lock(mutex_);  // 获取锁
    // ...
    peakSize_ = std::max(peakSize_, size());    // size() 内部再次 lock(mutex_) → 死锁!
}
```

**修复（方案 B）**：直接访问底层容器 size，不调用 `size()` 方法：

```cpp
// 修复后
peakSize_ = std::max(peakSize_, usePriority_ ? priorityQueue_.size() : normalQueue_.size());
```

### 6.2 报告生成器数据格式不匹配（🔴 严重）

**现象**：HTML 报告中语句覆盖率和分支覆盖率都显示 0%，与实际情况（行 100%、分支 72.2%）完全不符。

**根因**：`coverage_report.json` 的数据结构与 `report_generator.py` 期望的结构不一致。

工作流 Agent 写入的 `coverage_report.json` 是平面结构：

```json
{
  "line_coverage_pct": 100.0,
  "branch_coverage_pct": 72.2,
  "line_covered": 109,
  "line_total": 109,
  ...
}
```

但 `report_generator.py` 第 346-349 行按嵌套结构读取：

```python
# ai_workflow/scripts/report_generator.py
cr = data.get('coverage_report', {})
overall = cr.get('overall', {})                          # ← 没有 "overall" 键，返回 {}
data['line_coverage'] = overall.get('line_coverage_pct', 0)   # ← 取不到 → 0
data['branch_coverage'] = overall.get('branch_coverage_pct', 0)  # ← 同上 → 0
```

而 `coverage.py` 中 `_parse_lcov_info()` 输出的却是嵌套结构：

```python
# coverage.py 输出格式
{
  'overall': {
    'line_coverage_pct': 100.0,
    'branch_coverage_pct': 72.2,
    ...
  },
  'files': {...},
  'gaps': [...]
}
```

**修复方向**（二选一）：
- **A**：在 `report_generator.py` 中兼容两种格式（平面 + 嵌套），先检查 `cr.get('overall')`，不存在则直接读顶层字段
- **B**：在 Agent 侧统一用 `coverage.py` 的 `coverage_analyze()` 输出结果写入 `coverage_report.json`，保证格式一致

### 6.3 只生成单元测试，缺少集成测试和性能测试（🔴 严重）

**现象**：`test_assessment.json` 明确标注全部 8 个影响函数需要三种测试类型：

```json
// test_assessment.json 摘要
TaskQueue::clear     → needed_test_types: ["integration", "performance", "unit"]
TaskQueue::peakSize  → needed_test_types: ["integration", "performance", "unit"]
clearQueue           → needed_test_types: ["integration", "performance", "unit"]
...（全部 8 个函数均标注三种）
```

但实际只生成了单元测试：

| 实际产出 | 文件 | 测试宏 | 数量 |
|---------|------|--------|------|
| `tests/threadpool/unit/task_queue_test.cpp` | 单元测试 | `TEST_F` | 29 |
| `tests/threadpool/unit/thread_pool_test.cpp` | 单元测试 | `TEST_F` | 19 |

缺失：
- `tests/threadpool/integration/` — 目录不存在，**无集成测试**（GMock 已编译但未使用）
- `tests/threadpool/performance/` — 目录不存在，**无性能测试**（Google Benchmark 已安装但未使用）

**根因**：test-generator Agent 在阶段 4 只调用了单元测试生成逻辑，没有按照 `test_assessment.json` 中 `needed_test_types` 字段分别生成集成测试和性能测试。Agent 定义文件 `test-generator.md` 或工作流编排逻辑需要补充按测试类型分发的逻辑。

**环境已就绪**：
- GMock：`build/lib/libgmock.a` + `build/lib/libgmock_main.a` 已编译
- Google Benchmark：`/usr/lib64/libbenchmark.so` 已安装，`pkg-config --modversion benchmark` → `1.8.5`
- 需要同时在 `CMakeLists.txt` 中添加 `find_package(benchmark REQUIRED)` 并创建对应的测试 target

### 6.4 集成测试完全缺失（🟡 中）

即使忽略 `needed_test_types` 的问题，整个工作流在集成测试方面存在空白：

1. **无 Mock 对象**：GMock 库已编译，但生成的测试代码中没有任何 `MOCK_METHOD` 或 `EXPECT_CALL`
2. **无集成测试目录**：`tests/threadpool/integration/` 未被创建
3. **test-generator 无集成测试模板**：`ai_workflow/config/templates/` 下有 `unit_test.cpp.j2`、`mock_test.cpp.j2`、`benchmark_test.cpp.j2` 三个模板，但 `mock_test.cpp.j2` 未被使用
4. **CMakeLists.txt 无集成测试的 FetchContent 声明**：如果需要 Mock 外部依赖（如网络、文件系统），需要额外的 mock 框架配置

### 6.5 性能测试完全缺失（🟡 中）

1. **无 BENCHMARK 宏**：生成的测试代码中没有任何 `BENCHMARK()` 宏
2. **无性能测试目录**：`tests/threadpool/performance/` 未被创建
3. **benchmark_test.cpp.j2 模板未使用**
4. **CMakeLists.txt 无 `find_package(benchmark)`**：即使系统已安装，构建系统也不知道 benchmark 的存在，需要添加：
   ```cmake
   find_package(benchmark REQUIRED)
   ```
   并在性能测试 target 中 `target_link_libraries(xxx_benchmark benchmark::benchmark threadpool_lib)`

### 6.6 env_checker.py 中 codegraph 包名过时（🟡 中）

`env_checker.py` 第 77-78 行的修复提示引用了不存在的 npm 包：

```python
'fix_hint': ('请安装 CodeGraph（npm install -g @codegraph-ai/cli 或 '
             '从内网已下载的包安装），或设置 CODEGRAPH_CMD 环境变量'),
```

实际可用的是 `@colbymchenry/codegraph`。需要更新 `fix_hint` 或者直接用 `command_exists('codegraph')` 检测命令是否存在即可（不关心包名）。当前检测逻辑已经通过 `command_exists` 判断，只是提示文本过时。

### 6.7 问题汇总清单

| # | 问题 | 严重度 | 涉及文件/Agent | 修复方向 |
|---|------|--------|---------------|----------|
| 1 | report_generator 数据格式不匹配 | 🔴 严重 | `report_generator.py` | 兼容平面 + 嵌套两种 JSON 结构 |
| 2 | 只生成单元测试 | 🔴 严重 | `test-generator` Agent、`test-orchestrator` Agent | 按 `needed_test_types` 分别调用三种生成器 |
| 3 | 集成测试完全缺失 | 🟡 中 | `test-generator`、`mock_test.cpp.j2` | Agent 需使用 mock 模板生成集成测试 |
| 4 | 性能测试完全缺失 | 🟡 中 | `test-generator`、`benchmark_test.cpp.j2`、CMakeLists.txt | Agent 需使用 benchmark 模板 + CMake 添加 `find_package` |
| 5 | env_checker codegraph 包名过时 | 🟡 中 | `env_checker.py` | 更新 `fix_hint` 文本或改为通用检测 |
| 6 | CMakeLists.txt 无 benchmark 声明 | 🟡 中 | `CMakeLists.txt` | 添加 `find_package(benchmark REQUIRED)` |
| 7 | codegraph_analyzer.py API 不兼容 | ✅ 已修复 | `codegraph_analyzer.py` | 已在第三章修改 |
| 8 | task_queue.cpp push/size 死锁 | ✅ 已修复 | `task_queue.cpp` | 已用方案 B 修复（内联容器 size）|

---

## 七、工作流试跑成功指标

尽管存在上述问题，以下部分运行正常：

| 阶段 | 结果 |
|------|------|
| 0-环境检查 | ✅ 全部通过 |
| 1-变更检测 | ✅ 正确识别 4 文件变更、3 直接变更函数 |
| 2-影响分析 | ✅ CodeGraph 成功分析 8 函数调用关系（非 grep 降级） |
| 3-已有测试评估 | ✅ 8/8 函数正确判定为 new |
| 4-测试生成 | ⚠️ 生成 48 用例但只有单元测试 |
| 5-编译 | ✅ 一次通过，零修复循环 |
| 6-测试执行 | ⚠️ 发现死锁 Bug（已修复），修复后 48/48 通过 |
| 7-覆盖率采集 | ✅ lcov 成功采集，数据正确（行 100%，分支 72.2%） |
| 8-覆盖率补充 | ⚠️ 补充 8 个用例但覆盖率不变（缺口为不可测试路径） |
| 9-报告生成 | ❌ HTML 覆盖率显示 0%（数据格式不匹配） |
| 10-完成 | ✅ 状态归档

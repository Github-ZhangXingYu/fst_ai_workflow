# FST AI 测试工作流 — 项目适配文档

## 目的

本工作流需要放置到 FST 项目中才能运行。放置前需要先根据 FST 项目的实际情况修改一些硬编码的假设。

**适配流程：**
1. 在内网 Windows 上，将本工作流文件放入 FST 项目
2. 按本文档检查并修改硬编码假设
3. 修改完成后，将整个 FST 项目传入 Linux 运行

## 工作原则

- 本文档中 `[需确认]` 标记的地方，需要你打开 FST 项目检查实际情况后做出判断
- 拿不准的地方记住，到 Linux 后让 Claude Code 自己判断或问你
- 你有权修改任何配置文件、CMakeLists.txt，甚至 Python 脚本，来让工作流适配 FST 项目

---

## 一、文件放置

本工作流包含以下目录和文件，需要放到 FST 项目根目录下（与 `service/`、`tests/`、`CMakeLists.txt`、`product/` 同级）：

```
fst/                              # FST 项目根目录
├── .claude/                      # Claude Code 配置（放到 fst/.claude/）
│   ├── settings.json             # Hook 自动触发配置
│   ├── CLAUDE.md                 # 项目规则（注意：会覆盖或合并到 fst 已有的 CLAUDE.md）
│   ├── commands/                 # Slash 命令
│   │   ├── test-analyze.md
│   │   ├── test-quick.md
│   │   └── test-coverage.md
│   └── agents/                   # 子 Agent 定义
│       ├── test-orchestrator.md
│       ├── compile-fixer.md
│       ├── coverage-supplementer.md
│       ├── impact-analyzer.md
│       ├── test-evaluator.md
│       └── test-generator.md
├── ai_workflow/                  # 工作流脚本（放到 fst/ai_workflow/）
│   ├── scripts/                  # Python 脚本（9 个）
│   │   ├── workflow_state.py
│   │   ├── change_detector.py
│   │   ├── codegraph_analyzer.py
│   │   ├── test_scanner.py
│   │   ├── build_runner.py
│   │   ├── test_runner.py
│   │   ├── coverage.py
│   │   ├── report_generator.py
│   │   └── env_checker.py
│   ├── config/
│   │   ├── workflow_config.json  # 核心配置文件
│   │   └── templates/            # C++ 测试模板（Jinja2）
│   │       ├── unit_test.cpp.j2
│   │       ├── mock_test.cpp.j2
│   │       └── benchmark_test.cpp.j2
│   ├── state/                    # 运行时状态目录（自动创建，可 gitignore）
│   └── reports/                  # 报告输出目录（自动创建）
```

### 关于 CLAUDE.md

如果 FST 项目已经有一个 `.claude/CLAUDE.md`，不要直接覆盖。把本工作流的 CLAUDE.md 内容**合并**进去（本工作流的 CLAUDE.md 包含测试规范、工作流阶段定义、环境变量等）。

---

## 二、[需确认] 适配硬编码假设

以下假设写死在工作流的多个文件中。大部分已经按 FST 惯例修改过，但你需要逐一确认。

### 假设 1：构建目录是 `build/`，编译流程是 `mkdir build && cd build && cmake .. && make -j8`

**已适配：**
- `workflow_config.json` → `paths.build_dir: "build"`
- `build_runner.py` 已改为 `cd build && cmake .. && make -j8` 模式
- agent/command md 中的示例命令已更新

**[需确认] FST 项目的 cmake 编译是否确实是这个流程？**
- 查看 `build/` 目录是否存在，里面有没有 `Makefile` 或 `CMakeCache.txt`
- 如果 FST 的编译流程有额外步骤（如先 source 某个脚本、需要特定 cmake 选项），记录下来

### 假设 2：测试目录是 `tests/`（不是 `test/`）

**已适配：**
- `workflow_config.json` → `paths.test_dir: "tests"`
- `CLAUDE.md` 目录结构图
- 所有脚本和 agent md

**[需确认] FST 的测试目录名是不是 `tests/`？**

### 假设 3：测试二进制输出到 `product/bin/unittest/`

**已适配：**
- `test_runner.py` 默认 `--build-dir` 改为 `product/bin/unittest`
- agent/command md 中的示例命令已更新

**[需确认] FST 的测试可执行文件实际输出到哪个目录？**
- `product/bin/unittest/`？`product/bin/test/`？其他？
- 如果不存在，检查 CMakeLists.txt 中 `set(EXECUTABLE_OUTPUT_PATH ...)` 或 `set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ...)` 的值

### 假设 4：测试目录结构是 `tests/<模块>/unit/`、`tests/<模块>/integration/`

**写死在：**
- `CLAUDE.md` 中的目录结构图
- `test_scanner.py` 的分类逻辑

**[需确认] FST 现有的测试代码目录结构是什么样的？**

检查方法：
```bash
ls -la tests/
find tests/ -name "*.cpp" | head -20
```

### 假设 5：覆盖率编译开关叫 `ENABLE_COVERAGE`

**写死在：**
- `build_runner.py`：`cd build && cmake .. -DENABLE_COVERAGE=ON`

**[需确认] FST 的 CMakeLists.txt 中有没有覆盖率相关的 option？**

检查方法：
```bash
grep -rn "ENABLE_COVERAGE\|coverage\|COVERAGE\|gcov\|fprofile" CMakeLists.txt service/*/CMakeLists.txt 2>/dev/null
```

**情况 A：** 已有覆盖率 option 但名字不同 → 修改 `build_runner.py` 第 119 行附近的 cmake flag

**情况 B：** 没有覆盖率 option → 在顶层 CMakeLists.txt 中添加：

```cmake
option(ENABLE_COVERAGE "Enable code coverage instrumentation (gcov/lcov)" OFF)
if(ENABLE_COVERAGE)
    if(CMAKE_COMPILER_IS_GNUCC OR CMAKE_COMPILER_IS_GNUCXX)
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} --coverage -fprofile-arcs -ftest-coverage")
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} --coverage -fprofile-arcs -ftest-coverage")
        set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} --coverage")
        set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} --coverage")
    endif()
    message(STATUS "Coverage instrumentation enabled")
endif()
```

### 假设 6：CodeGraph 命令名为 `codegraph`

**配置在：** 环境变量 `CODEGRAPH_CMD`，默认值 `codegraph`

CodeGraph 是必须工具，`env_checker.py` 会验证其可用性。

---

## 三、配置文件修改清单

### 必须确认

| 文件 | 改什么 | 说明 |
|------|--------|------|
| `workflow_config.json` | `paths.build_dir` | 确认是 `build` |
| `workflow_config.json` | `paths.test_dir` | 确认是 `tests` |
| `workflow_config.json` | `paths.test_binary_dir` | 确认是 `product/bin/unittest` |
| FST 顶层 `CMakeLists.txt` | 添加 `ENABLE_COVERAGE` option | 如果没有的话 |
| `build_runner.py` | 覆盖率 cmake flag 名 | 如果 FST 的覆盖率 option 不叫 `ENABLE_COVERAGE` |

### 建议确认

| 文件 | 改什么 | 说明 |
|------|--------|------|
| `CLAUDE.md`（合并后的） | 目录结构图 | 匹配实际目录结构 |
| `test_scanner.py` | `_classify_test_type` 函数 | 如果测试目录分类方式不同 |

### 可选

| 文件 | 改什么 | 说明 |
|------|--------|------|
| `workflow_config.json` | 覆盖率阈值 | 默认 90%/80% |
| `workflow_config.json` | 超时时间 | 按内网机器性能调整 |

---

## 四、.gitignore 配置

确保 FST 项目的 `.gitignore` 包含：

```gitignore
# FST AI 测试工作流 — 运行时产物
ai_workflow/state/
ai_workflow/reports/*.html

# Python
__pycache__/
*.pyc
```

---

## 五、FST 项目编译惯例速查

| 项目 | 路径/命令 |
|------|----------|
| 编译流程 | `mkdir -p build && cd build && cmake .. <options> && make -j8 <target>` |
| 构建目录 | `build/`（CMakeCache.txt、Makefile 所在） |
| 微服务输出 | `product/bin/` |
| 测试二进制输出 | `product/bin/unittest/`（或其他子目录） |
| 库文件 | `product/lib/` |
| 配置文件 | `product/conf/` |

## 六、工作流速查

| 命令 | 用途 | 适用场景 |
|------|------|---------|
| `/test-analyze [模块名]` | 完整 9 步工作流 | 改了 service/ 代码后，全面分析影响、生成测试、跑覆盖率 |
| `/test-quick [模块名]` | 快速验证（≤6 步） | 日常迭代，只跑已有测试 + 覆盖率，不生成新测试 |
| `/test-coverage [模块名]` | 只看覆盖率（≤4 步） | 检查某个模块的覆盖率现状 |

## 七、Python 脚本速查

| 脚本 | 功能 |
|------|------|
| `env_checker.py` | 环境检测（CMake/gcc/git/lcov 等是否安装） |
| `workflow_state.py` | 工作流状态机 |
| `change_detector.py` | 检测 git diff 变更的 C++ 文件 |
| `codegraph_analyzer.py` | CodeGraph 调用关系分析 |
| `test_scanner.py` | 扫描已有测试，建立函数→测试映射 |
| `build_runner.py` | `mkdir build && cd build && cmake .. && make -j8` |
| `test_runner.py` | 运行 Google Test 二进制 |
| `coverage.py` | 运行测试 + lcov 采集覆盖率 + 解析 |
| `report_generator.py` | 生成中文 HTML 报告 |

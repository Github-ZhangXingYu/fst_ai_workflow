# FST AI 测试工作流 — 环境搭建教程

## 前置说明

FST 项目运行在 **CentOS 8** 内网 Linux 服务器上。所有工具均通过 `dnf` 安装。

**以下所有工具均为必须**——缺少任何一项，工作流不会启动。

---

## 环境总览

| 工具 | 安装方式 | 用途 |
|------|---------|------|
| Python 3.9+ | `dnf install -y python39` | 运行所有工作流脚本 |
| CMake | CentOS 8 自带 | 编译 C++ 测试代码 |
| g++ | `dnf install -y gcc-c++`（通常已有） | C++14 编译器 |
| git | CentOS 8 自带 | 检测代码变更 |
| lcov + genhtml | `dnf install -y lcov` | 代码覆盖率采集 + HTML 报告 |
| gcov | 随 g++ 安装 | 覆盖率数据采集 |
| clang-tidy | `dnf install -y clang-tools-extra` | C++ 静态分析 |
| CodeGraph | 通过安装包安装（见 Confluence） | C++ 调用图分析 |
| Google Benchmark | `dnf install -y google-benchmark-devel` | 性能基准测试 |
| Google Test | `dnf install -y gtest-devel` | 单元测试框架 |
| Google Mock | `dnf install -y gmock-devel` | Mock 框架 |

---

## 一、Python 3.9+

```bash
# CentOS 8 自带 python39，直接安装
dnf install -y python39

# 验证
python3.9 --version

# 创建软链接，让 python3 命令可用
ln -s /usr/bin/python3.9 /usr/local/bin/python3

# 验证
python3 --version
```

---

## 二、CMake

CentOS 8 自带，无需额外安装：

```bash
cmake --version
# 如果缺失: dnf install -y cmake
```

---

## 三、g++ / gcov

g++ 通常已有（否则 FST 项目之前怎么编译的）：

```bash
g++ --version
# 要求 ≥ 5.0（C++14 支持）

# 如果缺失
dnf install -y gcc-c++
```

gcov 随 g++ 一起安装：
```bash
gcov --version
# 有输出说明已就绪
```

---

## 四、git

CentOS 8 自带：

```bash
git --version
# 如果缺失: dnf install -y git
```

---

## 五、lcov + genhtml

```bash
dnf install -y lcov

# 验证
lcov --version
genhtml --version
```

---

## 六、clang-tidy

```bash
dnf install -y clang-tools-extra

# 验证
clang-tidy --version
```

---

## 七、CodeGraph

**CodeGraph 通过提供的安装包进行安装，详见 Confluence 文档。**

也可通过环境变量指定已安装的 codegraph 路径：
```bash
export CODEGRAPH_CMD=/path/to/codegraph
```

---

## 八、Google Benchmark

```bash
dnf install -y google-benchmark-devel
```

---

## 九、Google Test / Google Mock

```bash
dnf install -y gtest-devel gmock-devel
```

---

## 十、快速安装（一键）

```bash
# 除 CodeGraph 外，全部可通过 dnf 安装
dnf install -y python39 cmake gcc-c++ git lcov clang-tools-extra google-benchmark-devel gtest-devel gmock-devel

# Python 软链接
ln -s /usr/bin/python3.9 /usr/local/bin/python3

# CodeGraph —— 参考 Confluence 文档通过安装包安装
```

---

## 十一、验证

在 FST 项目根目录运行：

```bash
python3 ai_workflow/scripts/env_checker.py
```

预期输出：

```
============================================================
  FST AI 测试工作流 — 环境检查
============================================================

【必须工具】— 缺少则无法运行
----------------------------------------
  ✅ python3 (3.9.x) — 运行工作流脚本
  ✅ cmake — 编译测试代码
  ✅ g++ — C++14 编译器
  ✅ git — 检测代码变更
  ✅ lcov — 代码覆盖率采集
  ✅ genhtml — 生成覆盖率的 HTML 报告
  ✅ gcov — 代码覆盖率数据采集
  ✅ clang-tidy — C++ 静态分析
  ✅ codegraph — C++ 调用图分析
  ✅ benchmark — 性能基准测试

【必须库】
----------------------------------------
  ✅ googletest — C++ 单元测试框架
  ✅ googlemock — C++ Mock 框架

【项目检查】
----------------------------------------
  ✅ python_version
  ✅ compile_commands
  ✅ project_structure — 目录结构正确
  ✅ scripts — 全部脚本就绪

============================================================
  结论: ✅ 环境就绪，可以启动测试工作流
============================================================
```

有任何 ❌ 的项都必须先修好，才能启动工作流。

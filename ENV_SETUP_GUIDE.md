# FST AI 测试工作流 — 内网环境搭建完整教程

## 前置说明

FST 项目运行在内网 Linux 服务器上，**无法访问互联网**。所有软件包需要：
1. 在外网下载安装包（Windows 本机）
2. 通过 JumpServer 上传到内网 Linux
3. 在内网 Linux 上离线安装

---

## 环境总览

| 工具 | 级别 | 版本要求 | 用途 |
|------|------|---------|------|
| Python | **必须** | ≥ 3.8 | 运行所有工作流脚本 |
| CMake | **必须** | ≥ 3.10 | 编译 C++ 测试代码 |
| g++ | **必须** | ≥ 5.0 | C++14 编译器 |
| git | **必须** | 任意 | 检测代码变更 (git diff) |
| lcov + genhtml | **推荐** | 任意 | 代码覆盖率采集 + HTML报告 |
| clang-tidy | **推荐** | 任意 | C++ 静态分析 |
| CodeGraph | **推荐** | 任意 | C++ 调用图分析（可降级为 grep） |
| gcovr | 可选 | 任意 | 覆盖率降级方案（lcov 不可用时） |
| Google Benchmark | 可选 | 任意 | 性能基准测试 |

---

## 一、Python 3.8+（必须）

### 下载

在外网 Windows 上打开：**https://www.python.org/downloads/**

选择 Linux 源码包（不要下载 Windows 版）：
- 直接链接：**https://www.python.org/ftp/python/3.12.5/Python-3.12.5.tgz**
- 也可以选 3.8 ~ 3.12 任意版本

下载完成后通过 JumpServer 传到内网 Linux。

### 在 Linux 上编译安装

```bash
# 1. 解压
tar -xzf Python-3.12.5.tgz
cd Python-3.12.5

# 2. 编译（--prefix 指定安装路径，避免覆盖系统 python）
./configure --prefix=/usr/local/python3 --enable-optimizations
make -j$(nproc)
sudo make install

# 3. 添加到 PATH（写入 ~/.bashrc 永久生效）
echo 'export PATH="/usr/local/python3/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# 4. 验证
python3 --version
# 输出: Python 3.12.5
```

### 备选方案：离线 RPM/DEB

如果 Linux 发行版是 CentOS/RHEL：
```bash
# 从外网下载 RPM 包
# https://pkgs.org/download/python3  → 下载对应版本 → 传内网
sudo rpm -ivh python3-*.rpm --nodeps
```

如果是 Ubuntu/Debian：
```bash
# 从外网下载 deb 包
# https://pkgs.org/download/python3  → 下载对应版本 → 传内网
sudo dpkg -i python3-*.deb
```

---

## 二、CMake 3.10+（必须）

### 下载

在外网 Windows 上打开：**https://cmake.org/download/**

下载 Linux x86_64 二进制包（不需要编译）：
- 直接链接：**https://github.com/Kitware/CMake/releases/download/v3.29.6/cmake-3.29.6-linux-x86_64.tar.gz**

### 在 Linux 上安装

```bash
# 1. 解压到 /usr/local
tar -xzf cmake-3.29.6-linux-x86_64.tar.gz
sudo mv cmake-3.29.6-linux-x86_64 /usr/local/cmake

# 2. 添加到 PATH
echo 'export PATH="/usr/local/cmake/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# 3. 验证
cmake --version
# 输出: cmake version 3.29.6
```

---

## 三、g++ / gcov（必须 + 附带）

g++ 是 C++ 编译器，几乎肯定已经装在内网 Linux 上了（否则 FST 项目之前怎么编译的）。

```bash
# 验证是否已有
g++ --version
# 要求 ≥ 5.0（C++14 支持）

# 如果缺失（极少见）
sudo apt-get install g++    # Ubuntu/Debian
sudo yum install gcc-c++    # CentOS/RHEL
```

gcov 随 g++ 一起安装，无需额外操作：
```bash
gcov --version  # 有输出说明已就绪
```

---

## 四、git（必须）

内网 Linux 上应该已有 git（FST 项目用 git 管理）。

```bash
git --version  # 验证

# 如果缺失
sudo apt-get install git    # Ubuntu/Debian
sudo yum install git        # CentOS/RHEL
```

---

## 五、lcov + genhtml（推荐，覆盖率报告）

### 下载

在外网 Windows 上打开：**https://github.com/linux-test-project/lcov/releases**

下载最新源码包：
- 直接链接：**https://github.com/linux-test-project/lcov/archive/refs/tags/v2.2.tar.gz**

### 在 Linux 上安装

```bash
# 1. 解压
tar -xzf lcov-2.2.tar.gz
cd lcov-2.2

# 2. 安装（不需要编译，是 Perl 脚本）
sudo make install

# 3. 验证
lcov --version
genhtml --version
```

**依赖检查**：lcov 是 Perl 脚本，需要 `perl`（系统自带）。如果报错 `perl: command not found`：

```bash
sudo apt-get install perl    # Ubuntu/Debian
sudo yum install perl        # CentOS/RHEL
```

### 如果 lcov 装不上

可以用 gcovr 代替（纯 Python，pip 安装）。gcovr 功能相同但报告格式稍有不同：
```bash
pip3 install gcovr
```

---

## 六、clang-tidy（推荐，静态分析）

### 下载

检查内网 Linux 发布版的包管理器是否能连本地源。如果不能联网，下载方式取决于发行版：

**Ubuntu/Debian**（从外网下载 deb 包）：
- https://packages.ubuntu.com/ → 搜索 `clang-tidy` → 下载对应版本及依赖

**CentOS/RHEL**：
```bash
# 如果内网有 yum 本地源
sudo yum install clang-tidy
```

**备选：LLVM 预编译包**（通用，推荐）
- 下载地址：**https://github.com/llvm/llvm-project/releases**
- 选择 `clang+llvm-*-x86_64-linux-gnu-*.tar.xz`
- 解压后 `bin/clang-tidy` 直接可用

```bash
tar -xf clang+llvm-*.tar.xz
sudo cp clang+llvm-*/bin/clang-tidy /usr/local/bin/
clang-tidy --version
```

**注意**：没有 clang-tidy 不影响工作流运行，只是少了静态分析这个辅助功能。

---

## 七、CodeGraph（推荐，调用图分析）

CodeGraph 是 npm 包。如果内网 Linux 上有 Node.js：
```bash
npm install -g @codegraph-ai/cli
```

如果没有 Node.js 或者装不上，**没关系**——工作流会自动降级为 `grep` 搜索调用关系，不影响核心功能。

---

## 八、Google Benchmark（可选，性能测试）

如果只需要单元测试和集成测试，不需要安装。需要用性能测试时才装。

### 下载

- 源码：**https://github.com/google/benchmark/archive/refs/tags/v1.9.0.tar.gz**

### 在 Linux 上编译安装

```bash
tar -xzf benchmark-1.9.0.tar.gz
cd benchmark-1.9.0
cmake -B build -DBENCHMARK_DOWNLOAD_DEPENDENCIES=ON
cmake --build build
sudo cmake --install build
```

---

## 九、快速安装检查清单

按优先级，推荐安装顺序：

```
第 1 批（必须装）:
  □ Python 3.8+        → 从 python.org 下载 tgz，编译安装
  □ g++                → 内网 Linux 上应该已有
  □ git                → 内网 Linux 上应该已有
  □ CMake 3.10+        → 从 GitHub Release 下载二进制包

第 2 批（强烈建议）:
  □ lcov + genhtml     → 从 GitHub Release 下载
  □ (或 gcovr)         → pip3 install gcovr（lcov 装不上时）

第 3 批（可选）:
  □ clang-tidy         → 从 LLVM Release 下载
  □ CodeGraph          → 需要 Node.js，没有就跳过
  □ Google Benchmark   → 需要时才装
```

---

## 十、全部安装完成后验证

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
  ✅ python3 (3.12.5) — 运行工作流脚本
  ✅ cmake (3.29.6) — 编译测试代码
  ✅ g++ (11.4.0) — C++14 编译器
  ✅ git — 检测代码变更

【项目检查】
----------------------------------------
  ✅ python_version — Python 3.12.5
  ✅ project_structure — 目录结构正确
  ✅ scripts — 全部脚本就绪

【推荐工具】— 缺少则部分功能降级
----------------------------------------
  ✅ lcov — 代码覆盖率分析
  ✅ genhtml — 生成覆盖率的 HTML 报告
  ✅ gcov — 代码覆盖率数据采集
  ⚠️ clang-tidy — C++ 静态分析（缺失也无妨）
  ⚠️ codegraph — C++ 调用图分析（会降级为 grep）

============================================================
  结论: ✅ 环境就绪，可以启动测试工作流
============================================================
```

有 ❌ 的必须项就得先修，⚠️ 的可以暂时不管。

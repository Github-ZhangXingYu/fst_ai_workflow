# FST AI 测试工作流 — 项目背景与继承指南

## 项目是什么

这是为**同花顺期货通（FST）** C++14 微服务后端项目打造的 AI 驱动测试工作流框架。
最终部署在内网 Linux 服务器上，由 Claude Code + DeepSeek V4 Flash 驱动。

## 为什么在外网 Windows 设备上开发

**核心原因：内网 Linux 服务器处于断网状态，无法访问外网。**

具体约束：
- FST 项目代码在内网 Linux 服务器，编译/测试环境（CMake、Google Test、gcov/lcov）也在内网
- 内网**无法连接互联网**，安装新工具需要先从外网下载 → 通过 JumpServer 传到内网
- 内网已部署 Claude Code + DeepSeek V4 Flash（本地模型），可以直接使用 AI 能力
- 本 Windows 设备连外网，用于：调研方案、设计架构、编写代码、GitHub 版本管理

**工作流程：**
```
外网 Windows（本机）           JumpServer             内网 Linux
─────────────────────         ──────────             ──────────
调研成熟方案 ← 互联网
设计架构
编写代码 → GitHub              → 下载包 →              → 安装工具
提交 Git                                          ← 拉取代码
                                                  ← 集成到 fst 项目
                                                  ← 实际运行测试
```

## 当前状态

### 已完成（本次会话）

- [x] 调研 AI 驱动 C++ 测试工作流的成熟方案
- [x] 确认技术选型：gcov/lcov/clang-tidy/CodeGraph/Python 3.8+
- [x] 设计 10 阶段工作流架构
- [x] 实现 Python 工作流脚本（9 个：覆盖检测、影响分析、编译、测试、覆盖率、报告生成等）
- [x] 实现 6 个 Claude Code 子 Agent
- [x] 实现 `/test-analyze` Skill（手动触发）
- [x] 配置 Hook（自动检测 C++ 文件变更 + 通知）
- [x] 3 个 Jinja2 测试模板（单元/集成/性能）
- [x] 工作流状态机 + 中文 HTML 报告
- [x] 环境预检脚本（分三级检查 + 缺失提示）

### 待完成

- [ ] 5 条工作流改进（见下方"待办改进"）
- [ ] 移到内网 Linux 实际集成测试
- [ ] 根据内网实际运行反馈调整
- [ ] 配置内网环境变量（CODEGRAPH_CMD 等）
- [ ] 补充 CMakeLists.txt 的覆盖率和 Benchmark 支持

## 架构要点（快速理解）

### 三层机制

```
触发层: Hook (auto) / /test-analyze (manual)
   ↓
编排层: 10 步工作流，Python 脚本 + AI 推理分工
   ↓
支撑层: state/*.json (步骤间数据), reports/ (报告)
```

### Python 脚本 vs AI 分工

| Python（确定性） | AI（推理） |
|-----------------|-----------|
| git diff 检测变更 | 测试充分性判断 |
| CodeGraph/grep 查询调用关系 | 测试代码生成 |
| CMake 编译 + 错误解析 | 编译错误修复 |
| Google Test 运行 + 结果解析 | 覆盖率补充策略 |
| gcov/lcov 覆盖率采集 + 解析 | 影响范围确认 |
| HTML 报告生成 | 已有测试质量评估 |

### 循环控制

- **编译修复循环**: 最多 3 次，每次 编译→解析错误→AI修复→重新编译
- **覆盖率补充循环**: 最多 2 次，每次 分析缺口→生成补充测试→重新走编译+测试+覆盖率

## 内网部署步骤

1. 将本仓库代码通过 JumpServer 传到内网 Linux
2. 放到 fst 项目根目录下（与 `service/`、`tests/` 同级）
3. 确保环境就绪：`python scripts/env_checker.py`
4. 如缺少工具，根据提示从外网下载 → JumpServer → 内网安装
5. 运行 `python scripts/env_checker.py --json` 确认全部通过
6. 在 Claude Code 中运行 `/test-analyze` 测试完整流程

## 关键设计决策

| 决策 | 原因 |
|------|------|
| Python 处理确定性操作 | DeepSeek V4 Flash 能力中等，编译/覆盖率等操作 Python 更可靠 |
| 单函数处理 | 每次只处理一个函数/一个错误，控制上下文长度 |
| JSON 文件传递步骤间数据 | 简单、可追溯、可手动检查 |
| JSON 文件传递步骤间数据 | 简单、可追溯、可手动检查 |
| 代码先在外网写再传内网 | 内网无互联网，无法安装 npm/pip 包 |
| CodeGraph + grep 降级 | CodeGraph 可能不可用，grep 保证基本可用 |
| 中文报告 | 团队使用中文 |

## 重要文件索引

| 文件 | 用途 | 谁需要改 |
|------|------|---------|
| `.claude/CLAUDE.md` | 项目规则总纲 | 项目维护者 |
| `.claude/commands/test-analyze.md` | `/test-analyze` Skill 指令 | 工作流调整时 |
| `.claude/agents/*.md` | 6 个子 Agent 定义 | Agent 行为调整时 |
| `.claude/settings.json` | Hook 触发配置 | 触发规则调整时 |
| `config/workflow_config.json` | 阈值/路径/循环限制 | 参数调整时 |
| `config/templates/*.j2` | C++ 测试模板 | 测试规范调整时 |
| `scripts/*.py` | Python 确定性操作 | 脚本逻辑调整时 |

## 待办改进（优先级排序）

1. **工作流移入 test-orchestrator Agent** — 当前 362 行 Skill 指令 AI 容易丢步骤
2. **中间状态校验** — 步骤间增加强制数据校验关卡
3. **编译修复错误优先级排序** — 先修 header/include 类错误，减少无效修复
4. **`/test-quick` 快捷命令** — 日常迭代只需跑已有测试 + 覆盖率
5. **Agent 调用策略强化** — 更刚性的约束确保 AI 启动子 Agent

## 给后续 Claude Code 会话的提示

- 内网环境没有 Internet，推荐安装工具已在 `env_checker.py` 中列出
- 当前 Hook 格式已经按 Claude Code 官方文档修正（参考 `claude-code-reference.md`）
- Git 历史是本项目最完整的设计文档，关键提交都写了详细的 commit message
- 如果遇到 Hook 报错，先检查 `claude-code-reference.md` 中的 Hook 章节（第 177-447 行）
- 如果工作流某步卡住，检查 `state/` 目录下对应 JSON 文件是否损坏

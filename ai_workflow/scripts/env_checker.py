#!/usr/bin/env python3
"""
环境检测器：在运行测试工作流之前，检测所有必需工具和环境是否就绪。
必须在工作流 Step 0 初始化之前执行。

所有工具均为必须 — 缺少任何一项工作流都无法启动。
不再区分 required/recommended/nice_to_have，不再有降级兼容路径。
"""
import subprocess
import os
import json
import shutil
import sys
from pathlib import Path
from datetime import datetime


# 所有工具均为必须 — 缺少即工作流无法运行
REQUIRED_TOOLS = {
    # 基础工具链
    'python3': {
        'check': 'command_exists',
        'fix_hint': (
            'dnf install -y python39\n'
            '    然后创建软链接: ln -s /usr/bin/python3.9 /usr/local/bin/python3'
        ),
        'purpose': '运行工作流脚本',
        'min_version': '3.8',
        'version_flag': '--version',
        'version_pattern': r'Python (\d+\.\d+\.\d+)',
    },
    'cmake': {
        'check': 'command_exists',
        'fix_hint': 'dnf install -y cmake  (CentOS 8 自带)',
        'purpose': '编译测试代码',
        'min_version': '3.10',
        'version_flag': '--version',
        'version_pattern': r'cmake version (\d+\.\d+\.\d+)',
    },
    'g++': {
        'check': 'command_exists',
        'fix_hint': 'dnf install -y gcc-c++  (CentOS 8 自带，通常已有)',
        'purpose': 'C++14 编译器',
        'min_version': '5.0',
        'version_flag': '--version',
        'version_pattern': r'g\+\+.*?(\d+\.\d+\.\d+)',
    },
    'git': {
        'check': 'command_exists',
        'fix_hint': 'dnf install -y git  (CentOS 8 自带)',
        'purpose': '检测代码变更',
    },
    # 覆盖率工具链
    'lcov': {
        'check': 'command_exists',
        'fix_hint': 'dnf install -y lcov',
        'purpose': '代码覆盖率采集',
    },
    'genhtml': {
        'check': 'command_exists',
        'fix_hint': 'dnf install -y lcov  (genhtml 随 lcov 一起安装)',
        'purpose': '生成覆盖率的 HTML 报告',
    },
    'gcov': {
        'check': 'command_exists',
        'fix_hint': 'gcov 随 g++ 一起安装。如缺失: dnf install -y gcc',
        'purpose': '代码覆盖率数据采集（gcov 运行时）',
    },
    # 静态分析 & 调用图
    'clang-tidy': {
        'check': 'command_exists',
        'fix_hint': 'dnf install -y clang-tools-extra',
        'purpose': 'C++ 静态分析',
    },
    'codegraph': {
        'check': 'command_exists',
        'fix_hint': ('请参考 Confluence 文档获取 CodeGraph 安装包和安装说明，'
                     '或设置 CODEGRAPH_CMD 环境变量指向已安装的 codegraph 二进制'),
        'purpose': 'C++ 调用图分析（影响范围分析）',
        'env_override': 'CODEGRAPH_CMD',
    },
    # 性能测试
    'benchmark': {
        'check': 'pkg_config_exists',
        'pkg_name': 'benchmark',
        'fix_hint': 'dnf install -y google-benchmark-devel',
        'purpose': '性能基准测试',
    },
}


def command_exists(cmd: str) -> bool:
    """检查命令是否存在于 PATH 中。"""
    return shutil.which(cmd) is not None


def get_command_version(cmd: str, flag: str = '--version',
                        pattern: str = None) -> str:
    """获取命令的版本号。"""
    import re
    try:
        result = subprocess.run(
            [cmd, flag],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout or result.stderr
        if pattern:
            match = re.search(pattern, output)
            if match:
                return match.group(1)
        # 默认：取第一行
        return output.strip().split('\n')[0][:80]
    except Exception:
        return 'unknown'


def pkg_config_exists(pkg_name: str) -> bool:
    """通过 pkg-config 检查库是否存在。"""
    try:
        result = subprocess.run(
            ['pkg-config', '--exists', pkg_name],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def check_python_version() -> dict:
    """检查 Python 版本是否 ≥ 3.8。"""
    version = sys.version_info
    ok = version.major >= 3 and version.minor >= 8
    return {
        'name': 'python3',
        'available': True,
        'version': f'{version.major}.{version.minor}.{version.micro}',
        'ok': ok,
        'required': '3.8',
        'message': '' if ok else f'Python 版本 {version.major}.{version.minor} < 3.8，请升级',
    }


def check_googletest() -> dict:
    """检查 Google Test 头文件是否在系统标准位置。"""
    search_paths = [
        '/usr/include/gtest/gtest.h',
        '/usr/local/include/gtest/gtest.h',
        '/usr/include/gtest.h',
    ]
    found = None
    for p in search_paths:
        if os.path.exists(p):
            found = p
            break
    return {
        'available': found is not None,
        'version': f'位于 {found}' if found else '',
        'ok': found is not None,
        'purpose': 'C++ 单元测试框架',
        'fix_hint': 'dnf install -y gtest-devel',
    }


def check_googlemock() -> dict:
    """检查 Google Mock 头文件是否在系统标准位置。"""
    search_paths = [
        '/usr/include/gmock/gmock.h',
        '/usr/local/include/gmock/gmock.h',
    ]
    found = None
    for p in search_paths:
        if os.path.exists(p):
            found = p
            break
    return {
        'available': found is not None,
        'version': f'位于 {found}' if found else '',
        'ok': found is not None,
        'purpose': 'C++ Mock 框架（集成测试必需）',
        'fix_hint': 'dnf install -y gmock-devel',
    }


def check_compile_commands() -> dict:
    """检查 compile_commands.json 是否存在（clang-tidy 和 CodeGraph 需要）。"""
    locations = [
        'build/compile_commands.json',
        'compile_commands.json',
    ]
    found = None
    for loc in locations:
        if os.path.exists(loc):
            found = loc
            break

    return {
        'name': 'compile_commands.json',
        'available': found is not None,
        'version': f'位于 {found}' if found else '',
        'ok': found is not None,
        'required': '用于 clang-tidy 和 CodeGraph',
        'message': ('' if found else '未找到 compile_commands.json。'
                    '运行 cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON 来生成。'),
    }


def check_project_structure() -> dict:
    """检查 FST 项目的目录结构是否正确。"""
    issues = []

    if not os.path.exists('service'):
        issues.append('缺少 service/ 目录（微服务源码目录）')
    if not os.path.exists('tests'):
        issues.append('缺少 tests/ 目录（测试代码目录）')

    return {
        'name': '项目目录结构',
        'available': len(issues) == 0,
        'version': '',
        'ok': len(issues) == 0,
        'required': 'service/ 和 tests/ 目录',
        'message': '; '.join(issues) if issues else '目录结构正确',
    }


def check_scripts() -> dict:
    """检查 Python 脚本是否都存在。"""
    required_scripts = [
        'workflow_state.py', 'change_detector.py', 'codegraph_analyzer.py',
        'test_scanner.py', 'build_runner.py', 'test_runner.py',
        'coverage.py', 'report_generator.py',
    ]

    missing = []
    for s in required_scripts:
        path = os.path.join('ai_workflow/scripts', s)
        if not os.path.exists(path):
            missing.append(s)

    return {
        'name': '工作流脚本',
        'available': len(missing) == 0,
        'version': '',
        'ok': len(missing) == 0,
        'required': 'ai_workflow/scripts/ 下全部 9 个脚本',
        'message': f'缺少脚本: {", ".join(missing)}' if missing else '全部脚本就绪',
    }


def run_all_checks() -> dict:
    """执行所有环境检查。

    Returns:
        {
            passed: bool,
            can_start: bool,      # 所有检查通过才可启动
            check_time: str,
            tools: {name: {available, version, ok, purpose, fix_hint}},
            libraries: {name: {available, version, ok, purpose, fix_hint}},
            project: {name: {available, version, ok, message}},
            failed: [str],        # 失败的检查项名称列表
            summary: str,
        }
    """
    results = {
        'check_time': datetime.now().isoformat(),
        'tools': {},
        'libraries': {},
        'project': {},
    }

    # 1. 检查所有命令行工具
    for name, config in REQUIRED_TOOLS.items():
        if config['check'] == 'command_exists':
            check_name = config.get('env_override', name)
            actual_cmd = os.environ.get(check_name, name)
            available = command_exists(actual_cmd)
            version = ''
            if available and 'version_flag' in config:
                version = get_command_version(
                    actual_cmd,
                    config['version_flag'],
                    config.get('version_pattern')
                )
            results['tools'][name] = {
                'available': available,
                'version': version,
                'ok': available,
                'required': config.get('min_version', 'any'),
                'purpose': config['purpose'],
                'fix_hint': config['fix_hint'],
            }
        elif config['check'] == 'pkg_config_exists':
            available = pkg_config_exists(config['pkg_name'])
            results['tools'][name] = {
                'available': available,
                'version': '',
                'ok': available,
                'required': 'any',
                'purpose': config['purpose'],
                'fix_hint': config['fix_hint'],
            }

    # 2. 检查必须的头文件库
    results['libraries']['googletest'] = check_googletest()
    results['libraries']['googlemock'] = check_googlemock()

    # 3. 项目级检查
    results['project']['python_version'] = check_python_version()
    results['project']['compile_commands'] = check_compile_commands()
    results['project']['project_structure'] = check_project_structure()
    results['project']['scripts'] = check_scripts()

    # 4. 汇总：所有项都必须通过
    all_tools_ok = all(v['ok'] for v in results['tools'].values())
    all_libs_ok = all(v['ok'] for v in results['libraries'].values())
    all_project_ok = all(v['ok'] for v in results['project'].values())

    results['passed'] = all_tools_ok and all_libs_ok and all_project_ok
    results['can_start'] = results['passed']

    # 5. 收集失败项
    failed = []
    failed.extend(k for k, v in results['tools'].items() if not v['ok'])
    failed.extend(k for k, v in results['libraries'].items() if not v['ok'])
    failed.extend(k for k, v in results['project'].items() if not v['ok'])
    results['failed'] = failed

    # 6. 生成摘要
    if failed:
        results['summary'] = f'❌ 缺少必须依赖 ({len(failed)}): {", ".join(failed)}'
    else:
        results['summary'] = '✅ 所有环境和工具就绪'

    return results


def format_terminal_report(results: dict) -> str:
    """生成终端格式的环境检查报告。"""
    lines = []
    lines.append('=' * 60)
    lines.append('  FST AI 测试工作流 — 环境检查')
    lines.append('=' * 60)
    lines.append(f'  检查时间: {results["check_time"]}')
    lines.append('')

    # 命令行工具
    lines.append('【必须工具】— 缺少则无法运行')
    lines.append('-' * 40)
    for name, info in results['tools'].items():
        status = '✅' if info['ok'] else '❌'
        ver = f' ({info["version"]})' if info.get('version') else ''
        lines.append(f'  {status} {name}{ver} — {info["purpose"]}')
        if not info['ok']:
            lines.append(f'     → 修复: {info["fix_hint"]}')

    # 头文件库
    lines.append('')
    lines.append('【必须库】')
    lines.append('-' * 40)
    for name, info in results['libraries'].items():
        status = '✅' if info['ok'] else '❌'
        ver = f' ({info["version"]})' if info.get('version') else ''
        lines.append(f'  {status} {name}{ver} — {info["purpose"]}')
        if not info['ok']:
            lines.append(f'     → 修复: {info["fix_hint"]}')

    # 项目检查
    lines.append('')
    lines.append('【项目检查】')
    lines.append('-' * 40)
    for name, info in results['project'].items():
        status = '✅' if info['ok'] else '❌'
        ver = f' ({info["version"]})' if info.get('version') else ''
        lines.append(f'  {status} {name}{ver}')
        if info.get('message') and not info['ok']:
            lines.append(f'     → {info["message"]}')

    # 结论
    lines.append('')
    lines.append('=' * 60)
    if results['can_start']:
        lines.append('  结论: ✅ 环境就绪，可以启动测试工作流')
    else:
        lines.append(f'  结论: ❌ 缺少 {len(results["failed"])} 项必须依赖，请先修复上述检查项')
    lines.append('=' * 60)

    return '\n'.join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='FST 工作流环境检测器：在运行测试工作流前检查所有依赖'
    )
    parser.add_argument('--json', action='store_true',
                        help='以 JSON 格式输出检查结果')
    parser.add_argument('--output',
                        help='将结果写入 JSON 文件')
    parser.add_argument('--exit-code', action='store_true',
                        help='如果环境不满足则退出码≠0（用于 CI）')

    args = parser.parse_args()

    results = run_all_checks()

    # 输出
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(format_terminal_report(results))

    # 写入文件
    if args.output:
        os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    # 退出码
    if args.exit_code and not results['can_start']:
        sys.exit(1)


if __name__ == '__main__':
    main()

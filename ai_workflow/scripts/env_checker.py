#!/usr/bin/env python3
"""
环境检测器：在运行测试工作流之前，检测所有必需工具和环境是否就绪。
必须在工作流 Step 0 初始化之前执行。
"""
import subprocess
import os
import json
import shutil
import sys
from pathlib import Path
from datetime import datetime


# 工具分级定义
REQUIRED_TOOLS = {
    # 必须：缺少则工作流完全无法运行
    'python3': {
        'category': 'required',
        'check': 'command_exists',
        'fix_hint': '请安装 Python 3.8+（sudo apt-get install python3）',
        'purpose': '运行工作流脚本',
    },
    'cmake': {
        'category': 'required',
        'check': 'command_exists',
        'fix_hint': '请安装 CMake（sudo apt-get install cmake）',
        'purpose': '编译测试代码',
    },
    'g++': {
        'category': 'required',
        'check': 'command_exists',
        'fix_hint': '请安装 g++（sudo apt-get install g++）',
        'purpose': 'C++14 编译器',
        'min_version': '5.0',
        'version_flag': '--version',
        'version_pattern': r'g\+\+.*?(\d+\.\d+\.\d+)',
    },
    'git': {
        'category': 'required',
        'check': 'command_exists',
        'fix_hint': '请安装 git（sudo apt-get install git）',
        'purpose': '检测代码变更',
    },
}

RECOMMENDED_TOOLS = {
    # 推荐：缺少则部分功能降级但工作流仍可继续
    'lcov': {
        'category': 'recommended',
        'check': 'command_exists',
        'fix_hint': '请安装 lcov（sudo apt-get install lcov）',
        'purpose': '代码覆盖率分析',
        'fallback': 'gcovr（sudo apt-get install gcovr）',
    },
    'genhtml': {
        'category': 'recommended',
        'check': 'command_exists',
        'fix_hint': '请安装 lcov（genhtml 随 lcov 一起安装）',
        'purpose': '生成覆盖率的 HTML 报告',
    },
    'gcov': {
        'category': 'recommended',
        'check': 'command_exists',
        'fix_hint': 'gcov 通常随 g++ 一起安装。如缺失请安装 gcovr',
        'purpose': '代码覆盖率数据采集',
    },
    'clang-tidy': {
        'category': 'recommended',
        'check': 'command_exists',
        'fix_hint': '请安装 clang-tidy（sudo apt-get install clang-tidy）',
        'purpose': 'C++ 静态分析',
    },
    'codegraph': {
        'category': 'recommended',
        'check': 'command_exists',
        'fix_hint': ('请安装 CodeGraph（npm install -g @colbymchenry/codegraph），'
                     '或设置 CODEGRAPH_CMD 环境变量指向已安装的 codegraph 二进制'),
        'purpose': 'C++ 调用图分析（影响范围分析）',
        'env_override': 'CODEGRAPH_CMD',
    },
}

NICE_TO_HAVE_TOOLS = {
    # 增强：缺少不影响核心功能
    'gcovr': {
        'category': 'nice_to_have',
        'check': 'command_exists',
        'fix_hint': '可选。如 lcov 不可用，作为覆盖率分析的降级方案',
        'purpose': '覆盖率分析降级方案',
    },
    'google-benchmark': {
        'category': 'nice_to_have',
        'check': 'pkg_config_exists',
        'pkg_name': 'benchmark',
        'fix_hint': '可选。用于性能测试（Google Benchmark）',
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
    """检查是否可以找到 Google Test 头文件。"""
    # 常见位置
    search_paths = [
        '/usr/include/gtest/gtest.h',
        '/usr/local/include/gtest/gtest.h',
        '/usr/include/gtest.h',
    ]

    # 也检查 CMake FetchContent 的下载位置
    build_dirs = ['build', 'cmake-build-debug']
    for bd in build_dirs:
        if os.path.exists(bd):
            for root, dirs, files in os.walk(bd):
                if 'gtest.h' in files and 'gtest' in root:
                    search_paths.append(os.path.join(root, 'gtest.h'))

    found = None
    for p in search_paths:
        if os.path.exists(p):
            found = p
            break

    return {
        'name': 'Google Test',
        'available': found is not None,
        'version': f'位于 {found}' if found else '',
        'ok': found is not None,
        'required': 'header file (gtest/gtest.h)',
        'message': '' if found else ('未找到 Google Test 头文件。'
                                    '请确保 CMake 已通过 FetchContent 下载，或手动安装。'),
    }


def check_compile_commands() -> dict:
    """检查 compile_commands.json 是否存在（clang-tidy 和 CodeGraph 需要）。"""
    locations = [
        'build/compile_commands.json',
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
            can_start: bool,      # 是否可以启动工作流（必须项全过）
            check_time: str,
            required: {name: {available, version, ok, message, purpose, fix_hint}},
            recommended: {...},
            extra: {...},
            summary: str,
        }
    """
    results = {
        'check_time': datetime.now().isoformat(),
        'required': {},
        'recommended': {},
        'nice_to_have': {},
        'extra_checks': {},
    }

    # 1. 检查必须工具
    for name, config in REQUIRED_TOOLS.items():
        if config['check'] == 'command_exists':
            available = command_exists(name)
            version = ''
            if available and 'version_flag' in config:
                version = get_command_version(
                    name,
                    config['version_flag'],
                    config.get('version_pattern')
                )
            results['required'][name] = {
                'available': available,
                'version': version,
                'ok': available,
                'required': config.get('min_version', 'any'),
                'purpose': config['purpose'],
                'fix_hint': config['fix_hint'],
            }

    # 2. 检查推荐工具
    for name, config in RECOMMENDED_TOOLS.items():
        if config['check'] == 'command_exists':
            check_name = config.get('env_override', name)
            actual_cmd = os.environ.get(check_name, name)
            available = command_exists(actual_cmd)
            results['recommended'][name] = {
                'available': available,
                'version': get_command_version(name) if available else '',
                'ok': available,
                'purpose': config['purpose'],
                'fix_hint': config['fix_hint'],
                'fallback': config.get('fallback', ''),
            }

    # 3. 检查增强工具
    for name, config in NICE_TO_HAVE_TOOLS.items():
        if config['check'] == 'command_exists':
            available = command_exists(name)
        elif config['check'] == 'pkg_config_exists':
            available = pkg_config_exists(config['pkg_name'])
        else:
            available = False
        results['nice_to_have'][name] = {
            'available': available,
            'version': '',
            'ok': True,  # 增强工具不影响运行判断
            'purpose': config['purpose'],
            'fix_hint': config['fix_hint'],
        }

    # 4. 额外检查
    results['extra_checks']['python_version'] = check_python_version()
    results['extra_checks']['googletest'] = check_googletest()
    results['extra_checks']['compile_commands'] = check_compile_commands()
    results['extra_checks']['project_structure'] = check_project_structure()
    results['extra_checks']['scripts'] = check_scripts()

    # 5. 汇总判断
    all_required_ok = all(v['ok'] for v in results['required'].values())
    all_extra_ok = all(v['ok'] for v in results['extra_checks'].values())
    all_recommended_ok = all(v['ok'] for v in results['recommended'].values())

    results['passed'] = all_required_ok and all_extra_ok
    results['can_start'] = all_required_ok and all_extra_ok

    # 6. 生成摘要
    required_failed = [k for k, v in results['required'].items() if not v['ok']]
    recommended_failed = [k for k, v in results['recommended'].items() if not v['ok']]
    extra_failed = [k for k, v in results['extra_checks'].items() if not v['ok']]

    parts = []
    if required_failed:
        parts.append(f'❌ 缺少必须工具 ({len(required_failed)}): {", ".join(required_failed)}')
    if extra_failed:
        parts.append(f'❌ 系统检查未通过 ({len(extra_failed)}): {", ".join(extra_failed)}')
    if recommended_failed:
        parts.append(f'⚠️ 缺少推荐工具 ({len(recommended_failed)}): {", ".join(recommended_failed)}')

    if not parts:
        if not all_recommended_ok:
            parts.append('⚠️ 必须项全部就绪，部分推荐工具缺失（工作流可正常运行但功能受限）')
        else:
            parts.append('✅ 所有环境和工具就绪')

    results['summary'] = '\n'.join(parts)
    results['required_failed'] = required_failed
    results['recommended_failed'] = recommended_failed
    results['extra_failed'] = extra_failed

    return results


def format_terminal_report(results: dict) -> str:
    """生成彩色终端格式的环境检查报告。"""
    lines = []
    lines.append('=' * 60)
    lines.append('  FST AI 测试工作流 — 环境检查')
    lines.append('=' * 60)
    lines.append(f'  检查时间: {results["check_time"]}')
    lines.append('')

    # 必须工具
    lines.append('【必须工具】— 缺少则无法运行')
    lines.append('-' * 40)
    for name, info in results['required'].items():
        status = '✅' if info['ok'] else '❌'
        ver = f' ({info["version"]})' if info.get('version') else ''
        lines.append(f'  {status} {name}{ver} — {info["purpose"]}')
        if not info['ok']:
            lines.append(f'     → 修复: {info["fix_hint"]}')

    # 项目检查
    lines.append('')
    lines.append('【项目检查】')
    lines.append('-' * 40)
    for name, info in results['extra_checks'].items():
        status = '✅' if info['ok'] else '❌'
        ver = f' ({info["version"]})' if info.get('version') else ''
        lines.append(f'  {status} {name}{ver}')
        if info.get('message') and not info['ok']:
            lines.append(f'     → {info["message"]}')

    # 推荐工具
    lines.append('')
    lines.append('【推荐工具】— 缺少则部分功能降级')
    lines.append('-' * 40)
    for name, info in results['recommended'].items():
        status = '✅' if info['ok'] else '⚠️'
        ver = f' ({info["version"]})' if info.get('version') else ''
        lines.append(f'  {status} {name}{ver} — {info["purpose"]}')
        if not info['ok']:
            lines.append(f'     → 修复: {info["fix_hint"]}')
            if info.get('fallback'):
                lines.append(f'     → 降级方案: {info["fallback"]}')

    # 增强工具
    lines.append('')
    lines.append('【增强工具】— 缺少不影响核心功能')
    lines.append('-' * 40)
    for name, info in results['nice_to_have'].items():
        status = '✅' if info['ok'] else '○'
        lines.append(f'  {status} {name} — {info["purpose"]}')

    # 结论
    lines.append('')
    lines.append('=' * 60)
    if results['can_start']:
        lines.append('  结论: ✅ 环境就绪，可以启动测试工作流')
    else:
        lines.append('  结论: ❌ 环境不满足最低要求，请先修复上述必须项')
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

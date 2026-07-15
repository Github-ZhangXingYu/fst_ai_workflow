#!/usr/bin/env python3
"""
覆盖率运行器：在gcov/lcov下编译和运行测试，生成覆盖率报告。
用于Stage 7：覆盖率分析。
"""
import subprocess
import json
import argparse
import os
import glob
from pathlib import Path


def clean_coverage_data(build_dir: str) -> bool:
    """清理旧的覆盖率数据文件。

    Args:
        build_dir: 构建目录

    Returns:
        bool: 是否成功
    """
    try:
        # 使用lcov清理计数器
        subprocess.run(
            ['lcov', '--zerocounters', '--directory', build_dir],
            capture_output=True, text=True, timeout=30
        )
        subprocess.run(
            ['lcov', '--directory', build_dir, '--zerocounters'],
            capture_output=True, text=True, timeout=30
        )
        # 也删除.gcda文件
        for root, dirs, files in os.walk(build_dir):
            for f in files:
                if f.endswith('.gcda'):
                    os.remove(os.path.join(root, f))
        return True
    except Exception as e:
        print(f"清理覆盖率数据时出错: {e}", file=__import__('sys').stderr)
        return False


def run_coverage(test_binary: str, source_dir: str, output_dir: str,
                 build_dir: str = 'build/test',
                 exclude_patterns: list = None) -> dict:
    """在覆盖率插桩下运行测试，生成lcov报告。

    流程：
    1. 清理旧覆盖率数据
    2. 运行测试二进制（已在覆盖率模式下编译）
    3. 用lcov采集覆盖率数据
    4. 过滤第三方和测试代码
    5. 生成HTML报告

    Args:
        test_binary: 测试二进制文件路径
        source_dir: 被测源码目录
        output_dir: 覆盖率报告输出目录
        build_dir: 包含.gcno文件的构建目录
        exclude_patterns: 排除的路径模式（glob格式）

    Returns:
        {
            success: bool,
            coverage_info_path: str,
            html_report_path: str,
            test_output: str
        }
    """
    os.makedirs(output_dir, exist_ok=True)

    # 默认排除模式
    if exclude_patterns is None:
        exclude_patterns = [
            '/usr/include/*',
            '/usr/local/include/*',
            '*/googletest/*',
            '*/gtest/*',
            '*/gmock/*',
            '*/test/*',
            '*/tests/*',
            '*/build/*',
            '*/third_party/*',
            '*/3rdparty/*',
            '*/external/*',
        ]

    # 1. 清理旧数据
    clean_coverage_data(build_dir)

    # 2. 运行测试
    try:
        test_result = subprocess.run(
            [test_binary],
            capture_output=True, text=True,
            timeout=300,
            env={**os.environ, 'GCOV_PREFIX': output_dir,
                 'GCOV_PREFIX_STRIP': '0'}
        )
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': '测试执行超时（300秒）',
            'coverage_info_path': '',
            'html_report_path': ''
        }

    # 3. 采集覆盖率数据
    coverage_info = os.path.join(output_dir, 'coverage.info')
    capture_args = [
        'lcov', '--capture',
        '--directory', build_dir,
        '--output-file', coverage_info,
        '--rc', 'lcov_branch_coverage=1',
        '--no-external',
    ]

    capture_result = subprocess.run(
        capture_args,
        capture_output=True, text=True,
        timeout=120
    )

    if not os.path.exists(coverage_info) or os.path.getsize(coverage_info) == 0:
        # 尝试用gcovr作为降级方案
        return _fallback_gcovr(build_dir, output_dir, test_result)

    # 4. 过滤覆盖率数据
    filtered_info = os.path.join(output_dir, 'coverage_filtered.info')
    filter_args = [
        'lcov',
        '--remove', coverage_info,
    ]
    for pattern in exclude_patterns:
        filter_args.append(pattern)
    filter_args.extend([
        '--output-file', filtered_info,
        '--rc', 'lcov_branch_coverage=1',
    ])

    filter_result = subprocess.run(
        filter_args,
        capture_output=True, text=True,
        timeout=60
    )

    final_info = filtered_info if os.path.exists(filtered_info) else coverage_info

    # 5. 生成HTML报告
    html_dir = os.path.join(output_dir, 'html')
    genhtml_args = [
        'genhtml', final_info,
        '--output-directory', html_dir,
        '--rc', 'lcov_branch_coverage=1',
        '--title', 'FST 代码覆盖率报告',
        '--num-spaces', '2',
        '--legend',
        '--function-coverage',
        '--branch-coverage',
    ]

    genhtml_result = subprocess.run(
        genhtml_args,
        capture_output=True, text=True,
        timeout=120
    )

    # 6. 同时生成JSON摘要（通过coverage_parser.py完成）
    return {
        'success': capture_result.returncode == 0,
        'coverage_info_path': final_info,
        'raw_info_path': coverage_info,
        'html_report_path': os.path.join(html_dir, 'index.html')
        if genhtml_result.returncode == 0 else '',
        'genhtml_output': genhtml_result.stdout[-2000:]
        if genhtml_result.stdout else '',
        'test_exit_code': test_result.returncode
    }


def _fallback_gcovr(build_dir: str, output_dir: str, test_result) -> dict:
    """gcovr降级方案（当lcov不可用时）。"""
    try:
        html_dir = os.path.join(output_dir, 'html')
        os.makedirs(html_dir, exist_ok=True)
        result = subprocess.run(
            ['gcovr', '--root', '.', '--html', '--html-details',
             '-o', os.path.join(html_dir, 'index.html'),
             '--print-summary'],
            capture_output=True, text=True, timeout=60
        )
        return {
            'success': result.returncode == 0,
            'method': 'gcovr_fallback',
            'coverage_info_path': '',
            'html_report_path': os.path.join(html_dir, 'index.html'),
            'test_exit_code': test_result.returncode
        }
    except FileNotFoundError:
        return {
            'success': False,
            'error': 'lcov和gcovr均不可用',
            'method': 'none',
            'coverage_info_path': '',
            'html_report_path': '',
            'test_exit_code': test_result.returncode
        }


def check_tools_available() -> dict:
    """检查覆盖率工具的可用性。

    Returns:
        {lcov: bool, genhtml: bool, gcovr: bool, gcov: bool}
    """
    tools = {}
    for tool in ['lcov', 'genhtml', 'gcovr', 'gcov']:
        result = subprocess.run(
            ['which', tool] if os.name != 'nt' else ['where', tool],
            capture_output=True, text=True
        )
        tools[tool] = result.returncode == 0
    return tools


def main():
    parser = argparse.ArgumentParser(
        description='FST覆盖率运行器：gcov/lcov覆盖率采集和HTML报告生成'
    )
    parser.add_argument('--binary', required=True,
                        help='测试二进制文件路径')
    parser.add_argument('--source', required=True,
                        help='被测源码目录')
    parser.add_argument('--output', required=True,
                        help='覆盖率报告输出目录')
    parser.add_argument('--build-dir', default='build/test',
                        help='包含.gcno文件的构建目录')
    parser.add_argument('--exclude', nargs='*',
                        help='排除的路径模式（glob格式）')
    parser.add_argument('--check-tools', action='store_true',
                        help='检查覆盖率工具的可用性')

    args = parser.parse_args()

    if args.check_tools:
        tools = check_tools_available()
        print(json.dumps(tools, indent=2, ensure_ascii=False))
        return

    result = run_coverage(
        test_binary=args.binary,
        source_dir=args.source,
        output_dir=args.output,
        build_dir=args.build_dir,
        exclude_patterns=args.exclude
    )

    # 保存结果
    result_path = os.path.join(args.output, 'coverage_result.json')
    os.makedirs(args.output, exist_ok=True)
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

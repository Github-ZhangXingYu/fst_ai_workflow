#!/usr/bin/env python3
"""
测试运行器：执行Google Test测试二进制文件，解析测试结果。
用于Stage 6：测试执行。
支持Google Test和Google Benchmark。
"""
import subprocess
import json
import argparse
import os
import re
import glob
from pathlib import Path
from typing import Optional


def run_gtest_binary(binary_path: str, gtest_filter: str = None,
                     timeout: int = 300, repeat: int = 1,
                     shuffle: bool = False) -> dict:
    """运行Google Test二进制并解析结果。

    使用Google Test的JSON输出（--gtest_output=json:）和
    控制台输出两种方式解析测试结果。

    Args:
        binary_path: 测试二进制文件路径
        gtest_filter: Google Test过滤器模式（如 "SuiteName.*:-*Slow*"）
        timeout: 超时秒数
        repeat: 重复运行次数
        shuffle: 是否随机化测试顺序

    Returns:
        {
            success: bool,
            tests, passed, failed, skipped,
            suites: [{name, tests, passed, failures, skipped, cases: [...]}],
            total_time_ms, returncode
        }
    """
    if not os.path.exists(binary_path):
        return {
            'success': False,
            'error': f'测试二进制文件不存在: {binary_path}',
            'tests': 0, 'passed': 0, 'failed': 0, 'skipped': 0,
            'suites': []
        }

    args = [binary_path]

    # Google Test JSON格式输出
    json_output_path = f'{binary_path}.results.json'
    args.append(f'--gtest_output=json:{json_output_path}')

    if gtest_filter:
        args.append(f'--gtest_filter={gtest_filter}')
    if repeat > 1:
        args.append(f'--gtest_repeat={repeat}')
    if shuffle:
        args.append('--gtest_shuffle')

    try:
        result = subprocess.run(
            args,
            capture_output=True, text=True,
            timeout=timeout,
            env={**os.environ, 'GTEST_COLOR': 'no'}
        )
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': f'测试执行超时（{timeout}秒）',
            'tests': 0, 'passed': 0, 'failed': 0, 'skipped': 0,
            'suites': []
        }

    # 尝试解析JSON输出
    test_results = None
    if os.path.exists(json_output_path):
        try:
            with open(json_output_path, 'r', encoding='utf-8') as f:
                gtest_data = json.load(f)
            test_results = _parse_gtest_json(gtest_data)
        except (json.JSONDecodeError, KeyError, PermissionError):
            pass

    # 降级：解析控制台输出
    if test_results is None or test_results.get('tests', 0) == 0:
        test_results = _parse_gtest_console(result.stdout)

    test_results['returncode'] = result.returncode
    test_results['success'] = (result.returncode == 0 and
                               test_results.get('failed', 0) == 0)
    test_results['raw_stdout_last_500'] = result.stdout[-500:]

    return test_results


def run_benchmark_binary(binary_path: str, benchmark_filter: str = None,
                         timeout: int = 600) -> dict:
    """运行Google Benchmark二进制并解析结果。

    Args:
        binary_path: Benchmark二进制文件路径
        benchmark_filter: Benchmark过滤器
        timeout: 超时秒数

    Returns:
        {success, benchmarks: [{name, iterations, real_time, cpu_time, ...}], ...}
    """
    if not os.path.exists(binary_path):
        return {
            'success': False,
            'error': f'Benchmark二进制文件不存在: {binary_path}',
            'benchmarks': []
        }

    # 使用JSON输出格式
    args = [
        binary_path,
        '--benchmark_format=json',
        '--benchmark_out=/dev/stdout',
        '--benchmark_counters_tabular=true',
    ]
    if benchmark_filter:
        args.append(f'--benchmark_filter={benchmark_filter}')

    try:
        result = subprocess.run(
            args,
            capture_output=True, text=True,
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': f'Benchmark执行超时（{timeout}秒）',
            'benchmarks': []
        }

    # 尝试解析JSON（benchmark输出在stdout中）
    benchmarks = []
    try:
        # 找到最后一个完整的JSON对象
        json_start = result.stdout.rfind('{')
        json_end = result.stdout.rfind('}')
        if json_start >= 0 and json_end > json_start:
            json_str = result.stdout[json_start:json_end + 1]
            data = json.loads(json_str)
            benchmarks = data.get('benchmarks', [])
    except (json.JSONDecodeError, KeyError, IndexError):
        pass

    # 打印解析后的benchmarks用于调试
    return {
        'success': result.returncode == 0,
        'benchmarks': benchmarks,
        'benchmark_count': len(benchmarks),
        'returncode': result.returncode
    }


def _parse_gtest_json(data: dict) -> dict:
    """解析Google Test JSON输出格式。

    处理两种格式：
    1. {tests: N, testsuites: [...]}  (新格式)
    2. {tests: N, testsuite: [...]}   (旧格式)
    """
    suites = []
    total_tests = 0
    total_passed = 0
    total_failed = 0
    total_skipped = 0
    total_time_ms = 0

    # 确定testsuites的键名
    suite_key = 'testsuites' if 'testsuites' in data else 'testsuite'
    suite_list = data.get(suite_key, data.get('testsuite', []))

    if not isinstance(suite_list, list):
        suite_list = [suite_list] if suite_list else []

    for suite_data in suite_list:
        parsed = _parse_single_suite(suite_data)
        suites.append(parsed)
        total_tests += parsed['tests']
        total_passed += parsed['passed']
        total_failed += parsed['failures']
        total_skipped += parsed.get('skipped', 0)
        total_time_ms += parsed.get('time_ms', 0)

    return {
        'tests': total_tests,
        'passed': total_passed,
        'failed': total_failed,
        'skipped': total_skipped,
        'suites': suites,
        'total_time_ms': total_time_ms
    }


def _parse_single_suite(suite: dict) -> dict:
    """解析单个测试套件。"""
    testcases = suite.get('testcase', [])
    if not isinstance(testcases, list):
        testcases = [testcases] if testcases else []

    failures = 0
    passed = 0
    skipped = 0
    total_time = 0
    cases = []

    for tc in testcases:
        tc_name = tc.get('name', '?')
        tc_class = tc.get('classname', '?')

        # 判定状态
        has_failure = False
        if 'failures' in tc:
            failures_data = tc['failures']
            if isinstance(failures_data, list):
                has_failure = len(failures_data) > 0
            elif isinstance(failures_data, dict):
                has_failure = bool(failures_data)
            elif isinstance(failures_data, str):
                has_failure = bool(failures_data.strip())

        status = tc.get('status', '').upper()

        if has_failure or status == 'FAILED':
            status = 'FAILED'
            failures += 1
        elif 'DISABLED' in status or 'SKIPPED' in status:
            status = 'SKIPPED'
            skipped += 1
        else:
            status = 'PASSED'
            passed += 1

        # 提取失败消息
        failure_msg = ''
        if has_failure:
            fd = tc.get('failures', {})
            if isinstance(fd, dict):
                failure_msg = fd.get('message', str(fd))
            elif isinstance(fd, str):
                failure_msg = fd
            # 截断长失败消息
            if len(failure_msg) > 500:
                failure_msg = failure_msg[:500] + '...'

        case_time = float(tc.get('time', 0))
        total_time += case_time

        cases.append({
            'name': tc_name,
            'classname': tc_class,
            'status': status,
            'time_ms': int(case_time * 1000),
            'failure_message': failure_msg
        })

    return {
        'name': suite.get('name', ''),
        'tests': len(testcases),
        'passed': passed,
        'failures': failures,
        'skipped': skipped,
        'time_ms': int(total_time * 1000),
        'cases': cases
    }


def _parse_gtest_console(output: str) -> dict:
    """降级方案：解析Google Test控制台文本输出。"""
    tests = 0
    failed = 0
    passed = 0
    skipped = 0

    # 匹配 "[  PASSED  ] 42 tests."
    total_match = re.search(r'(\d+)\s+tests?\s+from', output)
    ran_match = re.search(r'(\d+)\s+test(?:s)?\s+ran', output, re.IGNORECASE)
    failed_match = re.search(r'(\d+)\s+test(?:s)?\s+FAILED', output, re.IGNORECASE)
    skipped_match = re.search(r'(\d+)\s+test(?:s)?\s+SKIPPED', output, re.IGNORECASE)

    if failed_match:
        failed = int(failed_match.group(1))
    if ran_match:
        total_ran = int(ran_match.group(1))
        if total_ran > tests:
            tests = total_ran
    if skipped_match:
        skipped = int(skipped_match.group(1))
    if total_match:
        tests = max(tests, int(total_match.group(1)))

    passed = tests - failed

    return {
        'tests': tests,
        'passed': passed,
        'failed': failed,
        'skipped': skipped,
        'suites': [],
        'parse_method': 'console_fallback'
    }


def find_test_binaries(build_dir: str, pattern: str = '*_test') -> list:
    """在构建目录中查找测试二进制文件。

    Args:
        build_dir: 构建目录
        pattern: 文件名匹配模式

    Returns:
        [str]: 测试二进制文件路径列表
    """
    binaries = []
    # 递归搜索
    for root, dirs, files in os.walk(build_dir):
        for f in files:
            if (pattern in f or f.endswith('_test') or f.endswith('_tests')
                    or f.endswith('_benchmark')):
                full_path = os.path.join(root, f)
                if os.access(full_path, os.X_OK) or '.exe' in f:
                    binaries.append(full_path)
    return sorted(binaries)


def main():
    parser = argparse.ArgumentParser(
        description='FST测试运行器：执行Google Test/Benchmark，解析结果'
    )
    parser.add_argument('--binary', required=True,
                        help='测试二进制文件路径')
    parser.add_argument('--gtest-filter',
                        help='Google Test过滤器（如 SuiteName.*）')
    parser.add_argument('--benchmark', action='store_true',
                        help='以Benchmark模式运行')
    parser.add_argument('--benchmark-filter',
                        help='Benchmark过滤器')
    parser.add_argument('--output',
                        help='结果JSON输出路径')
    parser.add_argument('--timeout', type=int, default=300,
                        help='超时秒数（默认300，benchmark默认600）')
    parser.add_argument('--repeat', type=int, default=1,
                        help='重复运行次数')
    parser.add_argument('--shuffle', action='store_true',
                        help='随机化测试顺序')
    parser.add_argument('--find-binaries', action='store_true',
                        help='在构建目录中查找所有测试二进制')
    parser.add_argument('--build-dir', default='build/test',
                        help='构建目录路径（用于--find-binaries）')

    args = parser.parse_args()

    if args.find_binaries:
        binaries = find_test_binaries(args.build_dir)
        for b in binaries:
            print(b)
        return

    if args.benchmark:
        result = run_benchmark_binary(
            args.binary,
            benchmark_filter=args.benchmark_filter,
            timeout=max(args.timeout, 600)
        )
    else:
        result = run_gtest_binary(
            args.binary,
            gtest_filter=args.gtest_filter,
            timeout=args.timeout,
            repeat=args.repeat,
            shuffle=args.shuffle
        )

    output = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)

    # 打印摘要
    if not args.benchmark:
        print(f"测试: {result.get('tests', 0)} 总, "
              f"{result.get('passed', 0)} 通过, "
              f"{result.get('failed', 0)} 失败, "
              f"{result.get('skipped', 0)} 跳过")
        if result.get('failed', 0) > 0:
            for suite in result.get('suites', []):
                for case in suite.get('cases', []):
                    if case['status'] == 'FAILED':
                        print(f"  FAILED: {suite['name']}.{case['name']}")
                        if case.get('failure_message'):
                            print(f"    {case['failure_message'][:200]}")
    else:
        print(f"Benchmark: {result.get('benchmark_count', 0)} 个")
    print(output)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
测试扫描器：扫描test/目录，解析Google Test宏，建立函数到测试的映射表。
用于Stage 3：已有测试评估。
"""
import os
import re
import json
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Optional

# Google Test宏模式
GTEST_PATTERNS = {
    'TEST': re.compile(r'TEST\(\s*(\w+)\s*,\s*(\w+)\s*\)'),
    'TEST_F': re.compile(r'TEST_F\(\s*(\w+)\s*,\s*(\w+)\s*\)'),
    'TEST_P': re.compile(r'TEST_P\(\s*(\w+)\s*,\s*(\w+)\s*\)'),
    'TYPED_TEST': re.compile(r'TYPED_TEST\(\s*(\w+)\s*,\s*(\w+)\s*\)'),
    'TYPED_TEST_P': re.compile(r'TYPED_TEST_P\(\s*(\w+)\s*,\s*(\w+)\s*\)'),
    'INSTANTIATE_TEST_SUITE_P': re.compile(
        r'INSTANTIATE_TEST_SUITE_P\(\s*(\w+)\s*,\s*(\w+)'
    ),
}

# Google Benchmark模式
BENCHMARK_PATTERN = re.compile(r'BENCHMARK\(\s*(\w+)\s*\)')
BENCHMARK_TEMPLATE_PATTERN = re.compile(
    r'BENCHMARK_TEMPLATE\d?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)'
)

# Google Mock模式
MOCK_METHOD_PATTERN = re.compile(r'MOCK_METHOD\d*\s*\(\s*(\w+)\s*,\s*(\w+)\s*\(')

# 从测试名推断目标函数：约定为 FunctionName_Scenario_Expected
TARGET_FUNCTION_REGEX = re.compile(r'^(\w+?)_')


def scan_test_directory(test_root: str) -> dict:
    """扫描所有测试文件，将测试映射到目标函数。

    遍历test/下所有.cpp文件，解析：
    - Google Test宏（TEST/TEST_F/TEST_P等）
    - Google Benchmark宏
    - Mock方法声明
    建立 函数名 → [测试信息列表] 的映射。

    Args:
        test_root: test/目录的根路径

    Returns:
        {
            function_tests: {function_name: [test_info, ...]},
            all_tests: [test_info, ...],
            total_tests: int,
            covered_functions: int,
            module_stats: {module: {unit: N, integration: N, ...}}
        }
    """
    test_path = Path(test_root)
    if not test_path.exists():
        return {
            'function_tests': {},
            'all_tests': [],
            'total_tests': 0,
            'covered_functions': 0,
            'module_stats': {}
        }

    function_tests = defaultdict(list)
    all_tests = []
    module_stats = defaultdict(lambda: defaultdict(int))

    for cpp_file in test_path.rglob('*.cpp'):
        # 跳过构建目录
        if 'build/' in str(cpp_file) or 'cmake-build' in str(cpp_file):
            continue

        relative_path = cpp_file.relative_to(test_path)
        parts = relative_path.parts
        module = parts[0] if len(parts) > 0 else 'unknown'
        test_type = _classify_test_type(relative_path)

        try:
            with open(cpp_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except (PermissionError, OSError):
            continue

        # 解析Google Test用例
        for pattern_name, pattern in GTEST_PATTERNS.items():
            for match in pattern.finditer(content):
                if pattern_name == 'INSTANTIATE_TEST_SUITE_P':
                    suite = match.group(2)
                    name = match.group(1)
                else:
                    suite = match.group(1)
                    name = match.group(2)

                target = _infer_target_function(name, suite, content)

                test_info = {
                    'suite': suite,
                    'name': name,
                    'file': str(relative_path),
                    'file_absolute': str(cpp_file),
                    'module': module,
                    'test_type': test_type,
                    'test_framework': 'gtest',
                    'gtest_macro': pattern_name,
                    'target_function': target,
                    'full_name': f"{suite}.{name}"
                }
                all_tests.append(test_info)
                if target:
                    function_tests[target].append(test_info)

                module_stats[module][test_type] += 1

        # 解析Google Benchmark
        for match in BENCHMARK_PATTERN.finditer(content):
            target = match.group(1)
            test_info = {
                'suite': 'Benchmark',
                'name': f'BM_{target}',
                'file': str(relative_path),
                'file_absolute': str(cpp_file),
                'module': module,
                'test_type': 'performance',
                'test_framework': 'benchmark',
                'gtest_macro': 'BENCHMARK',
                'target_function': target,
                'full_name': f"BM_{target}"
            }
            all_tests.append(test_info)
            function_tests[target].append(test_info)
            module_stats[module]['performance'] += 1

    # 将defaultdict转换为普通dict
    function_tests_dict = {k: list(v) for k, v in function_tests.items()}
    module_stats_dict = {
        k: dict(v) for k, v in module_stats.items()
    }

    return {
        'function_tests': function_tests_dict,
        'all_tests': all_tests,
        'total_tests': len(all_tests),
        'covered_functions': len(function_tests_dict),
        'module_stats': module_stats_dict
    }


def _classify_test_type(relative_path: Path) -> str:
    """根据目录结构分类测试类型。

    测试类型映射：
    - unit/        → unit
    - integration/ → integration
    - performance/ 或 benchmark/ → performance
    - tools/       → tools
    - 其他         → unknown
    """
    parts = [p.lower() for p in relative_path.parts]
    for p in parts:
        if p in ('unit', 'unittest', 'unit_test'):
            return 'unit'
        if p in ('integration', 'integ', 'integration_test'):
            return 'integration'
        if p in ('performance', 'perf', 'benchmark', 'perf_test'):
            return 'performance'
        if p in ('tools', 'helpers', 'util', 'mocks'):
            return 'tools'
    return 'unknown'


def _infer_target_function(test_name: str, suite_name: str,
                          file_content: str) -> Optional[str]:
    """推断该测试用例测试的目标函数。

    推断策略（按优先级）：
    1. 命名约定：FunctionName_Scenario_Expected → FunctionName
    2. Suite名匹配：如果Suite名看起来像函数名
    3. Mock方法：从EXPECT_CALL/MOCK_METHOD中提取

    Args:
        test_name: 测试名
        suite_name: 测试套件名
        file_content: 测试文件内容

    Returns:
        推断的目标函数名，或None
    """
    # 策略1: 命名约定
    match = TARGET_FUNCTION_REGEX.match(test_name)
    if match:
        candidate = match.group(1)
        # 排除常见的非函数前缀
        if candidate not in ('test', 'Test', 'it', 'should', 'when', 'given'):
            return candidate

    # 策略2: Suite名可能直接就是被测类名
    # 不做过度推断，让AI来判断
    return suite_name


def build_assessment(impact_set: list, test_map: dict,
                     source_dir: str = 'service') -> dict:
    """为每个影响函数构建测试评估。

    评估结论：
    - reuse: 已有覆盖该函数多个场景的充分测试
    - adapt: 有测试但需要修改（如接口变更）
    - new: 没有现有测试或测试不充分

    Args:
        impact_set: 影响函数名列表
        test_map: 函数→测试映射（来自scan_test_directory）
        source_dir: 源码目录（用于读取源码行数）

    Returns:
        {function_name: {existing_tests, verdict, reason, needed_test_types}}
    """
    assessment = {}

    for func in impact_set:
        existing = test_map.get(func, [])
        test_types = set(t['test_type'] for t in existing)

        if not existing:
            verdict = 'new'
            reason = f'函数 {func} 没有现有的测试用例'
        elif 'unit' in test_types and len(existing) >= 3:
            # 有3个以上单元测试且涵盖不同场景 → 可能充分
            verdict = 'reuse'
            reason = (f'已有 {len(existing)} 个测试用例'
                      f'（含 {",".join(sorted(test_types))} 测试），覆盖较充分')
        elif 'unit' in test_types:
            verdict = 'adapt'
            reason = (f'已有 {len(existing)} 个测试但场景覆盖可能不足，'
                      f'建议审查并补充')
        else:
            verdict = 'adapt'
            reason = (f'已有 {len(existing)} 个测试但缺少单元测试'
                      f'（仅有 {",".join(sorted(test_types))}），需要补充')

        # 确定还需要的测试类型
        needed = _determine_needed_types(existing)

        assessment[func] = {
            'existing_tests': existing,
            'existing_test_count': len(existing),
            'existing_test_types': sorted(test_types),
            'verdict': verdict,
            'reason': reason,
            'needed_test_types': needed,
            'needed_test_count': len(needed)
        }

    return assessment


def _determine_needed_types(existing_tests: list) -> list:
    """确定该函数还缺少哪些类型的测试。"""
    existing_types = set(t['test_type'] for t in existing_tests)
    # 所有希望的测试类型 → 已存在的 = 缺少的
    all_desired = {'unit', 'integration', 'performance'}
    # tools类型不算
    return sorted(all_desired - existing_types)


def main():
    parser = argparse.ArgumentParser(
        description='FST测试扫描器：扫描已有测试，建立函数映射'
    )
    parser.add_argument('--impact-set', required=True,
                        help='影响集JSON文件路径（impact_set.json）')
    parser.add_argument('--output', required=True,
                        help='评估结果输出路径')
    parser.add_argument('--test-dir', default='test',
                        help='测试目录根路径')
    parser.add_argument('--source-dir', default='service',
                        help='源码目录根路径')
    parser.add_argument('--scan-only', action='store_true',
                        help='只扫描测试，不生成评估（输出原始映射）')

    args = parser.parse_args()

    # 加载影响集
    with open(args.impact_set, 'r', encoding='utf-8') as f:
        impact_data = json.load(f)

    impact_functions = impact_data.get('full_impact_set', [])
    if not impact_functions:
        impact_functions = impact_data.get('direct_changes', [])

    # 扫描测试
    scan_result = scan_test_directory(args.test_dir)

    if args.scan_only:
        # 只输出扫描结果
        output = scan_result
    else:
        # 构建评估
        assessment = build_assessment(
            impact_functions,
            scan_result['function_tests'],
            args.source_dir
        )

        output = {
            'assessment': assessment,
            'scan_summary': {
                'total_existing_tests': scan_result['total_tests'],
                'covered_functions': scan_result['covered_functions'],
                'module_stats': scan_result.get('module_stats', {})
            },
            'impacted_functions_count': len(impact_functions),
            'new_tests_needed': sum(
                1 for v in assessment.values() if v['verdict'] == 'new'),
            'adapt_tests_needed': sum(
                1 for v in assessment.values() if v['verdict'] == 'adapt'),
            'reuse_tests': sum(
                1 for v in assessment.values() if v['verdict'] == 'reuse'),
            'all_impact_functions': impact_functions
        }

    # 写入输出
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # 打印摘要
    if not args.scan_only:
        print(f"影响函数总数: {output['impacted_functions_count']}")
        print(f"  直接复用:   {output['reuse_tests']}")
        print(f"  需要改造:   {output['adapt_tests_needed']}")
        print(f"  需要新建:   {output['new_tests_needed']}")
    else:
        print(f"扫描完成: {scan_result['total_tests']} 个测试, "
              f"覆盖 {scan_result['covered_functions']} 个函数")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
覆盖率解析器：解析lcov .info文件，计算覆盖率指标，识别未覆盖区域。
用于Stage 7：覆盖率分析（分析阶段）。
"""
import re
import json
import argparse
import os
import sys
from collections import defaultdict


def parse_lcov_info(info_path: str) -> dict:
    """解析lcov .info文件，计算覆盖率指标。

    解析SF（源文件）、DA（行数据）、BRDA（分支数据）、
    FN（函数）、FNDA（函数命中）等标记。

    Args:
        info_path: lcov .info文件路径

    Returns:
        {
            overall: {line_coverage_pct, branch_coverage_pct, ...},
            files: {filepath: {line_coverage_pct, ...}},
            gaps: [{file, type, current, uncovered_items, ...}],
            functions: [{name, file, line, hit_count, covered}]
        }
    """
    if not os.path.exists(info_path):
        return {
            'error': f'覆盖率文件不存在: {info_path}',
            'overall': {'line_coverage_pct': 0, 'branch_coverage_pct': 0},
            'files': {},
            'gaps': [],
            'functions': []
        }

    with open(info_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # 按 end_of_record 分割文件段
    sections = content.split('end_of_record\n')

    files_coverage = {}
    all_functions = []

    total_lines_found = 0
    total_lines_hit = 0
    total_branches_found = 0
    total_branches_hit = 0
    total_functions_found = 0
    total_functions_hit = 0

    for section in sections:
        if not section.strip():
            continue

        # 提取源文件路径
        sf_match = re.search(r'^SF:(.+)$', section, re.MULTILINE)
        if not sf_match:
            continue

        file_path = sf_match.group(1)

        # ---- 解析行覆盖率 ----
        lines_found = 0
        lines_hit = 0
        uncovered_lines = []

        for da_match in re.finditer(r'^DA:(\d+),(\d+)$', section, re.MULTILINE):
            line_num = int(da_match.group(1))
            hit_count = int(da_match.group(2))
            lines_found += 1
            if hit_count > 0:
                lines_hit += 1
            else:
                uncovered_lines.append(line_num)

        # ---- 解析分支覆盖率 ----
        branches_found = 0
        branches_hit = 0
        uncovered_branches = []

        for br_match in re.finditer(
                r'^BRDA:(\d+),(\d+),(\d+),(\S+)$', section, re.MULTILINE):
            line_num = int(br_match.group(1))
            block = br_match.group(2)
            branch = br_match.group(3)
            taken = br_match.group(4)
            branches_found += 1
            if taken != '-' and taken != '0':
                branches_hit += 1
            else:
                uncovered_branches.append({
                    'line': line_num,
                    'block': block,
                    'branch': branch
                })

        # ---- 解析函数覆盖率 ----
        fn_map = {}  # line -> function_name
        for fn_match in re.finditer(r'^FN:(\d+),(.+)$', section, re.MULTILINE):
            fn_map[int(fn_match.group(1))] = fn_match.group(2)

        for fnda_match in re.finditer(
                r'^FNDA:(\d+),(.+)$', section, re.MULTILINE):
            hit = int(fnda_match.group(1))
            fn_name = fnda_match.group(2)
            fn_line = 0
            for line, name in fn_map.items():
                if name == fn_name:
                    fn_line = line
                    break

            all_functions.append({
                'name': fn_name,
                'file': file_path,
                'line': fn_line,
                'hit_count': hit,
                'covered': hit > 0
            })
            total_functions_found += 1
            if hit > 0:
                total_functions_hit += 1

        # 如果没解析到FNDA，从FN中统计
        if not fn_map:
            total_functions_found += 0

        # ---- 按文件汇总 ----
        if lines_found > 0:
            line_cov_pct = round(lines_hit / lines_found * 100, 2)
            branch_cov_pct = round(branches_hit / branches_found * 100, 2) \
                if branches_found > 0 else 100.0

            files_coverage[file_path] = {
                'lines_found': lines_found,
                'lines_hit': lines_hit,
                'line_coverage_pct': line_cov_pct,
                'uncovered_lines': uncovered_lines,
                'uncovered_line_count': len(uncovered_lines),
                'branches_found': branches_found,
                'branches_hit': branches_hit,
                'branch_coverage_pct': branch_cov_pct,
                'uncovered_branches': uncovered_branches,
                'uncovered_branch_count': len(uncovered_branches),
            }

            total_lines_found += lines_found
            total_lines_hit += lines_hit
            total_branches_found += branches_found
            total_branches_hit += branches_hit

    # ---- 总体指标 ----
    overall_line_cov = (
        round(total_lines_hit / total_lines_found * 100, 2)
        if total_lines_found > 0 else 0
    )
    overall_branch_cov = (
        round(total_branches_hit / total_branches_found * 100, 2)
        if total_branches_found > 0 else 100.0
    )
    overall_function_cov = (
        round(total_functions_hit / total_functions_found * 100, 2)
        if total_functions_found > 0 else 0
    )

    overall = {
        'line_coverage_pct': overall_line_cov,
        'branch_coverage_pct': overall_branch_cov,
        'function_coverage_pct': overall_function_cov,
        'total_lines': total_lines_found,
        'covered_lines': total_lines_hit,
        'total_branches': total_branches_found,
        'covered_branches': total_branches_hit,
        'total_functions': total_functions_found,
        'covered_functions': total_functions_hit,
        'line_threshold_met': overall_line_cov >= 90.0,
        'branch_threshold_met': overall_branch_cov >= 80.0,
    }

    # ---- 识别覆盖率缺口 ----
    gaps = _identify_coverage_gaps(files_coverage)

    return {
        'overall': overall,
        'files': files_coverage,
        'files_count': len(files_coverage),
        'functions': all_functions,
        'gaps': gaps,
        'thresholds': {
            'statement': {'target': 90, 'met': overall['line_threshold_met']},
            'branch': {'target': 80, 'met': overall['branch_threshold_met']},
        }
    }


def _identify_coverage_gaps(files_coverage: dict) -> list:
    """识别优先级覆盖率缺口。

    按未覆盖项数量排序，优先处理最大的缺口。

    Args:
        files_coverage: 按文件汇总的覆盖率数据

    Returns:
        [{file, type, current, target, uncovered_items, count}]
    """
    gaps = []

    for file_path, cov in files_coverage.items():
        # 行覆盖率缺口
        if cov['line_coverage_pct'] < 90.0:
            gaps.append({
                'file': file_path,
                'type': 'line_coverage',
                'current': cov['line_coverage_pct'],
                'target': 90.0,
                'uncovered_lines': cov['uncovered_lines'][:30],
                'total_uncovered': cov['uncovered_line_count'],
                'priority': 'high' if cov['line_coverage_pct'] < 50 else 'medium'
            })

        # 分支覆盖率缺口
        if cov['branch_coverage_pct'] < 80.0 and cov['branches_found'] > 0:
            gaps.append({
                'file': file_path,
                'type': 'branch_coverage',
                'current': cov['branch_coverage_pct'],
                'target': 80.0,
                'uncovered_branches': cov['uncovered_branches'][:30],
                'total_uncovered': cov['uncovered_branch_count'],
                'priority': 'high' if cov['branch_coverage_pct'] < 50 else 'medium'
            })

    # 按未覆盖项数量降序排序
    gaps.sort(key=lambda g: g.get('total_uncovered', 0), reverse=True)

    return gaps


def format_summary(parsed: dict) -> str:
    """格式化覆盖率摘要文本。

    Args:
        parsed: parse_lcov_info的返回值

    Returns:
        格式化的中文摘要字符串
    """
    overall = parsed.get('overall', {})
    lines = []
    lines.append('=' * 50)
    lines.append('FST 代码覆盖率分析摘要')
    lines.append('=' * 50)
    lines.append(f"语句覆盖率:   {overall.get('line_coverage_pct', 0)}% "
                 f"{'✓ 达标' if overall.get('line_threshold_met') else '✗ 未达标（目标≥90%）'}")
    lines.append(f"分支覆盖率:   {overall.get('branch_coverage_pct', 0)}% "
                 f"{'✓ 达标' if overall.get('branch_threshold_met') else '✗ 未达标（目标≥80%）'}")
    lines.append(f"函数覆盖率:   {overall.get('function_coverage_pct', 0)}%")
    lines.append(f"总行数:       {overall.get('total_lines', 0)} "
                 f"(覆盖 {overall.get('covered_lines', 0)})")
    lines.append(f"总分支数:     {overall.get('total_branches', 0)} "
                 f"(覆盖 {overall.get('covered_branches', 0)})")
    lines.append(f"分析文件数:   {parsed.get('files_count', 0)}")

    gaps = parsed.get('gaps', [])
    if gaps:
        lines.append(f"\n覆盖率缺口 ({len(gaps)} 个):")
        for gap in gaps[:10]:
            lines.append(
                f"  [{gap['priority']}] {gap['type']}: {gap['file']} "
                f"当前 {gap['current']}% → 目标 {gap['target']}% "
                f"(未覆盖: {gap.get('total_uncovered', '?')} 项)"
            )
    else:
        lines.append("\n全部文件覆盖率达标 ✓")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='FST覆盖率解析器：解析lcov .info文件，计算覆盖率指标'
    )
    parser.add_argument('--input', required=True,
                        help='lcov .info文件路径或包含它的目录')
    parser.add_argument('--output', required=True,
                        help='解析结果JSON输出路径')
    parser.add_argument('--summary', action='store_true',
                        help='同时输出文本摘要')

    args = parser.parse_args()

    # 支持目录输入（自动找coverage_filtered.info或coverage.info）
    info_path = args.input
    if os.path.isdir(info_path):
        # 优先使用过滤后的文件
        for name in ['coverage_filtered.info', 'coverage.info']:
            candidate = os.path.join(info_path, name)
            if os.path.exists(candidate):
                info_path = candidate
                break

    result = parse_lcov_info(info_path)

    # 写入JSON输出
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # 打印摘要
    print(format_summary(result))

    # 也输出JSON（用于管道）
    if args.summary:
        json.dumps(result, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
覆盖率分析器：采集 + 解析 + 缺口识别，一步完成。
用于 Stage 7：覆盖率分析。
"""
import subprocess
import json
import argparse
import os
import re


# ============================================================
# 覆盖率采集（原 coverage_runner.py 逻辑）
# ============================================================

def clean_coverage_data(build_dir: str) -> bool:
    """清理旧的覆盖率数据文件。"""
    try:
        subprocess.run(
            ['lcov', '--zerocounters', '--directory', build_dir],
            capture_output=True, text=True, timeout=30
        )
        subprocess.run(
            ['lcov', '--directory', build_dir, '--zerocounters'],
            capture_output=True, text=True, timeout=30
        )
        for root, _dirs, files in os.walk(build_dir):
            for f in files:
                if f.endswith('.gcda'):
                    os.remove(os.path.join(root, f))
        return True
    except Exception as e:
        print(f"清理覆盖率数据时出错: {e}", file=__import__('sys').stderr)
        return False


def _run_lcov_capture(test_binary: str, build_dir: str,
                       work_dir: str, exclude_patterns: list) -> dict:
    """运行 lcov 采集覆盖率数据，返回 .info 文件路径。"""
    os.makedirs(work_dir, exist_ok=True)

    # 1. 清理
    clean_coverage_data(build_dir)

    # 2. 运行测试
    try:
        test_result = subprocess.run(
            [test_binary],
            capture_output=True, text=True, timeout=300,
            env={**os.environ, 'GCOV_PREFIX': work_dir,
                 'GCOV_PREFIX_STRIP': '0'}
        )
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': '测试执行超时（300秒）',
                'info_path': '', 'html_path': ''}

    # 3. lcov --capture
    raw_info = os.path.join(work_dir, 'coverage.info')
    capture_result = subprocess.run(
        ['lcov', '--capture', '--directory', build_dir,
         '--output-file', raw_info, '--rc', 'lcov_branch_coverage=1',
         '--no-external'],
        capture_output=True, text=True, timeout=120
    )

    if not os.path.exists(raw_info) or os.path.getsize(raw_info) == 0:
        return {
            'success': False,
            'error': 'lcov 采集失败：生成的 coverage.info 为空',
            'info_path': '', 'html_path': '',
            'test_exit_code': test_result.returncode
        }

    # 4. 过滤
    filtered_info = os.path.join(work_dir, 'coverage_filtered.info')
    filter_args = ['lcov', '--remove', raw_info]
    filter_args.extend(exclude_patterns)
    filter_args.extend(['--output-file', filtered_info,
                        '--rc', 'lcov_branch_coverage=1'])
    subprocess.run(filter_args, capture_output=True, text=True, timeout=60)

    info_path = filtered_info if os.path.exists(filtered_info) else raw_info

    # 5. HTML 报告
    html_dir = os.path.join(work_dir, 'html')
    gen_result = subprocess.run(
        ['genhtml', info_path, '--output-directory', html_dir,
         '--rc', 'lcov_branch_coverage=1', '--title', 'FST 代码覆盖率报告',
         '--num-spaces', '2', '--legend', '--function-coverage', '--branch-coverage'],
        capture_output=True, text=True, timeout=120
    )

    return {
        'success': capture_result.returncode == 0,
        'info_path': info_path,
        'html_path': os.path.join(html_dir, 'index.html')
                     if gen_result.returncode == 0 else '',
        'test_exit_code': test_result.returncode
    }




# ============================================================
# 覆盖率解析（原 coverage_parser.py 逻辑）
# ============================================================

def _parse_lcov_info(info_path: str) -> dict:
    """解析 lcov .info 文件，计算覆盖率指标和缺口。"""
    if not info_path or not os.path.exists(info_path):
        return {
            'error': f'覆盖率文件不存在: {info_path or "(空)"}',
            'overall': {'line_coverage_pct': 0, 'branch_coverage_pct': 0,
                        'function_coverage_pct': 0},
            'files': {}, 'gaps': [], 'functions': []
        }

    with open(info_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    sections = content.split('end_of_record\n')
    files_coverage = {}
    all_functions = []
    total_lines = total_lines_hit = 0
    total_branches = total_branches_hit = 0
    total_funcs = total_funcs_hit = 0

    for section in sections:
        if not section.strip():
            continue
        sf_match = re.search(r'^SF:(.+)$', section, re.MULTILINE)
        if not sf_match:
            continue
        file_path = sf_match.group(1)

        # 行覆盖率
        lines_found = lines_hit = 0
        uncovered_lines = []
        for da in re.finditer(r'^DA:(\d+),(\d+)$', section, re.MULTILINE):
            ln, hit = int(da.group(1)), int(da.group(2))
            lines_found += 1
            if hit > 0:
                lines_hit += 1
            else:
                uncovered_lines.append(ln)

        # 分支覆盖率
        branches_found = branches_hit = 0
        uncovered_branches = []
        for br in re.finditer(r'^BRDA:(\d+),(\d+),(\d+),(\S+)$', section, re.MULTILINE):
            ln, blk, br_id, taken = int(br.group(1)), br.group(2), br.group(3), br.group(4)
            branches_found += 1
            if taken != '-' and taken != '0':
                branches_hit += 1
            else:
                uncovered_branches.append({'line': ln, 'block': blk, 'branch': br_id})

        # 函数覆盖率
        fn_map = {int(m.group(1)): m.group(2)
                  for m in re.finditer(r'^FN:(\d+),(.+)$', section, re.MULTILINE)}
        for fnda in re.finditer(r'^FNDA:(\d+),(.+)$', section, re.MULTILINE):
            hit = int(fnda.group(1))
            fn_name = fnda.group(2)
            fn_line = next((l for l, n in fn_map.items() if n == fn_name), 0)
            all_functions.append(
                {'name': fn_name, 'file': file_path, 'line': fn_line,
                 'hit_count': hit, 'covered': hit > 0})
            total_funcs += 1
            if hit > 0:
                total_funcs_hit += 1

        if lines_found > 0:
            line_pct = round(lines_hit / lines_found * 100, 2)
            branch_pct = round(branches_hit / branches_found * 100, 2) if branches_found > 0 else 100.0
            files_coverage[file_path] = {
                'lines_found': lines_found, 'lines_hit': lines_hit,
                'line_coverage_pct': line_pct,
                'uncovered_lines': uncovered_lines,
                'uncovered_line_count': len(uncovered_lines),
                'branches_found': branches_found, 'branches_hit': branches_hit,
                'branch_coverage_pct': branch_pct,
                'uncovered_branches': uncovered_branches,
                'uncovered_branch_count': len(uncovered_branches),
            }
            total_lines += lines_found
            total_lines_hit += lines_hit
            total_branches += branches_found
            total_branches_hit += branches_hit

    overall_line = round(total_lines_hit / total_lines * 100, 2) if total_lines > 0 else 0
    overall_branch = round(total_branches_hit / total_branches * 100, 2) if total_branches > 0 else 100.0
    overall_func = round(total_funcs_hit / total_funcs * 100, 2) if total_funcs > 0 else 0

    overall = {
        'line_coverage_pct': overall_line, 'branch_coverage_pct': overall_branch,
        'function_coverage_pct': overall_func,
        'total_lines': total_lines, 'covered_lines': total_lines_hit,
        'total_branches': total_branches, 'covered_branches': total_branches_hit,
        'total_functions': total_funcs, 'covered_functions': total_funcs_hit,
        'line_threshold_met': overall_line >= 90.0,
        'branch_threshold_met': overall_branch >= 80.0,
    }

    gaps = _identify_gaps(files_coverage)

    return {
        'overall': overall, 'files': files_coverage,
        'files_count': len(files_coverage), 'functions': all_functions,
        'gaps': gaps, 'thresholds': {
            'statement': {'target': 90, 'met': overall['line_threshold_met']},
            'branch': {'target': 80, 'met': overall['branch_threshold_met']},
        }
    }


def _identify_gaps(files_coverage: dict) -> list:
    """识别优先级覆盖率缺口。"""
    gaps = []
    for fp, cov in files_coverage.items():
        if cov['line_coverage_pct'] < 90.0:
            gaps.append({
                'file': fp, 'type': 'line_coverage',
                'current': cov['line_coverage_pct'], 'target': 90.0,
                'uncovered_lines': cov['uncovered_lines'][:30],
                'total_uncovered': cov['uncovered_line_count'],
                'priority': 'high' if cov['line_coverage_pct'] < 50 else 'medium'
            })
        if cov['branch_coverage_pct'] < 80.0 and cov['branches_found'] > 0:
            gaps.append({
                'file': fp, 'type': 'branch_coverage',
                'current': cov['branch_coverage_pct'], 'target': 80.0,
                'uncovered_branches': cov['uncovered_branches'][:30],
                'total_uncovered': cov['uncovered_branch_count'],
                'priority': 'high' if cov['branch_coverage_pct'] < 50 else 'medium'
            })
    gaps.sort(key=lambda g: g.get('total_uncovered', 0), reverse=True)
    return gaps


def format_summary(report: dict) -> str:
    """格式化为中文文本摘要。"""
    o = report.get('overall', {})
    lines = [
        '=' * 50, 'FST 代码覆盖率分析摘要', '=' * 50,
        f"语句覆盖率: {o.get('line_coverage_pct', 0)}% "
        f"{'✓ 达标' if o.get('line_threshold_met') else '✗ 未达标（目标≥90%）'}",
        f"分支覆盖率: {o.get('branch_coverage_pct', 0)}% "
        f"{'✓ 达标' if o.get('branch_threshold_met') else '✗ 未达标（目标≥80%）'}",
        f"函数覆盖率: {o.get('function_coverage_pct', 0)}%",
        f"总行数: {o.get('total_lines', 0)} (覆盖 {o.get('covered_lines', 0)})",
        f"总分支: {o.get('total_branches', 0)} (覆盖 {o.get('covered_branches', 0)})",
        f"分析文件数: {report.get('files_count', 0)}"
    ]
    gaps = report.get('gaps', [])
    if gaps:
        lines.append(f"\n覆盖率缺口 ({len(gaps)} 个):")
        for g in gaps[:10]:
            lines.append(
                f"  [{g['priority']}] {g['type']}: {g['file']} "
                f"当前 {g['current']}% → 目标 {g['target']}% "
                f"(未覆盖: {g.get('total_uncovered', '?')} 项)")
    else:
        lines.append("\n全部文件覆盖率达标 ✓")
    return '\n'.join(lines)


# ============================================================
# 统一入口：采集 + 解析
# ============================================================

def coverage_analyze(test_binary: str, source_dir: str,
                      output_path: str = 'ai_workflow/state/coverage_report.json',
                      build_dir: str = 'build') -> dict:
    """一步完成覆盖率采集和解析。

    Args:
        test_binary: 测试二进制文件路径（如 product/bin/unittest/xxx_tests）
        source_dir: 被测源码目录
        output_path: 最终 JSON 报告输出路径
        build_dir: CMake 构建目录（用于 lcov --directory）

    Returns:
        完整的覆盖率报告 dict（同原 coverage_parser 输出）
    """
    exclude_patterns = [
        '/usr/include/*', '/usr/local/include/*',
        '*/googletest/*', '*/gtest/*', '*/gmock/*',
        '*/test/*', '*/tests/*', '*/build/*',
        '*/third_party/*', '*/3rdparty/*', '*/external/*',
    ]

    # 中间产物目录：放在 output_path 同级目录下
    work_dir = os.path.join(os.path.dirname(output_path) or 'ai_workflow/state', 'coverage')

    # 1. 采集
    capture_result = _run_lcov_capture(test_binary, build_dir, work_dir, exclude_patterns)
    if not capture_result['success']:
        return {
            'error': capture_result.get('error', '覆盖率采集失败'),
            'overall': {'line_coverage_pct': 0, 'branch_coverage_pct': 0,
                        'line_threshold_met': False, 'branch_threshold_met': False},
            'files': {}, 'gaps': [], 'functions': [],
            '_capture': capture_result,
        }

    # 2. 解析
    report = _parse_lcov_info(capture_result['info_path'])

    # 3. 附上采集元数据
    report['_capture'] = {
        'html_report_path': capture_result['html_path'],
        'info_path': capture_result['info_path'],
        'test_exit_code': capture_result.get('test_exit_code', -1),
    }

    # 4. 写入 JSON
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='FST 覆盖率分析器：采集 lcov 数据 + 解析指标（一步完成）')
    parser.add_argument('--binary', required=True,
                        help='测试二进制文件路径')
    parser.add_argument('--source', required=True,
                        help='被测源码目录')
    parser.add_argument('--output', default='ai_workflow/state/coverage_report.json',
                        help='最终 JSON 报告输出路径')
    parser.add_argument('--build-dir', default='build',
                        help='CMake 构建目录（用于 lcov 采集，默认 build/）')
    parser.add_argument('--summary', action='store_true',
                        help='完成后输出文本摘要')

    args = parser.parse_args()

    report = coverage_analyze(
        test_binary=args.binary, source_dir=args.source,
        output_path=args.output, build_dir=args.build_dir
    )

    if args.summary:
        print(format_summary(report))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

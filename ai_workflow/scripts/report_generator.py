#!/usr/bin/env python3
"""
报告生成器：根据工作流状态数据生成中文 Markdown 测试报告。
用于 Stage 8：报告生成。
"""
import json
import argparse
import os
from datetime import datetime
from pathlib import Path


def _load_json(filepath: Path, data: dict, key: str):
    """安全地加载 JSON 文件到 data 字典的指定 key。"""
    if filepath.exists():
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data[key] = json.load(f)
        except (json.JSONDecodeError, PermissionError):
            pass


def _load_state_data(state_dir: str) -> dict:
    """从 state 目录加载所有工作流数据。"""
    state_path = Path(state_dir)

    data = {
        'user': 'unknown', 'trigger_type': 'manual',
        'workflow_id': datetime.now().strftime('%Y%m%d_%H%M%S'),
        'changed_files_count': 0, 'impacted_functions_count': 0,
        'tests_total': 0, 'tests_passed': 0, 'tests_failed': 0, 'tests_skipped': 0,
        'line_coverage': 0, 'branch_coverage': 0,
        'line_threshold_met': False, 'branch_threshold_met': False,
        'changed_files': [], 'impact_set': {}, 'assessment': {},
        'test_results': {}, 'coverage_report': {},
        'coverage_files': {}, 'coverage_gaps': [],
        'compile_fixes': [], 'workflow_state': {},
        'failure_analysis': {},    # 失败分析汇总（来自 workflow_state.json）
        'failure_details': None,  # 失败分析详细数据（来自 failure_analysis.json）
    }

    _load_json(state_path / 'workflow_state.json', data, 'workflow_state')
    _load_json(state_path / 'changed_files.json', data, 'changed_files_raw')
    _load_json(state_path / 'impact_set.json', data, 'impact_set')
    _load_json(state_path / 'test_assessment.json', data, 'assessment')
    _load_json(state_path / 'test_results.json', data, 'test_results')
    _load_json(state_path / 'coverage_report.json', data, 'coverage_report')
    _load_json(state_path / 'failure_analysis.json', data, 'failure_details')

    # 从 workflow_state 提取元数据
    ws = data.get('workflow_state', {})
    data['user'] = ws.get('user', data['user'])
    data['trigger_type'] = ws.get('trigger_type', data['trigger_type'])
    data['workflow_id'] = ws.get('workflow_id', data['workflow_id'])
    data['failure_analysis'] = ws.get('failure_analysis', {})

    # 变更文件
    cf = data.get('changed_files_raw', {})
    data['changed_files'] = cf.get('changed_files', [])
    data['changed_files_count'] = cf.get('total_files', len(data['changed_files']))

    # 影响集
    impact = data.get('impact_set', {})
    data['impacted_functions_count'] = impact.get('impact_depth', {}).get(
        'total_unique', len(impact.get('full_impact_set', [])))

    # 测试结果
    tr = data.get('test_results', {})
    data['tests_total'] = tr.get('tests', 0)
    data['tests_passed'] = tr.get('passed', 0)
    data['tests_failed'] = tr.get('failed', 0)
    data['tests_skipped'] = tr.get('skipped', 0)

    # 覆盖率 — 兼容嵌套 {"overall": {...}} 和平面 {"line_coverage_pct": ...} 两种格式
    cr = data.get('coverage_report', {})
    if 'overall' in cr:
        overall = cr['overall']
    else:
        overall = cr  # 平面格式（编排器 Agent 直接写的顶层字段）
    data['line_coverage'] = overall.get('line_coverage_pct', 0)
    data['branch_coverage'] = overall.get('branch_coverage_pct', 0)
    data['line_threshold_met'] = overall.get('line_threshold_met', data['line_coverage'] >= 90)
    data['branch_threshold_met'] = overall.get('branch_threshold_met', data['branch_coverage'] >= 80)
    data['coverage_files'] = cr.get('files', {})
    data['coverage_gaps'] = cr.get('gaps', [])

    # 循环次数
    data['test_fix_loops'] = ws.get('test_fix_iterations', 0)
    data['coverage_supplement_loops'] = ws.get('coverage_supplement_iterations', 0)

    # 编译修复记录
    compile_fix_dir = state_path / 'compile_fixes'
    if compile_fix_dir.exists():
        for f in sorted(compile_fix_dir.iterdir()):
            if f.suffix == '.json':
                try:
                    with open(f, 'r', encoding='utf-8') as fh:
                        data['compile_fixes'].append(json.load(fh))
                except Exception:
                    pass

    return data


# ============================================================
# 报告生成
# ============================================================

def _verdict(data: dict) -> str:
    """计算总体判定文本。"""
    if data['test_fix_loops'] >= 4 and data['tests_total'] == 0:
        return '❌ FAIL — 编译失败未解决'
    if data['tests_failed'] > 0:
        fa = data.get('failure_analysis', {})
        service_bugs = fa.get('service_bugs', 0)
        test_bugs_unfixed = fa.get('test_bugs_unfixed', 0)
        parts = []
        if service_bugs > 0:
            parts.append(f'{service_bugs} 个 service 缺陷')
        if test_bugs_unfixed > 0:
            parts.append(f'{test_bugs_unfixed} 个 test_bug 未修复')
        if not parts:
            parts.append(f'{data["tests_failed"]} 个测试失败')
        return '⚠️ WARN — ' + '，'.join(parts)
    if not data['line_threshold_met'] or not data['branch_threshold_met']:
        return '⚠️ WARN — 覆盖率未达标'
    if data['tests_total'] == 0:
        return '⚠️ WARN — 无测试运行'
    return '✅ PASS'


def _method_label(method: str) -> str:
    """中文化分析方法名。"""
    return 'CodeGraph 调用图分析'


def _severity_label(severity: str) -> str:
    """中文化严重级别。"""
    return {
        'critical': '🔴 严重',
        'major': '🟠 重要',
        'minor': '🟡 轻微',
    }.get(severity, severity)


def _confidence_label(confidence: str) -> str:
    """中文化置信度。"""
    return {
        'high': '高',
        'medium': '中',
        'low': '低',
    }.get(confidence, confidence)


def _root_cause_label(root_cause: str) -> str:
    """中文化根因分类。"""
    return {
        'test_bug': '测试代码缺陷',
        'service_bug': 'Service 代码缺陷',
    }.get(root_cause, root_cause)


def generate_report(state_dir: str, output_path: str) -> str:
    """生成完整的 Markdown 测试报告。"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    data = _load_state_data(state_dir)

    w = []  # lines accumulator
    A = w.append

    lc = data['line_coverage']
    bc = data['branch_coverage']
    lc_ok = '✅' if data['line_threshold_met'] else '❌'
    bc_ok = '✅' if data['branch_threshold_met'] else '❌'

    # === 标题 ===
    A('# 🧪 FST AI 测试分析报告')
    A('')
    trigger_label = '自动触发' if data['trigger_type'] == 'auto' else '手动触发'
    A(f'| 项目 | 值 |')
    A(f'|------|----|')
    A(f'| 生成时间 | {timestamp} |')
    A(f'| 触发用户 | {data["user"]} |')
    A(f'| 触发方式 | {trigger_label} |')
    A(f'| 工作流 ID | {data["workflow_id"]} |')
    A(f'| 总体判定 | {_verdict(data)} |')
    A('')

    # === 1. 摘要 ===
    A('## 1. 📊 摘要')
    A('')
    fa = data.get('failure_analysis', {})
    A(f'| 指标 | 值 | 判定 |')
    A(f'|------|----|------|')
    A(f'| 变更文件数 | {data["changed_files_count"]} | — |')
    A(f'| 影响函数数 | {data["impacted_functions_count"]} | — |')
    A(f'| 测试总数 | {data["tests_total"]} | — |')
    A(f'| 测试通过 | {data["tests_passed"]} | — |')
    A(f'| 测试失败 | {data["tests_failed"]} | {"❌" if data["tests_failed"] > 0 else "—"} |')
    A(f'| 语句覆盖率 | {lc}% | {lc_ok} (目标 ≥90%) |')
    A(f'| 分支覆盖率 | {bc}% | {bc_ok} (目标 ≥80%) |')
    A(f'| 测试修复次数 | {data["test_fix_loops"]} | — |')
    A(f'| 覆盖率补充次数 | {data["coverage_supplement_loops"]} | — |')
    if fa.get('test_bugs_fixed', 0) > 0:
        A(f'| Test Bug 修复 | {fa["test_bugs_fixed"]} 个 | ✅ |')
    if fa.get('test_bugs_unfixed', 0) > 0:
        A(f'| Test Bug 未修复 | {fa["test_bugs_unfixed"]} 个 | ❌ |')
    if fa.get('service_bugs', 0) > 0:
        A(f'| Service 缺陷 | {fa["service_bugs"]} 个 | 🔴 |')
    A('')

    # === 2. 变更影响分析 ===
    A('## 2. 🔍 变更影响分析')
    A('')
    impact = data.get('impact_set', {})
    A(f'分析方法: **{_method_label(impact.get("analysis_method", "unknown"))}**')
    A('')
    depth = impact.get('impact_depth', {})
    A(f'- 直接影响: **{depth.get("direct", 0)}** 个函数')
    A(f'- 间接调用者: **{depth.get("indirect_callers", 0)}**')
    A(f'- 间接被调用者: **{depth.get("indirect_callees", 0)}**')
    A(f'- 合计影响: **{depth.get("total_unique", 0)}** 个函数')
    A('')

    direct = impact.get('direct_changes', [])
    callers_list = impact.get('callers', [])
    callees_list = impact.get('callees', [])
    if direct or callers_list or callees_list:
        A('| 影响类型 | 函数 |')
        A('|---------|------|')
        for fn in direct:
            A(f'| 🔴 直接变更 | `{fn}` |')
        for fn in callers_list:
            if fn not in direct:
                A(f'| 🟡 调用者 | `{fn}` |')
        for fn in callees_list:
            if fn not in direct:
                A(f'| 🔵 被调用者 | `{fn}` |')
        A('')

    # === 3. 已有测试评估 ===
    A('## 3. 📋 已有测试评估')
    A('')
    assessment = data.get('assessment', {}).get('assessment', {})
    if assessment:
        new_c = sum(1 for v in assessment.values() if v.get('verdict') == 'new')
        adapt_c = sum(1 for v in assessment.values() if v.get('verdict') == 'adapt')
        reuse_c = sum(1 for v in assessment.values() if v.get('verdict') == 'reuse')
        A(f'| 结论 | 数量 |')
        A(f'|------|------|')
        A(f'| ✅ 可直接复用 | {reuse_c} |')
        A(f'| 🔧 需改造 | {adapt_c} |')
        A(f'| 🆕 需新建 | {new_c} |')
        A('')
        A('| 函数 | 结论 | 原因 | 已有测试 | 缺失类型 |')
        A('|------|------|------|---------|---------|')
        for fn, info in assessment.items():
            v = info.get('verdict', '?')
            needed = ', '.join(info.get('needed_test_types', [])) or '—'
            A(f'| `{fn}` | {v} | {info.get("reason", "")} | {info.get("existing_test_count", 0)} | {needed} |')
        A('')
    else:
        A('无可用的测试评估数据。')
        A('')

    # === 4. 测试执行结果 ===
    A('## 4. ✅ 测试执行结果')
    A('')
    tr = data.get('test_results', {})
    A(f'- ✅ 通过: **{tr.get("passed", 0)}**')
    A(f'- ❌ 失败: **{tr.get("failed", 0)}**')
    A(f'- ⏭️ 跳过: **{tr.get("skipped", 0)}**')
    A(f'- ⏱ 总耗时: **{tr.get("total_time_ms", 0)}ms**')
    A('')

    # ---- 失败用例详细分析（含根因结论） ----
    failure_details = data.get('failure_details')
    if failure_details:
        all_cases = failure_details.get('failed_cases', [])
        if all_cases:
            A('### 4.1 失败用例分析')
            A('')
            A('| 测试用例 | 根因 | 置信度 | 分析结论 |')
            A('|---------|------|--------|---------|')
            for case in all_cases:
                tc = case.get('test_case', '?')
                rc = _root_cause_label(case.get('root_cause', '?'))
                conf = _confidence_label(case.get('confidence', 'medium'))
                analysis = (case.get('analysis', '') or '')[:120]
                A(f'| `{tc}` | {rc} | {conf} | {analysis} |')
            A('')

    suites = tr.get('suites', [])
    if suites:
        A('### 4.2 测试套件明细')
        A('')
        A('| 测试套件 | 测试用例 | 状态 | 耗时 |')
        A('|---------|---------|------|------|')
        for suite in suites:
            for case in suite.get('cases', []):
                status = case.get('status', '?')
                icon = '✅' if status == 'PASSED' else ('❌' if status == 'FAILED' else '⏭️')
                A(f'| {suite["name"]} | {case["name"]} | {icon} {status} | {case.get("time_ms", 0)}ms |')
                if case.get('failure_message'):
                    msg = case['failure_message'][:300].replace('\n', ' ')
                    A(f'| | > 失败: {msg} | | |')
        A('')

    # === 5. Service 代码缺陷 ===
    A('## 5. 🔴 Service 代码缺陷')
    A('')
    if failure_details:
        service_bugs = failure_details.get('service_bugs', [])
        if service_bugs:
            A(f'测试发现 **{len(service_bugs)}** 个 service 代码缺陷，需由其他修复流程处理：')
            A('')
            for i, bug in enumerate(service_bugs, 1):
                sev = _severity_label(bug.get('severity', 'major'))
                conf = _confidence_label(bug.get('confidence', 'medium'))
                A(f'### 5.{i}. {sev} — `{bug.get("test_case", "")}`')
                A('')
                A(f'| 属性 | 值 |')
                A(f'|------|----|')
                A(f'| 置信度 | {conf} |')
                A(f'| 被测函数 | `{bug.get("service_function", "?")}` |')
                A(f'| 源码位置 | `{bug.get("source_location", "?")}` |')
                A(f'| 失败现象 | {bug.get("analysis", "")} |')
                if bug.get('fix_suggestion'):
                    A(f'| 修复建议 | {bug["fix_suggestion"]} |')
                A('')
        else:
            A('✅ 未发现 service 代码缺陷。')
            A('')
    else:
        A('✅ 未发现 service 代码缺陷。')
        A('')

    # === 6. 测试代码修复记录 ===
    A('## 6. 🔧 测试代码修复记录')
    A('')
    test_bugs_fixed = fa.get('test_bugs_fixed', 0)
    test_bugs_unfixed = fa.get('test_bugs_unfixed', 0)
    A(f'- 修复成功: **{test_bugs_fixed}** 个')
    A(f'- 未修复: **{test_bugs_unfixed}** 个')
    A(f'- 修复总轮次: **{data["test_fix_loops"]}** / 4')
    A('')

    # 详细修复记录（来自 failure_analysis.json）
    if failure_details:
        test_bugs = failure_details.get('test_bugs', [])
        if test_bugs:
            A('| 测试用例 | 状态 | 修复建议 |')
            A('|---------|------|---------|')
            for bug in test_bugs:
                tc = bug.get('test_case', '?')
                fixed = '✅ 已修复' if bug.get('fixed') else '❌ 未修复'
                suggestion = (bug.get('fix_suggestion', '') or '')[:100]
                A(f'| `{tc}` | {fixed} | {suggestion} |')
            A('')

    fixes = data.get('compile_fixes', [])
    if fixes:
        A('### 编译修复记录')
        A('')
        for fix in fixes:
            if isinstance(fix, dict):
                det = fix.get('details', fix)
                it = det.get('iteration', fix.get('iteration', '?'))
                err_count = det.get('error_count', '?')
                fixed = det.get('fixed', False)
                status = '✅' if fixed else '❌'
                summary = str(det.get('error_summary', det.get('summary', '')))[:300]
                A(f'- **迭代 {it}**: 错误数 {err_count} | {status} {"成功" if fixed else "失败"}')
                if summary:
                    A(f'  > {summary}')
        A('')
    elif not test_bugs and not fixes:
        A('✅ 无需修复。')
        A('')

    # === 7. 覆盖率详情 ===
    A('## 7. 📈 覆盖率详情')
    A('')
    overall = data.get('coverage_report', {})
    if 'overall' in overall:
        ov = overall['overall']
    else:
        ov = overall
    A(f'| 指标 | 值 | 目标 | 达标 |')
    A(f'|------|----|------|------|')
    A(f'| 语句覆盖率 | {lc}% | ≥90% | {lc_ok} |')
    A(f'| 分支覆盖率 | {bc}% | ≥80% | {bc_ok} |')
    A(f'| 函数覆盖率 | {ov.get("function_coverage_pct", 0)}% | — | — |')
    A(f'| 总行数 | {ov.get("total_lines", 0)} (覆盖 {ov.get("covered_lines", 0)}) | — | — |')
    A(f'| 总分支 | {ov.get("total_branches", 0)} (覆盖 {ov.get("covered_branches", 0)}) | — | — |')
    A('')

    files = data.get('coverage_files', {})
    if files:
        A('### 按文件明细')
        A('')
        A('| 文件 | 行覆盖率 | 分支覆盖率 | 未覆盖行 | 未覆盖分支 |')
        A('|------|---------|-----------|---------|-----------|')
        for fp, fc in sorted(files.items()):
            short = fp
            for sep in ('/service/', '/tests/', '/test/'):
                if sep in fp:
                    short = fp.split(sep, 1)[-1]
                    break
            A(f'| `{short}` | {fc.get("line_coverage_pct", 0)}% '
              f'| {fc.get("branch_coverage_pct", 0)}% '
              f'| {fc.get("uncovered_line_count", 0)} '
              f'| {fc.get("uncovered_branch_count", 0)} |')
        A('')

    # === 8. 测试用例追溯 ===
    A('## 8. 🔗 测试用例追溯')
    A('')
    if assessment:
        A('| 被测函数 | 测试数量 | 状态 |')
        A('|---------|---------|------|')
        for fn, info in assessment.items():
            existing = info.get('existing_tests', [])
            v = info.get('verdict', '?')
            icon = '✅' if v == 'reuse' else ('🔧' if v == 'adapt' else '🆕')
            A(f'| `{fn}` | {len(existing)} | {icon} {v} |')
        A('')
    else:
        A('无可用的追溯数据。')
        A('')

    # === 9. 未达标项与建议 ===
    A('## 9. ⚠️ 未达标项与建议')
    A('')
    items = []
    if not data['line_threshold_met']:
        items.append(f'- ❌ **语句覆盖率未达标**: {lc}% (要求 ≥90%)')
    if not data['branch_threshold_met']:
        items.append(f'- ❌ **分支覆盖率未达标**: {bc}% (要求 ≥80%)')

    # Service 缺陷（来自结构化数据）
    if failure_details:
        service_bugs = failure_details.get('service_bugs', [])
        if service_bugs:
            items.append(f'- 🔴 **{len(service_bugs)} 个 Service 代码缺陷**需要修复（详见第5章）')
            for bug in service_bugs:
                items.append(f'  - `{bug.get("service_function", "?")}` ({_severity_label(bug.get("severity", "major"))}): {bug.get("analysis", "")[:100]}')

    # 未修复的 test_bug
    if failure_details:
        test_bugs = [b for b in failure_details.get('test_bugs', []) if not b.get('fixed')]
        if test_bugs:
            items.append(f'- ⚠️ **{len(test_bugs)} 个 Test Bug 未能自动修复**，需人工介入')
            for bug in test_bugs:
                items.append(f'  - `{bug.get("test_case", "?")}`: {bug.get("fix_suggestion", "")[:100]}')

    if data['tests_failed'] > 0 and not failure_details:
        items.append(f'- ❌ **{data["tests_failed"]} 个测试失败**，需要人工检查')

    for g in data.get('coverage_gaps', [])[:10]:
        icon = '🔴' if g.get('priority') == 'high' else '🟡'
        items.append(f'- {icon} **{g["type"]}**: `{g["file"]}` '
                     f'当前 {g["current"]}% → 目标 {g["target"]}% '
                     f'(未覆盖 {g.get("total_uncovered", "?")} 项)')
    new_cnt = sum(1 for v in assessment.values() if v.get('verdict') == 'new')
    if new_cnt > 0:
        items.append(f'- ⚠️ {new_cnt} 个函数缺少测试')
    if not items:
        items.append('🎉 所有指标均已达标！')
    for item in items:
        A(item)
    A('')

    # === 尾部 ===
    A('---')
    A(f'> 由 FST AI 测试工作流自动生成 | 报告时间: {timestamp}')

    md_content = '\n'.join(w)

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='FST 报告生成器：生成中文 Markdown 测试报告')
    parser.add_argument('--state-dir', default='ai_workflow/state',
                        help='工作流状态目录')
    parser.add_argument('--output', default=None,
                        help='Markdown 报告输出路径')
    args = parser.parse_args()

    if args.output is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        args.output = f'ai_workflow/reports/test_report_{timestamp}.md'

    report_path = generate_report(args.state_dir, args.output)
    print(f'报告已生成: {report_path}')
    print(f'  文件: {os.path.abspath(report_path)}')


if __name__ == '__main__':
    main()

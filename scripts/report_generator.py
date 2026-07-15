#!/usr/bin/env python3
"""
报告生成器：根据工作流状态数据生成中文格式的HTML测试报告。
用于Stage 9：报告生成。
"""
import json
import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


# 完整HTML模板
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FST AI测试分析报告 - {{timestamp}}</title>
    <style>
        :root {
            --pass-color: #27ae60;
            --fail-color: #c0392b;
            --warn-color: #e67e22;
            --primary: #2980b9;
            --bg: #f5f7fa;
            --card-bg: #ffffff;
            --text: #333333;
            --text-secondary: #666666;
            --border: #e0e0e0;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC",
                         -apple-system, BlinkMacSystemFont, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 24px;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }
        h1 {
            color: #1a3a4a;
            border-bottom: 3px solid var(--primary);
            padding-bottom: 12px;
            margin-bottom: 8px;
            font-size: 1.8em;
        }
        h2 {
            color: #1a5276;
            border-bottom: 2px solid #85c1e9;
            padding-bottom: 8px;
            margin-top: 36px;
            margin-bottom: 16px;
            font-size: 1.4em;
        }
        h3 {
            color: #2c3e50;
            margin: 16px 0 8px;
            font-size: 1.15em;
        }
        .meta {
            color: var(--text-secondary);
            font-size: 0.9em;
            margin-bottom: 20px;
        }
        .meta span { margin-right: 24px; }
        .verdict {
            display: inline-block;
            padding: 4px 16px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 1.2em;
        }
        .verdict-pass { background: #d5f5e3; color: var(--pass-color); }
        .verdict-warn { background: #fdebd0; color: var(--warn-color); }
        .verdict-fail { background: #fadbd8; color: var(--fail-color); }

        /* 摘要卡片 */
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin: 20px 0;
        }
        .summary-card {
            background: var(--card-bg);
            border-radius: 8px;
            padding: 18px 16px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.08);
            text-align: center;
        }
        .summary-card .value {
            font-size: 2.2em;
            font-weight: 700;
            line-height: 1.2;
        }
        .summary-card .label {
            color: var(--text-secondary);
            margin-top: 6px;
            font-size: 0.9em;
        }
        .summary-card.good .value { color: var(--pass-color); }
        .summary-card.warn .value { color: var(--warn-color); }
        .summary-card.bad .value { color: var(--fail-color); }
        .summary-card.neutral .value { color: var(--primary); }

        /* 进度条 */
        .progress-bar {
            background: #ecf0f1;
            border-radius: 10px;
            height: 14px;
            overflow: hidden;
            margin: 8px 0;
        }
        .progress-fill {
            height: 100%;
            border-radius: 10px;
            transition: width 0.6s ease;
        }
        .progress-good { background: var(--pass-color); }
        .progress-warn { background: var(--warn-color); }
        .progress-bad { background: var(--fail-color); }

        /* 表格 */
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 12px 0;
            background: var(--card-bg);
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
            border-radius: 6px;
            overflow: hidden;
        }
        th, td {
            padding: 10px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border);
            font-size: 0.92em;
        }
        th {
            background: var(--primary);
            color: white;
            font-weight: 600;
        }
        tr:last-child td { border-bottom: none; }
        tr:hover td { background: #f0f4f8; }

        /* 徽章 */
        .badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 4px;
            font-size: 0.82em;
            font-weight: 600;
            color: white;
            white-space: nowrap;
        }
        .badge-pass { background: var(--pass-color); }
        .badge-fail { background: var(--fail-color); }
        .badge-skip { background: #95a5a6; }
        .badge-new { background: var(--primary); }
        .badge-adapt { background: var(--warn-color); }
        .badge-reuse { background: var(--pass-color); }
        .badge-unit { background: #2980b9; }
        .badge-integration { background: #8e44ad; }
        .badge-performance { background: #16a085; }
        .badge-direct { background: #c0392b; }
        .badge-caller { background: var(--warn-color); }
        .badge-callee { background: var(--primary); }

        /* 审计日志区 */
        .audit-log {
            max-height: 400px;
            overflow-y: auto;
            font-family: "Consolas", "Courier New", monospace;
            font-size: 0.88em;
            background: #1e2a36;
            color: #cfd8dc;
            padding: 16px;
            border-radius: 8px;
            line-height: 1.7;
        }
        .audit-entry {
            padding: 4px 0;
            border-left: 3px solid #3498db;
            padding-left: 12px;
            margin: 4px 0;
        }
        .audit-entry.error { border-left-color: var(--fail-color); color: #f5b7b1; }
        .audit-entry.success { border-left-color: var(--pass-color); }

        /* 底部 */
        .footer {
            text-align: center;
            color: #aaa;
            margin-top: 48px;
            padding-top: 16px;
            border-top: 1px solid var(--border);
            font-size: 0.82em;
        }

        @media print {
            body { background: white; padding: 0; }
            .summary-card { box-shadow: none; border: 1px solid var(--border); }
        }
    </style>
</head>
<body>
    <h1>🧪 FST AI测试分析报告</h1>
    <div class="meta">
        <span>📅 生成时间: {{timestamp}}</span>
        <span>👤 触发用户: {{user}}</span>
        <span>🔧 触发方式: {{trigger_type}}</span>
        <span>🆔 工作流ID: {{workflow_id}}</span>
    </div>
    <div>
        总体判定: {{verdict_html}}
    </div>

    <!-- 1. 摘要 -->
    <h2>1. 📊 摘要</h2>
    <div class="summary-grid">
        <div class="summary-card neutral">
            <div class="value">{{changed_files_count}}</div>
            <div class="label">变更文件数</div>
        </div>
        <div class="summary-card neutral">
            <div class="value">{{impacted_functions_count}}</div>
            <div class="label">影响函数数</div>
        </div>
        <div class="summary-card neutral">
            <div class="value">{{tests_total}}</div>
            <div class="label">测试总数</div>
        </div>
        <div class="summary-card {{tests_passed_class}}">
            <div class="value">{{tests_passed}}</div>
            <div class="label">测试通过</div>
        </div>
        <div class="summary-card {{tests_failed_class}}">
            <div class="value">{{tests_failed}}</div>
            <div class="label">测试失败</div>
        </div>
        <div class="summary-card {{line_cov_class}}">
            <div class="value">{{line_coverage}}%</div>
            <div class="label">语句覆盖率 (≥90%)</div>
            <div class="progress-bar">
                <div class="progress-fill {{line_cov_bar_class}}"
                     style="width:{{line_coverage_bar}}%"></div>
            </div>
        </div>
        <div class="summary-card {{branch_cov_class}}">
            <div class="value">{{branch_coverage}}%</div>
            <div class="label">分支覆盖率 (≥80%)</div>
            <div class="progress-bar">
                <div class="progress-fill {{branch_cov_bar_class}}"
                     style="width:{{branch_coverage_bar}}%"></div>
            </div>
        </div>
        <div class="summary-card neutral">
            <div class="value">{{compile_fix_loops}}</div>
            <div class="label">编译修复次数</div>
        </div>
        <div class="summary-card neutral">
            <div class="value">{{coverage_supplement_loops}}</div>
            <div class="label">覆盖率补充次数</div>
        </div>
    </div>

    <!-- 2. 变更影响分析 -->
    <h2>2. 🔍 变更影响分析</h2>
    <p>分析方法: <strong>{{analysis_method}}</strong></p>
    {{impact_section}}

    <!-- 3. 已有测试评估 -->
    <h2>3. 📋 已有测试评估</h2>
    {{assessment_section}}

    <!-- 4. 测试执行结果 -->
    <h2>4. ✅ 测试执行结果</h2>
    {{test_results_section}}

    <!-- 5. 覆盖率详情 -->
    <h2>5. 📈 覆盖率详情</h2>
    {{coverage_section}}

    <!-- 6. 测试用例追溯 -->
    <h2>6. 🔗 测试用例追溯</h2>
    {{traceability_section}}

    <!-- 7. 编译修复记录 -->
    <h2>7. 🔧 编译修复记录</h2>
    {{compile_fix_section}}

    <!-- 8. 审计追踪 -->
    <h2>8. 📝 审计追踪</h2>
    {{audit_section}}

    <!-- 9. 未达标项 -->
    <h2>9. ⚠️ 未达标项与建议</h2>
    {{gaps_section}}

    <div class="footer">
        由 FST AI测试工作流自动生成 | AI模型: DeepSeek V4 Flash |
        报告时间: {{timestamp}}
    </div>
</body>
</html>
'''


def _load_state_data(state_dir: str) -> dict:
    """从state目录加载所有工作流数据。"""
    state_path = Path(state_dir)

    data = {
        'user': 'unknown',
        'trigger_type': 'manual',
        'workflow_id': datetime.now().strftime('%Y%m%d_%H%M%S'),
        'changed_files_count': 0,
        'impacted_functions_count': 0,
        'tests_total': 0,
        'tests_passed': 0,
        'tests_failed': 0,
        'tests_skipped': 0,
        'line_coverage': 0,
        'branch_coverage': 0,
        'changed_files': [],
        'impact_set': {},
        'assessment': {},
        'test_results': {},
        'coverage_report': {},
        'compile_fixes': [],
        'coverage_supplements': [],
        'audit_entries': [],
        'workflow_state': {},
    }

    # 加载各数据文件
    _load_json(state_path / 'workflow_state.json', data, 'workflow_state')
    _load_json(state_path / 'changed_files.json', data, 'changed_files_raw')
    _load_json(state_path / 'impact_set.json', data, 'impact_set')
    _load_json(state_path / 'test_assessment.json', data, 'assessment')
    _load_json(state_path / 'test_results.json', data, 'test_results')
    _load_json(state_path / 'coverage_report.json', data, 'coverage_report')

    # 从workflow_state提取元数据
    ws = data.get('workflow_state', {})
    data['user'] = ws.get('user', data['user'])
    data['trigger_type'] = ws.get('trigger_type', data['trigger_type'])
    data['workflow_id'] = ws.get('workflow_id', data['workflow_id'])

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

    # 覆盖率
    cr = data.get('coverage_report', {})
    overall = cr.get('overall', {})
    data['line_coverage'] = overall.get('line_coverage_pct', 0)
    data['branch_coverage'] = overall.get('branch_coverage_pct', 0)

    # 循环次数
    compile_fix_loops = ws.get('compile_fix_iterations', 0)
    coverage_supp_loops = ws.get('coverage_supplement_iterations', 0)
    data['compile_fix_loops'] = compile_fix_loops
    data['coverage_supplement_loops'] = coverage_supp_loops

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

    # 审计日志
    audit_path = Path('reports/audit/audit_log.jsonl')
    if audit_path.exists():
        with open(audit_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data['audit_entries'].append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    # 编译修复记录也可以从审计日志中提取
    if not data['compile_fixes']:
        data['compile_fixes'] = [
            e for e in data['audit_entries']
            if e.get('event') == 'compile_fix'
        ]

    # 覆盖率补充记录
    data['coverage_supplements'] = [
        e for e in data['audit_entries']
        if e.get('event') == 'coverage_supplement'
    ]

    return data


def _load_json(filepath: Path, data: dict, key: str):
    """安全地加载JSON文件到data字典的指定key。"""
    if filepath.exists():
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data[key] = json.load(f)
        except (json.JSONDecodeError, PermissionError):
            pass


def generate_report(state_dir: str, output_path: str) -> str:
    """生成完整的HTML测试报告。

    Args:
        state_dir: 工作流状态目录
        output_path: 输出HTML文件路径

    Returns:
        str: 输出文件路径
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    data = _load_state_data(state_dir)

    html = HTML_TEMPLATE

    # === 基础替换 ===
    html = html.replace('{{timestamp}}', timestamp)
    html = html.replace('{{user}}', data['user'])
    html = html.replace('{{trigger_type}}',
                        '自动触发' if data['trigger_type'] == 'auto' else '手动触发')
    html = html.replace('{{workflow_id}}', data['workflow_id'])

    # === 总体判定 ===
    verdict = _compute_verdict(data)
    html = html.replace('{{verdict_html}}', verdict)

    # === 数值替换 ===
    replacements = {
        '{{changed_files_count}}': str(data['changed_files_count']),
        '{{impacted_functions_count}}': str(data['impacted_functions_count']),
        '{{tests_total}}': str(data['tests_total']),
        '{{tests_passed}}': str(data['tests_passed']),
        '{{tests_failed}}': str(data['tests_failed']),
        '{{line_coverage}}': str(data['line_coverage']),
        '{{branch_coverage}}': str(data['branch_coverage']),
        '{{line_coverage_bar}}': str(min(data['line_coverage'], 100)),
        '{{branch_coverage_bar}}': str(min(data['branch_coverage'], 100)),
        '{{compile_fix_loops}}': str(data['compile_fix_loops']),
        '{{coverage_supplement_loops}}': str(data['coverage_supplement_loops']),
        '{{analysis_method}}': _get_analysis_method(data),
    }

    # 覆盖率卡片样式
    for metric, threshold in [('line', 90), ('branch', 80)]:
        cov = data[f'{metric}_coverage']
        if cov >= threshold:
            replacements[f'{{{{{metric}_cov_class}}}}'] = 'good'
            replacements[f'{{{{{metric}_cov_bar_class}}}}'] = 'progress-good'
        elif cov >= threshold - 20:
            replacements[f'{{{{{metric}_cov_class}}}}'] = 'warn'
            replacements[f'{{{{{metric}_cov_bar_class}}}}'] = 'progress-warn'
        else:
            replacements[f'{{{{{metric}_cov_class}}}}'] = 'bad'
            replacements[f'{{{{{metric}_cov_bar_class}}}}'] = 'progress-bad'

    # 测试结果样式
    tests_passed = data['tests_passed']
    tests_failed = data['tests_failed']
    tests_total = data['tests_total']
    if tests_total > 0:
        pass_rate = tests_passed / tests_total
        replacements['{{tests_passed_class}}'] = (
            'good' if pass_rate >= 0.95 else ('warn' if pass_rate >= 0.8 else 'bad'))
        replacements['{{tests_failed_class}}'] = (
            'good' if tests_failed == 0 else ('warn' if tests_failed <= 2 else 'bad'))
    else:
        replacements['{{tests_passed_class}}'] = 'neutral'
        replacements['{{tests_failed_class}}'] = 'neutral'

    for k, v in replacements.items():
        html = html.replace(k, v)

    # === 各章节 ===
    html = html.replace('{{impact_section}}', _build_impact_section(data))
    html = html.replace('{{assessment_section}}', _build_assessment_section(data))
    html = html.replace('{{test_results_section}}', _build_test_results_section(data))
    html = html.replace('{{coverage_section}}', _build_coverage_section(data))
    html = html.replace('{{traceability_section}}', _build_traceability_section(data))
    html = html.replace('{{compile_fix_section}}', _build_compile_fix_section(data))
    html = html.replace('{{audit_section}}', _build_audit_section(data))
    html = html.replace('{{gaps_section}}', _build_gaps_section(data))

    # 写入文件
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return output_path


def _compute_verdict(data: dict) -> str:
    """计算总体判定。"""
    line_cov = data['line_coverage']
    branch_cov = data['branch_coverage']
    failed = data['tests_failed']
    compile_loops = data['compile_fix_loops']

    # 最高优先级：编译修复用完仍失败
    if compile_loops >= 3 and data['tests_total'] == 0:
        return '<span class="verdict verdict-fail">FAIL — 编译失败未解决</span>'

    if failed > 0 and data['tests_total'] > 0:
        return f'<span class="verdict verdict-warn">WARN — {failed} 个测试失败</span>'

    if line_cov < 90 or branch_cov < 80:
        return '<span class="verdict verdict-warn">WARN — 覆盖率未达标</span>'

    if data['tests_total'] == 0:
        return '<span class="verdict verdict-warn">WARN — 无测试运行</span>'

    return '<span class="verdict verdict-pass">PASS ✓</span>'


def _get_analysis_method(data: dict) -> str:
    """获取影响分析方法名（中文化）。"""
    method = data.get('impact_set', {}).get('analysis_method', 'unknown')
    method_map = {
        'codegraph': 'CodeGraph调用图分析',
        'grep_fallback': '文本搜索降级方案',
        'direct_only': '仅直接变更',
        'module_fallback': '模块级别降级',
        'none_detected': '未检测到影响关系',
    }
    return method_map.get(method, method)


def _build_impact_section(data: dict) -> str:
    """构建影响分析章节。"""
    impact = data.get('impact_set', {})
    direct = impact.get('direct_changes', [])
    callers = impact.get('callers', [])
    callees = impact.get('callees', [])
    per_func = impact.get('per_function', {})

    if not direct and not callers and not callees:
        return '<p>无可用的影响分析数据。</p>'

    # 影响传播表
    rows = ''
    for fn in direct:
        rows += (f'<tr><td><span class="badge badge-direct">直接变更</span></td>'
                 f'<td><strong>{fn}</strong></td>'
                 f'<td>{per_func.get(fn, {}).get("caller_count", 0)} 个调用者</td></tr>')
    for fn in callers:
        if fn not in direct:
            rows += (f'<tr><td><span class="badge badge-caller">调用者</span></td>'
                     f'<td>{fn}</td><td>依赖变更函数</td></tr>')
    for fn in callees:
        if fn not in direct:
            rows += (f'<tr><td><span class="badge badge-callee">被调用者</span></td>'
                     f'<td>{fn}</td><td>被变更函数调用</td></tr>')

    depth = impact.get('impact_depth', {})
    summary = (
        f'<p>直接影响: <strong>{depth.get("direct", 0)}</strong> 个函数，'
        f'间接调用者: <strong>{depth.get("indirect_callers", 0)}</strong>，'
        f'间接被调用者: <strong>{depth.get("indirect_callees", 0)}</strong>，'
        f'合计影响: <strong>{depth.get("total_unique", 0)}</strong> 个函数</p>'
    )

    return f'''
    {summary}
    <table>
        <tr><th>影响类型</th><th>函数</th><th>影响说明</th></tr>
        {rows}
    </table>
    '''


def _build_assessment_section(data: dict) -> str:
    """构建已有测试评估章节。"""
    assessment = data.get('assessment', {}).get('assessment', {})

    if not assessment:
        return '<p>无可用的测试评估数据。</p>'

    # 统计摘要
    new_count = sum(1 for v in assessment.values() if v.get('verdict') == 'new')
    adapt_count = sum(1 for v in assessment.values() if v.get('verdict') == 'adapt')
    reuse_count = sum(1 for v in assessment.values() if v.get('verdict') == 'reuse')

    summary = (
        f'<div class="summary-grid" style="margin-bottom:16px">'
        f'<div class="summary-card good">'
        f'<div class="value">{reuse_count}</div>'
        f'<div class="label">可直接复用</div></div>'
        f'<div class="summary-card warn">'
        f'<div class="value">{adapt_count}</div>'
        f'<div class="label">需改造</div></div>'
        f'<div class="summary-card bad">'
        f'<div class="value">{new_count}</div>'
        f'<div class="label">需新建</div></div>'
        f'</div>'
    )

    rows = ''
    for fn, info in assessment.items():
        verdict = info.get('verdict', 'unknown')
        badge_class = f'badge-{verdict}' if verdict in ['new', 'adapt', 'reuse'] else ''
        needed = ', '.join(info.get('needed_test_types', [])) or '无'

        rows += f'''<tr>
            <td><code>{fn}</code></td>
            <td><span class="badge {badge_class}">{verdict}</span></td>
            <td>{info.get('reason', '')}</td>
            <td>{info.get('existing_test_count', 0)}</td>
            <td>{needed}</td>
        </tr>'''

    return f'''
    {summary}
    <table>
        <tr><th>函数</th><th>评估结论</th><th>原因</th><th>已有测试</th><th>缺失类型</th></tr>
        {rows}
    </table>
    '''


def _build_test_results_section(data: dict) -> str:
    """构建测试执行结果章节。"""
    tr = data.get('test_results', {})

    html = f'''
    <div class="summary-grid">
        <div class="summary-card good">
            <div class="value">{tr.get('passed', 0)}</div>
            <div class="label">✅ 通过</div>
        </div>
        <div class="summary-card {'bad' if tr.get('failed', 0) > 0 else 'good'}">
            <div class="value">{tr.get('failed', 0)}</div>
            <div class="label">❌ 失败</div>
        </div>
        <div class="summary-card neutral">
            <div class="value">{tr.get('skipped', 0)}</div>
            <div class="label">⏭️ 跳过</div>
        </div>
        <div class="summary-card neutral">
            <div class="value">{tr.get('total_time_ms', 0)}ms</div>
            <div class="label">⏱ 总耗时</div>
        </div>
    </div>
    '''

    suites = tr.get('suites', [])
    if suites:
        rows = ''
        for suite in suites:
            for case in suite.get('cases', []):
                status = case['status']
                if status == 'PASSED':
                    badge_class = 'badge-pass'
                    status_text = 'PASS'
                elif status == 'FAILED':
                    badge_class = 'badge-fail'
                    status_text = 'FAIL'
                else:
                    badge_class = 'badge-skip'
                    status_text = status

                rows += f'''<tr>
                    <td>{suite['name']}</td>
                    <td>{case['name']}</td>
                    <td><span class="badge {badge_class}">{status_text}</span></td>
                    <td>{case.get('time_ms', 0)}ms</td>
                </tr>'''
                if case.get('failure_message'):
                    rows += (f'<tr><td colspan="4" style="color:{HTML_TEMPLATE[HTML_TEMPLATE.find("--fail-color:"):].split(";")[0].split(":")[1].strip() if False else "#c0392b"};font-size:0.85em;background:#fdf2f2">'
                             f'失败原因: {_escape_html(case["failure_message"][:300])}'
                             f'</td></tr>')

        html += f'''<table>
            <tr><th>测试套件</th><th>测试用例</th><th>状态</th><th>耗时</th></tr>
            {rows}
        </table>'''
    else:
        html += '<p>无测试结果详情</p>'

    return html


def _build_coverage_section(data: dict) -> str:
    """构建覆盖率详情章节。"""
    cr = data.get('coverage_report', {})
    overall = cr.get('overall', {})

    line_cov = overall.get('line_coverage_pct', 0)
    branch_cov = overall.get('branch_coverage_pct', 0)

    html = f'''
    <div class="summary-grid">
        <div class="summary-card {'good' if line_cov >= 90 else 'warn' if line_cov >= 70 else 'bad'}">
            <div class="value">{line_cov}%</div>
            <div class="label">语句覆盖率 (目标≥90%)</div>
            <div class="progress-bar">
                <div class="progress-fill {'progress-good' if line_cov >= 90 else 'progress-warn' if line_cov >= 70 else 'progress-bad'}"
                     style="width:{min(line_cov, 100)}%"></div>
            </div>
        </div>
        <div class="summary-card {'good' if branch_cov >= 80 else 'warn' if branch_cov >= 60 else 'bad'}">
            <div class="value">{branch_cov}%</div>
            <div class="label">分支覆盖率 (目标≥80%)</div>
            <div class="progress-bar">
                <div class="progress-fill {'progress-good' if branch_cov >= 80 else 'progress-warn' if branch_cov >= 60 else 'progress-bad'}"
                     style="width:{min(branch_cov, 100)}%"></div>
            </div>
        </div>
        <div class="summary-card neutral">
            <div class="value">{overall.get('function_coverage_pct', 0)}%</div>
            <div class="label">函数覆盖率</div>
        </div>
    </div>
    <p>总行数: {overall.get('total_lines', 0)} | 覆盖行数: {overall.get('covered_lines', 0)} |
       总分支: {overall.get('total_branches', 0)} | 覆盖分支: {overall.get('covered_branches', 0)}</p>
    '''

    # 按文件明细
    files = cr.get('files', {})
    if files:
        rows = ''
        for fp, cov in sorted(files.items()):
            line_cls = ('badge-pass' if cov['line_coverage_pct'] >= 90
                        else 'badge-adapt' if cov['line_coverage_pct'] >= 70
                        else 'badge-new')
            branch_cls = ('badge-pass' if cov['branch_coverage_pct'] >= 80
                          else 'badge-adapt' if cov['branch_coverage_pct'] >= 60
                          else 'badge-new')
            # 缩短文件路径
            short_path = fp
            if '/service/' in fp:
                short_path = fp.split('/service/', 1)[-1]
            elif '/test/' in fp:
                short_path = fp.split('/test/', 1)[-1]
            rows += f'''<tr>
                <td style="font-size:0.83em;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                    title="{fp}">{short_path}</td>
                <td><span class="badge {line_cls}">{cov['line_coverage_pct']}%</span></td>
                <td><span class="badge {branch_cls}">{cov['branch_coverage_pct']}%</span></td>
                <td>{cov['uncovered_line_count']}</td>
                <td>{cov['uncovered_branch_count']}</td>
            </tr>'''

        html += f'''<table>
            <tr><th>文件</th><th>行覆盖率</th><th>分支覆盖率</th><th>未覆盖行</th><th>未覆盖分支</th></tr>
            {rows}
        </table>'''

    return html


def _build_traceability_section(data: dict) -> str:
    """构建测试追溯章节。"""
    assessment = data.get('assessment', {}).get('assessment', {})

    if not assessment:
        return '<p>无可用追溯数据。</p>'

    rows = ''
    for fn, info in assessment.items():
        existing = info.get('existing_tests', [])
        test_names = ', '.join(
            f'<span class="badge badge-{t.get("test_type", "unit")}">{t.get("full_name", t.get("name", ""))}</span>'
            for t in existing[:5]
        )
        if len(existing) > 5:
            test_names += f' <em>... (+{len(existing) - 5} 个)</em>'

        verdict = info.get('verdict', '')
        badge = f'<span class="badge badge-{verdict}">{verdict}</span>'

        rows += f'''<tr>
            <td><code>{fn}</code></td>
            <td>{len(existing)}</td>
            <td>{test_names or '—'}</td>
            <td>{badge}</td>
        </tr>'''

    return f'''<table>
        <tr><th>被测函数</th><th>测试数量</th><th>测试用例</th><th>状态</th></tr>
        {rows}
    </table>'''


def _build_compile_fix_section(data: dict) -> str:
    """构建编译修复章节。"""
    fixes = data.get('compile_fixes', [])

    if not fixes:
        return '<p>✅ 无编译修复记录（编译一次性通过或无须编译）。</p>'

    html = ''
    for fix in fixes:
        if isinstance(fix, dict):
            det = fix.get('details', fix)
            it = det.get('iteration', fix.get('iteration', '?'))
            err_count = det.get('error_count', '?')
            fixed = det.get('fixed', False)
            status = '✅ 成功' if fixed else '❌ 失败'
            summary = det.get('error_summary', det.get('summary', ''))

            html += (f'<div style="margin:8px 0;padding:10px;background:{"#eafaf1" if fixed else "#fdf2f2"};'
                     f'border-radius:6px;border-left:4px solid {"#27ae60" if fixed else "#c0392b"}">'
                     f'<strong>迭代 {it}</strong>: '
                     f'错误数 {err_count} | {status}<br>'
                     f'<span style="font-size:0.85em;color:#666">{_escape_html(str(summary)[:300])}</span>'
                     f'</div>')

    return html or '<p>无编译修复记录。</p>'


def _build_audit_section(data: dict) -> str:
    """构建审计追踪章节。"""
    entries = data.get('audit_entries', [])

    if not entries:
        return '<p>无审计记录。</p>'

    html = '<div class="audit-log">'
    for entry in entries[-50:]:  # 最近50条
        ts = entry.get('timestamp', '')[:19]  # 截断到秒
        event = entry.get('event', '?')
        user = entry.get('user', '?')
        stage = entry.get('stage', '')
        css_class = 'error' if event == 'error' else ''
        if event in ('workflow_end', 'compile_fix'):
            css_class = 'success'
        html += (f'<div class="audit-entry {css_class}">'
                 f'[{ts}] [{user}] <strong>{event}</strong>'
                 f'{(" @ " + stage) if stage else ""}'
                 f'</div>')
    html += '</div>'

    if len(entries) > 50:
        html += f'<p style="margin-top:8px;color:#999">... 共 {len(entries)} 条记录，显示最近 50 条</p>'

    return html


def _build_gaps_section(data: dict) -> str:
    """构建未达标项章节。"""
    cr = data.get('coverage_report', {})
    gaps = cr.get('gaps', [])
    overall = cr.get('overall', {})

    items = []

    # 覆盖率未达标
    if not overall.get('line_threshold_met', False):
        items.append(
            f'<li style="color:var(--fail-color)"><strong>语句覆盖率未达标：</strong>'
            f'{overall.get("line_coverage_pct", 0)}% (要求≥90%)</li>'
        )
    if not overall.get('branch_threshold_met', False):
        items.append(
            f'<li style="color:var(--fail-color)"><strong>分支覆盖率未达标：</strong>'
            f'{overall.get("branch_coverage_pct", 0)}% (要求≥80%)</li>'
        )

    # 测试失败
    if data['tests_failed'] > 0:
        items.append(
            f'<li style="color:var(--fail-color)"><strong>{data["tests_failed"]} 个测试用例失败：</strong>'
            f'需要人工检查和修复</li>'
        )

    # 覆盖率缺口
    for gap in gaps[:10]:
        priority_icon = '🔴' if gap.get('priority') == 'high' else '🟡'
        items.append(
            f'<li>{priority_icon} <strong>{gap["type"]}</strong>: <code>{gap["file"]}</code> '
            f'— 当前 <strong>{gap["current"]}%</strong> (目标 {gap["target"]}%), '
            f'未覆盖: {gap.get("total_uncovered", "?")} 项</li>'
        )

    # 新增测试
    new_count = sum(
        1 for v in data.get('assessment', {}).get('assessment', {}).values()
        if v.get('verdict') == 'new'
    )
    if new_count > 0:
        items.append(
            f'<li style="color:var(--warn-color)">{new_count} 个函数缺少测试，'
            f'需要后续手动补充</li>'
        )

    if not items:
        return '<p style="color:var(--pass-color);font-size:1.1em">🎉 所有指标均已达标，无未完成项！</p>'

    return '<ul style="list-style:none;padding:0">' + '\n'.join(items) + '</ul>'


def _escape_html(text: str) -> str:
    """转义HTML特殊字符。"""
    return (text.replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


def main():
    parser = argparse.ArgumentParser(
        description='FST报告生成器：生成中文HTML测试报告'
    )
    parser.add_argument('--state-dir', default='state',
                        help='工作流状态目录（默认state/）')
    parser.add_argument('--output', default=None,
                        help='HTML报告输出路径（默认自动生成带时间戳的文件名）')

    args = parser.parse_args()

    if args.output is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        args.output = f'reports/reports/test_report_{timestamp}.html'

    report_path = generate_report(args.state_dir, args.output)
    print(f'报告已生成: {report_path}')
    print(f'  文件: {os.path.abspath(report_path)}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
CodeGraph分析器：查询函数的调用者和被调用者，构建影响范围集。
用于Stage 2：影响分析。
如果CodeGraph不可用，使用grep作为降级方案。
"""
import subprocess
import json
import argparse
import os
import re
from pathlib import Path
from typing import Optional


# CodeGraph CLI命令前缀（可根据实际安装路径修改）
CODEGRAPH_CMD = os.environ.get('CODEGRAPH_CMD', 'codegraph')


def _run_codegraph(args: list, timeout: int = 30) -> Optional[dict]:
    """安全地运行CodeGraph命令。

    Args:
        args: 命令参数列表
        timeout: 超时秒数

    Returns:
        dict或None: 解析后的JSON结果，或None（不可用时）
    """
    try:
        result = subprocess.run(
            [CODEGRAPH_CMD] + args,
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired,
            json.JSONDecodeError, OSError):
        pass
    return None


def query_callers(function_name: str, search_path: str) -> list:
    """查询函数的调用者（谁调用了这个函数）。

    Args:
        function_name: 函数名（如 "ClassName::methodName"）
        search_path: 搜索路径

    Returns:
        [{name, file, line}]: 调用者列表
    """
    result = _run_codegraph(['query', '--callers', function_name,
                             '--path', search_path])
    if result and 'callers' in result:
        return result['callers']

    # 降级：grep搜索
    return _fallback_callers(function_name, search_path)


def query_callees(function_name: str, search_path: str) -> list:
    """查询函数的被调用者（这个函数调用了谁）。

    Args:
        function_name: 函数名
        search_path: 搜索路径

    Returns:
        [{name, file, line}]: 被调用者列表
    """
    result = _run_codegraph(['query', '--callees', function_name,
                             '--path', search_path])
    if result and 'callees' in result:
        return result['callees']

    # 降级：函数体搜索
    return _fallback_callees(function_name, search_path)


def query_call_graph(function_name: str, search_path: str) -> dict:
    """查询完整的调用图（同时获取callers和callees）。

    Args:
        function_name: 函数名
        search_path: 搜索路径

    Returns:
        {callers: [...], callees: [...]}
    """
    result = _run_codegraph(['query', '--call-graph', function_name,
                             '--path', search_path])
    if result:
        return {
            'callers': result.get('callers', []),
            'callees': result.get('callees', [])
        }

    return {
        'callers': query_callers(function_name, search_path),
        'callees': query_callees(function_name, search_path)
    }


def _fallback_callers(function_name: str, search_path: str) -> list:
    """grep降级方案：搜索函数调用者。

    在源代码中搜索函数调用模式。
    """
    # 提取短函数名（去掉类名前缀）
    short_name = function_name.split('::')[-1] if '::' in function_name else function_name

    try:
        result = subprocess.run(
            ['grep', '-rn', '--include=*.cpp', '--include=*.h', '--include=*.hpp',
             f'{short_name}\\s*\\(', search_path],
            capture_output=True, text=True, timeout=30
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    callers = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split(':', 2)
        if len(parts) >= 2:
            callers.append({
                'name': f'unknown@{parts[0]}',
                'file': parts[0],
                'line': parts[1] if len(parts) > 1 else '?',
                'source': 'grep_fallback'
            })

    return callers


def _fallback_callees(function_name: str, search_path: str) -> list:
    """grep降级方案：搜索被调用函数。

    由于grep无法直接识别调用关系，返回空列表。
    可在后续版本中通过解析函数体来增强。
    """
    return []


def build_impact_set(changed_functions: list, module_path: str,
                     fallback_to_module: bool = False) -> dict:
    """构建完整的影响范围集。

    对每个变更函数：
    1. 查询其调用者（谁依赖它）
    2. 查询其被调用者（它依赖谁）
    3. 取并集得到全量影响集

    Args:
        changed_functions: 变更的函数名列表
        module_path: 模块路径
        fallback_to_module: 如果所有查询都失败，是否将该模块所有函数作为影响集

    Returns:
        {
            direct_changes: [str],
            callers: [str],
            callees: [str],
            full_impact_set: [str],
            analysis_method: 'codegraph' | 'grep_fallback' | 'module_fallback',
            per_function: {function_name: {callers: [...], callees: [...]}}
        }
    """
    direct = list(changed_functions)
    all_callers = set()
    all_callees = set()
    per_function = {}
    codegraph_available = False

    for func in changed_functions:
        callers = query_callers(func, module_path)
        callees = query_callees(func, module_path)

        caller_names = [c.get('name', f"{c.get('file', '')}:{c.get('line', '')}")
                        for c in callers]
        callee_names = [c.get('name', f"{c.get('file', '')}:{c.get('line', '')}")
                        for c in callees]

        # 检查CodeGraph是否可用
        if any(c.get('source') != 'grep_fallback' for c in callers + callees):
            codegraph_available = True

        all_callers.update(caller_names)
        all_callees.update(callee_names)

        per_function[func] = {
            'callers': caller_names,
            'callees': callee_names,
            'caller_count': len(caller_names),
            'callee_count': len(callee_names)
        }

    # 构建全量影响集（并集，去重）
    full_set = list(set(direct) | all_callers | all_callees)

    # 确定分析方法
    if direct and not full_set.difference(direct):
        analysis_method = 'none_detected'
    elif codegraph_available:
        analysis_method = 'codegraph'
    elif all_callers:
        analysis_method = 'grep_fallback'
    elif fallback_to_module:
        analysis_method = 'module_fallback'
    else:
        analysis_method = 'direct_only'

    return {
        'direct_changes': direct,
        'callers': list(all_callers),
        'callees': list(all_callees),
        'full_impact_set': full_set,
        'analysis_method': analysis_method,
        'per_function': per_function,
        'impact_depth': {
            'direct': len(direct),
            'indirect_callers': len(all_callers),
            'indirect_callees': len(all_callees),
            'total_unique': len(full_set)
        }
    }


def main():
    parser = argparse.ArgumentParser(
        description='FST CodeGraph分析器：查询调用关系，构建影响范围集'
    )
    parser.add_argument('--function', required=True,
                        help='函数名（如 ClassName::methodName）')
    parser.add_argument('--module', required=True,
                        help='模块名')
    parser.add_argument('--service-dir', default='service',
                        help='服务目录路径')
    parser.add_argument('--output',
                        help='输出JSON路径（可选）')
    parser.add_argument('--mode', choices=['callers', 'callees', 'full'],
                        default='full',
                        help='查询模式：callers/callees/full（默认full）')

    args = parser.parse_args()

    module_path = os.path.join(args.service_dir, args.module)

    if args.mode == 'callers':
        result = query_callers(args.function, module_path)
        output = json.dumps({'function': args.function, 'callers': result},
                            indent=2, ensure_ascii=False)
    elif args.mode == 'callees':
        result = query_callees(args.function, module_path)
        output = json.dumps({'function': args.function, 'callees': result},
                            indent=2, ensure_ascii=False)
    else:
        result = build_impact_set([args.function], module_path)
        output = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)

    print(output)


if __name__ == '__main__':
    main()

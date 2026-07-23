#!/usr/bin/env python3
"""
CodeGraph 分析器：查询函数的调用者和被调用者，构建影响范围集。
用于 Stage 2：影响分析。

codegraph 是必须依赖（env_checker 确保可用），不再有 grep 降级路径。
"""
import subprocess
import json
import argparse
import os
from typing import Optional


# CodeGraph CLI 命令前缀（可通过环境变量覆盖）
CODEGRAPH_CMD = os.environ.get('CODEGRAPH_CMD', 'codegraph')


def _run_codegraph(args: list, timeout: int = 30) -> Optional[dict]:
    """运行 CodeGraph 命令并返回解析后的 JSON。

    Args:
        args: 命令参数列表
        timeout: 超时秒数

    Returns:
        dict 或 None：解析后的 JSON 结果
    """
    try:
        result = subprocess.run(
            [CODEGRAPH_CMD] + args,
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired,
            json.JSONDecodeError, OSError) as e:
        raise RuntimeError(
            f'CodeGraph 调用失败: {e}\n'
            f'请参考 Confluence 文档获取 CodeGraph 安装包和安装说明，'
            f'或设置 CODEGRAPH_CMD 环境变量'
        )
    return None


def query_callers(function_name: str, search_path: str) -> list:
    """查询函数的调用者（谁调用了这个函数）。

    Args:
        function_name: 函数名（如 "ClassName::methodName"）
        search_path: 搜索路径

    Returns:
        [{name, file, line}]: 调用者列表
    """
    result = _run_codegraph(['callers', function_name,
                             '-p', search_path, '-j'])
    if result:
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and 'callers' in result:
            return result['callers']

    return []


def query_callees(function_name: str, search_path: str) -> list:
    """查询函数的被调用者（这个函数调用了谁）。

    Args:
        function_name: 函数名
        search_path: 搜索路径

    Returns:
        [{name, file, line}]: 被调用者列表
    """
    result = _run_codegraph(['callees', function_name,
                             '-p', search_path, '-j'])
    if result:
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and 'callees' in result:
            return result['callees']

    return []


def query_call_graph(function_name: str, search_path: str) -> dict:
    """查询完整的调用图（分别调用 callers 和 callees 后合并）。

    Args:
        function_name: 函数名
        search_path: 搜索路径

    Returns:
        {callers: [...], callees: [...]}
    """
    return {
        'callers': query_callers(function_name, search_path),
        'callees': query_callees(function_name, search_path)
    }


def build_impact_set(changed_functions: list, module_path: str) -> dict:
    """构建完整的影响范围集。

    对每个变更函数：
    1. 查询其调用者（谁依赖它）
    2. 查询其被调用者（它依赖谁）
    3. 取并集得到全量影响集

    Args:
        changed_functions: 变更的函数名列表
        module_path: 模块路径

    Returns:
        {
            direct_changes: [str],
            callers: [str],
            callees: [str],
            full_impact_set: [str],
            analysis_method: 'codegraph',
            per_function: {function_name: {callers: [...], callees: [...]}}
        }
    """
    direct = list(changed_functions)
    all_callers = set()
    all_callees = set()
    per_function = {}

    for func in changed_functions:
        callers = query_callers(func, module_path)
        callees = query_callees(func, module_path)

        caller_names = [c.get('name', f"{c.get('file', '')}:{c.get('line', '')}")
                        for c in callers]
        callee_names = [c.get('name', f"{c.get('file', '')}:{c.get('line', '')}")
                        for c in callees]

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

    return {
        'direct_changes': direct,
        'callers': list(all_callers),
        'callees': list(all_callees),
        'full_impact_set': full_set,
        'analysis_method': 'codegraph',
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
        description='FST CodeGraph 分析器：查询调用关系，构建影响范围集'
    )
    parser.add_argument('--function', required=True,
                        help='函数名（如 ClassName::methodName）')
    parser.add_argument('--module', required=True,
                        help='模块名')
    parser.add_argument('--service-dir', default='service',
                        help='服务目录路径')
    parser.add_argument('--output',
                        help='输出 JSON 路径（可选）')
    parser.add_argument('--mode', choices=['callers', 'callees', 'full'],
                        default='full',
                        help='查询模式：callers/callees/full（默认 full）')

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

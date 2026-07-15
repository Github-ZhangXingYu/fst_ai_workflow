#!/usr/bin/env python3
"""
变更检测器：通过git diff检测C++文件变更，识别变更的函数。
用于Stage 1：变更检测。
"""
import subprocess
import json
import re
import argparse
import os
from pathlib import Path

# 成员函数模式: ClassName::methodName(...) {
MEMBER_FUNCTION_PATTERN = re.compile(
    r'^\+?\s*(?:\w[\w\s\*&:<>,]*)\s+(\w+)::(\w+)\s*\([^)]*\)\s*(?:const)?\s*(?:override)?\s*\{',
    re.MULTILINE
)

# 自由函数模式: returnType functionName(...) {
FREE_FUNCTION_PATTERN = re.compile(
    r'^\+?\s*(?:\w[\w\s\*&:<>,]*)\s+(\w+)\s*\([^)]*\)\s*\{',
    re.MULTILINE
)

# C++关键字，不应被视为函数名
CPP_KEYWORDS = {
    'if', 'while', 'for', 'switch', 'return', 'catch', 'class',
    'struct', 'enum', 'namespace', 'template', 'typename', 'throw'
}

# 源文件扩展名
SOURCE_EXTENSIONS = {'.cpp', '.h', '.hpp', '.cc', '.cxx', '.hxx'}


def detect_changed_files(auto: bool = False, specific_files: list = None,
                         include_staged: bool = True) -> list:
    """检测变更的C++文件。

    Args:
        auto: True时检测工作区变更（含未暂存的）
        specific_files: 指定文件列表
        include_staged: 是否包含暂存区变更

    Returns:
        [str]: 变更的C++文件路径列表
    """
    if specific_files:
        return [f for f in specific_files
                if any(f.endswith(ext) for ext in SOURCE_EXTENSIONS)]

    files = set()

    # 检测未暂存的变更
    result = subprocess.run(
        ['git', 'diff', '--name-only'],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0:
        for f in result.stdout.strip().split('\n'):
            if f:
                files.add(f)

    # 检测暂存的变更
    if include_staged:
        result = subprocess.run(
            ['git', 'diff', '--name-only', '--cached'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            for f in result.stdout.strip().split('\n'):
                if f:
                    files.add(f)

    # 如果是自动模式，也检查未追踪的新文件
    if auto:
        result = subprocess.run(
            ['git', 'ls-files', '--others', '--exclude-standard'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            for f in result.stdout.strip().split('\n'):
                if f:
                    files.add(f)

    # 过滤：只保留C++源文件
    return sorted(f for f in files
                  if any(f.endswith(ext) for ext in SOURCE_EXTENSIONS))


def classify_file(filepath: str) -> dict:
    """按模块和类型对文件分类。

    从路径中提取模块名：
    - service/<module>/... → module=<module>, type=service
    - test/<module>/...   → module=<module>, type=test

    Args:
        filepath: 文件路径

    Returns:
        dict: {path, module, file_type, extension}
    """
    parts = Path(filepath).parts
    module = 'unknown'
    file_type = 'unknown'

    for i, part in enumerate(parts):
        if part == 'service' and i + 1 < len(parts):
            module = parts[i + 1]
            file_type = 'service'
            break
        elif part == 'test' and i + 1 < len(parts):
            module = parts[i + 1]
            file_type = 'test'
            break

    return {
        'path': filepath,
        'module': module,
        'file_type': file_type,
        'extension': Path(filepath).suffix
    }


def extract_changed_functions(filepath: str) -> list:
    """从文件diff中提取变更的函数名。

    分析git diff输出中新增或修改行的函数签名。

    Args:
        filepath: 文件路径

    Returns:
        [str]: 函数名列表（如 "ClassName::methodName" 或 "freeFunction"）
    """
    # 获取文件diff
    result = subprocess.run(
        ['git', 'diff', 'HEAD', '--', filepath],
        capture_output=True, text=True, timeout=30
    )
    diff_text = result.stdout

    # 如果文件是新的（未追踪），检查整个文件
    if not diff_text:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                diff_text = f.read()
        except (FileNotFoundError, PermissionError):
            return []

    functions = []

    # 匹配成员函数: Class::method
    for match in MEMBER_FUNCTION_PATTERN.finditer(diff_text):
        class_name = match.group(1)
        method_name = match.group(2)
        functions.append(f"{class_name}::{method_name}")

    # 匹配自由函数
    for match in FREE_FUNCTION_PATTERN.finditer(diff_text):
        name = match.group(1)
        if name not in CPP_KEYWORDS:
            functions.append(name)

    # 去重并保持顺序
    seen = set()
    result_list = []
    for fn in functions:
        if fn not in seen:
            seen.add(fn)
            result_list.append(fn)

    return result_list


def detect_by_module(module_name: str, service_dir: str = 'service') -> list:
    """检测指定模块的文件变更。

    Args:
        module_name: 模块名
        service_dir: 服务目录路径

    Returns:
        [str]: 变更文件路径列表
    """
    module_path = os.path.join(service_dir, module_name)
    result = subprocess.run(
        ['git', 'diff', '--name-only', 'HEAD', '--', module_path],
        capture_output=True, text=True, timeout=30
    )
    files = [f for f in result.stdout.strip().split('\n') if f]

    # 也检查未追踪新文件
    result2 = subprocess.run(
        ['git', 'ls-files', '--others', '--exclude-standard', '--', module_path],
        capture_output=True, text=True, timeout=30
    )
    files += [f for f in result2.stdout.strip().split('\n') if f]

    return sorted(set(f for f in files
                      if any(f.endswith(ext) for ext in SOURCE_EXTENSIONS)))


def main():
    parser = argparse.ArgumentParser(
        description='FST变更检测器：检测C++文件变更并提取变更函数'
    )
    parser.add_argument('--auto', action='store_true',
                        help='自动检测所有工作区变更')
    parser.add_argument('--files', nargs='*',
                        help='指定的文件路径列表')
    parser.add_argument('--module',
                        help='检测指定模块的变更')
    parser.add_argument('--output', default='state/changed_files.json',
                        help='输出JSON路径')
    parser.add_argument('--service-dir', default='service',
                        help='服务目录路径')

    args = parser.parse_args()

    # 检测变更文件
    if args.module:
        files = detect_by_module(args.module, args.service_dir)
    else:
        files = detect_changed_files(auto=args.auto, specific_files=args.files)

    # 分类并提取函数
    results = []
    for f in files:
        info = classify_file(f)
        info['changed_functions'] = extract_changed_functions(f)
        results.append(info)

    # 生成输出
    output_data = {
        'changed_files': results,
        'total_files': len(results),
        'total_functions': sum(len(f['changed_functions']) for f in results),
        'detection_method': 'module' if args.module else ('specific' if args.files else 'auto')
    }

    # 写入文件
    output_path = args.output
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as fout:
        json.dump(output_data, fout, indent=2, ensure_ascii=False)

    # 同时输出到stdout
    print(json.dumps(output_data, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

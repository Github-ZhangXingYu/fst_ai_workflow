#!/usr/bin/env python3
"""
编译运行器：执行 CMake 配置和 make 构建，解析编译错误。
用于 Stage 5：编译修复循环。

适配 FST 项目编译惯例：
  1. mkdir -p build && cd build
  2. cmake .. <options>
  3. make -j8 <target>
  4. 可执行文件输出到 product/bin/ 下
"""
import subprocess
import json
import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional


# GCC/Clang编译错误模式
ERROR_PATTERN = re.compile(
    r'^(.+?):(\d+):(\d+):\s*(error|warning|note):\s*(.+)$',
    re.MULTILINE
)

# 链接错误模式
LINK_ERROR_PATTERN = re.compile(
    r'undefined reference to [`\'](.+?)\'',
    re.MULTILINE
)

# 常见错误类型的分类
ERROR_CATEGORIES = {
    'missing_include': [
        r'no such file or directory',
        r'has not been declared',
        r'was not declared in this scope',
        r'is not a member of',
    ],
    'type_mismatch': [
        r'cannot convert',
        r'no matching function',
        r'no known conversion',
        r'invalid conversion',
        r'could not convert',
    ],
    'syntax_error': [
        r'expected .* before',
        r'expected .* at end of input',
        r'missing terminating',
        r'expected unqualified-id',
    ],
    'link_error': [
        r'undefined reference',
        r'ld returned',
        r'duplicate symbol',
    ],
    'missing_symbol': [
        r'was not declared in this scope',
        r'undeclared',
    ],
    'const_correctness': [
        r'passing .* as .this. argument',
        r'discards qualifiers',
        r'binding reference of type',
    ],
}

# 文件名清理模式
FILE_PATH_CLEANUP = re.compile(r'^(\.\.?/)+')


def configure_and_build(build_dir: str, target: str = None,
                        coverage: bool = False, source_dir: str = '.',
                        cmake_options: str = None, clean_first: bool = False,
                        parallel_jobs: int = None,
                        timeout: int = 300) -> dict:
    """执行 CMake 配置和 make 构建（适配 FST 项目编译惯例）。

    FST 编译流程：
      1. mkdir -p build && cd build
      2. cmake .. <options>
      3. make -j8 <target>
      4. 可执行文件输出到 product/bin/ 下

    Args:
        build_dir: 构建目录（如 build/）
        target: make 目标名（可选，不指定则 make all）
        coverage: 是否启用覆盖率标志
        source_dir: 源码根目录（默认 .）
        cmake_options: 额外的 cmake 选项字符串（可选，如 "-DFOO=ON -DBAR=OFF"）
        clean_first: 构建前先 make clean
        parallel_jobs: 并行任务数（默认 8，匹配 FST 惯例 -j8）
        timeout: 编译超时秒数

    Returns:
        {
            success: bool,
            stage: 'configure'|'build',
            stdout, stderr, returncode,
            errors: [{file, line, column, severity, message, category}],
            error_count, warning_count,
            duration_ms
        }
    """
    import time
    start_time = time.time()

    build_path = Path(build_dir)
    os.makedirs(build_path, exist_ok=True)

    # FST 惯例用 -j8
    if parallel_jobs is None:
        parallel_jobs = 8

    # ---- 配置阶段：cd build && cmake .. <options> ----
    cmake_args = [
        'cmake', '..',
        '-DCMAKE_BUILD_TYPE=Debug',
        '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
    ]

    if coverage:
        cmake_args.append('-DENABLE_COVERAGE=ON')

    # 追加用户自定义 cmake 选项（从 CMakeLists.txt 中的 option 读取）
    if cmake_options:
        cmake_args.extend(cmake_options.split())

    try:
        config_result = subprocess.run(
            cmake_args,
            cwd=build_dir,               # 在 build/ 目录内执行 cmake ..
            capture_output=True, text=True,
            timeout=min(timeout, 120)
        )
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'stage': 'configure',
            'error': 'CMake 配置超时',
            'errors': [],
            'error_count': 1,
            'duration_ms': int((time.time() - start_time) * 1000)
        }

    if config_result.returncode != 0:
        errors = _parse_compile_errors(
            config_result.stdout + '\n' + config_result.stderr
        )
        return {
            'success': False,
            'stage': 'configure',
            'stdout': config_result.stdout[-5000:],
            'stderr': config_result.stderr[-5000:],
            'returncode': config_result.returncode,
            'errors': errors,
            'error_count': len(errors),
            'duration_ms': int((time.time() - start_time) * 1000)
        }

    # ---- 构建阶段：make -j8 <target> ----
    if clean_first:
        subprocess.run(
            ['make', 'clean'],
            cwd=build_dir, capture_output=True, text=True, timeout=60
        )

    build_args = ['make', '-j', str(parallel_jobs)]
    if target:
        build_args.append(target)

    try:
        build_result = subprocess.run(
            build_args,
            cwd=build_dir,              # 在 build/ 目录内执行 make
            capture_output=True, text=True,
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'stage': 'build',
            'error': f'编译超时（{timeout}秒）',
            'errors': [],
            'error_count': 1,
            'duration_ms': int((time.time() - start_time) * 1000)
        }

    combined_output = build_result.stdout + '\n' + build_result.stderr
    errors = _parse_compile_errors(combined_output)

    return {
        'success': build_result.returncode == 0,
        'stage': 'build',
        'stdout': build_result.stdout[-10000:],
        'stderr': build_result.stderr[-10000:],
        'returncode': build_result.returncode,
        'errors': errors,
        'error_count': len([e for e in errors if e.get('severity') == 'error']),
        'warning_count': len([e for e in errors if e.get('severity') == 'warning']),
        'duration_ms': int((time.time() - start_time) * 1000)
    }


def _parse_compile_errors(output: str) -> list:
    """解析编译器输出，提取结构化错误信息。

    Args:
        output: 编译器标准输出/错误输出

    Returns:
        [{file, line, column, severity, message, category, context}]
    """
    errors = []
    lines = output.split('\n')

    for match in ERROR_PATTERN.finditer(output):
        file_path = match.group(1)
        line_num = int(match.group(2))
        col_num = int(match.group(3))
        severity = match.group(4).lower()
        message = match.group(5).strip()

        # 分类错误
        category = _categorize_error(message)

        # 查找上下文（该错误所在行的前后几行）
        context = _extract_context(output, match.start(), lines)

        errors.append({
            'file': _clean_file_path(file_path),
            'line': line_num,
            'column': col_num,
            'severity': severity,
            'message': message,
            'category': category,
            'context': context
        })

    # 也检查链接错误
    for link_match in LINK_ERROR_PATTERN.finditer(output):
        errors.append({
            'file': '',
            'line': 0,
            'column': 0,
            'severity': 'error',
            'message': f"undefined reference to '{link_match.group(1)}'",
            'category': 'link_error',
            'context': ''
        })

    return errors


def _categorize_error(message: str) -> str:
    """根据错误消息文本分类到错误类别。"""
    for category, patterns in ERROR_CATEGORIES.items():
        for pattern in patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return category
    return 'other'


def _extract_context(full_output: str, match_pos: int, lines: list) -> str:
    """提取错误位置的上下文（附近3行）。"""
    # 简化版：返回空串。后续可增强为行号定位。
    return ''


def _clean_file_path(path: str) -> str:
    """清理文件路径中的 ../ 前缀。"""
    return FILE_PATH_CLEANUP.sub('', path).strip()


def run_clang_tidy(file_path: str, build_dir: str,
                   checks: str = None) -> dict:
    """在指定文件上运行clang-tidy静态分析。

    Args:
        file_path: 要分析的文件路径
        build_dir: 包含compile_commands.json的构建目录
        checks: clang-tidy检查项（逗号分隔），默认使用bugprone-*,cert-*,cppcoreguidelines-*

    Returns:
        {success, warnings: [str], warning_count}
    """
    if checks is None:
        checks = ('bugprone-*,cert-*,cppcoreguidelines-*,'
                  'performance-*,modernize-*,-modernize-use-trailing-return-type')

    try:
        result = subprocess.run(
            ['clang-tidy', file_path,
             '-p', build_dir,
             '-checks=' + checks,
             '--quiet',
             '--warnings-as-errors=*'],
            capture_output=True, text=True, timeout=120
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {
            'success': False,
            'error': 'clang-tidy not found or timed out',
            'warnings': [],
            'warning_count': 0
        }

    warnings = []
    for line in result.stdout.strip().split('\n'):
        stripped = line.strip()
        if stripped and ('warning:' in stripped or 'error:' in stripped):
            warnings.append(stripped)

    return {
        'success': True,
        'warnings': warnings,
        'warning_count': len(warnings),
        'returncode': result.returncode
    }


def get_build_targets(build_dir: str) -> list:
    """获取 Makefile 中所有可用的构建目标。

    使用 make help（如果 CMake 生成的 Makefile 支持）
    或 make -nqp | grep -E '^[a-zA-Z]' 作为降级方案。

    Args:
        build_dir: 构建目录

    Returns:
        [str]: 构建目标名列表
    """
    targets = set()
    try:
        # 优先：make help（CMake 生成的 Makefile 支持）
        result = subprocess.run(
            ['make', 'help'],
            cwd=build_dir,
            capture_output=True, text=True, timeout=30
        )
        for line in result.stdout.split('\n'):
            line = line.strip()
            # CMake make help 输出格式: "... target_name"
            if line and not line.startswith('.') and not line.startswith('The following'):
                # 提取目标名（通常是最后一个词或 ... 后面的部分）
                parts = line.split()
                if parts:
                    # 取最后一个看起来像目标名的部分
                    candidate = parts[-1].rstrip('.')
                    if candidate and not candidate.startswith('-'):
                        targets.add(candidate)
    except Exception:
        pass

    # 降级：从 Makefile 中解析目标
    if not targets:
        try:
            with open(os.path.join(build_dir, 'Makefile'), 'r') as f:
                for line in f:
                    if ':' in line and not line.startswith('\t') and not line.startswith('.'):
                        target = line.split(':')[0].strip()
                        if target and not target.startswith('#'):
                            targets.add(target)
        except Exception:
            pass

    return sorted(targets)


def main():
    parser = argparse.ArgumentParser(
        description='FST编译运行器：CMake配置 + make构建、错误解析、clang-tidy分析'
    )
    parser.add_argument('--build-dir', default='build',
                        help='构建目录（默认 build/）')
    parser.add_argument('--target',
                        help='make 构建目标（不指定则 make all）')
    parser.add_argument('--cmake-options', default=None,
                        help='额外的 cmake 选项（如 "-DFOO=ON"），传递给 cmake ..')
    parser.add_argument('--coverage', action='store_true',
                        help='启用覆盖率编译标志（-DENABLE_COVERAGE=ON）')
    parser.add_argument('--source-dir', default='.',
                        help='源码根目录（默认当前目录）')
    parser.add_argument('--output',
                        help='结果JSON输出路径')
    parser.add_argument('--clean', action='store_true',
                        help='构建前先 make clean')
    parser.add_argument('--clang-tidy',
                        help='对指定文件运行clang-tidy分析')
    parser.add_argument('--list-targets', action='store_true',
                        help='列出 make 可用的构建目标')
    parser.add_argument('--timeout', type=int, default=300,
                        help='编译超时秒数（默认300）')
    parser.add_argument('-j', '--jobs', type=int, default=8,
                        help='并行任务数（默认 8，匹配 FST 惯例 -j8）')

    args = parser.parse_args()

    if args.list_targets:
        targets = get_build_targets(args.build_dir)
        for t in targets:
            print(t)
        return

    if args.clang_tidy:
        result = run_clang_tidy(args.clang_tidy, args.build_dir)
    else:
        result = configure_and_build(
            build_dir=args.build_dir,
            target=args.target,
            coverage=args.coverage,
            source_dir=args.source_dir,
            cmake_options=args.cmake_options,
            clean_first=args.clean,
            parallel_jobs=args.jobs,
            timeout=args.timeout
        )

    output = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)

    # 打印摘要
    if not args.clang_tidy:
        print(f"编译{'成功' if result['success'] else '失败'} "
              f"({result.get('duration_ms', 0)}ms)")
        if result.get('error_count', 0) > 0:
            print(f"  错误: {result['error_count']}")
            for err in result.get('errors', [])[:5]:
                if err['severity'] == 'error':
                    print(f"    {err['file']}:{err['line']}: {err['message'][:100]}")
    else:
        print(f"clang-tidy分析完成: {result['warning_count']} 个警告")
    print(output)


if __name__ == '__main__':
    main()

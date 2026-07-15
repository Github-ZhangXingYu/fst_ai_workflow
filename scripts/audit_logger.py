#!/usr/bin/env python3
"""
审计日志记录器：JSONL格式的审计追踪管理。
用于所有阶段：记录每次工作流事件。

功能：
- 追加写入JSONL审计日志
- 自动每日轮转
- 支持结构化事件记录
- 查询和导出接口
"""
import json
import argparse
import os
import getpass
import hashlib
from datetime import datetime, date
from pathlib import Path
from typing import Optional
import threading


# 默认审计日志目录和文件
DEFAULT_AUDIT_DIR = 'reports/audit'
AUDIT_LOG_FILE = 'audit_log.jsonl'


class AuditLogger:
    """JSONL审计日志记录器。

    线程安全的追加写入，记录所有工作流事件。

    用法:
        logger = AuditLogger()
        logger.log_event('workflow_start', details={'trigger': 'manual'})
        logger.log_event('compile_fix', details={'iteration': 1, 'fixed': True})
    """

    def __init__(self, log_dir: str = DEFAULT_AUDIT_DIR):
        """
        Args:
            log_dir: 审计日志目录路径
        """
        self.log_dir = Path(log_dir)
        self.log_file = self.log_dir / AUDIT_LOG_FILE
        self._lock = threading.Lock()
        os.makedirs(self.log_dir, exist_ok=True)
        # 启动时检查是否需要轮转
        self._rotate_if_needed()

    def log_event(self, event: str, details: dict = None,
                  user: str = None, stage: str = None,
                  result: str = None,
                  duration_ms: float = None,
                  workflow_id: str = None) -> dict:
        """记录一个审计事件。

        Args:
            event: 事件类型标识符
            details: 事件详情的字典
            user: 触发用户（None则自动检测）
            stage: 工作流阶段
            result: 结果摘要字符串
            duration_ms: 持续时间（毫秒）
            workflow_id: 工作流ID

        Returns:
            dict: 写入的审计条目
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'user': user or self._detect_user(),
            'event': event,
            'details': details or {},
        }

        if stage:
            entry['stage'] = stage
        if result:
            entry['result'] = result
        if duration_ms:
            entry['duration_ms'] = duration_ms
        if workflow_id:
            entry['workflow_id'] = workflow_id

        # 计算条目哈希（用于防篡改检测）
        entry['hash'] = self._compute_hash(entry)

        with self._lock:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

        return entry

    # ---- 便捷方法 ----

    def log_workflow_start(self, trigger_type: str, user: str,
                           changed_files: list = None) -> dict:
        """记录工作流启动事件。"""
        return self.log_event(
            'workflow_start',
            details={
                'trigger_type': trigger_type,
                'changed_files': changed_files or [],
                'file_count': len(changed_files) if changed_files else 0
            },
            user=user,
            stage='INIT'
        )

    def log_workflow_end(self, success: bool, summary: str = '') -> dict:
        """记录工作流结束事件。"""
        return self.log_event(
            'workflow_end',
            details={'success': success, 'summary': summary},
            result='success' if success else 'failure',
            stage='DONE'
        )

    def log_stage_transition(self, from_stage: str, to_stage: str) -> dict:
        """记录阶段转移。"""
        return self.log_event(
            'stage_transition',
            details={'from': from_stage, 'to': to_stage},
            stage=to_stage
        )

    def log_test_generated(self, function_name: str, test_type: str,
                           test_file: str, verdict: str) -> dict:
        """记录测试生成事件。"""
        return self.log_event(
            'test_generated',
            details={
                'function': function_name,
                'test_type': test_type,
                'test_file': test_file,
                'verdict': verdict
            },
            stage='TEST_GENERATE'
        )

    def log_compile_fix(self, iteration: int, error_count: int,
                        fixed: bool, error_summary: str = '') -> dict:
        """记录编译修复事件。"""
        return self.log_event(
            'compile_fix',
            details={
                'iteration': iteration,
                'error_count': error_count,
                'fixed': fixed,
                'error_summary': error_summary[:500]
            },
            stage='COMPILE_FIX_LOOP',
            result='fixed' if fixed else 'failed'
        )

    def log_compile_result(self, success: bool, error_count: int,
                           warning_count: int = 0) -> dict:
        """记录编译结果。"""
        return self.log_event(
            'compile_result',
            details={
                'success': success,
                'error_count': error_count,
                'warning_count': warning_count
            },
            stage='COMPILE_FIX_LOOP',
            result='success' if success else 'failed'
        )

    def log_test_execution(self, total: int, passed: int, failed: int,
                           skipped: int = 0) -> dict:
        """记录测试执行结果。"""
        return self.log_event(
            'test_execution',
            details={
                'total': total, 'passed': passed,
                'failed': failed, 'skipped': skipped
            },
            stage='TEST_EXECUTE',
            result='passed' if failed == 0 else 'partial_failure'
        )

    def log_coverage(self, line_cov: float, branch_cov: float,
                     thresholds_met: bool) -> dict:
        """记录覆盖率分析结果。"""
        return self.log_event(
            'coverage_analysis',
            details={
                'line_coverage': line_cov,
                'branch_coverage': branch_cov,
                'thresholds_met': thresholds_met
            },
            stage='COVERAGE_ANALYZE'
        )

    def log_coverage_supplement(self, iteration: int,
                                before_line_cov: float, after_line_cov: float,
                                before_branch_cov: float, after_branch_cov: float
                                ) -> dict:
        """记录覆盖率补充事件。"""
        return self.log_event(
            'coverage_supplement',
            details={
                'iteration': iteration,
                'before_line_coverage': before_line_cov,
                'after_line_coverage': after_line_cov,
                'before_branch_coverage': before_branch_cov,
                'after_branch_coverage': after_branch_cov
            },
            stage='COVERAGE_SUPPLEMENT_LOOP'
        )

    def log_error(self, stage: str, error_message: str,
                  error_data: dict = None) -> dict:
        """记录错误事件。"""
        return self.log_event(
            'error',
            details={
                'stage': stage,
                'error_message': error_message,
                'error_data': error_data or {}
            },
            stage=stage,
            result='error'
        )

    def log_user_intervention(self, action: str, reason: str) -> dict:
        """记录用户介入事件。"""
        return self.log_event(
            'user_intervention',
            details={'action': action, 'reason': reason},
            stage='MANUAL'
        )

    # ---- 查询和导出 ----

    def get_recent_events(self, limit: int = 50) -> list:
        """获取最近的审计事件。

        Args:
            limit: 返回的最大事件数

        Returns:
            [dict]: 审计事件列表
        """
        events = []
        if self.log_file.exists():
            with open(self.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        return events

    def query_events(self, event_type: str = None, user: str = None,
                     stage: str = None, max_results: int = 100) -> list:
        """按条件查询审计事件。

        Args:
            event_type: 按事件类型过滤
            user: 按用户过滤
            stage: 按阶段过滤
            max_results: 最大返回数

        Returns:
            [dict]: 匹配的审计事件
        """
        results = []
        if self.log_file.exists():
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if event_type and entry.get('event') != event_type:
                        continue
                    if user and entry.get('user') != user:
                        continue
                    if stage and entry.get('stage') != stage:
                        continue

                    results.append(entry)
                    if len(results) >= max_results:
                        break
        return results

    def export_json(self, output_path: str, query_args: dict = None) -> str:
        """导出审计日志为完整JSON文件。

        Args:
            output_path: 输出文件路径
            query_args: 查询过滤条件（传递给query_events）

        Returns:
            str: 输出文件路径
        """
        if query_args:
            events = self.query_events(**query_args)
        else:
            events = self.get_recent_events(limit=10000)

        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({'audit_events': events, 'exported_at': datetime.now().isoformat()},
                      f, indent=2, ensure_ascii=False)
        return output_path

    # ---- 内部方法 ----

    def _detect_user(self) -> str:
        """检测当前用户。"""
        try:
            return getpass.getuser()
        except Exception:
            return 'unknown'

    def _compute_hash(self, entry: dict) -> str:
        """计算条目哈希值（用于完整性校验）。"""
        # 排除hash字段本身
        data = {k: v for k, v in entry.items() if k != 'hash'}
        content = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _rotate_if_needed(self):
        """按日期轮转审计日志文件。"""
        if not self.log_file.exists():
            return

        # 获取日志文件的最后修改日期
        mtime = os.path.getmtime(self.log_file)
        file_date = date.fromtimestamp(mtime)
        today = date.today()

        if file_date < today:
            # 重命名为昨天的日期
            rotated_name = f'audit_log.{file_date.isoformat()}.jsonl'
            try:
                os.rename(self.log_file, self.log_dir / rotated_name)
            except OSError:
                pass

    def verify_integrity(self) -> dict:
        """验证审计日志的完整性。

        检查每个条目的哈希值是否匹配。

        Returns:
            {valid: bool, total_entries: int, tampered: int}
        """
        total = 0
        tampered = 0

        if self.log_file.exists():
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    try:
                        entry = json.loads(line)
                        stored_hash = entry.pop('hash', None)
                        computed = self._compute_hash(entry)
                        if stored_hash and stored_hash != computed:
                            tampered += 1
                        entry['hash'] = stored_hash
                    except json.JSONDecodeError:
                        tampered += 1

        return {
            'valid': tampered == 0,
            'total_entries': total,
            'tampered': tampered,
            'checked_at': datetime.now().isoformat()
        }


# ---- CLI ----

def main():
    parser = argparse.ArgumentParser(
        description='FST审计日志记录器：JSONL格式的审计追踪管理'
    )
    parser.add_argument('--event', required=True,
                        help='事件类型')
    parser.add_argument('--details', default='{}',
                        help='事件详情的JSON字符串')
    parser.add_argument('--user',
                        help='触发用户标识')
    parser.add_argument('--stage',
                        help='工作流阶段')
    parser.add_argument('--input',
                        help='从JSON文件读取详情')
    parser.add_argument('--output',
                        help='输出JSON路径（用于管道串联）')
    parser.add_argument('--log-dir', default=DEFAULT_AUDIT_DIR,
                        help='审计日志目录')
    parser.add_argument('--workflow-id',
                        help='工作流ID')
    parser.add_argument('--query', action='store_true',
                        help='查询审计日志')
    parser.add_argument('--query-event',
                        help='按事件类型过滤查询')
    parser.add_argument('--query-user',
                        help='按用户过滤查询')
    parser.add_argument('--export',
                        help='导出审计日志到此JSON文件')
    parser.add_argument('--verify', action='store_true',
                        help='验证审计日志完整性')

    args = parser.parse_args()

    logger = AuditLogger(args.log_dir)

    # 查询模式
    if args.query:
        events = logger.query_events(
            event_type=args.query_event,
            user=args.query_user,
            max_results=100
        )
        print(json.dumps(events, indent=2, ensure_ascii=False))
        return

    # 导出模式
    if args.export:
        path = logger.export_json(args.export)
        print(f'审计日志已导出到: {path}')
        return

    # 完整性验证
    if args.verify:
        result = logger.verify_integrity()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # 写入模式
    details = {}
    if args.input and os.path.exists(args.input):
        with open(args.input, 'r', encoding='utf-8') as f:
            details = json.load(f)
    elif args.details:
        try:
            details = json.loads(args.details)
        except json.JSONDecodeError:
            details = {'raw': args.details}

    entry = logger.log_event(
        event=args.event,
        details=details,
        user=args.user,
        stage=args.stage,
        workflow_id=args.workflow_id
    )

    output = json.dumps(entry, ensure_ascii=False)
    if args.output:
        os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
    print(output)


if __name__ == '__main__':
    main()

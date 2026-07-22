#!/usr/bin/env python3
"""
工作流状态机：追踪各阶段进度和循环迭代次数。
用于所有阶段：管理和持久化工作流状态。
"""
import json
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# 所有有效状态
STATES = [
    'INIT',
    'CHANGE_DETECT',
    'IMPACT_ANALYZE',
    'TEST_ASSESS',
    'TEST_GENERATE',
    'TEST_VERIFY_FIX_LOOP',
    'COVERAGE_ANALYZE',
    'COVERAGE_SUPPLEMENT_LOOP',
    'REPORT',
    'DONE',
    'ERROR',
    'PAUSED',
]


class WorkflowState:
    """工作流状态机管理器。

    职责：
    - 追踪当前工作流阶段
    - 管理循环迭代计数
    - 持久化状态到磁盘
    - 提供循环继续判断

    用法:
        state = WorkflowState('ai_workflow/state/')
        state.init('manual', 'zhangsan')
        state.transition('CHANGE_DETECT')
        if state.can_continue_test_fix():
            state.increment_test_fix()
    """

    def __init__(self, state_dir: str = 'ai_workflow/state'):
        self.state_dir = Path(state_dir)
        self.state_file = self.state_dir / 'workflow_state.json'
        os.makedirs(self.state_dir, exist_ok=True)

    # ---- 初始化 ----

    def init(self, trigger_type: str = 'manual', user: str = 'unknown',
             changed_files: list = None) -> dict:
        """初始化新的工作流。

        Args:
            trigger_type: 'manual' 或 'auto'
            user: 触发用户
            changed_files: 变更文件列表

        Returns:
            dict: 初始状态
        """
        state = {
            'workflow_id': datetime.now().strftime('%Y%m%d_%H%M%S'),
            'trigger_type': trigger_type,
            'user': user,
            'current_stage': 'INIT',
            'started_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'stages': {},
            'test_fix_iterations': 0,
            'coverage_supplement_iterations': 0,
            'max_test_fix_iterations': 4,
            'max_coverage_supplement_iterations': 2,
            'failure_analysis': {
                'total_failed': 0,
                'test_bugs_fixed': 0,
                'test_bugs_unfixed': 0,
                'service_bugs': 0,
            },
            'changed_files': changed_files or [],
            'errors': [],
            'completed': False,
            'success': None,
        }
        self._save(state)
        return state

    # ---- 状态转移 ----

    def transition(self, to_stage: str, metadata: dict = None) -> dict:
        """转移到新阶段。

        Args:
            to_stage: 目标阶段名（必须是STATES中的值）
            metadata: 阶段元数据

        Returns:
            dict: 更新后的状态

        Raises:
            RuntimeError: 如果工作流未初始化
            ValueError: 如果目标阶段无效
        """
        if to_stage not in STATES:
            raise ValueError(f'无效的阶段: {to_stage}。有效值: {STATES}')

        state = self._load()
        if not state:
            raise RuntimeError('工作流未初始化。请先调用 init()。')

        now = datetime.now().isoformat()

        state['current_stage'] = to_stage
        state['updated_at'] = now
        state['stages'][to_stage] = {
            'entered_at': now,
            'metadata': metadata or {}
        }

        self._save(state)
        return state

    # ---- 循环管理 ----

    def increment_test_fix(self) -> dict:
        """测试验证修复迭代计数+1（编译错误+test_bug修复共用）。

        Returns:
            dict: 更新后的状态
        """
        state = self._load()
        if not state:
            raise RuntimeError('工作流未初始化。')
        state['test_fix_iterations'] = state.get('test_fix_iterations', 0) + 1
        state['updated_at'] = datetime.now().isoformat()
        self._save(state)
        return state

    def increment_coverage_supplement(self) -> dict:
        """覆盖率补充迭代计数+1。

        Returns:
            dict: 更新后的状态
        """
        state = self._load()
        if not state:
            raise RuntimeError('工作流未初始化。')
        state['coverage_supplement_iterations'] = \
            state.get('coverage_supplement_iterations', 0) + 1
        state['updated_at'] = datetime.now().isoformat()
        self._save(state)
        return state

    def can_continue_test_fix(self) -> bool:
        """检查测试验证修复循环是否可以继续。"""
        state = self._load()
        if not state:
            return False
        current = state.get('test_fix_iterations', 0)
        max_iter = state.get('max_test_fix_iterations', 4)
        return current < max_iter

    def can_continue_coverage_supplement(self) -> bool:
        """检查覆盖率补充循环是否可以继续。"""
        state = self._load()
        if not state:
            return False
        current = state.get('coverage_supplement_iterations', 0)
        max_iter = state.get('max_coverage_supplement_iterations', 2)
        return current < max_iter

    def get_remaining_test_fix(self) -> int:
        """获取测试验证修复剩余次数。"""
        state = self._load()
        if not state:
            return 0
        return max(0, state.get('max_test_fix_iterations', 4) -
                   state.get('test_fix_iterations', 0))

    def get_remaining_coverage_supplement(self) -> int:
        """获取覆盖率补充剩余次数。"""
        state = self._load()
        if not state:
            return 0
        return max(0, state.get('max_coverage_supplement_iterations', 2) -
                   state.get('coverage_supplement_iterations', 0))

    # ---- 失败分析 ----

    def update_failure_analysis(self, total_failed: int = None,
                                 test_bugs_fixed: int = None,
                                 test_bugs_unfixed: int = None,
                                 service_bugs: int = None) -> dict:
        """更新失败分析汇总数据。

        Args:
            total_failed: 失败用例总数
            test_bugs_fixed: 已修复的 test_bug 数
            test_bugs_unfixed: 未修复的 test_bug 数
            service_bugs: service_bug 数量

        Returns:
            dict: 更新后的状态
        """
        state = self._load()
        if not state:
            raise RuntimeError('工作流未初始化。')
        fa = state.get('failure_analysis', {})
        if total_failed is not None:
            fa['total_failed'] = total_failed
        if test_bugs_fixed is not None:
            fa['test_bugs_fixed'] = test_bugs_fixed
        if test_bugs_unfixed is not None:
            fa['test_bugs_unfixed'] = test_bugs_unfixed
        if service_bugs is not None:
            fa['service_bugs'] = service_bugs
        state['failure_analysis'] = fa
        state['updated_at'] = datetime.now().isoformat()
        self._save(state)
        return state

    # ---- 错误和完成 ----

    def add_error(self, stage: str, error_message: str) -> dict:
        """记录错误。

        Args:
            stage: 发生错误的阶段
            error_message: 错误描述

        Returns:
            dict: 更新后的状态
        """
        state = self._load()
        if not state:
            raise RuntimeError('工作流未初始化。')
        state['errors'].append({
            'stage': stage,
            'message': error_message,
            'timestamp': datetime.now().isoformat()
        })
        state['updated_at'] = datetime.now().isoformat()
        self._save(state)
        return state

    def pause(self, reason: str = '') -> dict:
        """暂停工作流（需要用户介入时）。

        注意：service_bug 不作为暂停条件。仅环境缺失、编译死循环、
        无变更、影响集过大等情况下才暂停。

        Args:
            reason: 暂停原因
        """
        state = self._load()
        if state:
            state['current_stage'] = 'PAUSED'
            state['paused_reason'] = reason
            state['updated_at'] = datetime.now().isoformat()
            self._save(state)
        return state

    def resume(self) -> dict:
        """从暂停状态恢复。"""
        state = self._load()
        if state and state.get('current_stage') == 'PAUSED':
            stage_keys = list(state.get('stages', {}).keys())
            state['current_stage'] = stage_keys[-1] if stage_keys else 'INIT'
            state['updated_at'] = datetime.now().isoformat()
            self._save(state)
        return state

    def complete(self, success: bool = True, summary: str = '') -> dict:
        """标记工作流完成。

        Args:
            success: 是否成功
            summary: 结果摘要

        Returns:
            dict: 最终状态
        """
        state = self._load()
        if not state:
            raise RuntimeError('工作流未初始化。')

        state['current_stage'] = 'DONE' if success else 'ERROR'
        state['completed_at'] = datetime.now().isoformat()
        state['updated_at'] = datetime.now().isoformat()
        state['completed'] = True
        state['success'] = success
        state['summary'] = summary

        # 计算总耗时
        if 'started_at' in state:
            try:
                start = datetime.fromisoformat(state['started_at'])
                end = datetime.fromisoformat(state['completed_at'])
                state['total_duration_seconds'] = (end - start).total_seconds()
            except (ValueError, AttributeError):
                pass

        self._save(state)
        return state

    # ---- 查询 ----

    def get_state(self) -> Optional[dict]:
        """获取当前工作流状态。"""
        return self._load()

    def get_current_stage(self) -> str:
        """获取当前阶段名。"""
        state = self._load()
        return state['current_stage'] if state else 'UNKNOWN'

    def get_stage_timeline(self) -> list:
        """获取各阶段的时间线。

        Returns:
            [{stage, entered_at, duration_since_previous}]
        """
        state = self._load()
        if not state:
            return []

        stages = state.get('stages', {})
        timeline = []
        prev_time = None

        for stage_name in STATES:
            if stage_name in stages:
                entry_time = stages[stage_name].get('entered_at')
                item = {
                    'stage': stage_name,
                    'entered_at': entry_time,
                    'duration_from_start_s': 0
                }
                if prev_time and entry_time:
                    try:
                        t1 = datetime.fromisoformat(prev_time)
                        t2 = datetime.fromisoformat(entry_time)
                        item['duration_from_previous_s'] = (t2 - t1).total_seconds()
                    except (ValueError, AttributeError):
                        item['duration_from_previous_s'] = 0
                timeline.append(item)
                prev_time = entry_time

        return timeline

    # ---- 内部方法 ----

    def _load(self) -> Optional[dict]:
        """从磁盘加载状态。"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, PermissionError):
                return None
        return None

    def _save(self, state: dict):
        """将状态保存到磁盘。"""
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)


# ---- CLI ----

def main():
    parser = argparse.ArgumentParser(
        description='FST工作流状态机：阶段追踪和循环管理'
    )
    parser.add_argument('--init', action='store_true',
                        help='初始化新工作流')
    parser.add_argument('--trigger', default='manual',
                        help='触发方式: manual/auto')
    parser.add_argument('--user', default='unknown',
                        help='触发用户')
    parser.add_argument('--transition-to',
                        help='转移到指定阶段')
    parser.add_argument('--metadata', default='{}',
                        help='阶段元数据（JSON字符串）')
    parser.add_argument('--check-test-fix', action='store_true',
                        help='检查测试验证修复循环是否可继续（exit 0=可继续, 1=不可）')
    parser.add_argument('--check-coverage-supplement', action='store_true',
                        help='检查覆盖率补充循环是否可继续')
    parser.add_argument('--increment-test-fix', action='store_true',
                        help='测试验证修复迭代计数+1')
    parser.add_argument('--increment-coverage-supplement', action='store_true',
                        help='覆盖率补充迭代计数+1')
    parser.add_argument('--update-failure-analysis',
                        help='更新失败分析汇总（JSON: {total_failed, test_bugs_fixed, test_bugs_unfixed, service_bugs}）')
    parser.add_argument('--add-error',
                        help='记录错误消息')
    parser.add_argument('--pause',
                        help='暂停工作流（可选原因）')
    parser.add_argument('--complete', action='store_true',
                        help='完成工作流')
    parser.add_argument('--success', action='store_true',
                        help='标记为成功（与--complete一起用）')
    parser.add_argument('--summary', default='',
                        help='结果摘要（与--complete一起用）')
    parser.add_argument('--get-state', action='store_true',
                        help='获取当前状态')
    parser.add_argument('--timeline', action='store_true',
                        help='显示阶段时间线')
    parser.add_argument('--state-dir', default='ai_workflow/state',
                        help='状态目录（默认state/）')

    args = parser.parse_args()
    wf = WorkflowState(args.state_dir)

    if args.init:
        state = wf.init(args.trigger, args.user)
        print(json.dumps({
            'status': 'initialized',
            'workflow_id': state['workflow_id'],
            'current_stage': state['current_stage']
        }, ensure_ascii=False))

    elif args.transition_to:
        try:
            metadata = json.loads(args.metadata) if args.metadata else {}
        except json.JSONDecodeError:
            metadata = {'raw': args.metadata}
        state = wf.transition(args.transition_to, metadata)
        print(json.dumps({
            'status': 'transitioned',
            'stage': args.transition_to
        }, ensure_ascii=False))

    elif args.check_test_fix:
        can = wf.can_continue_test_fix()
        state = wf.get_state()
        current = state.get('test_fix_iterations', 0) if state else 0
        max_iter = state.get('max_test_fix_iterations', 4) if state else 4
        print(json.dumps({
            'can_continue': can,
            'current': current,
            'max': max_iter,
            'remaining': max_iter - current
        }, ensure_ascii=False))
        sys.exit(0 if can else 1)

    elif args.check_coverage_supplement:
        can = wf.can_continue_coverage_supplement()
        state = wf.get_state()
        current = state.get('coverage_supplement_iterations', 0) if state else 0
        max_iter = state.get('max_coverage_supplement_iterations', 2) if state else 2
        print(json.dumps({
            'can_continue': can,
            'current': current,
            'max': max_iter,
            'remaining': max_iter - current
        }, ensure_ascii=False))
        sys.exit(0 if can else 1)

    elif args.increment_test_fix:
        state = wf.increment_test_fix()
        print(json.dumps({
            'status': 'incremented',
            'test_fix_iterations': state['test_fix_iterations']
        }, ensure_ascii=False))

    elif args.increment_coverage_supplement:
        state = wf.increment_coverage_supplement()
        print(json.dumps({
            'status': 'incremented',
            'coverage_supplement_iterations': state['coverage_supplement_iterations']
        }, ensure_ascii=False))

    elif args.update_failure_analysis:
        try:
            fa = json.loads(args.update_failure_analysis)
        except json.JSONDecodeError:
            print(json.dumps({'status': 'error', 'message': '无效的 JSON'}, ensure_ascii=False))
            sys.exit(1)
        state = wf.update_failure_analysis(**fa)
        print(json.dumps({
            'status': 'updated',
            'failure_analysis': state.get('failure_analysis', {})
        }, ensure_ascii=False))

    elif args.add_error:
        state = wf.add_error(
            wf.get_current_stage() if wf.get_current_stage() != 'UNKNOWN' else 'unknown',
            args.add_error
        )
        print(json.dumps({'status': 'error_recorded'}, ensure_ascii=False))

    elif args.pause is not None:
        # --pause 可以带原因也可以不带
        reason = args.pause if args.pause else ''
        wf.pause(reason)
        print(json.dumps({'status': 'paused', 'reason': reason}, ensure_ascii=False))

    elif args.complete:
        state = wf.complete(args.success, args.summary)
        print(json.dumps({
            'status': 'completed',
            'success': args.success,
            'total_duration_s': state.get('total_duration_seconds', 'unknown')
        }, ensure_ascii=False))

    elif args.get_state:
        state = wf.get_state()
        if state:
            print(json.dumps(state, indent=2, ensure_ascii=False))
        else:
            print('{"status": "no_active_workflow"}')

    elif args.timeline:
        timeline = wf.get_stage_timeline()
        if timeline:
            print(json.dumps(timeline, indent=2, ensure_ascii=False))
        else:
            print('{"status": "no_timeline_data"}')


if __name__ == '__main__':
    main()

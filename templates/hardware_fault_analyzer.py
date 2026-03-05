#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CTC日志硬件故障分析器模块

分析CTC通信日志中的硬件故障和通信中断事件：
1. 通信中断检测 ("检测到通信中断")
2. DC2/DC3握手协议分析
3. 硬件故障检测 ("检测到硬件故障")
4. 故障恢复事件检测

DC2/DC3协议说明：
- DC2帧 (类型0x12): 连接建立请求帧
- DC3帧 (类型0x13): 连接确认帧
- 通信中断后，系统会发送最多3次DC2帧
- 如果3次DC2后仍未收到DC3，则判定为硬件故障
- 进入硬件故障处理模式后，每6秒发送一次DC2尝试恢复
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from collections import defaultdict
from datetime import datetime


@dataclass
class HardwareFaultEvent:
    """硬件故障事件"""

    timestamp: str
    fault_type: str  # "communication_interruption" 或 "hardware_fault"
    severity: str  # "WARNING" 或 "ERROR"
    thread_id: str
    function_name: str
    line_number: int
    message: str
    dc2_attempts: int = 0  # DC2重试次数（仅适用于hardware_fault）
    recovery_attempted: bool = False  # 是否尝试恢复

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "timestamp": self.timestamp,
            "fault_type": self.fault_type,
            "severity": self.severity,
            "thread_id": self.thread_id,
            "function_name": self.function_name,
            "line_number": self.line_number,
            "message": self.message,
            "dc2_attempts": self.dc2_attempts,
            "recovery_attempted": self.recovery_attempted,
        }


@dataclass
class ConnectionRecoveryEvent:
    """连接恢复事件"""

    timestamp: str
    recovery_type: str  # "DC3_RECEIVED" 或其他
    thread_id: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "timestamp": self.timestamp,
            "recovery_type": self.recovery_type,
            "thread_id": self.thread_id,
            "message": self.message,
        }


class CTCLogHardwareFaultAnalyzer:
    """CTC日志硬件故障分析器"""

    # 正则表达式模式
    # 格式: 2026-02-01 00:09:21.524 [WARNING][7fc0d2ffd700][8][CheckConnection:634]
    LOG_PATTERN = re.compile(
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+"
        r"\[(\w+)\]\["  # 日志级别
        r"([0-9a-fA-F]+)\]\["  # 线程ID
        r"(\d+)\]\["  # 日志模块编号
        r"(\w+):(\d+)\]\s*"  # 函数名:行号
        r"(.+)"  # 消息内容
    )

    # DC2帧内容正则
    DC2_FRAME_PATTERN = re.compile(r"DC2帧内容:\s*\[([0-9A-Fa-f\s]+)\]")

    def __init__(self, log_file: str):
        self.log_file = log_file
        self.fault_events: List[HardwareFaultEvent] = []
        self.recovery_events: List[ConnectionRecoveryEvent] = []
        self.dc2_frame_history: List[Dict[str, Any]] = []
        self.connection_status: Dict[str, Any] = {
            "last_dc2_time": None,
            "dc2_count_in_fault_mode": 0,
            "last_fault_time": None,
            "is_in_fault_mode": False,
        }

    def analyze(self) -> Dict[str, Any]:
        """分析日志文件，提取硬件故障事件

        Returns:
            分析结果字典，包含故障事件、恢复事件和统计信息
        """
        self.fault_events = []
        self.recovery_events = []
        self.dc2_frame_history = []

        current_fault_session = None

        with open(self.log_file, "r", encoding="utf-8", errors="ignore") as f:
            for line_num, line in enumerate(f, 1):
                self._process_line(line, line_num, current_fault_session)

        # 生成统计信息
        stats = self._generate_statistics()

        return {
            "fault_events": [e.to_dict() for e in self.fault_events],
            "recovery_events": [e.to_dict() for e in self.recovery_events],
            "dc2_frame_history": self.dc2_frame_history,
            "statistics": stats,
        }

    def _process_line(
        self, line: str, line_num: int, current_fault_session: Optional[Dict] = None
    ):
        """处理单行日志"""
        match = self.LOG_PATTERN.search(line)
        if not match:
            return

        timestamp = match.group(1)
        log_level = match.group(2)
        thread_id = match.group(3)
        log_module = match.group(4)
        function_name = match.group(5)
        line_number = int(match.group(6))
        message = match.group(7)

        # 检测通信中断
        if "检测到通信中断" in message:
            fault_event = HardwareFaultEvent(
                timestamp=timestamp,
                fault_type="communication_interruption",
                severity=log_level,
                thread_id=thread_id,
                function_name=function_name,
                line_number=line_number,
                message=message,
                dc2_attempts=0,
                recovery_attempted=False,
            )
            self.fault_events.append(fault_event)
            self.connection_status["is_in_fault_mode"] = False

        # 检测硬件故障
        elif "检测到硬件故障" in message:
            # 提取DC2尝试次数
            dc2_attempts = 3  # 默认3次
            if "发送" in message and "次 DC2" in message:
                try:
                    import re as re_module

                    match_attempts = re_module.search(
                        r"发送\s*(\d+)\s*次\s*DC2", message
                    )
                    if match_attempts:
                        dc2_attempts = int(match_attempts.group(1))
                except:
                    pass

            fault_event = HardwareFaultEvent(
                timestamp=timestamp,
                fault_type="hardware_fault",
                severity=log_level,
                thread_id=thread_id,
                function_name=function_name,
                line_number=line_number,
                message=message,
                dc2_attempts=dc2_attempts,
                recovery_attempted="尝试与联锁备机通信" in message,
            )
            self.fault_events.append(fault_event)
            self.connection_status["last_fault_time"] = timestamp
            self.connection_status["is_in_fault_mode"] = True
            self.connection_status["dc2_count_in_fault_mode"] = 0

        # 检测进入硬件故障处理模式
        elif "进入硬件故障处理模式" in message:
            self.connection_status["is_in_fault_mode"] = True

        # 检测DC2帧
        elif "DC2帧内容" in message:
            dc2_match = self.DC2_FRAME_PATTERN.search(message)
            if dc2_match:
                frame_data = dc2_match.group(1)
                self.dc2_frame_history.append(
                    {
                        "timestamp": timestamp,
                        "thread_id": thread_id,
                        "frame_data": frame_data,
                        "in_fault_mode": self.connection_status["is_in_fault_mode"],
                    }
                )
                if self.connection_status["is_in_fault_mode"]:
                    self.connection_status["dc2_count_in_fault_mode"] += 1

        # 检测DC3帧（恢复）
        elif "收到DC3" in message or "DC3" in message and "收到" in message:
            recovery_event = ConnectionRecoveryEvent(
                timestamp=timestamp,
                recovery_type="DC3_RECEIVED",
                thread_id=thread_id,
                message=message,
            )
            self.recovery_events.append(recovery_event)
            self.connection_status["is_in_fault_mode"] = False
            self.connection_status["dc2_count_in_fault_mode"] = 0

        # 检测连接恢复
        elif "连接已建立" in message or "连接恢复" in message:
            recovery_event = ConnectionRecoveryEvent(
                timestamp=timestamp,
                recovery_type="CONNECTION_RESTORED",
                thread_id=thread_id,
                message=message,
            )
            self.recovery_events.append(recovery_event)
            self.connection_status["is_in_fault_mode"] = False
            self.connection_status["dc2_count_in_fault_mode"] = 0

    def _generate_statistics(self) -> Dict[str, Any]:
        """生成统计信息"""
        # 按故障类型统计
        fault_type_counts = defaultdict(int)
        severity_counts = defaultdict(int)

        for event in self.fault_events:
            fault_type_counts[event.fault_type] += 1
            severity_counts[event.severity] += 1

        # 计算时间分布
        fault_times = [e.timestamp for e in self.fault_events]

        # 计算故障间隔（如果有多个故障）
        intervals = []
        if len(fault_times) >= 2:
            for i in range(1, len(fault_times)):
                try:
                    t1 = datetime.strptime(
                        fault_times[i - 1][:19], "%Y-%m-%d %H:%M:%S"
                    )
                    t2 = datetime.strptime(fault_times[i][:19], "%Y-%m-%d %H:%M:%S")
                    interval = (t2 - t1).total_seconds()
                    intervals.append(interval)
                except:
                    pass

        return {
            "total_fault_events": len(self.fault_events),
            "total_recovery_events": len(self.recovery_events),
            "total_dc2_frames": len(self.dc2_frame_history),
            "dc2_in_fault_mode": self.connection_status["dc2_count_in_fault_mode"],
            "fault_type_distribution": dict(fault_type_counts),
            "severity_distribution": dict(severity_counts),
            "fault_intervals_seconds": intervals,
            "average_fault_interval": sum(intervals) / len(intervals)
            if intervals
            else 0,
        }

    def generate_report(self, output_file: Optional[str] = None) -> str:
        """生成硬件故障分析报告

        Args:
            output_file: 输出文件路径（None则不写入文件）

        Returns:
            报告文本字符串
        """
        # 执行分析
        analysis_result = self.analyze()
        stats = analysis_result["statistics"]

        lines = []
        lines.append("=" * 80)
        lines.append("CTC通信日志硬件故障分析报告")
        lines.append("=" * 80)
        lines.append(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"日志文件: {self.log_file}")
        lines.append("")

        # 总体统计
        lines.append("-" * 80)
        lines.append("总体统计")
        lines.append("-" * 80)
        lines.append(f"故障事件总数: {stats['total_fault_events']}")
        lines.append(f"恢复事件总数: {stats['total_recovery_events']}")
        lines.append(f"DC2帧发送总数: {stats['total_dc2_frames']}")
        lines.append(f"故障模式期间DC2发送数: {stats['dc2_in_fault_mode']}")
        if stats["average_fault_interval"] > 0:
            lines.append(f"平均故障间隔: {stats['average_fault_interval']:.1f}秒")
        lines.append("")

        # 故障类型分布
        lines.append("-" * 80)
        lines.append("故障类型分布")
        lines.append("-" * 80)
        for fault_type, count in stats["fault_type_distribution"].items():
            type_name = (
                "通信中断" if fault_type == "communication_interruption" else "硬件故障"
            )
            lines.append(f"  {type_name}: {count}次")
        lines.append("")

        # 严重程度分布
        lines.append("-" * 80)
        lines.append("严重程度分布")
        lines.append("-" * 80)
        for severity, count in stats["severity_distribution"].items():
            lines.append(f"  {severity}: {count}次")
        lines.append("")

        # 详细故障事件
        if self.fault_events:
            lines.append("-" * 80)
            lines.append("详细故障事件")
            lines.append("-" * 80)
            for i, event in enumerate(self.fault_events, 1):
                lines.append(f"\n故障 #{i}")
                lines.append(f"  时间戳: {event.timestamp}")
                lines.append(f"  故障类型: {event.fault_type}")
                lines.append(f"  严重程度: {event.severity}")
                lines.append(f"  线程ID: {event.thread_id}")
                lines.append(f"  函数: {event.function_name}:{event.line_number}")
                lines.append(f"  消息: {event.message}")
                if event.dc2_attempts > 0:
                    lines.append(f"  DC2尝试次数: {event.dc2_attempts}")
                if event.recovery_attempted:
                    lines.append(f"  恢复尝试: 是")

        # 恢复事件
        if self.recovery_events:
            lines.append("")
            lines.append("-" * 80)
            lines.append("连接恢复事件")
            lines.append("-" * 80)
            for i, event in enumerate(self.recovery_events, 1):
                lines.append(f"\n恢复 #{i}")
                lines.append(f"  时间戳: {event.timestamp}")
                lines.append(f"  恢复类型: {event.recovery_type}")
                lines.append(f"  线程ID: {event.thread_id}")
                lines.append(f"  消息: {event.message}")

        # DC2帧历史（只显示故障模式期间的前20个）
        fault_mode_dc2s = [d for d in self.dc2_frame_history if d["in_fault_mode"]]
        if fault_mode_dc2s:
            lines.append("")
            lines.append("-" * 80)
            lines.append(
                f"故障模式期间DC2帧历史 (显示前{min(20, len(fault_mode_dc2s))}个)"
            )
            lines.append("-" * 80)
            for i, dc2 in enumerate(fault_mode_dc2s[:20], 1):
                lines.append(f"\nDC2 #{i}")
                lines.append(f"  时间戳: {dc2['timestamp']}")
                lines.append(f"  线程ID: {dc2['thread_id']}")
                lines.append(f"  帧数据: {dc2['frame_data']}")

        report = "\n".join(lines)

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(report)

        return report

    def export_to_csv(self, output_file: str):
        """导出故障事件到CSV文件

        Args:
            output_file: CSV输出文件路径
        """
        import csv

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # 写入表头
            writer.writerow(
                [
                    "timestamp",
                    "fault_type",
                    "severity",
                    "thread_id",
                    "function_name",
                    "line_number",
                    "message",
                    "dc2_attempts",
                    "recovery_attempted",
                ]
            )
            # 写入数据
            for event in self.fault_events:
                writer.writerow(
                    [
                        event.timestamp,
                        event.fault_type,
                        event.severity,
                        event.thread_id,
                        event.function_name,
                        event.line_number,
                        event.message,
                        event.dc2_attempts,
                        "是" if event.recovery_attempted else "否",
                    ]
                )


def analyze_hardware_faults(log_file: str, output_dir: str = ".") -> Dict[str, Any]:
    """分析CTC日志中的硬件故障（便捷函数）

    Args:
        log_file: CTC日志文件路径
        output_dir: 输出目录

    Returns:
        分析结果字典
    """
    import os

    analyzer = CTCLogHardwareFaultAnalyzer(log_file)

    # 执行分析
    result = analyzer.analyze()

    # 生成报告
    report_file = os.path.join(output_dir, "hardware_fault_analysis_report.txt")
    analyzer.generate_report(output_file=report_file)

    # 导出CSV
    csv_file = os.path.join(output_dir, "hardware_fault_events.csv")
    analyzer.export_to_csv(csv_file)

    return result

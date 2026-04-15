#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CTC日志分析器模块

整合SDCI帧解析、硬件故障分析等功能。
"""

import re
import os
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import defaultdict

from .device_types import DeviceInfo, DeviceState, SDCIFrame
from .code_position_table import CodePositionTable
from .sdci_parser import SDCIFrameParser
from .state_decoder import StateDecoder
from .frame_utils import FrameUtils


class CTCLogAnalyzer:
    """CTC日志分析器"""

    def __init__(self, log_file: str, code_position_table: CodePositionTable):
        self.log_file = log_file
        self.cpt = code_position_table
        self.parser = SDCIFrameParser(code_position_table)
        self.frames: List[SDCIFrame] = []

    def analyze(self, max_frames: Optional[int] = None) -> List[SDCIFrame]:
        """分析日志文件，提取SDCI帧

        Args:
            max_frames: 最大解析帧数（None表示不限制）

        Returns:
            解析出的SDCIFrame列表
        """
        # 正则表达式匹配包含帧数据的行
        # 支持两种日志格式：
        # 1. PacketToString格式: "... Data: 7D 04 11 65 BF 8A 03 00 ..."
        # 2. 完整报文格式: "... 内容=[7D 04 11 65 BF 8A 03 00 ...]"
        data_pattern = re.compile(
            r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+).*?(?:Data:\s+|内容=\[)([0-9A-Fa-f\s]+?)(?:\]|$)"
        )

        frame_count = 0
        with open(self.log_file, "r", encoding="utf-8", errors="ignore") as f:
            for line_num, line in enumerate(f, 1):
                match = data_pattern.search(line)
                if match:
                    timestamp = match.group(1)
                    hex_data = match.group(2).strip()

                    # 解析十六进制数据
                    try:
                        raw_bytes = bytes.fromhex(hex_data.replace(" ", ""))

                        # 检查是否是SDCI帧（帧类型0x8A）
                        if len(raw_bytes) >= 6 and raw_bytes[5] == 0x8A:
                            frame = self.parser.parse_frame(raw_bytes, timestamp)
                            if frame:
                                self.frames.append(frame)
                                frame_count += 1

                                if max_frames and frame_count >= max_frames:
                                    break

                    except ValueError:
                        continue

        return self.frames

    def generate_report(
        self, output_file: Optional[str] = None, max_frames_in_report: int = 100
    ) -> str:
        """生成分析报告

        Args:
            output_file: 输出文件路径（None则不写入文件）
            max_frames_in_report: 报告中包含的最大帧数

        Returns:
            报告文本字符串
        """
        lines = []

        lines.append("=" * 80)
        lines.append("SDCI帧分析报告")
        lines.append("=" * 80)
        lines.append(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"日志文件: {self.log_file}")
        lines.append(f"码位表文件: {self.cpt.file_path}")
        lines.append(f"总SDCI帧数: {len(self.frames)}")
        lines.append("")

        # 统计信息
        lines.append("-" * 80)
        lines.append("统计信息")
        lines.append("-" * 80)

        device_type_counts = defaultdict(int)
        total_device_changes = 0

        for frame in self.frames:
            total_device_changes += frame.get_device_count()
            for ds in frame.device_states:
                device_type_counts[ds.device.get_type_description()] += 1

        lines.append(f"设备状态变化总次数: {total_device_changes}")
        lines.append("")
        lines.append("按设备类型统计:")
        for dtype, count in sorted(device_type_counts.items()):
            lines.append(f"  {dtype}: {count}次")
        lines.append("")

        # 详细帧信息
        lines.append("-" * 80)
        lines.append(f"SDCI帧详细信息 (显示前{max_frames_in_report}帧)")
        lines.append("-" * 80)

        for i, frame in enumerate(self.frames[:max_frames_in_report], 1):
            lines.append(f"\n帧 #{i}")
            lines.append(f"  时间戳: {frame.timestamp}")
            lines.append(f"  发送序号: 0x{frame.send_seq:02X} ({frame.send_seq})")
            lines.append(f"  确认序号: 0x{frame.ack_seq:02X} ({frame.ack_seq})")
            lines.append(f"  数据长度: {frame.data_length}字节")
            crc_status = "通过" if frame.crc_valid else "失败"
            lines.append(f"  CRC校验: 0x{frame.crc:04X} ({crc_status})")
            lines.append(f"  变化设备数: {frame.get_device_count()}")
            lines.append(f"  原始数据: {frame.raw_data.hex().upper()}")

            if frame.device_states:
                lines.append("  设备状态详情:")
                for ds in frame.device_states:
                    lines.append(
                        f"    - {ds.device.name} [{ds.device.get_type_description()}]"
                    )
                    lines.append(f"      设备序号: {ds.device.byte_index}")
                    lines.append(
                        f"      原始状态: 0x{ds.raw_state:02X} ({ds.raw_state})"
                    )
                    for key, value in ds.decoded_state.items():
                        lines.append(f"      {key}: {value}")

        report = "\n".join(lines)

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(report)

        return report


def export_to_json(frames: List[SDCIFrame], output_file: str):
    """导出帧数据为JSON格式

    Args:
        frames: SDCIFrame列表
        output_file: 输出JSON文件路径
    """
    data = []
    for frame in frames:
        frame_data = {
            "timestamp": frame.timestamp,
            "send_seq": frame.send_seq,
            "ack_seq": frame.ack_seq,
            "data_length": frame.data_length,
            "crc": f"0x{frame.crc:04X}",
            "raw_data": frame.raw_data.hex().upper(),
            "devices": [],
        }

        for ds in frame.device_states:
            device_data = {
                "name": ds.device.name,
                "type": ds.device.get_type_description(),
                "index": ds.device.byte_index,
                "raw_state": f"0x{ds.raw_state:02X}",
                "decoded_state": ds.decoded_state,
            }
            frame_data["devices"].append(device_data)

        data.append(frame_data)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_sdci_log(log_file: str, code_table: str, output_dir: str = "."):
    """解析SDCI日志文件（便捷函数）

    Args:
        log_file: CTC日志文件路径
        code_table: 码位表文件路径
        output_dir: 输出目录

    Returns:
        解析出的SDCIFrame列表
    """
    # 加载码位表
    cpt = CodePositionTable(code_table)

    # 分析日志
    analyzer = CTCLogAnalyzer(log_file, cpt)
    frames = analyzer.analyze()

    # 生成报告
    report_file = os.path.join(output_dir, "sdci_analysis_report.txt")
    analyzer.generate_report(output_file=report_file)

    # 导出JSON
    json_file = os.path.join(output_dir, "sdci_frames.json")
    export_to_json(frames, json_file)

    return frames

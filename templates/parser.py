#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SDCI帧解析器核心模块 - 联锁系统与调度集中系统通信日志分析

帧格式：
- 帧头：1字节 (0x7D)
- 首部长：1字节 (0x04)
- 版本号：1字节 (0x11)
- 发送序号：1字节
- 确认序号：1字节
- 帧类型：1字节 (0x8A为SDCI帧)
- 数据长度：2字节 (大端序)
- 站场表示数据：N字节 (每设备3字节：2字节序号+1字节状态)
- CRC校验：2字节
- 帧尾：1字节 (0x7E)
"""

import re
import os
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import IntEnum


class DeviceType(IntEnum):
    """设备类型枚举"""

    SWITCH_SECTION = 1  # 道岔区段（纯数字名称）
    SIGNAL = 2  # 信号机（D开头数字结尾）
    TRACK_SECTION = 3  # 无岔区段（其他命名规则）


@dataclass
class DeviceInfo:
    """设备信息"""

    name: str
    device_type: DeviceType
    object_index: int  # objects表中的索引（从0开始）
    byte_index: int  # zlobjects表中的字节索引（从1开始）
    bit_offset: int  # 位偏移（0或4，用于无岔区段共享字节）

    def is_high_nibble(self) -> bool:
        """是否使用高4位（无岔区段）"""
        return self.bit_offset == 4

    def get_type_description(self) -> str:
        """获取设备类型描述"""
        if self.device_type == DeviceType.SWITCH_SECTION:
            return "道岔区段"
        elif self.device_type == DeviceType.SIGNAL:
            return "信号机"
        else:
            return "无岔区段"


@dataclass
class DeviceState:
    """设备状态"""

    device: DeviceInfo
    raw_state: int
    decoded_state: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        state_str = ", ".join([f"{k}={v}" for k, v in self.decoded_state.items()])
        return f"{self.device.name} (0x{self.raw_state:02X}): {state_str}"


@dataclass
class SDCIFrame:
    """SDCI帧结构"""

    timestamp: str
    send_seq: int  # 发送序号
    ack_seq: int  # 确认序号
    data_length: int  # 数据长度
    raw_data: bytes  # 原始数据（包含帧头到帧尾）
    payload: bytes  # 站场表示数据
    crc: int  # CRC校验值
    device_states: List[DeviceState] = field(default_factory=list)

    def get_device_count(self) -> int:
        """获取变化的设备数量"""
        return len(self.device_states)


class CodePositionTable:
    """码位表解析器

    解析lgxtq.zl文件，包含两个部分：
    - [objects]: 对象索引表，用于SDCI帧设备状态解析，索引从0开始
    - [zlobjects]: SDI Buffer对象位置信息表，用于字节索引映射
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.devices: Dict[int, DeviceInfo] = {}  # 以字节索引为键 (zlobjects)
        self.devices_by_object_index: Dict[
            int, DeviceInfo
        ] = {}  # 以object索引为键 (objects)
        self.devices_by_name: Dict[str, DeviceInfo] = {}  # 以设备名称为键
        self.objects: Dict[str, int] = {}  # objects表: 名称->索引
        self._parse()

    def _determine_device_type(self, name: str) -> DeviceType:
        """根据设备名称确定设备类型"""
        # 纯数字 - 道岔区段
        if name.isdigit():
            return DeviceType.SWITCH_SECTION
        # D开头数字结尾 - 信号机
        elif re.match(r"^D\d+$", name):
            return DeviceType.SIGNAL
        # 其他 - 无岔区段
        else:
            return DeviceType.TRACK_SECTION

    def _parse(self):
        """解析码位表文件"""
        with open(self.file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 解析[objects]部分
        objects_match = re.search(r"\[objects\](.*?)\[end\]", content, re.DOTALL)
        if objects_match:
            objects_section = objects_match.group(1)
            for line in objects_section.strip().split("\n"):
                line = line.strip()
                if line.startswith("#,"):
                    parts = line.split(",")
                    if len(parts) >= 3:
                        name = parts[1].strip()
                        index = int(parts[2].strip())
                        self.objects[name] = index

        # 解析[zlobjects]部分
        zlobjects_match = re.search(r"\[zlobjects\](.*?)\[end\]", content, re.DOTALL)
        if zlobjects_match:
            zlobjects_section = zlobjects_match.group(1)
            for line in zlobjects_section.strip().split("\n"):
                line = line.strip()
                if line.startswith("#,"):
                    parts = line.split(",")
                    if len(parts) >= 4:
                        name = parts[1].strip()
                        byte_index = int(parts[2].strip())
                        bit_offset = int(parts[3].strip())

                        device_type = self._determine_device_type(name)
                        object_index = self.objects.get(name, -1)

                        device = DeviceInfo(
                            name=name,
                            device_type=device_type,
                            object_index=object_index,
                            byte_index=byte_index,
                            bit_offset=bit_offset,
                        )

                        self.devices[byte_index] = device
                        self.devices_by_name[name] = device
                        # 同时建立object索引映射（用于SDCI帧解析）
                        if object_index >= 0:
                            self.devices_by_object_index[object_index] = device

    def get_device_by_byte_index(self, byte_index: int) -> Optional[DeviceInfo]:
        """根据字节索引获取设备信息 (zlobjects表)"""
        return self.devices.get(byte_index)

    def get_device_by_object_index(self, object_index: int) -> Optional[DeviceInfo]:
        """根据object索引获取设备信息 (objects表)"""
        return self.devices_by_object_index.get(object_index)

    def get_device_by_name(self, name: str) -> Optional[DeviceInfo]:
        """根据设备名称获取设备信息"""
        return self.devices_by_name.get(name)


class StateDecoder:
    """设备状态解码器

    根据设备类型解码状态字节：
    - 道岔区段（纯数字名称）：0-2位道岔位置，3位区段锁闭，4位区段占用，5位道岔锁闭
    - 信号机（D开头）：0-5位灯色，6位进路转岔，7位延时解锁
    - 无岔区段：0/4位区段锁闭，1/5位区段占用（高/低4位共享字节）
    """

    # 道岔位置
    SWITCH_POSITIONS = {0x01: "定位", 0x02: "反位", 0x04: "无表示"}

    # 信号机颜色
    SIGNAL_COLORS = {
        0x01: "灯丝短丝",
        0x02: "蓝",
        0x04: "白",
        0x08: "红",
        0x10: "绿",
        0x11: "黄",
        0x12: "2黄",
        0x13: "引白",
    }

    @classmethod
    def decode_switch_section(cls, raw_state: int) -> Dict[str, Any]:
        """解码道岔区段状态

        状态字节包含以下信息（8位，按位组合）：
        - bit 0-2: 道岔位置 (1=定位, 2=反位, 4=无表示，可组合)
        - bit 3: 区段锁闭状态 (0=未锁闭, 1=锁闭)
        - bit 4: 区段占用状态 (0=未占用, 1=占用)
        - bit 5: 道岔锁闭状态 (0=未锁闭, 1=锁闭)
        - bit 6-7: 保留

        Returns:
            {
                "位置": "定位" | "反位" | "无表示" | "定位+反位" | ...,
                "区段状态": {
                    "锁闭": "未锁闭" | "锁闭",
                    "占用": "未占用" | "占用"
                },
                "道岔锁闭": "未锁闭" | "锁闭"
            }
        """
        result = {}

        # bit 0-2: 道岔位置（按位组合）
        position_bits = raw_state & 0x07
        position_parts = []
        if position_bits & 0x01:
            position_parts.append("定位")
        if position_bits & 0x02:
            position_parts.append("反位")
        if position_bits & 0x04:
            position_parts.append("无表示")

        if position_parts:
            result["位置"] = " + ".join(position_parts)
        else:
            result["位置"] = "未知(0)"

        # bit 3: 区段锁闭状态
        section_lock = (raw_state >> 3) & 0x01
        # bit 4: 区段占用状态
        occupancy = (raw_state >> 4) & 0x01
        result["区段状态"] = {
            "锁闭": "锁闭" if section_lock else "未锁闭",
            "占用": "占用" if occupancy else "未占用",
        }

        # bit 5: 道岔锁闭状态
        switch_lock = (raw_state >> 5) & 0x01
        result["道岔锁闭"] = "锁闭" if switch_lock else "未锁闭"

        return result

    @classmethod
    def decode_signal(cls, raw_state: int) -> Dict[str, Any]:
        """解码信号机状态

        状态字节包含以下信息（8位）：
        - bit 0-5: 灯色状态 (灯丝断丝、蓝、白、红、绿、黄、2黄、引白)
        - bit 6: 进路转岔过程中的始终信号机 (0=否, 1=是)
        - bit 7: 延时解锁状态 (0=无延时, 1=延时中)

        Returns:
            {
                "颜色": "灯丝断丝" | "蓝" | "白" | "红" | "绿" | "黄" | "2黄" | "引白",
                "进路转岔过程中的始终信号机": "是" | "否",
                "延时解锁": "延时中" | "无延时"
            }
        """
        result = {}

        # bit 0-5: 颜色编码（按位组合）
        color_bits = raw_state & 0x3F

        # 颜色分量（按位检测）
        color_parts = []
        if color_bits & 0x01:
            color_parts.append("灯丝短丝")
        if color_bits & 0x02:
            color_parts.append("蓝")
        if color_bits & 0x04:
            color_parts.append("白")
        if color_bits & 0x08:
            color_parts.append("红")
        if color_bits & 0x10:
            color_parts.append("绿")

        # 特殊组合检测（bit 5组合）
        if color_bits & 0x20:
            if color_bits == 0x20:
                color_parts = ["黄"]  # bit5单独=黄
            elif color_bits == 0x22:
                color_parts = ["2黄"]  # bit5+蓝=2黄
            elif color_bits == 0x23:
                color_parts = ["引白"]  # bit5+蓝+灯丝短丝=引白
            else:
                # bit5与其他颜色组合
                color_parts.insert(0, "[bit5组合]")

        if color_parts:
            result["颜色"] = " + ".join(color_parts)
        else:
            result["颜色"] = "灭灯"

        # bit 6: 进路转岔过程中的始终信号机
        is_route_transition = (raw_state >> 6) & 0x01
        result["进路转岔过程中的始终信号机"] = "是" if is_route_transition else "否"

        # bit 7: 延时解锁状态
        delay_unlock = (raw_state >> 7) & 0x01
        result["延时解锁"] = "延时中" if delay_unlock else "无延时"

        return result

    @classmethod
    def decode_track_section(
        cls, raw_state: int, is_high_nibble: bool
    ) -> Dict[str, Any]:
        """解码无岔区段状态

        状态字节包含以下信息（使用低4位或高4位）：
        - 低4位模式: bit 0=锁闭, bit 1=占用
        - 高4位模式: bit 4=锁闭, bit 5=占用

        Args:
            raw_state: 原始状态字节
            is_high_nibble: 是否使用高4位（bit_offset=4时为True）

        Returns:
            {
                "区段状态": {
                    "锁闭": "未锁闭" | "锁闭",
                    "占用": "未占用" | "占用"
                }
            }
        """
        result = {}

        if is_high_nibble:
            # 使用高4位 (bit_offset=4)
            # bit 4: 区段锁闭状态
            lock = (raw_state >> 4) & 0x01
            # bit 5: 区段占用状态
            occupancy = (raw_state >> 5) & 0x01
        else:
            # 使用低4位 (bit_offset=0)
            # bit 0: 区段锁闭状态
            lock = raw_state & 0x01
            # bit 1: 区段占用状态
            occupancy = (raw_state >> 1) & 0x01

        result["区段状态"] = {
            "锁闭": "锁闭" if lock else "未锁闭",
            "占用": "占用" if occupancy else "未占用",
        }

        return result


class SDCIFrameParser:
    """SDCI帧解析器"""

    # 帧常量
    FRAME_HEADER = 0x7D
    FRAME_TAIL = 0x7E
    HEADER_LENGTH = 0x04
    VERSION = 0x11
    FRAME_TYPE_SDCI = 0x8A  # SDCI帧（变化设备列表）
    FRAME_TYPE_SDI = 0x85  # SDI帧（完整站场状态）
    FRAME_TYPE_CONTROL = 0x06

    def __init__(self, code_position_table: CodePositionTable):
        self.cpt = code_position_table

    def parse_frame(
        self, raw_data: bytes, timestamp: Optional[str] = None
    ) -> Optional[SDCIFrame]:
        """解析SDCI帧

        Args:
            raw_data: 帧的原始字节数据
            timestamp: 可选的时间戳字符串

        Returns:
            解析成功的SDCIFrame对象，失败返回None
        """
        if len(raw_data) < 9:
            return None

        # 检查帧头和帧尾
        if raw_data[0] != self.FRAME_HEADER or raw_data[-1] != self.FRAME_TAIL:
            return None

        # 检查首部长和版本号
        if raw_data[1] != self.HEADER_LENGTH or raw_data[2] != self.VERSION:
            return None

        # 检查帧类型
        frame_type = raw_data[5]
        is_sdi = frame_type == self.FRAME_TYPE_SDI
        is_sdci = frame_type == self.FRAME_TYPE_SDCI
        if not (is_sdi or is_sdci):
            return None  # 不支持的帧类型

        # 解析序号
        send_seq = raw_data[3]
        ack_seq = raw_data[4]

        # 解析数据长度（大端序）
        data_length = (raw_data[6] << 8) | raw_data[7]

        # 提取CRC（最后3字节：2字节CRC + 1字节帧尾）
        crc = (raw_data[-3] << 8) | raw_data[-2]

        # 提取数据载荷（跳过8字节首部，到CRC之前）
        payload_start = 8
        payload_end = len(raw_data) - 3
        payload = raw_data[payload_start:payload_end]

        # 根据帧类型解析数据载荷
        if is_sdi:
            # SDI帧：完整站场状态字节数组
            device_states = self._parse_sdi_payload(payload)
        else:
            # SDCI帧：变化设备列表（每3字节一个设备）
            device_states = self._parse_sdci_payload(payload)

        return SDCIFrame(
            timestamp=timestamp or "",
            send_seq=send_seq,
            ack_seq=ack_seq,
            data_length=data_length,
            raw_data=raw_data,
            payload=payload,
            crc=crc,
            device_states=device_states,
        )

    def _parse_sdci_payload(self, payload: bytes) -> List[DeviceState]:
        """解析SDCI帧数据载荷

        SDCI帧每3字节表示一个变化设备：
        - 前2字节：设备序号（objects表索引，大端序）
        - 第3字节：设备状态（无岔区段使用bit_offset判断高/低4位）
        """
        device_states = []

        for i in range(0, len(payload), 3):
            if i + 2 >= len(payload):
                break

            # 解析设备序号（大端序）
            device_index = (payload[i] << 8) | payload[i + 1]
            raw_state = payload[i + 2]

            # 查找设备信息（SDCI帧中使用的是objects表的索引，从0开始）
            device = self.cpt.get_device_by_object_index(device_index)

            if device:
                # 解码设备状态（SDCI帧需要根据bit_offset判断使用高/低4位）
                if device.device_type == DeviceType.SWITCH_SECTION:
                    decoded = StateDecoder.decode_switch_section(raw_state)
                elif device.device_type == DeviceType.SIGNAL:
                    decoded = StateDecoder.decode_signal(raw_state)
                else:  # TRACK_SECTION - SDCI帧需要根据bit_offset使用高/低4位
                    decoded = StateDecoder.decode_track_section(
                        raw_state, device.is_high_nibble()
                    )

                device_state = DeviceState(
                    device=device, raw_state=raw_state, decoded_state=decoded
                )
                device_states.append(device_state)
            else:
                # 未找到设备信息，创建设备状态但不解码
                unknown_device = DeviceInfo(
                    name=f"Unknown_{device_index}",
                    device_type=DeviceType.TRACK_SECTION,
                    object_index=-1,
                    byte_index=device_index,
                    bit_offset=0,
                )
                device_state = DeviceState(
                    device=unknown_device,
                    raw_state=raw_state,
                    decoded_state={"原始状态": f"0x{raw_state:02X}"},
                )
                device_states.append(device_state)

        return device_states

    def _parse_sdi_payload(self, payload: bytes) -> List[DeviceState]:
        """解析SDI帧数据载荷

        SDI帧包含完整的站场状态字节数组。
        每个字节位置对应一个设备（通过zlobjects表的byte_index映射）。
        字节内的比特位从低位向高位计数。

        Args:
            payload: 站场状态字节数组

        Returns:
            所有设备的当前状态列表
        """
        device_states = []

        # 遍历所有已知的设备（从zlobjects表）
        for byte_index, device in self.cpt.devices.items():
            # 检查字节索引是否在payload范围内
            # 注意：zlobjects表的byte_index从1开始，而payload索引从0开始
            payload_index = byte_index - 1

            if payload_index < 0 or payload_index >= len(payload):
                continue  # 超出范围，跳过

            raw_state = payload[payload_index]

            # 解码设备状态（SDI帧需要根据bit_offset判断高/低4位）
            if device.device_type == DeviceType.SWITCH_SECTION:
                decoded = StateDecoder.decode_switch_section(raw_state)
            elif device.device_type == DeviceType.SIGNAL:
                decoded = StateDecoder.decode_signal(raw_state)
            else:  # TRACK_SECTION - SDI帧需要根据bit_offset使用高/低4位
                decoded = StateDecoder.decode_track_section(
                    raw_state, device.is_high_nibble()
                )

            device_state = DeviceState(
                device=device, raw_state=raw_state, decoded_state=decoded
            )
            device_states.append(device_state)

        return device_states


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
        # 正则表达式匹配包含SDCI数据的行
        # 匹配模式: "Data: 7D 04 11 65 BF 8A 03 00 00 B7 10 28 81 7E"
        data_pattern = re.compile(
            r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+).*?Data:\s+([0-9A-Fa-f\s]+)"
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
            lines.append(f"  CRC校验: 0x{frame.crc:04X}")
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
    """CTC日志硬件故障分析器

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
            from datetime import datetime as dt_module

            for i in range(1, len(fault_times)):
                try:
                    t1 = dt_module.strptime(
                        fault_times[i - 1][:19], "%Y-%m-%d %H:%M:%S"
                    )
                    t2 = dt_module.strptime(fault_times[i][:19], "%Y-%m-%d %H:%M:%S")
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


def analyze_hardware_faults(log_file: str, output_dir: str = ".") -> Dict[str, Any]:
    """分析CTC日志中的硬件故障（便捷函数）

    Args:
        log_file: CTC日志文件路径
        output_dir: 输出目录

    Returns:
        分析结果字典
    """
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

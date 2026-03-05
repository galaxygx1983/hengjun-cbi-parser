#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
恒久CBI帧解析器核心模块 - 联锁系统与调度集中系统通信日志分析

支持以下帧类型：
- DC2 (0x12) - 连接请求帧
- DC3 (0x13) - 连接确认帧
- ACK (0x06) - 应答/心跳帧
- NACK (0x15) - 否定应答帧
- VERROR (0x10) - 版本错误帧
- SDCI (0x8A) - 站场数据变化帧（增量）
- SDI (0x85) - 站场完整数据帧（全量）
- SDIQ (0x6A) - 站场数据请求帧
- FIR (0x65) - 故障信息报告帧
- RSR (0xAA) - 系统工作状态报告帧
- BCC (0x95) - 按钮控制命令帧
- ACQ (0x75) - 自律控制请求帧
- ACA (0x7A) - 自律控制同意帧
- TSQ (0x9A) - 时间同步请求帧
- TSD (0xA5) - 时间同步数据帧

通用帧格式：
- 帧头：1字节 (0x7D)
- 首部长：1字节 (0x04)
- 版本号：1字节 (0x11)
- 发送序号：1字节
- 确认序号：1字节
- 帧类型：1字节
- 数据长度：2字节 (大端序，SDCI/SDI/FIR等有数据载荷的帧)
- 数据载荷：N字节 (帧类型相关)
- CRC校验：2字节
- 帧尾：1字节 (0x7E)
"""

import re
import os
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from enum import IntEnum


class DeviceType(IntEnum):
    """设备类型枚举"""

    SWITCH_SECTION = 1  # 道岔区段（纯数字名称）
    SIGNAL = 2  # 信号机（D开头数字结尾）
    TRACK_SECTION = 3  # 无岔区段（其他命名规则）


# FIR帧错误码映射表（来自Error.sys）
ERROR_CODE_MAP = {
    0x00: "错误办理",
    0x01: "运行表满",
    0x02: "区段占用",
    0x03: "敌对进路",
    0x04: "不能转岔",
    0x05: "灯丝断丝",
    0x06: "道岔锁闭",
    0x07: "照查不对",
    0x08: "侵限占用",
    0x09: "区段锁闭",
    0x0A: "道口未关",
    0x0B: "信号未关",
    0x0C: "区段未锁",
    0x0D: "口令错误",
    0x0E: "半自动复原",
    0x0F: "信号关闭",
    0x10: "双动道岔占用",
    0x11: "双动道岔锁闭",
    0x12: "双动道岔锁闭",
    0x13: "正在转岔",
    0x14: "未经同意",
    0x15: "非法码",
    0x16: "未办半自动",
    0x17: "接近区段占用",
    0x18: "条件不满足",
    0x19: "对方信号不对",
    0x1A: "跳表示",
    0x1B: "已办引导总锁",
    0x1C: "正在办理进路",
    0x1D: "非法版权",
    0x1E: "初始化失败",
    0x1F: "初始化成功",
    0x20: "岔位不对",
    0x21: "不能开放",
    0x22: "冒进信号",
    0x23: "轨道故障",
    0x24: "远程中断",
    0x25: "远程恢复",
    0x26: "禁止操作",
    0x27: "禁止切换",
    0x28: "初始化联系口",
    0x29: "通讯中断",
    0x2A: "通讯恢复",
}


# BCC帧命令类型映射表
BCC_COMMAND_MAP = {
    3: "人工解锁",
    4: "取消进路",
    5: "重复开放",
    6: "故障解锁",
    7: "道岔定位",
    8: "道岔反位",
    9: "道岔锁闭",
    10: "道岔解锁",
    12: "调车作业",
    13: "关闭信号",
    14: "列车作业",
    15: "引导总解锁",
    16: "引导锁闭",
    18: "引导总锁",
}


# RSR帧状态值映射表
RSR_STATUS_MAP = {
    0x55: {"role": "主机", "mode_ctc": "同意自律", "mode_ilock": "自律控制"},
    0xAA: {"role": "备机", "mode_ctc": "不同意自律", "mode_ilock": "非常站控"},
    0xCC: {"role": "未知", "mode_ctc": "不确定", "mode_ilock": "中间状态"},
}


# ACA帧同意标志映射表
ACA_RESPONSE_MAP = {
    0x55: "同意",
    0xAA: "不同意",
}


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
class Frame:
    """通用帧结构"""

    timestamp: str
    frame_type: int  # 帧类型代码
    frame_type_name: str  # 帧类型名称
    send_seq: int  # 发送序号
    ack_seq: int  # 确认序号
    data_length: int  # 数据长度
    raw_data: bytes  # 原始数据
    payload: bytes  # 数据载荷
    crc: int  # CRC校验值
    direction: str  # 传输方向
    device_states: List[DeviceState] = field(default_factory=list)  # 设备状态列表（仅SDCI/SDI帧）
    fir_events: List[Dict[str, Any]] = field(default_factory=list)  # 故障事件列表（仅FIR帧）
    rsr_status: Optional[Dict[str, Any]] = None  # RSR状态信息
    bcc_command: Optional[Dict[str, Any]] = None  # BCC命令信息
    tsd_time: Optional[Dict[str, Any]] = None  # TSD时间信息
    aca_response: Optional[Dict[str, Any]] = None  # ACA响应信息

    def get_frame_name(self) -> str:
        """获取帧类型名称"""
        return self.frame_type_name

    def has_device_states(self) -> bool:
        """是否有设备状态（SDCI/SDI帧）"""
        return len(self.device_states) > 0

    def get_device_count(self) -> int:
        """获取变化的设备数量"""
        return len(self.device_states)

    def has_payload(self) -> bool:
        """是否有数据载荷"""
        return FrameType.has_payload(self.frame_type)


# 保留向后兼容：SDCIFrame 作为 Frame 的别名
SDCIFrame = Frame


class FrameType(IntEnum):
    """帧类型枚举"""

    # 控制帧（无数据载荷）
    DC2 = 0x12  # 连接请求帧
    DC3 = 0x13  # 连接确认帧
    ACK = 0x06  # 应答/心跳帧
    NACK = 0x15  # 否定应答帧
    VERROR = 0x10  # 版本错误帧

    # 数据帧（有数据载荷）
    SDCI = 0x8A  # 站场数据变化帧（增量）
    SDI = 0x85  # 站场完整数据帧（全量）
    SDIQ = 0x6A  # 站场数据请求帧
    FIR = 0x65  # 故障信息报告帧
    RSR = 0xAA  # 系统工作状态报告帧
    BCC = 0x95  # 按钮控制命令帧
    ACQ = 0x75  # 自律控制请求帧
    ACA = 0x7A  # 自律控制同意帧
    TSQ = 0x9A  # 时间同步请求帧
    TSD = 0xA5  # 时间同步数据帧

    @classmethod
    def get_name(cls, code: int) -> str:
        """获取帧类型名称"""
        try:
            return cls(code).name
        except ValueError:
            return f"UNKNOWN_0x{code:02X}"

    @classmethod
    def has_payload(cls, code: int) -> bool:
        """判断帧类型是否有数据载荷"""
        no_payload = {cls.DC2, cls.DC3, cls.ACK, cls.NACK, cls.VERROR, cls.SDIQ, cls.TSQ, cls.ACQ}
        return code not in no_payload


class FrameTypeInfo:
    """帧类型信息映射"""

    FRAME_INFO = {
        0x12: {"name": "DC2", "direction": "CTC→联锁", "has_payload": False, "desc": "连接建立请求帧"},
        0x13: {"name": "DC3", "direction": "联锁→CTC", "has_payload": False, "desc": "连接确认帧"},
        0x06: {"name": "ACK", "direction": "双向", "has_payload": False, "desc": "应答/心跳帧"},
        0x15: {"name": "NACK", "direction": "双向", "has_payload": False, "desc": "否定应答帧"},
        0x10: {"name": "VERROR", "direction": "双向", "has_payload": False, "desc": "版本错误帧"},
        0x8A: {"name": "SDCI", "direction": "联锁→CTC", "has_payload": True, "desc": "站场数据变化（增量）"},
        0x85: {"name": "SDI", "direction": "联锁→CTC", "has_payload": True, "desc": "站场完整数据（全量）"},
        0x6A: {"name": "SDIQ", "direction": "CTC→联锁", "has_payload": False, "desc": "站场数据请求帧"},
        0x65: {"name": "FIR", "direction": "联锁→CTC", "has_payload": True, "desc": "故障信息报告帧"},
        0xAA: {"name": "RSR", "direction": "双向", "has_payload": True, "desc": "系统工作状态报告帧"},
        0x95: {"name": "BCC", "direction": "CTC→联锁", "has_payload": True, "desc": "按钮控制命令帧"},
        0x75: {"name": "ACQ", "direction": "联锁→CTC", "has_payload": False, "desc": "自律控制请求帧"},
        0x7A: {"name": "ACA", "direction": "CTC→联锁", "has_payload": True, "desc": "自律控制同意帧"},
        0x9A: {"name": "TSQ", "direction": "联锁→CTC", "has_payload": False, "desc": "时间同步请求帧"},
        0xA5: {"name": "TSD", "direction": "CTC→联锁", "has_payload": True, "desc": "时间同步数据帧"},
    }

    @classmethod
    def get_info(cls, frame_type: int) -> Dict[str, Any]:
        """获取帧类型信息"""
        return cls.FRAME_INFO.get(frame_type, {"name": f"UNKNOWN_0x{frame_type:02X}", "direction": "未知", "has_payload": False, "desc": "未知帧类型"})


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


# 保留向后兼容：SDCIFrameParser 作为 FrameParser 的别名
class FrameParser:
    """通用帧解析器 - 支持所有帧类型

    支持的帧类型：
    - 无数据载荷帧：DC2(0x12), DC3(0x13), ACK(0x06), NACK(0x15), VERROR(0x10), SDIQ(0x6A), TSQ(0x9A), ACQ(0x75)
    - 有数据载荷帧：SDCI(0x8A), SDI(0x85), FIR(0x65), RSR(0xAA), BCC(0x95), ACA(0x7A), TSD(0xA5)
    """

    # 帧常量
    FRAME_HEADER = 0x7D
    FRAME_TAIL = 0x7E
    HEADER_LENGTH = 0x04
    VERSION = 0x11

    # 支持的帧类型
    FRAME_TYPES = {
        0x12,  # DC2
        0x13,  # DC3
        0x06,  # ACK
        0x15,  # NACK
        0x10,  # VERROR
        0x8A,  # SDCI
        0x85,  # SDI
        0x6A,  # SDIQ
        0x65,  # FIR
        0xAA,  # RSR
        0x95,  # BCC
        0x75,  # ACQ
        0x7A,  # ACA
        0x9A,  # TSQ
        0xA5,  # TSD
    }

    # 有数据载荷的帧类型
    FRAMES_WITH_PAYLOAD = {0x8A, 0x85, 0x65, 0xAA, 0x95, 0x7A, 0xA5}

    def __init__(self, code_position_table: Optional[CodePositionTable] = None):
        self.cpt = code_position_table

    def parse_frame(
        self, raw_data: bytes, timestamp: Optional[str] = None
    ) -> Optional[Frame]:
        """解析任意帧类型

        Args:
            raw_data: 帧的原始字节数据
            timestamp: 可选的时间戳字符串

        Returns:
            解析成功的Frame对象，失败返回None
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
        if frame_type not in self.FRAME_TYPES:
            return None  # 不支持的帧类型

        # 解析序号
        send_seq = raw_data[3]
        ack_seq = raw_data[4]

        # 获取帧类型信息
        frame_type_info = FrameTypeInfo.get_info(frame_type)
        frame_type_name = frame_type_info["name"]
        direction = frame_type_info["direction"]

        # 解析数据长度（无数据载荷帧为0）
        data_length = 0
        if frame_type in self.FRAMES_WITH_PAYLOAD:
            if len(raw_data) < 12:
                return None
            data_length = (raw_data[6] << 8) | raw_data[7]

        # 提取CRC（最后3字节：2字节CRC + 1字节帧尾）
        crc = (raw_data[-3] << 8) | raw_data[-2]

        # 提取数据载荷
        payload = b""
        if frame_type in self.FRAMES_WITH_PAYLOAD:
            payload_start = 8
            payload_end = len(raw_data) - 3
            payload = raw_data[payload_start:payload_end]

        # 根据帧类型解析数据载荷
        device_states = []
        fir_events = []
        rsr_status = None
        bcc_command = None
        tsd_time = None
        aca_response = None

        if frame_type == 0x8A:  # SDCI - 站场数据变化
            device_states = self._parse_sdci_payload(payload)
        elif frame_type == 0x85:  # SDI - 站场完整数据
            device_states = self._parse_sdi_payload(payload)
        elif frame_type == 0x65:  # FIR - 故障信息报告
            fir_events = self._parse_fir_payload(payload)
        elif frame_type == 0xAA:  # RSR - 系统工作状态报告
            rsr_status = self._parse_rsr_payload(payload)
        elif frame_type == 0x95:  # BCC - 按钮控制命令
            bcc_command = self._parse_bcc_payload(payload)
        elif frame_type == 0xA5:  # TSD - 时间同步数据
            tsd_time = self._parse_tsd_payload(payload)
        elif frame_type == 0x7A:  # ACA - 自律控制同意
            aca_response = self._parse_aca_payload(payload)

        return Frame(
            timestamp=timestamp or "",
            frame_type=frame_type,
            frame_type_name=frame_type_name,
            send_seq=send_seq,
            ack_seq=ack_seq,
            data_length=data_length,
            raw_data=raw_data,
            payload=payload,
            crc=crc,
            direction=direction,
            device_states=device_states,
            fir_events=fir_events,
            rsr_status=rsr_status,
            bcc_command=bcc_command,
            tsd_time=tsd_time,
            aca_response=aca_response,
        )

    def _parse_sdci_payload(self, payload: bytes) -> List[DeviceState]:
        """解析SDCI帧数据载荷

        SDCI帧每3字节表示一个变化设备：
        - 前2字节：设备序号（objects表索引，大端序）
        - 第3字节：设备状态（无岔区段使用bit_offset判断高/低4位）
        """
        device_states = []

        if not self.cpt:
            return device_states

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

        if not self.cpt:
            return device_states

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

    def _parse_fir_payload(self, payload: bytes) -> List[Dict[str, Any]]:
        """解析FIR帧数据载荷（故障信息报告）

        FIR帧每4字节表示一个故障事件：
        - 字节0：提示码（固定为0）
        - 字节1-2：对象索引（16位有符号，小端序）
        - 字节3：故障类型（来自Error.sys的错误码）

        Args:
            payload: FIR帧数据载荷

        Returns:
            故障事件列表
        """
        fir_events = []

        for i in range(0, len(payload), 4):
            if i + 3 >= len(payload):
                break

            # 解析故障信息
            hint_code = payload[i]
            # 对象索引（小端序，16位有符号）
            object_index = (payload[i + 2] << 8) | payload[i + 1]
            # 转换为有符号数
            if object_index >= 0x8000:
                object_index = object_index - 0x10000
            fault_type_code = payload[i + 3]

            # 查找错误描述
            fault_description = ERROR_CODE_MAP.get(fault_type_code, f"未知错误(0x{fault_type_code:02X})")

            fir_event = {
                "hint_code": hint_code,
                "object_index": object_index,
                "fault_type_code": fault_type_code,
                "fault_description": fault_description,
            }
            fir_events.append(fir_event)

        return fir_events

    def _parse_rsr_payload(self, payload: bytes) -> Optional[Dict[str, Any]]:
        """解析RSR帧数据载荷（工作状态报告）

        RSR帧包含2字节状态信息：
        - 字节0：主备状态
        - 字节1：控制模式

        Args:
            payload: RSR帧数据载荷（应为2字节）

        Returns:
            状态信息字典
        """
        if len(payload) < 2:
            return None

        role_status = payload[0]
        control_mode = payload[1]

        # 查找状态映射
        status_info = RSR_STATUS_MAP.get(role_status, {"role": "未知", "mode_ctc": "未知", "mode_ilock": "未知"})

        # 根据方向判断控制模式含义（这里简化为返回所有可能）
        rsr_status = {
            "role_status": role_status,
            "role": status_info["role"],
            "control_mode": control_mode,
            "mode_ctc": status_info["mode_ctc"],
            "mode_ilock": status_info["mode_ilock"],
        }

        return rsr_status

    def _parse_bcc_payload(self, payload: bytes) -> Optional[Dict[str, Any]]:
        """解析BCC帧数据载荷（按钮控制命令）

        BCC帧包含7字节命令数据：
        - 字节0：命令类型
        - 字节1-2：按钮索引1（小端序）
        - 字节3-4：按钮索引2（小端序，未使用则为-1）
        - 字节5-6：按钮索引3（小端序，未使用则为-1）

        Args:
            payload: BCC帧数据载荷（通常为7字节）

        Returns:
            命令信息字典
        """
        if len(payload) < 7:
            return None

        command_type = payload[0]
        button_index1 = (payload[2] << 8) | payload[1]
        button_index2 = (payload[4] << 8) | payload[3]
        button_index3 = (payload[6] << 8) | payload[5]

        # 处理未使用的索引（0xFFFF = -1）
        if button_index1 == 0xFFFF:
            button_index1 = -1
        if button_index2 == 0xFFFF:
            button_index2 = -1
        if button_index3 == 0xFFFF:
            button_index3 = -1

        # 查找命令描述
        command_description = BCC_COMMAND_MAP.get(command_type, f"未知命令({command_type})")

        bcc_command = {
            "command_type": command_type,
            "command_description": command_description,
            "button_index1": button_index1,
            "button_index2": button_index2,
            "button_index3": button_index3,
        }

        return bcc_command

    def _parse_tsd_payload(self, payload: bytes) -> Optional[Dict[str, Any]]:
        """解析TSD帧数据载荷（时间同步数据）

        TSD帧包含7字节时间数据：
        - 字节0-1：年份（小端序）
        - 字节2：月份
        - 字节3：日期
        - 字节4：小时
        - 字节5：分钟
        - 字节6：秒

        Args:
            payload: TSD帧数据载荷（应为7字节）

        Returns:
            时间信息字典
        """
        if len(payload) < 7:
            return None

        # 解析时间数据（小端序年份）
        year = (payload[1] << 8) | payload[0]
        month = payload[2]
        day = payload[3]
        hour = payload[4]
        minute = payload[5]
        second = payload[6]

        # 格式化为时间字符串
        try:
            time_str = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
        except:
            time_str = "无效时间"

        tsd_time = {
            "year": year,
            "month": month,
            "day": day,
            "hour": hour,
            "minute": minute,
            "second": second,
            "time_string": time_str,
        }

        return tsd_time

    def _parse_aca_payload(self, payload: bytes) -> Optional[Dict[str, Any]]:
        """解析ACA帧数据载荷（自律控制同意）

        ACA帧包含1字节同意标志：
        - 字节0：同意标志（0x55=同意，0xAA=不同意）

        Args:
            payload: ACA帧数据载荷（应为1字节）

        Returns:
            同意响应信息字典
        """
        if len(payload) < 1:
            return None

        response_flag = payload[0]
        response_description = ACA_RESPONSE_MAP.get(response_flag, f"未知({response_flag})")

        aca_response = {
            "response_flag": response_flag,
            "response_description": response_description,
        }

        return aca_response


# 保留向后兼容：SDCIFrameParser 作为 FrameParser 的别名
SDCIFrameParser = FrameParser


class CTCLogAnalyzer:
    """CTC日志分析器 - 支持所有帧类型"""

    def __init__(self, log_file: str, code_position_table: Optional[CodePositionTable] = None):
        self.log_file = log_file
        self.cpt = code_position_table
        self.parser = FrameParser(code_position_table)
        self.frames: List[Frame] = []

    def analyze(self, max_frames: Optional[int] = None, frame_types: Optional[set] = None) -> List[Frame]:
        """分析日志文件，提取所有类型的帧

        Args:
            max_frames: 最大解析帧数（None表示不限制）
            frame_types: 要解析的帧类型集合（None表示所有类型）

        Returns:
            解析出的Frame列表
        """
        # 默认解析所有支持的帧类型
        if frame_types is None:
            frame_types = FrameParser.FRAME_TYPES

        # 正则表达式匹配包含帧数据的行
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

                        # 检查帧类型是否在目标类型中
                        if len(raw_bytes) >= 6:
                            frame_type = raw_bytes[5]
                            if frame_type in frame_types:
                                frame = self.parser.parse_frame(raw_bytes, timestamp)
                                if frame:
                                    self.frames.append(frame)
                                    frame_count += 1

                                    if max_frames and frame_count >= max_frames:
                                        break

                    except ValueError:
                        continue

        return self.frames

    def analyze_sdci(self, max_frames: Optional[int] = None) -> List[Frame]:
        """分析日志文件，只提取SDCI帧（向后兼容）

        Args:
            max_frames: 最大解析帧数

        Returns:
            解析出的SDCI帧列表
        """
        return self.analyze(max_frames=max_frames, frame_types={0x8A})

    def analyze_sdi(self, max_frames: Optional[int] = None) -> List[Frame]:
        """分析日志文件，只提取SDI帧

        Args:
            max_frames: 最大解析帧数

        Returns:
            解析出的SDI帧列表
        """
        return self.analyze(max_frames=max_frames, frame_types={0x85})

    def analyze_fir(self, max_frames: Optional[int] = None) -> List[Frame]:
        """分析日志文件，只提取FIR帧

        Args:
            max_frames: 最大解析帧数

        Returns:
            解析出的FIR帧列表
        """
        return self.analyze(max_frames=max_frames, frame_types={0x65})

    def analyze_control_frames(self, max_frames: Optional[int] = None) -> List[Frame]:
        """分析日志文件，只提取控制帧（DC2/DC3/ACK/NACK/VERROR）

        Args:
            max_frames: 最大解析帧数

        Returns:
            解析出的控制帧列表
        """
        return self.analyze(max_frames=max_frames, frame_types={0x12, 0x13, 0x06, 0x15, 0x10})

    def get_frame_statistics(self) -> Dict[str, Any]:
        """获取帧统计信息

        Returns:
            统计信息字典
        """
        stats = defaultdict(int)
        for frame in self.frames:
            stats[frame.frame_type_name] += 1
        return dict(stats)

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
        lines.append("CTC帧分析报告")
        lines.append("=" * 80)
        lines.append(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"日志文件: {self.log_file}")
        lines.append(f"码位表文件: {self.cpt.file_path if self.cpt else 'N/A'}")
        lines.append(f"总帧数: {len(self.frames)}")
        lines.append("")

        # 统计信息
        lines.append("-" * 80)
        lines.append("帧类型统计")
        lines.append("-" * 80)

        stats = self.get_frame_statistics()
        for frame_type, count in sorted(stats.items()):
            lines.append(f"  {frame_type}: {count}帧")
        lines.append("")

        # 详细帧信息
        lines.append("-" * 80)
        lines.append(f"帧详细信息 (显示前{max_frames_in_report}帧)")
        lines.append("-" * 80)

        for i, frame in enumerate(self.frames[:max_frames_in_report], 1):
            lines.append(f"\n帧 #{i}")
            lines.append(f"  帧类型: {frame.frame_type_name} (0x{frame.frame_type:02X})")
            lines.append(f"  方向: {frame.direction}")
            lines.append(f"  时间戳: {frame.timestamp}")
            lines.append(f"  发送序号: 0x{frame.send_seq:02X} ({frame.send_seq})")
            lines.append(f"  确认序号: 0x{frame.ack_seq:02X} ({frame.ack_seq})")
            lines.append(f"  数据长度: {frame.data_length}字节")
            lines.append(f"  CRC校验: 0x{frame.crc:04X}")
            lines.append(f"  原始数据: {frame.raw_data.hex().upper()}")

            # 帧类型特定信息
            if frame.device_states:
                lines.append(f"  设备状态变化数: {frame.get_device_count()}")
                lines.append("  设备状态详情:")
                for ds in frame.device_states[:10]:  # 最多显示10个
                    lines.append(
                        f"    - {ds.device.name} [{ds.device.get_type_description()}]"
                    )
                    lines.append(f"      设备序号: {ds.device.byte_index}")
                    lines.append(
                        f"      原始状态: 0x{ds.raw_state:02X} ({ds.raw_state})"
                    )
                    for key, value in ds.decoded_state.items():
                        lines.append(f"      {key}: {value}")

            if frame.fir_events:
                lines.append("  故障事件:")
                for event in frame.fir_events:
                    lines.append(f"    - 对象索引: {event['object_index']}")
                    lines.append(f"      故障类型: 0x{event['fault_type_code']:02X} - {event['fault_description']}")

            if frame.rsr_status:
                lines.append("  工作状态:")
                lines.append(f"    主备状态: {frame.rsr_status['role']} (0x{frame.rsr_status['role_status']:02X})")
                lines.append(f"    控制模式: {frame.rsr_status['mode_ilock']}")

            if frame.bcc_command:
                lines.append("  按钮命令:")
                lines.append(f"    命令类型: {frame.bcc_command['command_description']} (0x{frame.bcc_command['command_type']:02X})")
                if frame.bcc_command['button_index1'] >= 0:
                    lines.append(f"    按钮1索引: {frame.bcc_command['button_index1']}")
                if frame.bcc_command['button_index2'] >= 0:
                    lines.append(f"    按钮2索引: {frame.bcc_command['button_index2']}")
                if frame.bcc_command['button_index3'] >= 0:
                    lines.append(f"    按钮3索引: {frame.bcc_command['button_index3']}")

            if frame.tsd_time:
                lines.append("  时间数据:")
                lines.append(f"    时间: {frame.tsd_time['time_string']}")

            if frame.aca_response:
                lines.append("  自律控制响应:")
                lines.append(f"    响应: {frame.aca_response['response_description']} (0x{frame.aca_response['response_flag']:02X})")

        report = "\n".join(lines)

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(report)

        return report


def export_to_json(frames: List[Frame], output_file: str):
    """导出帧数据为JSON格式

    Args:
        frames: Frame列表
        output_file: 输出JSON文件路径
    """
    data = []
    for frame in frames:
        frame_data = {
            "timestamp": frame.timestamp,
            "frame_type": f"0x{frame.frame_type:02X}",
            "frame_type_name": frame.frame_type_name,
            "direction": frame.direction,
            "send_seq": frame.send_seq,
            "ack_seq": frame.ack_seq,
            "data_length": frame.data_length,
            "crc": f"0x{frame.crc:04X}",
            "raw_data": frame.raw_data.hex().upper(),
            "devices": [],
            "fir_events": frame.fir_events,
            "rsr_status": frame.rsr_status,
            "bcc_command": frame.bcc_command,
            "tsd_time": frame.tsd_time,
            "aca_response": frame.aca_response,
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
        解析出的Frame列表
    """
    # 加载码位表
    cpt = CodePositionTable(code_table)

    # 分析日志
    analyzer = CTCLogAnalyzer(log_file, cpt)
    frames = analyzer.analyze_sdci()

    # 生成报告
    report_file = os.path.join(output_dir, "sdci_analysis_report.txt")
    analyzer.generate_report(output_file=report_file)

    # 导出JSON
    json_file = os.path.join(output_dir, "sdci_frames.json")
    export_to_json(frames, json_file)

    return frames


def parse_all_frames(log_file: str, code_table: Optional[str] = None, output_dir: str = "."):
    """解析所有帧类型日志文件（便捷函数）

    Args:
        log_file: CTC日志文件路径
        code_table: 码位表文件路径（可选）
        output_dir: 输出目录

    Returns:
        解析出的Frame列表
    """
    # 加载码位表（如果提供）
    cpt = None
    if code_table:
        cpt = CodePositionTable(code_table)

    # 分析日志
    analyzer = CTCLogAnalyzer(log_file, cpt)
    frames = analyzer.analyze()

    # 生成报告
    report_file = os.path.join(output_dir, "frame_analysis_report.txt")
    analyzer.generate_report(output_file=report_file)

    # 导出JSON
    json_file = os.path.join(output_dir, "all_frames.json")
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
class DeviceTimelineAnalyzer:
    """设备状态变化时间线分析器

    从日志文件中提取指定设备的状态变化时间线。
    支持按设备名称查询（如 "D1", "5", "I" 等）。
    """

    # 日志中帧的标记
    SDCI_MARKER = b"[SDCI ]"
    SDI_MARKER = b"[SDI  ]"

    def __init__(self, log_file: str, code_position_table: CodePositionTable):
        """初始化分析器

        Args:
            log_file: 日志文件路径
            code_position_table: 码位表解析器实例
        """
        self.log_file = log_file
        self.cpt = code_position_table
        self.frame_parser = FrameParser(code_position_table)

    def _extract_timestamp_from_line(self, line: bytes) -> Optional[str]:
        """从日志行中提取时间戳

        Args:
            line: 日志行字节数据

        Returns:
            时间戳字符串，格式 HH:MM:SS
        """
        match = re.search(rb"(\d{2}:\d{2}:\d{2})", line)
        if match:
            return match.group(1).decode("utf-8", errors="ignore")
        return None

    def _extract_hex_data_from_line(self, line: bytes) -> Optional[bytes]:
        """从日志行中提取十六进制帧数据

        Args:
            line: 日志行字节数据

        Returns:
            解析后的帧数据字节
        """
        # 查找帧标记后的十六进制数据
        hex_chars = b""
        for i, byte in enumerate(line):
            # 跳过标记部分，从数据区域开始提取
            if 48 <= byte <= 57:  # 0-9
                hex_chars += bytes([byte])
            elif 65 <= byte <= 70:  # A-F
                hex_chars += bytes([byte])
            elif 97 <= byte <= 102:  # a-f
                hex_chars += bytes([byte])
            elif len(hex_chars) > 0 and byte == 32:  # 空格
                continue
            else:
                if len(hex_chars) >= 20:  # 至少需要一帧的数据
                    break
                hex_chars = b""

        if len(hex_chars) >= 20:
            try:
                return bytes.fromhex(hex_chars.decode("ascii"))
            except:
                pass
        return None

    def _parse_log_frames(self) -> List[Tuple[str, Frame]]:
        """解析日志文件中的所有帧

        Returns:
            (时间戳, Frame对象) 列表
        """
        frames = []

        with open(self.log_file, "rb") as f:
            content = f.read()

        # 查找所有SDCI帧
        pos = 0
        while True:
            # 优先查找SDCI帧
            sdci_pos = content.find(self.SDCI_MARKER, pos)
            sdi_pos = content.find(self.SDI_MARKER, pos)

            # 取最近的帧
            if sdci_pos == -1 and sdi_pos == -1:
                break
            elif sdci_pos == -1:
                current_pos = sdi_pos
            elif sdi_pos == -1:
                current_pos = sdci_pos
            else:
                current_pos = min(sdci_pos, sdi_pos)

            # 提取行
            line_start = content.rfind(b"\n", 0, current_pos)
            line_start = line_start + 1 if line_start != -1 else 0
            line_end = content.find(b"\n", current_pos)
            line_end = line_end if line_end != -1 else len(content)

            line = content[line_start:line_end]

            # 提取时间戳
            timestamp = self._extract_timestamp_from_line(line)
            if not timestamp:
                pos = current_pos + 1
                continue

            # 提取十六进制数据
            hex_data = self._extract_hex_data_from_line(line)
            if not hex_data or len(hex_data) < 12:
                pos = current_pos + 1
                continue

            # 解析帧
            frame = self.frame_parser.parse_frame(hex_data, timestamp)
            if frame:
                frames.append((timestamp, frame))

            pos = current_pos + 1

        return frames

    def analyze_device(self, device_name: str) -> List[Dict[str, Any]]:
        """分析指定设备的状态变化时间线

        Args:
            device_name: 设备名称，支持格式如 "D1", "5", "I" 等

        Returns:
            状态变化列表，每个元素包含:
            - timestamp: 时间戳
            - frame_type: 帧类型 (SDCI/SDI)
            - raw_state: 原始状态值
            - decoded_state: 解码后的状态字典
            - device_name: 设备名称
        """
        # 查找设备信息
        device = self.cpt.get_device_by_name(device_name)
        if not device:
            # 尝试直接用名称搜索
            for name, dev in self.cpt.devices_by_name.items():
                if device_name in name or name in device_name:
                    device = dev
                    break

        if not device:
            return []

        # 解析日志中的所有帧
        frames = self._parse_log_frames()

        # 提取该设备的状态变化
        state_changes = []
        current_state = None

        for timestamp, frame in frames:
            frame_type = frame.frame_type_name

            # 查找当前帧中该设备的状态
            device_state = None

            if frame.device_states:
                for ds in frame.device_states:
                    if ds.device.object_index == device.object_index:
                        device_state = ds
                        break

            if device_state:
                raw_state = device_state.raw_state
                decoded_state = device_state.decoded_state

                # 状态变化记录（首次或状态值改变）
                if current_state is None or current_state != raw_state:
                    state_changes.append({
                        "timestamp": timestamp,
                        "frame_type": frame_type,
                        "raw_state": raw_state,
                        "decoded_state": decoded_state,
                        "device_name": device.name,
                    })
                    current_state = raw_state

        return state_changes

    def get_device_states_at_frames(self, device_name: str) -> List[Dict[str, Any]]:
        """获取设备在每一帧中的状态（不过滤变化）

        Args:
            device_name: 设备名称

        Returns:
            状态列表，包含每一帧的状态
        """
        # 查找设备信息
        device = self.cpt.get_device_by_name(device_name)
        if not device:
            for name, dev in self.cpt.devices_by_name.items():
                if device_name in name or name in device_name:
                    device = dev
                    break

        if not device:
            return []

        # 解析日志中的所有帧
        frames = self._parse_log_frames()

        # 提取该设备的状态
        states = []

        for timestamp, frame in frames:
            frame_type = frame.frame_type_name

            if frame.device_states:
                for ds in frame.device_states:
                    if ds.device.object_index == device.object_index:
                        states.append({
                            "timestamp": timestamp,
                            "frame_type": frame_type,
                            "raw_state": ds.raw_state,
                            "decoded_state": ds.decoded_state,
                            "device_name": device.name,
                        })
                        break

        return states

    def generate_timeline_report(
        self, device_name: str, output_file: str = None
    ) -> str:
        """生成设备时间线报告

        Args:
            device_name: 设备名称
            output_file: 输出文件路径（可选）

        Returns:
            报告文本内容
        """
        # 获取状态变化
        state_changes = self.analyze_device(device_name)

        # 如果没有变化，尝试获取所有状态
        if not state_changes:
            state_changes = self.get_device_states_at_frames(device_name)

        # 生成报告
        lines = []
        lines.append("=" * 80)
        lines.append(f"设备状态变化时间线报告")
        lines.append("=" * 80)
        lines.append(f"设备名称: {device_name}")

        if not state_changes:
            lines.append("未找到设备状态记录!")
            report = "\n".join(lines)
            if output_file:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(report)
            return report

        # 获取设备信息
        device = self.cpt.get_device_by_name(device_name)
        if not device:
            for name, dev in self.cpt.devices_by_name.items():
                if device_name in name or name in device_name:
                    device = dev
                    break

        if device:
            lines.append(f"设备类型: {device.device_type.name}")
            lines.append(f"Object Index: {device.object_index}")
            lines.append(f"Byte Index: {device.byte_index}")
            lines.append(f"Bit Offset: {device.bit_offset}")

        lines.append(f"记录数量: {len(state_changes)}")

        if len(state_changes) > 1:
            lines.append(
                f"时间范围: {state_changes[0]['timestamp']} - {state_changes[-1]['timestamp']}"
            )

        # 计算状态变化次数
        change_count = 0
        if len(state_changes) > 1:
            for i in range(1, len(state_changes)):
                if state_changes[i]["raw_state"] != state_changes[i - 1]["raw_state"]:
                    change_count += 1

        lines.append(f"状态变化次数: {change_count}")
        lines.append("")
        lines.append("-" * 80)
        lines.append("状态变化时间线")
        lines.append("-" * 80)

        # 打印表头
        if device and device.device_type == DeviceType.SWITCH_SECTION:
            lines.append(
                f"{'序号':<6} {'时间':<12} {'帧类型':<8} {'状态值':<10} {'位置':<14} {'区段锁闭':<10} {'区段占用':<10} {'道岔锁闭':<10}"
            )
        elif device and device.device_type == DeviceType.SIGNAL:
            lines.append(
                f"{'序号':<6} {'时间':<12} {'帧类型':<8} {'状态值':<10} {'颜色':<20} {'进路转岔':<10} {'延时解锁':<10}"
            )
        else:
            lines.append(
                f"{'序号':<6} {'时间':<12} {'帧类型':<8} {'状态值':<10} {'状态':<20}"
            )

        lines.append("-" * 80)

        # 打印每条记录
        for i, record in enumerate(state_changes, 1):
            ts = record["timestamp"]
            frame_type = record["frame_type"]
            raw_state = f"0x{record['raw_state']:02X}"
            decoded = record["decoded_state"]

            # 根据设备类型格式化输出
            if device and device.device_type == DeviceType.SWITCH_SECTION:
                position = decoded.get("位置", str(decoded))
                sec_lock = decoded.get("区段锁闭", "")
                sec_occ = decoded.get("区段占用", "")
                sw_lock = decoded.get("道岔锁闭", "")

                # 检查是否是状态变化点
                if i > 1 and record["raw_state"] != state_changes[i - 2]["raw_state"]:
                    lines.append("[状态变化]")
                elif i > 1:
                    lines.append("")

                lines.append(
                    f"{i:<6} {ts:<12} {frame_type:<8} {raw_state:<10} {position:<14} {sec_lock:<10} {sec_occ:<10} {sw_lock:<10}"
                )

            elif device and device.device_type == DeviceType.SIGNAL:
                color = decoded.get("颜色", str(decoded))
                route = decoded.get("进路转岔", "")
                delay = decoded.get("延时解锁", "")

                if i > 1 and record["raw_state"] != state_changes[i - 2]["raw_state"]:
                    lines.append("[状态变化]")
                elif i > 1:
                    lines.append("")

                lines.append(
                    f"{i:<6} {ts:<12} {frame_type:<8} {raw_state:<10} {color:<20} {route:<10} {delay:<10}"
                )

            else:
                state_str = str(decoded)

                if i > 1 and record["raw_state"] != state_changes[i - 2]["raw_state"]:
                    lines.append("[状态变化]")
                elif i > 1:
                    lines.append("")

                lines.append(f"{i:<6} {ts:<12} {frame_type:<8} {raw_state:<10} {state_str:<20}")

        lines.append("")
        lines.append("=" * 80)

        # 统计信息
        lines.append("统计汇总")
        lines.append("=" * 80)

        # 状态分布统计
        state_counts: Dict[str, int] = defaultdict(int)
        for record in state_changes:
            state_key = f"0x{record['raw_state']:02X}"
            state_counts[state_key] += 1

        lines.append("状态分布:")
        for state, count in sorted(state_counts.items(), key=lambda x: x[1], reverse=True):
            pct = count / len(state_changes) * 100
            lines.append(f"  {state}: {count:3d} 次 ({pct:5.1f}%)")

        report = "\n".join(lines)

        # 输出到文件
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(report)

        return report

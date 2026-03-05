#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设备类型定义模块

定义设备类型枚举和设备信息数据结构。
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, Optional


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
    decoded_state: Dict[str, any] = None

    def __post_init__(self):
        if self.decoded_state is None:
            self.decoded_state = {}

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
    device_states: list = None

    def __post_init__(self):
        if self.device_states is None:
            self.device_states = []

    def get_device_count(self) -> int:
        """获取变化的设备数量"""
        return len(self.device_states)

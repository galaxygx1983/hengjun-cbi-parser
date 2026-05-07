#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SDCI帧解析器模块

帧格式：
- 帧头：1字节 (0x7D)
- 首部长：1字节 (0x04)
- 版本号：1字节 (0x11)
- 发送序号：1字节
- 确认序号：1字节
- 帧类型：1字节 (0x8A为SDCI帧)
- 数据长度：2字节 (小端序)
- 站场表示数据：N字节 (每设备3字节：2字节设备索引(大端序)+1字节状态)
- CRC校验：2字节 (小端序，CRC-CCITT XModem)
- 帧尾：1字节 (0x7E)
"""

from dataclasses import dataclass
from typing import List, Optional

from .device_types import DeviceInfo, DeviceState, SDCIFrame, DeviceType
from .code_position_table import CodePositionTable
from .state_decoder import StateDecoder
from .frame_utils import FrameUtils


@dataclass
class FIRFrame:
    """FIR帧结构（故障信息报告）

    与CTC源码 HandleFIRFrame 一致：
    - object_index: 2字节小端序对象索引
    - error_code: 2字节小端序错误代码
    - error_text: 可变长度错误描述文本
    """
    timestamp: str
    send_seq: int
    ack_seq: int
    object_index: int  # 小端序
    error_code: int    # 小端序
    error_text: str    # 错误描述文本
    raw_data: bytes
    crc: int
    crc_valid: bool = True

    def __str__(self) -> str:
        return (f"FIR: object_index={self.object_index}, "
                f"error_code=0x{self.error_code:04X}, "
                f"text='{self.error_text}'")


@dataclass
class RSRFrame:
    """RSR帧结构（系统工作状态报告）

    与CTC源码 HandleRSRFrame 一致：
    - system_status: 系统主备状态（0x55=主机, 0xAA=备机）
    - dispatch_authority: 调度权限状态
    """
    timestamp: str
    send_seq: int
    ack_seq: int
    system_status: int     # 0x55=主机, 0xAA=备机
    dispatch_authority: int
    raw_data: bytes
    crc: int
    crc_valid: bool = True

    def get_system_status_desc(self) -> str:
        return "主机" if self.system_status == 0x55 else "备机" if self.system_status == 0xAA else f"未知(0x{self.system_status:02X})"

    def __str__(self) -> str:
        return (f"RSR: system={self.get_system_status_desc()}, "
                f"dispatch_authority=0x{self.dispatch_authority:02X}")


def _is_control_frame(frame_type: int) -> bool:
    """判断是否为控制帧（帧类型值0x01-0x1F）

    与CTC源码 protocol_types.h IsControlFrame 一致：
    控制帧包括 DC2(0x12), DC3(0x13), ACK(0x06), NACK(0x15), VERROR(0x10)
    """
    return 0x01 <= frame_type <= 0x1F


class SDCIFrameParser:
    """SDCI帧解析器"""

    # 帧常量
    FRAME_HEADER = 0x7D
    FRAME_TAIL = 0x7E
    FRAME_TYPE_SDCI = 0x8A  # SDCI帧（变化设备列表）
    FRAME_TYPE_SDI = 0x85  # SDI帧（完整站场状态）
    FRAME_TYPE_FIR = 0x65   # FIR帧（故障信息报告）
    FRAME_TYPE_RSR = 0xAA   # RSR帧（系统工作状态报告）
    FRAME_TYPE_CONTROL = 0x06

    def __init__(self, code_position_table: CodePositionTable):
        self.cpt = code_position_table

    def parse_frame(
        self, raw_data: bytes, timestamp: Optional[str] = None
    ) -> Optional[SDCIFrame]:
        """解析SDCI帧

        处理流程与CTC源码 core_ci_driver.cpp 一致：
        1. 检查帧头帧尾和基本字段
        2. 反转义整个帧体（不含帧头帧尾）
        3. 从反转义后的数据中提取CRC、数据长度、载荷

        Args:
            raw_data: 帧的原始字节数据（可能包含转义序列）
            timestamp: 可选的时间戳字符串

        Returns:
            解析成功的SDCIFrame对象，失败返回None
        """
        if len(raw_data) < 9:
            return None

        # 检查帧头和帧尾
        if raw_data[0] != self.FRAME_HEADER or raw_data[-1] != self.FRAME_TAIL:
            return None

        # 检查首部长和版本号（这些字段不会被转义，因为值是0x04和0x11）
        if raw_data[1] != FrameUtils.HEADER_LENGTH or raw_data[2] != FrameUtils.VERSION:
            return None

        # 检查帧类型（帧类型字段也不会被转义，常见值0x8A/0x85等都不是0x7D/0x7E/0x7F）
        frame_type = raw_data[5]
        is_sdi = frame_type == self.FRAME_TYPE_SDI
        is_sdci = frame_type == self.FRAME_TYPE_SDCI
        if not (is_sdi or is_sdci):
            return None  # 不支持的帧类型

        # 解析序号（这些单字节字段不在转义范围内）
        send_seq = raw_data[3]
        ack_seq = raw_data[4]

        # ===== 关键修正：先反转义帧体，再提取CRC和数据长度 =====
        # 与CTC源码一致：ProcessSinglePacketUnescape → CRC校验 → 解析字段
        # 反转义帧体（去掉帧头0x7D和帧尾0x7E，只反转义中间部分）
        frame_body = raw_data[1:-1]
        unescaped_body = FrameUtils.unescape_data(frame_body)

        # 从反转义后的数据中提取CRC（最后2字节，小端序）
        # CRC覆盖范围：从首部长度字节到CRC之前
        crc = unescaped_body[-2] | (unescaped_body[-1] << 8)

        # CRC校验：从unescaped_body开头到CRC之前
        crc_data = unescaped_body[:-2]
        calculated_crc = FrameUtils.calculate_crc(bytes(crc_data))
        crc_valid = (crc == calculated_crc)

        # 从反转义后的数据中提取数据长度（小端序）
        # 数据长度在帧体中的偏移为5（对应原始帧的offset 6-7）
        # 帧体结构：首部长(1) + 版本(1) + 发送序号(1) + 确认序号(1) + 帧类型(1) + 数据长度(2) + 数据(N) + CRC(2)
        data_length = unescaped_body[5] | (unescaped_body[6] << 8)

        # 提取数据载荷（从帧体偏移7开始，到CRC之前结束）
        payload_start = 7
        payload_end = len(unescaped_body) - 2  # 减去CRC的2字节
        payload = bytes(unescaped_body[payload_start:payload_end])

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
            crc_valid=crc_valid,
            frame_type=frame_type,
        )

    def _parse_sdci_payload(self, payload: bytes) -> List[DeviceState]:
        """解析SDCI帧数据载荷

        SDCI帧每3字节表示一个变化设备：
        - 前2字节：设备序号（objects表索引，大端序）
        - 第3字节：设备状态（无岔区段使用bit_offset判断高/低4位）
        """
        device_states = []

        for i in range(0, len(payload), 3):
            # 修复：确保剩余字节数至少为 3，避免不完整条目
            if len(payload) - i < 3:
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

    def parse_fir_frame(
        self, raw_data: bytes, timestamp: Optional[str] = None
    ) -> Optional[FIRFrame]:
        """解析FIR帧（故障信息报告）

        与CTC源码 HandleFIRFrame 一致：
        - 反转义帧体
        - CRC校验
        - 提取载荷：对象索引（2字节小端序）+ 错误代码（2字节小端序）+ 错误文本

        Args:
            raw_data: 帧的原始字节数据
            timestamp: 可选的时间戳字符串

        Returns:
            解析成功的FIRFrame对象，失败返回None
        """
        if len(raw_data) < 9:
            return None

        if raw_data[0] != self.FRAME_HEADER or raw_data[-1] != self.FRAME_TAIL:
            return None

        # 检查帧类型
        frame_type = raw_data[5]
        if frame_type != self.FRAME_TYPE_FIR:
            return None

        # 反转义帧体
        frame_body = raw_data[1:-1]
        unescaped_body = FrameUtils.unescape_data(frame_body)

        if len(unescaped_body) < 9:
            return None

        # CRC校验
        crc = unescaped_body[-2] | (unescaped_body[-1] << 8)
        crc_data = unescaped_body[:-2]
        calculated_crc = FrameUtils.calculate_crc(bytes(crc_data))
        crc_valid = (crc == calculated_crc)

        # 提取序号
        send_seq = unescaped_body[2]
        ack_seq = unescaped_body[3]

        # 数据长度（小端序）
        data_length = unescaped_body[5] | (unescaped_body[6] << 8)

        # 提取载荷
        payload_start = 7
        payload_end = len(unescaped_body) - 2
        payload = bytes(unescaped_body[payload_start:payload_end])

        # 解析FIR载荷：对象索引（小端序）+ 错误代码（小端序）+ 文本
        if len(payload) < 4:
            return None

        # 对象索引：小端序（与CTC源码 HandleFIRFrame 一致）
        # 注意：FIR帧的对象索引是小端序，与SDCI帧的大端序不同
        object_index = payload[0] | (payload[1] << 8)
        # 错误代码：小端序
        error_code = payload[2] | (payload[3] << 8)
        # 错误文本（剩余字节）
        error_text = payload[4:].decode("gbk", errors="replace").rstrip("\x00")

        return FIRFrame(
            timestamp=timestamp or "",
            send_seq=send_seq,
            ack_seq=ack_seq,
            object_index=object_index,
            error_code=error_code,
            error_text=error_text,
            raw_data=raw_data,
            crc=crc,
            crc_valid=crc_valid,
        )

    def parse_rsr_frame(
        self, raw_data: bytes, timestamp: Optional[str] = None
    ) -> Optional[RSRFrame]:
        """解析RSR帧（系统工作状态报告）

        与CTC源码 HandleRSRFrame 一致：
        - 反转义帧体
        - CRC校验
        - 提取载荷：第1字节为系统主备状态（0x55=主机, 0xAA=备机）
          第2字节为调度权限状态

        Args:
            raw_data: 帧的原始字节数据
            timestamp: 可选的时间戳字符串

        Returns:
            解析成功的RSRFrame对象，失败返回None
        """
        if len(raw_data) < 9:
            return None

        if raw_data[0] != self.FRAME_HEADER or raw_data[-1] != self.FRAME_TAIL:
            return None

        # 检查帧类型
        frame_type = raw_data[5]
        if frame_type != self.FRAME_TYPE_RSR:
            return None

        # 反转义帧体
        frame_body = raw_data[1:-1]
        unescaped_body = FrameUtils.unescape_data(frame_body)

        if len(unescaped_body) < 9:
            return None

        # CRC校验
        crc = unescaped_body[-2] | (unescaped_body[-1] << 8)
        crc_data = unescaped_body[:-2]
        calculated_crc = FrameUtils.calculate_crc(bytes(crc_data))
        crc_valid = (crc == calculated_crc)

        # 提取序号
        send_seq = unescaped_body[2]
        ack_seq = unescaped_body[3]

        # 数据长度（小端序）
        data_length = unescaped_body[5] | (unescaped_body[6] << 8)

        # 提取载荷
        payload_start = 7
        payload_end = len(unescaped_body) - 2
        payload = bytes(unescaped_body[payload_start:payload_end])

        # 解析RSR载荷
        system_status = payload[0] if len(payload) > 0 else 0
        dispatch_authority = payload[1] if len(payload) > 1 else 0

        return RSRFrame(
            timestamp=timestamp or "",
            send_seq=send_seq,
            ack_seq=ack_seq,
            system_status=system_status,
            dispatch_authority=dispatch_authority,
            raw_data=raw_data,
            crc=crc,
            crc_valid=crc_valid,
        )

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
- 数据长度：2字节 (大端序)
- 站场表示数据：N字节 (每设备3字节：2字节序号+1字节状态)
- CRC校验：2字节
- 帧尾：1字节 (0x7E)
"""

from typing import List, Optional

from .device_types import DeviceInfo, DeviceState, SDCIFrame, DeviceType
from .code_position_table import CodePositionTable
from .state_decoder import StateDecoder
from .frame_utils import FrameUtils


class SDCIFrameParser:
    """SDCI帧解析器"""

    # 帧常量
    FRAME_HEADER = 0x7D
    FRAME_TAIL = 0x7E
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
        if raw_data[1] != FrameUtils.HEADER_LENGTH or raw_data[2] != FrameUtils.VERSION:
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

        # 解析数据长度（小端序）
        data_length = raw_data[6] | (raw_data[7] << 8)

        # 提取CRC（最后3字节：2字节CRC + 1字节帧尾）
        crc = (raw_data[-3] << 8) | raw_data[-2]

        # 提取数据载荷（跳过8字节首部，到CRC之前）
        payload_start = 8
        payload_end = len(raw_data) - 3
        payload = raw_data[payload_start:payload_end]

        # 数据反转义（接收时需要反转义）
        # 注意：反转义会影响数据长度，需要记录原始长度用于校验
        original_payload_length = len(payload)
        unescaped_payload = FrameUtils.unescape_data(payload)

        # 如果发生了反转义，更新数据长度
        if len(unescaped_payload) != original_payload_length:
            # 数据长度字段需要反映反转义后的长度
            data_length = len(unescaped_payload)
            payload = unescaped_payload

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

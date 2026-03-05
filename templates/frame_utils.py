#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
帧处理工具模块 - 数据转义、CRC计算等

提供帧数据的转义/反转义功能，以及CRC16校验计算。
"""

from typing import Optional


class FrameUtils:
    """帧处理工具类"""

    # 帧常量
    FRAME_HEADER = 0x7D
    FRAME_TAIL = 0x7E
    ESCAPE_CHAR = 0x7F
    HEADER_LENGTH = 0x04
    VERSION = 0x11

    # 转义映射表
    ESCAPE_MAP = {
        0x7D: b"\x7F\xFD",  # 帧头标记转义
        0x7E: b"\x7F\xFE",  # 帧尾标记转义
        0x7F: b"\x7F\xFF",  # 转义字符转义
    }
    # 反转义映射表
    UNESCAPE_MAP = {
        0xFD: 0x7D,
        0xFE: 0x7E,
        0xFF: 0x7F,
    }

    @staticmethod
    def escape_data(data: bytes) -> bytes:
        """数据转义 - 发送时使用

        将特殊字节转换为转义序列：
        - 0x7D → 0x7F 0xFD
        - 0x7E → 0x7F 0xFE
        - 0x7F → 0x7F 0xFF

        Args:
            data: 原始数据（不含帧头、帧尾、CRC）

        Returns:
            转义后的数据
        """
        result = bytearray()
        for byte in data:
            if byte in FrameUtils.ESCAPE_MAP:
                result.extend(FrameUtils.ESCAPE_MAP[byte])
            else:
                result.append(byte)
        return bytes(result)

    @staticmethod
    def unescape_data(data: bytes) -> bytes:
        """数据反转义 - 接收时使用

        将转义序列还原为原始字节：
        - 0x7F 0xFD → 0x7D
        - 0x7F 0xFE → 0x7E
        - 0x7F 0xFF → 0x7F

        Args:
            data: 包含转义序列的数据

        Returns:
            反转义后的原始数据
        """
        result = bytearray()
        i = 0
        while i < len(data):
            if data[i] == FrameUtils.ESCAPE_CHAR and i + 1 < len(data):
                # 检测到转义字符，查找映射
                escape_second = data[i + 1]
                if escape_second in FrameUtils.UNESCAPE_MAP:
                    result.append(FrameUtils.UNESCAPE_MAP[escape_second])
                    i += 2
                    continue
            # 非转义序列，直接添加
            result.append(data[i])
            i += 1
        return bytes(result)

    @staticmethod
    def calculate_crc(data: bytes) -> int:
        """计算CRC16校验和（Modbus CRC16）

        Args:
            data: 待校验的数据

        Returns:
            16位CRC值
        """
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

    @staticmethod
    def build_frame(
        frame_type: int,
        send_seq: int,
        ack_seq: int,
        payload: bytes,
    ) -> bytes:
        """构建发送帧（自动进行数据转义）

        Args:
            frame_type: 帧类型（如0x8A为SDCI，0x85为SDI）
            send_seq: 发送序号
            ack_seq: 确认序号
            payload: 站场数据载荷

        Returns:
            完整的帧字节数据（已转义）
        """
        # 构建帧头部分（不含转义）
        header = bytes([
            FrameUtils.FRAME_HEADER,  # 帧头 0x7D
            FrameUtils.HEADER_LENGTH,   # 首部长 0x04
            FrameUtils.VERSION,         # 版本号 0x11
            send_seq,                       # 发送序号
            ack_seq,                        # 确认序号
            frame_type,                     # 帧类型
        ])

        # 数据长度（小端序）
        data_length = len(payload)
        data_length_bytes = bytes([data_length & 0xFF, (data_length >> 8) & 0xFF])

        # 对载荷进行转义
        escaped_payload = FrameUtils.escape_data(payload)

        # 构建待CRC计算的数据（不含帧头和帧尾）
        # 格式：首部长(1) + 版本号(1) + 发送序号(1) + 确认序号(1) + 帧类型(1) + 数据长度(2) + 载荷(已转义)
        crc_data = header[1:] + data_length_bytes + escaped_payload

        # 计算CRC16
        crc = FrameUtils.calculate_crc(crc_data)
        crc_bytes = bytes([(crc >> 8) & 0xFF, crc & 0xFF])

        # 构建完整帧（不含转义）
        # 帧头 + 首部长 + 版本号 + 序号 + 帧类型 + 数据长度 + 载荷 + CRC + 帧尾
        unescaped_frame = (
            bytes([FrameUtils.FRAME_HEADER]) +
            header[1:] +
            data_length_bytes +
            escaped_payload +
            crc_bytes +
            bytes([FrameUtils.FRAME_TAIL])
        )

        # 对帧头和帧尾之间的数据进行转义
        # 注意：帧头和帧尾不转义，只转义中间的数据部分
        frame_body = unescaped_frame[1:-1]  # 去掉帧头和帧尾
        escaped_body = FrameUtils.escape_data(frame_body)

        # 重新组装帧
        return bytes([FrameUtils.FRAME_HEADER]) + escaped_body + bytes([FrameUtils.FRAME_TAIL])


# 便捷函数
escape_data = FrameUtils.escape_data
unescape_data = FrameUtils.unescape_data
calculate_crc = FrameUtils.calculate_crc
build_frame = FrameUtils.build_frame

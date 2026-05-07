#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设备状态解码器模块

根据设备类型解码状态字节：
- 道岔区段（纯数字名称）：0-2位道岔位置，3位区段锁闭，4位区段占用，5位道岔锁闭
- 信号机（D开头）：0-5位灯色，6位进路转岔，7位延时解锁
- 无岔区段：0/4位区段锁闭，1/5位区段占用（高/低4位共享字节）
"""

from typing import Dict, Any


class StateDecoder:
    """设备状态解码器"""

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
            # 其他非标准组合忽略，只保留单 bit 颜色
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

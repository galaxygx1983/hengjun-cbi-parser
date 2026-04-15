#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁路计算机联锁 (CBI) 与调度集中 (CTC) 通信日志协议规范检查工具
检查日志文件是否符合协议规范要求 - 专注于序号和通信流程

序号规则（与CTC源码 ci_sequencemanager.cpp 一致）：
- 控制帧（DC2/DC3/ACK/NACK/VERROR，帧类型0x01-0x1F）不验证发送序号
- 数据帧（SDCI/SDI/FIR等，帧类型0x20-0xFF）才验证发送序号连续性
- 序号跳变（差值>=2）触发连接重置
- 序号重复（差值=0）视为重传帧
- 序号范围0x00-0xFF，0xFF后回绕到0x00
"""

import re
from datetime import datetime
from collections import defaultdict

# 帧类型定义
FRAME_TYPES = {
    0x12: ("DC2", "连接请求", "CTC→联锁", "control"),
    0x13: ("DC3", "连接确认", "联锁→CTC", "control"),
    0x06: ("ACK", "应答/心跳", "双向", "control"),
    0x15: ("NACK", "否定应答", "双向", "control"),
    0x10: ("VERROR", "版本错误", "双向", "control"),
    0x8A: ("SDCI", "站场数据变化 (增量)", "联锁→CTC", "data"),
    0x85: ("SDI", "站场完整数据 (全量)", "联锁→CTC", "data"),
    0x6A: ("SDIQ", "站场数据请求", "CTC→联锁", "data"),
    0x65: ("FIR", "故障信息报告", "联锁→CTC", "data"),
    0xAA: ("RSR", "系统工作状态报告", "双向", "data"),
    0x95: ("BCC", "按钮控制命令", "CTC→联锁", "data"),
    0x75: ("ACQ", "自律控制请求", "联锁→CTC", "data"),
    0x7A: ("ACA", "自律控制同意", "CTC→联锁", "data"),
    0x9A: ("TSQ", "时间同步请求", "联锁→CTC", "data"),
    0xA5: ("TSD", "时间同步数据", "CTC→联锁", "data"),
}

# 协议常量
FRAME_HEADER = 0x7D
FRAME_TAIL = 0x7E
HEADER_LENGTH = 0x04
VERSION = 0x11
ESCAPE_CHAR = 0x7F
ACK_TIMEOUT_MS = 500  # ACK 超时阈值 (ms)

# 反转义映射表（与CTC源码 ci_unescape.cpp 一致）
UNESCAPE_MAP = {
    0xFD: 0x7D,
    0xFE: 0x7E,
    0xFF: 0x7F,
}

# CRC-CCITT XModem 查找表（与CTC源码 ci_crccheck.cpp 一致）
_CRC_CCITT_TABLE = [
    0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
    0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
    0x1231, 0x0210, 0x3273, 0x2252, 0x52B5, 0x4294, 0x72F7, 0x62D6,
    0x9339, 0x8318, 0xB37B, 0xA35A, 0xD3BD, 0xC39C, 0xF3FF, 0xE3DE,
    0x2462, 0x3443, 0x0420, 0x1401, 0x64E6, 0x74C7, 0x44A4, 0x5485,
    0xA56A, 0xB54B, 0x8528, 0x9509, 0xE5EE, 0xF5CF, 0xC5AC, 0xD58D,
    0x3653, 0x2672, 0x1611, 0x0630, 0x76D7, 0x66F6, 0x5695, 0x46B4,
    0xB75B, 0xA77A, 0x9719, 0x8738, 0xF7DF, 0xE7FE, 0xD79D, 0xC7BC,
    0x48C4, 0x58E5, 0x6886, 0x78A7, 0x0840, 0x1861, 0x2802, 0x3823,
    0xC9CC, 0xD9ED, 0xE98E, 0xF9AF, 0x8948, 0x9969, 0xA90A, 0xB92B,
    0x5AF5, 0x4AD4, 0x7AB7, 0x6A96, 0x1A71, 0x0A50, 0x3A33, 0x2A12,
    0xDBFD, 0xCBDC, 0xFBBF, 0xEB9E, 0x9B79, 0x8B58, 0xBB3B, 0xAB1A,
    0x6CA6, 0x7C87, 0x4CE4, 0x5CC5, 0x2C22, 0x3C03, 0x0C60, 0x1C41,
    0xEDAE, 0xFD8F, 0xCDEC, 0xDDCD, 0xAD2A, 0xBD0B, 0x8D68, 0x9D49,
    0x7E97, 0x6EB6, 0x5ED5, 0x4EF4, 0x3E13, 0x2E32, 0x1E51, 0x0E70,
    0xFF9F, 0xEFBE, 0xDFDD, 0xCFFC, 0xBF1B, 0xAF3A, 0x9F59, 0x8F78,
    0x9188, 0x81A9, 0xB1CA, 0xA1EB, 0xD10C, 0xC12D, 0xF14E, 0xE16F,
    0x1080, 0x00A1, 0x30C2, 0x20E3, 0x5004, 0x4025, 0x7046, 0x6067,
    0x83B9, 0x9398, 0xA3FB, 0xB3DA, 0xC33D, 0xD31C, 0xE37F, 0xF35E,
    0x02B1, 0x1290, 0x22F3, 0x32D2, 0x4235, 0x5214, 0x6277, 0x7256,
    0xB5EA, 0xA5CB, 0x95A8, 0x8589, 0xF56E, 0xE54F, 0xD52C, 0xC50D,
    0x34E2, 0x24C3, 0x14A0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
    0xA7DB, 0xB7FA, 0x8799, 0x97B8, 0xE75F, 0xF77E, 0xC71D, 0xD73C,
    0x26D3, 0x36F2, 0x0691, 0x16B0, 0x6657, 0x7676, 0x4615, 0x5634,
    0xD94C, 0xC96D, 0xF90E, 0xE92F, 0x99C8, 0x89E9, 0xB98A, 0xA9AB,
    0x5844, 0x4865, 0x7806, 0x6827, 0x18C0, 0x08E1, 0x3882, 0x28A3,
    0xCB7D, 0xDB5C, 0xEB3F, 0xFB1E, 0x8BF9, 0x9BD8, 0xABBB, 0xBB9A,
    0x4A75, 0x5A54, 0x6A37, 0x7A16, 0x0AF1, 0x1AD0, 0x2AB3, 0x3A92,
    0xFD2E, 0xED0F, 0xDD6C, 0xCD4D, 0xBDAA, 0xAD8B, 0x9DE8, 0x8DC9,
    0x7C26, 0x6C07, 0x5C64, 0x4C45, 0x3CA2, 0x2C83, 0x1CE0, 0x0CC1,
    0xEF1F, 0xFF3E, 0xCF5D, 0xDF7C, 0xAF9B, 0xBFBA, 0x8FD9, 0x9FF8,
    0x6E17, 0x7E36, 0x4E55, 0x5E74, 0x2E93, 0x3EB2, 0x0ED1, 0x1EF0,
]


def unescape_frame_body(data):
    """反转义帧体数据（与CTC源码 ci_unescape.cpp 一致）"""
    result = bytearray()
    i = 0
    while i < len(data):
        if data[i] == ESCAPE_CHAR and i + 1 < len(data):
            second = data[i + 1]
            if second in UNESCAPE_MAP:
                result.append(UNESCAPE_MAP[second])
                i += 2
                continue
        result.append(data[i])
        i += 1
    return bytes(result)


def calculate_crc(data):
    """计算CRC16校验和（CRC-CCITT XModem，与CTC源码 ci_crccheck.cpp 一致）"""
    crc = 0x0000
    for byte in data:
        crc = ((crc << 8) ^ _CRC_CCITT_TABLE[(crc >> 8) ^ byte]) & 0xFFFF
    return crc


def parse_timestamp(ts_str):
    """解析时间戳字符串"""
    try:
        return datetime.strptime(ts_str, "%H:%M:%S.%f")
    except ValueError:
        return None


def is_control_frame(frame_type):
    """判断是否为控制帧（帧类型值0x01-0x1F）

    与CTC源码 protocol_types.h 一致：
    控制帧包括 DC2(0x12), DC3(0x13), ACK(0x06), NACK(0x15), VERROR(0x10)
    """
    return 0x01 <= frame_type <= 0x1F


def calculate_seq_diff(newer, older):
    """计算循环序号差值（与CTC源码 ci_sequencemanager.cpp 一致）

    处理0xFF→0x00的回绕情况
    """
    if newer >= older:
        return newer - older
    else:
        return newer + 256 - older


def parse_frame(hex_str):
    """解析单个帧数据 - 含反转义和CRC校验

    处理流程与CTC源码一致：
    1. 检查帧头帧尾
    2. 反转义帧体
    3. 从反转义后的数据中提取字段
    4. CRC校验
    """
    try:
        hex_clean = hex_str.strip()
        raw = bytes.fromhex(hex_clean.replace(" ", ""))
    except ValueError as e:
        return None, "无效的十六进制格式"

    if len(raw) < 9:
        return None, "帧长度过短"

    # 检查帧头帧尾
    if raw[0] != FRAME_HEADER:
        return None, f"帧头错误：期望 0x7D, 实际 0x{raw[0]:02X}"
    if raw[-1] != FRAME_TAIL:
        return None, f"帧尾错误：期望 0x7E, 实际 0x{raw[-1]:02X}"

    # 反转义帧体（去掉帧头0x7D和帧尾0x7E，只反转义中间部分）
    # 与CTC源码一致：ProcessSinglePacketUnescape → CRC校验 → 解析字段
    frame_body = raw[1:-1]
    unescaped = unescape_frame_body(frame_body)

    # 从反转义后的数据中提取字段
    header_len = unescaped[0]
    version = unescaped[1]
    send_seq = unescaped[2]
    ack_seq = unescaped[3]
    frame_type = unescaped[4]

    # 检查帧头长度和版本号
    errors = []
    if header_len != HEADER_LENGTH:
        errors.append(f"帧头长度错误：期望 0x04, 实际 0x{header_len:02X}")
    if version != VERSION:
        errors.append(f"版本号错误：期望 0x11, 实际 0x{version:02X}")

    # CRC校验（从反转义后的数据中提取）
    # CRC覆盖范围：从首部长度字节到CRC之前（小端序）
    crc = unescaped[-2] | (unescaped[-1] << 8)
    crc_data = unescaped[:-2]
    calculated_crc = calculate_crc(bytes(crc_data))
    crc_valid = (crc == calculated_crc)
    if not crc_valid:
        errors.append(f"CRC校验失败：计算值 0x{calculated_crc:04X}, 帧中值 0x{crc:04X}")

    # 提取数据长度（仅数据帧包含，小端序）
    data_length = 0
    payload = b""
    if not is_control_frame(frame_type) and len(unescaped) > 7:
        data_length = unescaped[5] | (unescaped[6] << 8)
        payload = bytes(unescaped[7:len(unescaped) - 2])

    # 获取帧类型信息
    frame_type_info = FRAME_TYPES.get(frame_type, (f"UNKNOWN(0x{frame_type:02X})", "未知", "未知", "data"))
    is_ctrl = is_control_frame(frame_type)

    return {
        "send_seq": send_seq,
        "ack_seq": ack_seq,
        "frame_type": frame_type,
        "frame_type_name": frame_type_info[0],
        "frame_type_desc": frame_type_info[1],
        "direction": frame_type_info[2],
        "frame_category": "control" if is_ctrl else "data",
        "data_length": data_length,
        "payload": payload,
        "crc": crc,
        "crc_valid": crc_valid,
        "raw": raw,
        "errors": errors
    }, None


def analyze_log(log_file):
    """分析日志文件 - 检查序号和通信流程

    序号检查逻辑与CTC源码 ci_sequencemanager.cpp 一致：
    - 控制帧不验证发送序号
    - 数据帧发送序号与recv_index差值为1时正常接收
    - 差值为0时为重复帧（重传）
    - 差值>=2时为序号跳变，触发连接重置
    - recvIndex字段用于确认对方收到己方最后一个数据帧
    """
    # 正则表达式匹配日志行
    line_pattern = re.compile(
        r"^(\d{2}:\d{2}:\d{2}\.\d{3})\s+(<<|>>)\[(\w{2,5})\s*\](.+)$"
    )

    frames = []
    frame_type_counts = defaultdict(int)
    direction_counts = defaultdict(int)
    errors = []
    ack_response_times = []

    # 序号追踪（与CTC源码 ci_sequencemanager 一致）
    ctc_to_cbi_send_seq = None  # CTC→联锁 期望的下一个发送序号
    ctc_to_cbi_recv_seq = None  # CTC→联锁 期望对方确认的序号
    cbi_to_ctc_send_seq = None  # 联锁→CTC 期望的下一个发送序号
    cbi_to_ctc_recv_seq = None  # 联锁→CTC 期望对方确认的序号

    # 配对追踪
    dc2_dc3_pairs = 0
    sdciq_sdi_pairs = 0
    dc2_pending = False

    # 通信中断检测 (超过 5 分钟视为中断，重置序号)
    COMM_TIMEOUT_MS = 300000  # 5 分钟
    last_comm_time = None
    comm_interrupted = False

    # 序号错误统计
    seq_errors = []
    pair_errors = []
    crc_errors = 0

    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        prev_time = None

        for line_num, line in enumerate(f, 1):
            line = line.strip()
            match = line_pattern.match(line)
            if not match:
                continue

            timestamp = match.group(1)
            direction = match.group(2)
            frame_type_label = match.group(3).strip()
            hex_data = match.group(4).strip()

            # 解析帧
            frame, error = parse_frame(hex_data)
            if error:
                errors.append(f"行{line_num}: {error}")
                continue

            if frame["errors"]:
                for e in frame["errors"]:
                    if "CRC" in e:
                        crc_errors += 1
                    errors.append(f"行{line_num}: {e}")

            # 解析时间戳
            ts = parse_timestamp(timestamp)

            # 统计帧类型
            frame_type_counts[frame["frame_type_name"]] += 1
            direction_counts[direction] += 1

            ft = frame["frame_type_name"]
            is_ctrl = frame["frame_category"] == "control"

            # DC2/DC3 握手后重置序号（与CTC源码 ResetOnDC2/InitOnDC3 一致）
            if ft == "DC2" and direction == "<<":
                dc2_pending = True
                ctc_to_cbi_send_seq = 0  # ResetOnDC2: 两个序号都重置为0
                ctc_to_cbi_recv_seq = 0
            elif ft == "DC3" and direction == ">>":
                if dc2_pending:
                    dc2_pending = False
                    dc2_dc3_pairs += 1
                cbi_to_ctc_send_seq = 0  # InitOnDC3: 两个序号都重置为0
                cbi_to_ctc_recv_seq = 0

            # 序号检查（与CTC源码 ProcessFrameSequence 一致）
            if direction == "<<" and ctc_to_cbi_send_seq is not None:
                # CTC→联锁方向
                if is_ctrl:
                    # 控制帧不验证发送序号（CTC源码直接返回ACK）
                    pass
                else:
                    # 数据帧：检查发送序号连续性
                    seq_diff = calculate_seq_diff(frame["send_seq"], ctc_to_cbi_send_seq)
                    if seq_diff == 1:
                        # 正常：序号递增1
                        ctc_to_cbi_send_seq = frame["send_seq"]
                    elif seq_diff == 0:
                        # 重复帧（重传），序号不递增
                        pass
                    elif seq_diff >= 2:
                        # 序号跳变，触发连接重置
                        seq_errors.append(
                            f"行{line_num}: {ft} 序号跳变，期望 0x{ctc_to_cbi_send_seq:02X}+1, "
                            f"实际 0x{frame['send_seq']:02X}（差值{seq_diff}），应触发DC2重连"
                        )

                # ack_seq字段：确认对方收到己方最后一个数据帧
                # （CTC源码：frameRecvIndex == send_index_ 时 last_send_acknowledged_ = true）

            elif direction == ">>" and cbi_to_ctc_send_seq is not None:
                # 联锁→CTC方向
                if is_ctrl:
                    # 控制帧不验证发送序号
                    pass
                else:
                    # 数据帧：检查发送序号连续性
                    seq_diff = calculate_seq_diff(frame["send_seq"], cbi_to_ctc_send_seq)
                    if seq_diff == 1:
                        cbi_to_ctc_send_seq = frame["send_seq"]
                    elif seq_diff == 0:
                        pass  # 重复帧
                    elif seq_diff >= 2:
                        seq_errors.append(
                            f"行{line_num}: {ft} 序号跳变，期望 0x{cbi_to_ctc_send_seq:02X}+1, "
                            f"实际 0x{frame['send_seq']:02X}（差值{seq_diff}），应触发DC2重连"
                        )

            # 检查通信中断 (超过 5 分钟视为中断)
            if ts and last_comm_time:
                gap_ms = (ts - last_comm_time).total_seconds() * 1000
                if gap_ms > COMM_TIMEOUT_MS:
                    ctc_to_cbi_send_seq = None
                    cbi_to_ctc_send_seq = None
                    comm_interrupted = True
            last_comm_time = ts

            # 检查 DC2/DC3 配对 (中断期间不记录错误)
            if ft == "DC2":
                dc2_pending = True
            elif ft == "DC3" and dc2_pending and ts:
                dc2_pending = False
                dc2_dc3_pairs += 1
                comm_interrupted = False

            # 检查 SDIQ/SDI 配对 (中断期间不记录错误)
            if ft == "SDIQ":
                last_sdciq_time = ts
            elif ft in ("SDI", "SDCI") and 'last_sdciq_time' in dir() and last_sdciq_time and ts:
                delta_ms = (ts - last_sdciq_time).total_seconds() * 1000
                if delta_ms < 500:
                    sdciq_sdi_pairs += 1
                    if comm_interrupted:
                        comm_interrupted = False
                elif not comm_interrupted:
                    pair_errors.append(f"行{line_num}: SDI/SDCI 响应延迟 ({delta_ms:.1f}ms)")
                last_sdciq_time = None

            # ACK 帧响应时间（与前一帧的时间差）
            if prev_time and ts and ft == "ACK":
                delta_ms = (ts - prev_time).total_seconds() * 1000
                ack_response_times.append(delta_ms)
                is_heartbeat = 450 <= delta_ms <= 650
                if delta_ms > ACK_TIMEOUT_MS and not comm_interrupted and not is_heartbeat:
                    errors.append(f"行{line_num}: ACK 响应超时 ({delta_ms:.1f}ms > {ACK_TIMEOUT_MS}ms)")

            prev_time = ts
            frames.append(frame)

    return {
        "total_frames": len(frames),
        "frame_type_counts": dict(frame_type_counts),
        "direction_counts": dict(direction_counts),
        "errors": errors,
        "seq_errors": seq_errors,
        "pair_errors": pair_errors,
        "ack_response_times": ack_response_times,
        "dc2_dc3_pairs": dc2_dc3_pairs,
        "sdciq_sdi_pairs": sdciq_sdi_pairs,
        "crc_errors": crc_errors,
    }


def generate_report(log_file, result):
    """生成分析报告"""
    lines = []
    lines.append("=" * 80)
    lines.append("CBI-CTC 通信日志协议规范检查报告")
    lines.append("=" * 80)
    lines.append(f"日志文件：{log_file}")
    lines.append(f"检查时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # 总体统计
    lines.append("-" * 80)
    lines.append("1. 总体统计")
    lines.append("-" * 80)
    lines.append(f"总帧数：{result['total_frames']}")
    lines.append(f"帧格式错误：{len(result['errors'])}")
    lines.append(f"CRC校验失败：{result['crc_errors']}")
    lines.append(f"序号错误：{len(result['seq_errors'])}")
    lines.append(f"配对错误：{len(result['pair_errors'])}")
    lines.append("")

    # 帧类型分布
    lines.append("-" * 80)
    lines.append("2. 帧类型分布")
    lines.append("-" * 80)
    for ft, count in sorted(result['frame_type_counts'].items(), key=lambda x: -x[1]):
        pct = count / result['total_frames'] * 100 if result['total_frames'] > 0 else 0
        lines.append(f"  {ft}: {count}帧 ({pct:.1f}%)")
    lines.append("")

    # 方向统计
    lines.append("-" * 80)
    lines.append("3. 通信方向统计")
    lines.append("-" * 80)
    for direction, count in sorted(result['direction_counts'].items()):
        lines.append(f"  {direction}: {count}帧")
    lines.append("")

    # ACK 响应时间分析
    if result['ack_response_times']:
        avg_time = sum(result['ack_response_times']) / len(result['ack_response_times'])
        max_time = max(result['ack_response_times'])
        lines.append("-" * 80)
        lines.append("4. ACK 响应时间分析")
        lines.append("-" * 80)
        lines.append(f"  平均响应时间：{avg_time:.2f}ms")
        lines.append(f"  最大响应时间：{max_time:.2f}ms")
        lines.append(f"  超时阈值：{ACK_TIMEOUT_MS}ms")
        timeout_count = sum(1 for t in result['ack_response_times'] if t > ACK_TIMEOUT_MS)
        lines.append(f"  超时次数：{timeout_count}")
        lines.append("")

    # 配对检查
    lines.append("-" * 80)
    lines.append("5. 握手配对检查")
    lines.append("-" * 80)
    lines.append(f"  DC2-DC3 成功配对：{result['dc2_dc3_pairs']}对")
    lines.append(f"  SDIQ-SDI/SDCI 成功配对：{result['sdciq_sdi_pairs']}对")
    lines.append("")

    # 序号连续性检查
    lines.append("-" * 80)
    lines.append("6. 序号连续性检查")
    lines.append("-" * 80)
    lines.append("  (控制帧不验证发送序号，仅数据帧检查)")
    if result['seq_errors']:
        for i, err in enumerate(result['seq_errors'][:20], 1):
            lines.append(f"  [{i}] {err}")
        if len(result['seq_errors']) > 20:
            lines.append(f"  ... 还有 {len(result['seq_errors']) - 20} 个序号错误")
    else:
        lines.append("  [OK] 序号连续性正常")
    lines.append("")

    # 配对错误详情
    if result['pair_errors']:
        lines.append("-" * 80)
        lines.append("7. 配对错误详情")
        lines.append("-" * 80)
        for i, err in enumerate(result['pair_errors'][:20], 1):
            lines.append(f"  [{i}] {err}")
        if len(result['pair_errors']) > 20:
            lines.append(f"  ... 还有 {len(result['pair_errors']) - 20} 个配对错误")
        lines.append("")

    # 错误详情
    if result['errors']:
        lines.append("-" * 80)
        lines.append("8. 帧格式错误详情")
        lines.append("-" * 80)
        for i, err in enumerate(result['errors'][:20], 1):
            lines.append(f"  [{i}] {err}")
        if len(result['errors']) > 20:
            lines.append(f"  ... 还有 {len(result['errors']) - 20} 个格式错误")
        lines.append("")

    # 结论
    lines.append("=" * 80)
    lines.append("检查结论")
    lines.append("=" * 80)
    total_errors = len(result['errors']) + len(result['seq_errors']) + len(result['pair_errors'])
    if total_errors == 0:
        lines.append("[PASS] 日志文件符合协议规范要求")
    else:
        lines.append(f"[FAIL] 发现 {total_errors} 个协议规范错误")
        if result['seq_errors']:
            lines.append(f"       - 序号错误：{len(result['seq_errors'])}个")
        if result['pair_errors']:
            lines.append(f"       - 配对错误：{len(result['pair_errors'])}个")
        if result['errors']:
            lines.append(f"       - 格式错误：{len(result['errors'])}个（含CRC失败{result['crc_errors']}个）")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    log_file = sys.argv[1] if len(sys.argv) > 1 else r"D:\UserFiles\Desktop\ZLEvents260331"

    print(f"正在分析日志：{log_file}")
    result = analyze_log(log_file)
    report = generate_report(log_file, result)

    # 保存报告
    output_file = log_file + "_protocol_check.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"报告已保存：{output_file}")
    print("")
    print(report)
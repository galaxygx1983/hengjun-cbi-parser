#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁路计算机联锁 (CBI) 与调度集中 (CTC) 通信日志协议规范检查工具
检查日志文件是否符合协议规范要求 - 专注于序号和通信流程
"""

import re
from datetime import datetime
from collections import defaultdict

# 帧类型定义
FRAME_TYPES = {
    0x12: ("DC2", "连接请求", "CTC→联锁"),
    0x13: ("DC3", "连接确认", "联锁→CTC"),
    0x06: ("ACK", "应答/心跳", "双向"),
    0x15: ("NACK", "否定应答", "双向"),
    0x10: ("VERROR", "版本错误", "双向"),
    0x8A: ("SDCI", "站场数据变化 (增量)", "联锁→CTC"),
    0x85: ("SDI", "站场完整数据 (全量)", "联锁→CTC"),
    0x6A: ("SDIQ", "站场数据请求", "CTC→联锁"),
    0x65: ("FIR", "故障信息报告", "联锁→CTC"),
    0xAA: ("RSR", "系统工作状态报告", "双向"),
    0x95: ("BCC", "按钮控制命令", "CTC→联锁"),
    0x75: ("ACQ", "自律控制请求", "联锁→CTC"),
    0x7A: ("ACA", "自律控制同意", "CTC→联锁"),
    0x9A: ("TSQ", "时间同步请求", "联锁→CTC"),
    0xA5: ("TSD", "时间同步数据", "CTC→联锁"),
}

# 协议常量
FRAME_HEADER = 0x7D
FRAME_TAIL = 0x7E
HEADER_LENGTH = 0x04
VERSION = 0x11
ACK_TIMEOUT_MS = 500  # ACK 超时阈值 (ms)


def parse_timestamp(ts_str):
    """解析时间戳字符串"""
    try:
        return datetime.strptime(ts_str, "%H:%M:%S.%f")
    except ValueError:
        return None


def parse_frame(hex_str):
    """解析单个帧数据 - 仅检查帧头和序号"""
    try:
        # 移除空格并解析十六进制
        hex_clean = hex_str.strip()
        raw = bytes.fromhex(hex_clean.replace(" ", ""))
    except ValueError as e:
        return None, f"无效的十六进制格式"

    if len(raw) < 9:
        return None, "帧长度过短"

    # 检查帧头帧尾
    if raw[0] != FRAME_HEADER:
        return None, f"帧头错误：期望 0x7D, 实际 0x{raw[0]:02X}"
    if raw[-1] != FRAME_TAIL:
        return None, f"帧尾错误：期望 0x7E, 实际 0x{raw[-1]:02X}"

    # 解析帧头字段
    header_len = raw[1]
    version = raw[2]
    send_seq = raw[3]
    ack_seq = raw[4]
    frame_type = raw[5]

    # 检查帧头长度和版本号
    errors = []
    if header_len != HEADER_LENGTH:
        errors.append(f"帧头长度错误：期望 0x04, 实际 0x{header_len:02X}")
    if version != VERSION:
        errors.append(f"版本号错误：期望 0x11, 实际 0x{version:02X}")

    # 获取帧类型信息
    frame_type_info = FRAME_TYPES.get(frame_type, (f"UNKNOWN(0x{frame_type:02X})", "未知", "未知"))

    return {
        "send_seq": send_seq,
        "ack_seq": ack_seq,
        "frame_type": frame_type,
        "frame_type_name": frame_type_info[0],
        "frame_type_desc": frame_type_info[1],
        "direction": frame_type_info[2],
        "raw": raw,
        "errors": errors
    }, None


def analyze_log(log_file):
    """分析日志文件 - 检查序号和通信流程"""
    # 正则表达式匹配日志行
    line_pattern = re.compile(
        r"^(\d{2}:\d{2}:\d{2}\.\d{3})\s+(<<|>>)\[(\w{2,5})\s*\](.+)$"
    )

    frames = []
    frame_type_counts = defaultdict(int)
    direction_counts = defaultdict(int)
    errors = []
    ack_response_times = []

    # 序号追踪
    ctc_to_cbi_seq = None  # CTC→联锁 期望序号 (None 表示未同步)
    cbi_to_ctc_seq = None  # 联锁→CTC 期望序号 (None 表示未同步)

    # 配对追踪
    last_dc2_time = None
    last_sdciq_time = None
    dc2_dc3_pairs = 0
    sdciq_sdi_pairs = 0
    dc2_pending = False  # 等待 DC3 来完成握手

    # 通信中断检测 (超过 5 分钟视为中断，重置序号)
    COMM_TIMEOUT_MS = 300000  # 5 分钟
    TX_TIMEOUT_MS = 500  # 发送超时阈值 (ms)
    last_comm_time = None
    comm_interrupted = False  # 通信中断标志
    last_ctc_tx_time = None  # CTC 最后发送时间
    last_cbi_tx_time = None  # 联锁最后发送时间

    # 序号错误统计
    seq_errors = []
    pair_errors = []

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
                    errors.append(f"行{line_num}: {e}")

            # 解析时间戳
            ts = parse_timestamp(timestamp)

            # 统计帧类型
            frame_type_counts[frame["frame_type_name"]] += 1
            direction_counts[direction] += 1

            # 记录各方最后发送时间
            if direction == "<<":
                last_ctc_tx_time = ts
            elif direction == ">>":
                last_cbi_tx_time = ts

            # 检查序号连续性
            ft = frame["frame_type_name"]

            # DC2/DC3 握手后重置序号 (双方都重置)
            # DC2 和 DC3 本身使用序号 0x00，所以下一帧从 0x01 开始
            if ft == "DC2" and direction == "<<":
                dc2_pending = True  # 等待 DC3
                ctc_to_cbi_seq = 1  # CTC 序号重置，下一帧从 0x01 开始
            elif ft == "DC3" and direction == ">>":
                if dc2_pending:
                    dc2_pending = False
                    dc2_dc3_pairs += 1
                cbi_to_ctc_seq = 1  # 联锁序号重置，下一帧从 0x01 开始

            # CTC→联锁方向 (<<) - CTC 发送的帧
            # ACK/ACA 帧不检查序号连续性 (因为重传时序号不变)
            if direction == "<<":
                if ft in ("DC2", "RSR", "SDIQ", "BCC", "TSD"):
                    if ctc_to_cbi_seq is not None:  # 已同步才检查
                        if frame["send_seq"] != ctc_to_cbi_seq:
                            # 允许序号回退 1 (重传机制)
                            if frame["send_seq"] != ((ctc_to_cbi_seq - 1) & 0xFF):
                                seq_errors.append(f"行{line_num}: {ft} 序号不连续，期望 0x{ctc_to_cbi_seq:02X}, 实际 0x{frame['send_seq']:02X}")
                            # 重传帧，不递增序号
                        else:
                            ctc_to_cbi_seq = (ctc_to_cbi_seq + 1) & 0xFF

            # 联锁→CTC 方向 (>>) - 联锁发送的帧
            # ACK/ACA 帧不检查序号连续性 (因为重传时序号不变)
            elif direction == ">>":
                if ft in ("DC3", "RSR", "SDI", "SDCI", "FIR", "ACQ", "TSQ"):
                    if cbi_to_ctc_seq is not None:  # 已同步才检查
                        if frame["send_seq"] != cbi_to_ctc_seq:
                            # 允许序号回退 1 (重传机制)
                            if frame["send_seq"] != ((cbi_to_ctc_seq - 1) & 0xFF):
                                seq_errors.append(f"行{line_num}: {ft} 序号不连续，期望 0x{cbi_to_ctc_seq:02X}, 实际 0x{frame['send_seq']:02X}")
                            # 重传帧，不递增序号
                        else:
                            cbi_to_ctc_seq = (cbi_to_ctc_seq + 1) & 0xFF

            # 检查通信中断/超时 (超过 5 分钟视为中断，任一方超过 500ms 无发送视为超时)
            if ts and last_comm_time:
                gap_ms = (ts - last_comm_time).total_seconds() * 1000
                if gap_ms > COMM_TIMEOUT_MS:
                    # 通信中断，重置序号期望，清除配对计时，标记中断状态
                    ctc_to_cbi_seq = None
                    cbi_to_ctc_seq = None
                    last_sdciq_time = None
                    last_dc2_time = None
                    last_ctc_tx_time = None
                    last_cbi_tx_time = None
                    comm_interrupted = True
            last_comm_time = ts

            # 检查发送超时 (正常通信期间，任何一方超过 500ms 没有发送数据)
            if ts and not comm_interrupted:
                if last_ctc_tx_time:
                    ctc_gap_ms = (ts - last_ctc_tx_time).total_seconds() * 1000
                    if ctc_gap_ms > TX_TIMEOUT_MS and ctc_gap_ms < COMM_TIMEOUT_MS:
                        errors.append(f"行{line_num}: CTC 发送超时 ({ctc_gap_ms:.1f}ms > {TX_TIMEOUT_MS}ms)")
                if last_cbi_tx_time:
                    cbi_gap_ms = (ts - last_cbi_tx_time).total_seconds() * 1000
                    if cbi_gap_ms > TX_TIMEOUT_MS and cbi_gap_ms < COMM_TIMEOUT_MS:
                        errors.append(f"行{line_num}: 联锁发送超时 ({cbi_gap_ms:.1f}ms > {TX_TIMEOUT_MS}ms)")

            # 检查 ACK 响应时间 (中断期间不记录错误)
            if prev_time and ts and ft == "ACK":
                delta_ms = (ts - prev_time).total_seconds() * 1000
                ack_response_times.append(delta_ms)
                # 跳过中断期间的超时，跳过 ACK 心跳模式 (500-600ms 是正常心跳间隔)
                is_heartbeat = 450 <= delta_ms <= 650  # 正常心跳间隔
                if delta_ms > ACK_TIMEOUT_MS and not comm_interrupted and not is_heartbeat:
                    errors.append(f"行{line_num}: ACK 响应超时 ({delta_ms:.1f}ms > {ACK_TIMEOUT_MS}ms)")

            # 检查 DC2/DC3 配对 (中断期间不记录错误)
            if ft == "DC2":
                last_dc2_time = ts
            elif ft == "DC3" and last_dc2_time and ts:
                delta_ms = (ts - last_dc2_time).total_seconds() * 1000
                if delta_ms < 200:  # DC3 应在 DC2 后 200ms 内响应
                    dc2_dc3_pairs += 1
                    # 成功握手，清除中断标志
                    comm_interrupted = False
                elif not comm_interrupted:
                    pair_errors.append(f"行{line_num}: DC3 响应延迟 ({delta_ms:.1f}ms)")

            # 检查 SDIQ/SDI 配对 (中断期间不记录错误)
            if ft == "SDIQ":
                last_sdciq_time = ts
            elif ft in ("SDI", "SDCI") and last_sdciq_time and ts:
                delta_ms = (ts - last_sdciq_time).total_seconds() * 1000
                if delta_ms < 500:  # SDI 应在 SDIQ 后 500ms 内响应
                    sdciq_sdi_pairs += 1
                    # 成功配对，清除中断标志
                    if comm_interrupted:
                        comm_interrupted = False
                elif not comm_interrupted:
                    pair_errors.append(f"行{line_num}: SDI/SDCI 响应延迟 ({delta_ms:.1f}ms)")
                # 无论成功还是失败，配对检查后清除 SDIQ 计时
                last_sdciq_time = None

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
        "sdciq_sdi_pairs": sdciq_sdi_pairs
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
            lines.append(f"       - 格式错误：{len(result['errors'])}个")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    log_file = sys.argv[1] if len(sys.argv) > 1 else r"D:\UserFiles\Desktop\ZLEvents260331"

    print(f"正在分析日志：{log_file}")
    result = analyze_log(log_file)
    report = generate_report(log_file, result)

    # 保存报告 (使用二进制模式避免编码问题)
    output_file = log_file + "_protocol_check.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"报告已保存：{output_file}")
    print("")
    print(report)

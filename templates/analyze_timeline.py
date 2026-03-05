#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用联锁设备状态分析脚本
分析SDCI帧中指定设备的状态变化时间线

支持设备类型:
- switch: 道岔区段（纯数字名称，如64, 110）
- signal: 信号机（D开头，如D114）
- track: 无岔区段（如DK5, 102/104G）

使用方法:
1. 先从日志中提取指定设备的SDCI帧:
   grep -E "8A.*00 {device_index:02X}" ZLEvents260201 > device_frames.txt

2. 运行分析脚本:
   python analyze_timeline.py <type> <frame_file> <device_index> [device_name]

示例:
   # 分析道岔区段64 (设备索引37)
   grep -E "8A.*00 25" ZLEvents260201 > device64_frames.txt
   python analyze_timeline.py switch device64_frames.txt 37 "道岔区段64"

   # 分析信号机D12 (设备索引66)
   grep -E "8A.*00 42" ZLEvents260201 > d12_frames.txt
   python analyze_timeline.py signal d12_frames.txt 66 "D12"
"""

import re
import sys
import argparse
from collections import Counter


# ============== 状态解码函数 ==============


def decode_switch_state(state_byte):
    """
    解码道岔区段状态字节

    状态字节包含以下信息（8位，按位组合）：
    - bit 0-2: 道岔位置 (1=定位, 2=反位, 4=无表示，可组合)
    - bit 3: 区段锁闭状态
    - bit 4: 区段占用状态
    - bit 5: 道岔锁闭状态
    """
    position_bits = state_byte & 0x07
    position_parts = []
    if position_bits & 0x01:
        position_parts.append("定位")
    if position_bits & 0x02:
        position_parts.append("反位")
    if position_bits & 0x04:
        position_parts.append("无表示")

    position_str = " + ".join(position_parts) if position_parts else "未知(0)"
    section_lock = (state_byte >> 3) & 0x01
    occupancy = (state_byte >> 4) & 0x01
    switch_lock = (state_byte >> 5) & 0x01

    return {
        "位置": position_str,
        "区段锁闭": "锁闭" if section_lock else "未锁闭",
        "区段占用": "占用" if occupancy else "未占用",
        "道岔锁闭": "锁闭" if switch_lock else "未锁闭",
        "state_byte": state_byte,
    }


def decode_signal_state(state_byte):
    """
    解码信号机状态字节

    状态字节包含以下信息（8位）：
    - bit 0-5: 颜色状态
    - bit 6: 进路转岔过程中的始终信号机
    - bit 7: 延时解锁状态
    """
    color_bits = state_byte & 0x3F
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

    # bit 5组合处理
    if color_bits & 0x20:
        if color_bits == 0x20:
            color_parts = ["黄"]
        elif color_bits == 0x22:
            color_parts = ["2黄"]
        elif color_bits == 0x23:
            color_parts = ["引白"]
        else:
            color_parts.insert(0, "[bit5组合]")

    color_str = " + ".join(color_parts) if color_parts else "灭灯"
    is_route = (state_byte >> 6) & 0x01
    delay = (state_byte >> 7) & 0x01

    return {
        "颜色": color_str,
        "进路转岔": "是" if is_route else "否",
        "延时解锁": "延时中" if delay else "无延时",
        "state_byte": state_byte,
    }


def decode_track_state(state_byte, bit_offset=0):
    """
    解码无岔区段状态字节

    - bit_offset=0: 使用低4位
    - bit_offset=4: 使用高4位
    """
    if bit_offset == 0:
        state_value = state_byte & 0x0F
    else:
        state_value = (state_byte >> 4) & 0x0F

    state_map = {
        0x00: "空闲未锁闭",
        0x01: "占用未锁闭",
        0x02: "空闲锁闭",
        0x03: "占用锁闭",
    }

    return {
        "状态": state_map.get(state_value, f"未知(0x{state_value:X})"),
        "占用": "占用" if state_value & 0x01 else "空闲",
        "锁闭": "锁闭" if state_value & 0x02 else "未锁闭",
        "state_byte": state_byte,
        "bit_offset": bit_offset,
    }


# ============== 分析函数 ==============


def analyze_by_index(frame_file, device_index, device_type):
    """
    通过设备索引分析（适用于道岔区段和信号机）
    """
    records = []
    device_hex = f"{device_index:02X}"

    with open(frame_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    for line in lines:
        parts = line.split()
        if len(parts) >= 12:
            time_str = parts[0]
            hex_data = " ".join(parts[3:])

            pattern = rf"00 {device_hex} ([0-9A-Fa-f]{{2}})"
            match = re.search(pattern, hex_data)

            if match:
                state = int(match.group(1), 16)
                if device_type == "switch":
                    decoded = decode_switch_state(state)
                elif device_type == "signal":
                    decoded = decode_signal_state(state)
                else:
                    continue
                records.append({"time": time_str, "state": state, "decoded": decoded})

    return records


def analyze_track_sections(log_file):
    """
    分析无岔区段（通过字节索引和位偏移）
    """
    # 设备配置示例（可从码位表读取）
    devices = {
        "102/104G": {"objects_index": 189, "byte_index": 324, "bit_offset": 0},
        "104/110G": {"objects_index": 190, "byte_index": 324, "bit_offset": 4},
    }

    device_data = {name: [] for name in devices}
    sdci_marker = b"[SDCI ]"

    with open(log_file, "rb") as f:
        content = f.read()

    pos = 0
    while True:
        pos = content.find(sdci_marker, pos)
        if pos == -1:
            break

        # 提取时间戳
        line_start = content.rfind(b"\n", 0, pos)
        line_start = line_start if line_start != -1 else 0
        line_end = content.find(b"\n", pos)
        line_end = line_end if line_end != -1 else len(content)

        line = content[line_start:line_end]
        ts_match = re.search(rb"(\d{2}:\d{2}:\d{2})", line)
        if not ts_match:
            pos += 1
            continue

        timestamp = ts_match.group(1).decode("latin1")

        # 提取十六进制数据
        after = content[pos + len(sdci_marker) :]
        hex_chars = b""
        for byte in after:
            if (48 <= byte <= 57) or (65 <= byte <= 70) or (97 <= byte <= 102):
                hex_chars += bytes([byte])
            elif len(hex_chars) >= 28:
                break

        if len(hex_chars) >= 14:
            try:
                hex_str = hex_chars.decode("ascii")
                data = bytes.fromhex(hex_str[:60])

                if len(data) >= 8 and data[5] == 0x8A:
                    remaining = data[8:-3]

                    for j in range(0, len(remaining) - 2, 3):
                        if j + 3 <= len(remaining):
                            idx_device = (remaining[j] << 8) | remaining[j + 1]
                            state = remaining[j + 2]

                            for name, config in devices.items():
                                if idx_device == config["objects_index"]:
                                    decoded = decode_track_state(
                                        state, config["bit_offset"]
                                    )
                                    device_data[name].append(
                                        {
                                            "timestamp": timestamp,
                                            "state": state,
                                            "decoded": decoded,
                                        }
                                    )
            except:
                pass

        pos += 1

    return device_data


# ============== 报告输出函数 ==============


def print_switch_report(records, device_index, device_name):
    """打印道岔区段分析报告"""
    name_str = f" ({device_name})" if device_name else ""

    print("=" * 80)
    print(f"道岔区段 {device_index} (0x{device_index:04X}){name_str} 状态变化时间线")
    print("=" * 80)
    print()

    if not records:
        print("未找到状态记录!")
        return

    print(f"总计: {len(records)} 条状态记录")
    print()
    print(
        f"{'序号':<6} {'时间':<12} {'状态值':<8} {'位置':<12} {'区段锁闭':<10} {'区段占用':<10} {'道岔锁闭':<10}"
    )
    print("-" * 80)

    prev_state = None
    change_count = 0

    for i, rec in enumerate(records, 1):
        time_str = rec["time"]
        state_val = f"0x{rec['state']:02X}"
        pos = rec["decoded"]["位置"]
        sec_lock = rec["decoded"]["区段锁闭"]
        sec_occ = rec["decoded"]["区段占用"]
        sw_lock = rec["decoded"]["道岔锁闭"]

        if prev_state is not None and prev_state != rec["state"]:
            change_count += 1
            print(
                f"{'':6} {'':12} {'':8} {'':12} {'':10} {'':10} {'':10} [--- 状态变化 #{change_count} ---]"
            )

        print(
            f"{i:<6} {time_str:<12} {state_val:<8} {pos:<12} {sec_lock:<10} {sec_occ:<10} {sw_lock:<10}"
        )
        prev_state = rec["state"]

    # 统计
    print()
    print("=" * 80)
    print("统计汇总")
    print("=" * 80)
    print(f"状态变化总次数: {len(records)}")
    print(f"实际状态转换次数: {change_count}")
    if records:
        print(f"时间范围: {records[0]['time']} 至 {records[-1]['time']}")

    # 状态分布
    state_counts = Counter(f"0x{r['state']:02X}" for r in records)
    print()
    print("状态分布:")
    for state, count in state_counts.most_common():
        print(f"  {state}: {count:3d} 次")

    print()
    print("=" * 80)


def print_signal_report(records, device_index, device_name):
    """打印信号机分析报告"""
    name_str = f" ({device_name})" if device_name else ""

    print("=" * 80)
    print(f"信号机 {device_index} (0x{device_index:04X}){name_str} 状态变化时间线")
    print("=" * 80)
    print()

    if not records:
        print("未找到状态记录!")
        return

    print(f"总计: {len(records)} 条状态记录")
    print()
    print(
        f"{'序号':<6} {'时间':<12} {'状态值':<8} {'颜色':<16} {'进路转岔':<12} {'延时解锁':<10}"
    )
    print("-" * 80)

    prev_state = None
    change_count = 0

    for i, rec in enumerate(records, 1):
        time_str = rec["time"]
        state_val = f"0x{rec['state']:02X}"
        color = rec["decoded"]["颜色"]
        route = rec["decoded"]["进路转岔"]
        delay = rec["decoded"]["延时解锁"]

        if prev_state is not None and prev_state != rec["state"]:
            change_count += 1
            print(
                f"{'':6} {'':12} {'':8} {'':16} {'':12} {'':10} [--- 状态变化 #{change_count} ---]"
            )

        print(
            f"{i:<6} {time_str:<12} {state_val:<8} {color:<16} {route:<12} {delay:<10}"
        )
        prev_state = rec["state"]

    # 统计
    print()
    print("=" * 80)
    print("统计汇总")
    print("=" * 80)
    print(f"状态变化总次数: {len(records)}")
    print(f"实际状态转换次数: {change_count}")
    if records:
        print(f"时间范围: {records[0]['time']} 至 {records[-1]['time']}")

    # 状态分布和颜色统计
    state_counts = Counter(f"0x{r['state']:02X}" for r in records)
    color_counts = Counter(r["decoded"]["颜色"] for r in records)

    print()
    print("状态分布:")
    for state, count in state_counts.most_common():
        print(f"  {state}: {count:3d} 次")

    print()
    print("颜色统计:")
    for color, count in color_counts.most_common():
        pct = count / len(records) * 100
        bar = "█" * int(pct / 5)
        print(f"  {color}: {count:3d} ({pct:5.1f}%) {bar}")

    # 延时统计
    delay_count = sum(1 for r in records if r["decoded"]["延时解锁"] == "延时中")
    if delay_count > 0:
        print(f"\n延时解锁-延时中: {delay_count} 次")

    print()
    print("=" * 80)


def print_track_report(device_data):
    """打印无岔区段分析报告"""
    print("=" * 80)
    print("无岔区段状态分析")
    print("=" * 80)
    print()

    for device_name, data in device_data.items():
        print(f"\n{device_name}:")
        print("-" * 40)
        print(f"记录数: {len(data)}")

        if data:
            print(f"\n状态时间线:")
            print(f"{'时间':<12} | {'状态':<16} | {'原始字节'}")
            print("-" * 50)

            for entry in data[:20]:  # 只显示前20条
                print(
                    f"{entry['timestamp']:<12} | {entry['decoded']['状态']:<16} | 0x{entry['state']:02X}"
                )

            if len(data) > 20:
                print(f"... 还有 {len(data) - 20} 条记录 ...")

            # 统计
            print(f"\n状态统计:")
            state_counts = Counter(e["decoded"]["状态"] for e in data)
            for state, count in state_counts.most_common():
                print(f"  {state}: {count} 次")

            # 状态转换
            print(f"\n状态转换:")
            changes = []
            last_state = None
            for entry in data:
                if entry["decoded"]["状态"] != last_state:
                    changes.append(
                        (entry["timestamp"], last_state, entry["decoded"]["状态"])
                    )
                    last_state = entry["decoded"]["状态"]

            print(f"  总转换次数: {len(changes)}")
            for ts, old, new in changes[:10]:
                old_display = old if old else "初始"
                print(f"    {ts}: {old_display} -> {new}")

            print(f"\n最终状态: {data[-1]['decoded']['状态']}")

    print()
    print("=" * 80)


# ============== 主函数 ==============


def main():
    parser = argparse.ArgumentParser(
        description="联锁设备状态分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 分析道岔区段64 (设备索引37)
  grep -E "8A.*00 25" ZLEvents260201 > device64_frames.txt
  python analyze_timeline.py switch device64_frames.txt 37 "道岔区段64"
  
  # 分析信号机D12 (设备索引66)
  grep -E "8A.*00 42" ZLEvents260201 > d12_frames.txt
  python analyze_timeline.py signal d12_frames.txt 66 "D12"
  
  # 分析无岔区段（直接分析日志文件）
  python analyze_timeline.py track ZLEvents260201
        """,
    )

    parser.add_argument(
        "type",
        choices=["switch", "signal", "track"],
        help="设备类型: switch=道岔区段, signal=信号机, track=无岔区段",
    )
    parser.add_argument(
        "frame_file",
        help="帧数据文件路径（switch/signal类型）或日志文件路径（track类型）",
    )
    parser.add_argument(
        "device_index",
        nargs="?",
        type=int,
        help="设备objects索引（switch/signal类型必需）",
    )
    parser.add_argument(
        "device_name", nargs="?", default="", help="设备名称（可选，用于显示）"
    )

    args = parser.parse_args()

    if args.type in ["switch", "signal"]:
        if args.device_index is None:
            parser.error(f"{args.type}类型需要提供device_index参数")

        records = analyze_by_index(args.frame_file, args.device_index, args.type)

        if args.type == "switch":
            print_switch_report(records, args.device_index, args.device_name)
        else:
            print_signal_report(records, args.device_index, args.device_name)

    elif args.type == "track":
        device_data = analyze_track_sections(args.frame_file)
        print_track_report(device_data)


if __name__ == "__main__":
    main()

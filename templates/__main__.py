#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hengjun-cbi-parser - 命令行入口

使用方法:
    python -m hengjun_cbi_parser <command> [options]

命令:
    parse-sdci <log_file> <code_table> [output_dir]  - 解析SDCI日志
    decode-frame <frame_data> <code_table>           - 解码单个帧

示例:
    python -m hengjun_cbi_parser parse-sdci lgxtcidriver.log lgxtq.zl ./output
    python -m hengjun_cbi_parser decode-frame 7D041165BF8A030000B71028817E lgxtq.zl
"""

import sys
import os

# 添加父目录到路径以支持直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hengjun_cbi_parser.code_position_table import CodePositionTable
from hengjun_cbi_parser.analyzer import CTCLogAnalyzer, export_to_json
from hengjun_cbi_parser.sdci_parser import SDCIFrameParser


def parse_sdci_command(args):
    """解析SDCI日志命令"""
    if len(args) < 2:
        print("用法: parse-sdci <log_file> <code_table> [output_dir]")
        sys.exit(1)

    log_file = args[0]
    code_table = args[1]
    output_dir = args[2] if len(args) > 2 else "."

    if not os.path.exists(log_file):
        print(f"错误: 日志文件不存在: {log_file}")
        sys.exit(1)

    if not os.path.exists(code_table):
        print(f"错误: 码位表文件不存在: {code_table}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    print(f"正在解析日志: {log_file}")
    print(f"码位表: {code_table}")

    # 加载码位表
    cpt = CodePositionTable(code_table)
    print(f"  已加载 {len(cpt.devices_by_name)} 个设备定义")

    # 分析日志
    analyzer = CTCLogAnalyzer(log_file, cpt)
    frames = analyzer.analyze()

    print(f"\n找到 {len(frames)} 个SDCI帧")

    # 生成报告
    report_file = os.path.join(output_dir, "sdci_analysis_report.txt")
    analyzer.generate_report(output_file=report_file)
    print(f"报告已保存: {report_file}")

    # 导出JSON
    json_file = os.path.join(output_dir, "sdci_frames.json")
    export_to_json(frames, json_file)
    print(f"JSON已导出: {json_file}")


def decode_frame_command(args):
    """解码单个帧命令"""
    if len(args) < 2:
        print("用法: decode-frame <frame_data> <code_table>")
        print("示例: decode-frame 7D041165BF8A030000B71028817E lgxtq.zl")
        sys.exit(1)

    frame_data = args[0]
    code_table = args[1]

    if not os.path.exists(code_table):
        print(f"错误: 码位表文件不存在: {code_table}")
        sys.exit(1)

    try:
        raw_bytes = bytes.fromhex(frame_data.replace(" ", ""))
    except ValueError:
        print(f"错误: 无效的十六进制数据: {frame_data}")
        sys.exit(1)

    # 加载码位表并解析帧
    cpt = CodePositionTable(code_table)
    parser = SDCIFrameParser(cpt)
    frame = parser.parse_frame(raw_bytes)

    if not frame:
        print("错误: 无法解析帧数据（可能不是有效的SDCI帧）")
        sys.exit(1)

    print("=" * 60)
    print("SDCI帧解码结果")
    print("=" * 60)
    print(f"发送序号: 0x{frame.send_seq:02X} ({frame.send_seq})")
    print(f"确认序号: 0x{frame.ack_seq:02X} ({frame.ack_seq})")
    print(f"数据长度: {frame.data_length}字节")
    print(f"CRC校验: 0x{frame.crc:04X}")
    print(f"变化设备数: {frame.get_device_count()}")
    print("")

    if frame.device_states:
        print("设备状态:")
        for i, ds in enumerate(frame.device_states, 1):
            print(f"\n  [{i}] {ds.device.name} [{ds.device.get_type_description()}]")
            print(f"      设备序号: {ds.device.byte_index}")
            print(f"      原始状态: 0x{ds.raw_state:02X} ({ds.raw_state})")
            for key, value in ds.decoded_state.items():
                print(f"      {key}: {value}")


def main():
    """主入口函数"""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:]

    if command == "parse-sdci":
        parse_sdci_command(args)
    elif command == "decode-frame":
        decode_frame_command(args)
    else:
        print(f"未知命令: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

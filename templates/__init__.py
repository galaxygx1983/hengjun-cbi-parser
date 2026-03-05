"""
hengjun-cbi-parser - 铁路CBI/CTC通信日志分析工具

用于解析联锁系统与调度集中系统之间的SDCI通信帧。

主要功能：
- 解析码位表文件（lgxtq.zl）
- 解析CTC日志中的SDCI帧
- 解码设备状态（道岔区段、信号机、无岔区段）
- 数据转义/反转义处理
- CRC16校验计算
- 生成详细分析报告

模块：
- device_types: 设备类型定义和数据结构
- code_position_table: 码位表解析器
- state_decoder: 设备状态解码器
- frame_utils: 帧处理工具（转义、CRC计算）
- sdci_parser: SDCI帧解析器
- analyzer: CTC日志分析器
- hardware_fault_analyzer: 硬件故障分析器

Author: Claude Code
Version: 2.1.0
"""

from .device_types import (
    DeviceType,
    DeviceInfo,
    DeviceState,
    SDCIFrame,
)

from .code_position_table import CodePositionTable

from .state_decoder import StateDecoder

from .frame_utils import (
    FrameUtils,
    escape_data,
    unescape_data,
    calculate_crc,
    build_frame,
)

from .sdci_parser import SDCIFrameParser

from .analyzer import (
    CTCLogAnalyzer,
    parse_sdci_log,
    export_to_json,
)

from .hardware_fault_analyzer import (
    CTCLogHardwareFaultAnalyzer,
    HardwareFaultEvent,
    ConnectionRecoveryEvent,
    analyze_hardware_faults,
)

__version__ = "2.1.0"
__all__ = [
    # 设备类型
    "DeviceType",
    "DeviceInfo",
    "DeviceState",
    "SDCIFrame",
    # 码位表
    "CodePositionTable",
    # 状态解码器
    "StateDecoder",
    # 帧处理工具
    "FrameUtils",
    "escape_data",
    "unescape_data",
    "calculate_crc",
    "build_frame",
    # SDCI解析器
    "SDCIFrameParser",
    # 日志分析器
    "CTCLogAnalyzer",
    "parse_sdci_log",
    "export_to_json",
    # 硬件故障分析
    "CTCLogHardwareFaultAnalyzer",
    "HardwareFaultEvent",
    "ConnectionRecoveryEvent",
    "analyze_hardware_faults",
]

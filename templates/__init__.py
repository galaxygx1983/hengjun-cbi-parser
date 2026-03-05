"""
hengjun-cbi-parser - 联锁系统CBI SDCI帧解析器

用于解析联锁系统与调度集中系统之间的SDCI通信帧。

主要功能：
- 解析码位表文件（lgxtq.zl）
- 解析CTC日志中的SDCI帧
- 解码设备状态（道岔区段、信号机、无岔区段）
- 生成详细分析报告

Author: Claude Code
Version: 1.0.0
"""

from .parser import (
    DeviceType,
    DeviceInfo,
    DeviceState,
    SDCIFrame,
    CodePositionTable,
    StateDecoder,
    SDCIFrameParser,
    CTCLogAnalyzer,
    HardwareFaultEvent,
    ConnectionRecoveryEvent,
    CTCLogHardwareFaultAnalyzer,
    parse_sdci_log,
    analyze_hardware_faults,
    export_to_json,
)

__version__ = "1.1.0"
__all__ = [
    "DeviceType",
    "DeviceInfo",
    "DeviceState",
    "SDCIFrame",
    "CodePositionTable",
    "StateDecoder",
    "SDCIFrameParser",
    "CTCLogAnalyzer",
    "HardwareFaultEvent",
    "ConnectionRecoveryEvent",
    "CTCLogHardwareFaultAnalyzer",
    "parse_sdci_log",
    "analyze_hardware_faults",
    "export_to_json",
]

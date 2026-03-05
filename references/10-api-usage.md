# Python API 使用说明

本技能提供完整的 Python API 用于铁路CBI/CTC通信日志分析。

## 快速导入

```python
# 方式1: 从模板目录直接导入
import sys
sys.path.insert(0, 'templates')
from parser import (
    CodePositionTable,      # 码位表解析
    FrameParser,            # 通用帧解析器
    CTCLogAnalyzer,         # 日志分析器
    DeviceTimelineAnalyzer, # 设备时间线分析
    StateDecoder,           # 设备状态解码
    CTCLogHardwareFaultAnalyzer,  # 硬件故障分析
    ERROR_CODE_MAP,         # 错误码映射
    BCC_COMMAND_MAP,        # BCC命令映射
    RSR_STATUS_MAP,         # RSR状态映射
    parse_all_frames,       # 解析所有帧
    parse_sdci_log,        # 解析SDCI帧
    analyze_hardware_faults, # 分析硬件故障
    export_to_json,         # JSON导出
)

# 方式2: 作为模块安装后导入
from hengjun_cbi_parser import *
```

## 常用场景

### 场景1: 解析日志中的所有帧

```python
from templates.parser import parse_all_frames

frames = parse_all_frames("ZLEvents260201", "references/lgxtq.zl")
print(f"共解析 {len(frames)} 个帧")

# 统计帧类型
from collections import Counter
frame_types = Counter(f.frame_type_name for f in frames)
print(frame_types)
```

### 场景2: 解析指定设备的时间线

```python
from templates.parser import DeviceTimelineAnalyzer, CodePositionTable

cpt = CodePositionTable("references/lgxtq.zl")
analyzer = DeviceTimelineAnalyzer("ZLEvents260201", cpt)

# 分析设备D1的时间线
timeline = analyzer.analyzer_device("D1")
print(f"设备D1共 {len(timeline)} 次状态变化")

# 生成报告
analyzer.generate_timeline_report("D1", "D1_report.txt")
```

### 场景3: 故障分析

```python
from templates.parser import CTCLogHardwareFaultAnalyzer

analyzer = CTCLogHardwareFaultAnalyzer("lgxtcidriver_20260101_1.log")
result = analyzer.analyze()

print(f"故障事件: {result['statistics']['total_fault_events']}")
print(f"恢复事件: {result['statistics']['total_recovery_events']}")
```

### 场景4: 解析单个帧

```python
from templates.parser import FrameParser, CodePositionTable

cpt = CodePositionTable("references/lgxtq.zl")
parser = FrameParser(cpt)

# 解析十六进制帧数据
hex_data = "7D 04 11 00 00 8A 03 00 25 10 7E"
raw_bytes = bytes.fromhex(hex_data.replace(" ", ""))

frame = parser.parse_frame(raw_bytes, "2026-02-01 00:00:03")

print(f"帧类型: {frame.frame_type_name}")  # SDCI
print(f"设备数: {frame.get_device_count()}")
for ds in frame.device_states:
    print(f"  {ds.device.name}: {ds.decoded_state}")
```

## API 参考

### CodePositionTable

码位表解析器，用于加载设备定义。

```python
cpt = CodePositionTable("lgxtq.zl")

# 查询设备
device = cpt.get_device_by_name("D1")      # 按名称
device = cpt.get_device_by_object_index(0)  # 按objects索引
device = cpt.get_device_by_byte_index(37)   # 按zlobjects索引
```

### FrameParser

通用帧解析器，支持所有15种帧类型。

```python
parser = FrameParser(code_position_table)

frame = parser.parse_frame(raw_bytes, timestamp)
# frame.frame_type_name  帧类型名称
# frame.device_states    设备状态列表(SDCI/SDI)
# frame.fir_events     故障事件列表(FIR)
# frame.rsr_status     工作状态(RSR)
# frame.bcc_command    按钮命令(BCC)
# frame.tsd_time       时间数据(TSD)
# frame.aca_response  自律控制响应(ACA)
```

### CTCLogAnalyzer

日志分析器，从日志文件提取帧。

```python
analyzer = CTCLogAnalyzer(log_file, code_position_table)

# 解析所有帧
frames = analyzer.analyze()

# 解析特定类型
sdci_frames = analyzer.analyze_sdci()
sdi_frames = analyzer.analyze_sdi()
fir_frames = analyzer.analyze_fir()
control_frames = analyzer.analyze_control_frames()

# 获取统计
stats = analyzer.get_frame_statistics()

# 生成报告
analyzer.generate_report("report.txt")
```

### DeviceTimelineAnalyzer

设备时间线分析器。

```python
analyzer = DeviceTimelineAnalyzer(log_file, cpt)

timeline = analyzer.analyzer_device("D1")
# 返回: [{"timestamp": "...", "frame_type": "SDCI", "raw_state": 0x10, "decoded_state": {...}}, ...]

analyzer.generate_timeline_report("D1", "output.txt")
```

### CTCLogHardwareFaultAnalyzer

硬件故障分析器。

```python
analyzer = CTCLogHardwareFaultAnalyzer(log_file)

result = analyzer.analyze()
# result["fault_events"]    故障事件列表
# result["recovery_events"] 恢复事件列表
# result["statistics"]     统计信息

analyzer.generate_report("fault_report.txt")
analyzer.export_to_csv("faults.csv")
```

## 数据结构

### Frame

```python
@dataclass
class Frame:
    timestamp: str           # 时间戳
    frame_type: int         # 帧类型代码
    frame_type_name: str     # 帧类型名称
    send_seq: int           # 发送序号
    ack_seq: int            # 确认序号
    data_length: int        # 数据长度
    raw_data: bytes         # 原始数据
    payload: bytes          # 数据载荷
    crc: int                # CRC校验值
    direction: str          # 传输方向
    device_states: List[DeviceState]  # 设备状态
    fir_events: List[Dict]   # 故障事件
    rsr_status: Dict        # RSR状态
    bcc_command: Dict       # BCC命令
    tsd_time: Dict          # 时间数据
    aca_response: Dict      # ACA响应
```

### DeviceState

```python
@dataclass
class DeviceState:
    device: DeviceInfo       # 设备信息
    raw_state: int          # 原始状态值
    decoded_state: Dict      # 解码后状态
```

### DeviceInfo

```python
@dataclass
class DeviceInfo:
    name: str               # 设备名称
    device_type: DeviceType # 设备类型
    object_index: int       # objects表索引
    byte_index: int         # zlobjects表字节索引
    bit_offset: int         # 位偏移(0或4)
```

## 便捷函数

```python
# 解析所有帧
frames = parse_all_frames(log_file, code_table, output_dir)

# 解析SDCI帧
frames = parse_sdci_log(log_file, code_table, output_dir)

# 分析硬件故障
result = analyze_hardware_faults(log_file, output_dir)

# 导出JSON
export_to_json(frames, output_file)
```

## 约束

- ACK超时: 500ms (协议固定)
- 最大帧长度: 1024字节
- 码位表: `references/lgxtq.zl`
- 错误码: `references/Error.sys`

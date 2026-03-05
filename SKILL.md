---
name: hengjun-cbi-parser
description: 铁路CBI/CTC通信日志分析工具。当用户需要分析铁路联锁系统日志、解析通信帧协议、排查故障时使用此技能。
trigger:
  - 分析铁路日志
  - CBI CTC 日志
  - 联锁 通信
  - 帧协议解析
  - SDCI SDI FIR
  - 设备状态解析
  - 故障码查询
  - ZLEvents
  - lgxtcidriver
---

# Hengjun CBI Parser

铁路计算机联锁(CBI)与调度集中(CTC)通信日志分析工具

## 何时使用

当用户提出以下问题时，使用此技能：

| 场景 | 示例问题 |
|------|----------|
| 解析通信帧 | "帮我解析这个SDCI帧" |
| 分析设备状态 | "信号机D1的状态是什么" |
| 故障排查 | "为什么会出现ACK超时" |
| 时间线分析 | "设备D5最近有什么状态变化" |
| 协议问答 | "DC2和DC3帧的作用是什么" |
| 提取帧数据 | "从日志中提取所有FIR帧" |

## 快速开始

### 1. 分析日志文件

用户提供日志文件路径后：

```
日志文件: ZLEvents260201
码位表: lgxtq.zl
```

执行分析：
```python
from parser import CTCLogAnalyzer, CodePositionTable

cpt = CodePositionTable("lgxtq.zl")
analyzer = CTCLogAnalyzer("ZLEvents260201", cpt)
frames = analyzer.analyze()  # 解析所有帧
analyzer.generate_report("report.txt")
```

### 2. 解析单个帧

用户提供十六进制帧数据：
```
7D 04 11 00 00 8A 03 00 25 10 7E
```

执行解析：
```python
from parser import FrameParser, CodePositionTable

parser = FrameParser(CodePositionTable("lgxtq.zl"))
frame = parser.parse_frame(bytes.fromhex("7D 04 11 00 00 8A 03 00 25 10 7E"))
# frame.frame_type_name → "SDCI"
# frame.device_states → 设备状态列表
```

### 3. 设备时间线分析

```
分析设备D1的状态变化
```

```python
from parser import DeviceTimelineAnalyzer, CodePositionTable

analyzer = DeviceTimelineAnalyzer("ZLEvents260201", cpt)
timeline = analyzer.analyze_device("D1")
analyzer.generate_timeline_report("D1", "d1_timeline.txt")
```

### 4. 故障分析

```
分析日志中的硬件故障
```

```python
from parser import CTCLogHardwareFaultAnalyzer

analyzer = CTCLogHardwareFaultAnalyzer("lgxtcidriver_20260101_1.log")
result = analyzer.analyze()
# result["fault_events"] → 故障事件列表
# result["recovery_events"] → 恢复事件列表
```

## 支持的帧类型

| 类型 | 代码 | 方向 | 说明 |
|------|------|------|------|
| DC2 | 0x12 | CTC→联锁 | 连接请求 |
| DC3 | 0x13 | 联锁→CTC | 连接确认 |
| ACK | 0x06 | 双向 | 应答/心跳 |
| NACK | 0x15 | 双向 | 否定应答 |
| VERROR | 0x10 | 双向 | 版本错误 |
| SDCI | 0x8A | 联锁→CTC | 站场数据变化(增量) |
| SDI | 0x85 | 联锁→CTC | 站场完整数据(全量) |
| SDIQ | 0x6A | CTC→联锁 | 站场数据请求 |
| FIR | 0x65 | 联锁→CTC | 故障信息报告 |
| RSR | 0xAA | 双向 | 系统工作状态报告 |
| BCC | 0x95 | CTC→联锁 | 按钮控制命令 |
| ACQ | 0x75 | 联锁→CTC | 自律控制请求 |
| ACA | 0x7A | CTC→联锁 | 自律控制同意 |
| TSQ | 0x9A | 联锁→CTC | 时间同步请求 |
| TSD | 0xA5 | CTC→联锁 | 时间同步数据 |

## 日志类型

### 联锁日志 (ZLEvents*)
- 格式: `ZLEventsMMDDYY`
- 内容: 联锁系统发送/接收的帧数据
- 标记: `>>[帧类型]` 发送, `<<[帧类型]` 接收

### CTC日志 (lgxtcidriver_*.log)
- 格式: `lgxtcidriver_YYYYMMDD_序号.log`
- 内容: 连接状态、故障检测、主备切换

## 约束

- ACK超时: 500ms
- 故障码参考: `references/Error.sys`
- 码位表参考: `references/lgxtq.zl`

## 常用API

```python
# 解析所有帧类型
from parser import parse_all_frames
frames = parse_all_frames("logfile", "lgxtq.zl")

# 仅解析SDCI帧
from parser import parse_sdci_log
frames = parse_sdci_log("logfile", "lgxtq.zl")

# 分析硬件故障
from parser import analyze_hardware_faults
result = analyze_hardware_faults("lgxtcidriver.log")
```

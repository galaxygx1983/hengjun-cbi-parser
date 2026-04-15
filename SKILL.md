---
name: hengjun-cbi-parser
version: 2.1.0
description: 铁路计算机联锁(CBI)与调度集中(CTC)通信日志分析工具。当用户需要分析亨均联锁系统日志文件(ZLEvents、lgxtcidriver)、解析CBI/CTC通信帧协议(SDCI、SDI、FIR、DC2、DC3、ACK、NACK等)、排查铁路信号故障、查询设备状态(信号机、道岔、无岔区段)、分析通信中断原因、解析故障码、生成设备时间线报告、分析硬件故障日志等相关问题时使用。支持SDCI增量数据帧、SDI全量数据帧、FIR故障报告帧、BCC按钮控制命令帧等铁路专用通信协议的完整解析。
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
github_url: https://github.com/galaxygx1983/hengjun-cbi-parser
github_hash: 0939b1c0
allowed-tools: 
disable: true
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
- 示例: `09:21:51.243 <<[DC2 ]7D 04 11 00 00 12 66 D6 7E`

### CTC日志 (lgxtcidriver_*.log)
- 格式: `lgxtcidriver_YYYYMMDD_序号.log`
- 内容: 连接状态、故障检测、主备切换、帧数据
- 帧数据格式（CVLog输出）：
  - INFO级别: `完整报文: 长度=N 字节, 内容=[XX XX ...]`
  - INFO级别: `DC2帧内容: [XX XX ...]`
  - DEBUG级别: `Timestamp: YYYY-MM-DD HH:MM:SS.MMMMMM, Size: N, Data: XX XX ...`
- 注意：`Data:` 格式仅在DEBUG级别输出，生产环境通常只有INFO级别日志

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

## 模板脚本 (templates/)

技能提供了三个分析模板，可直接修改使用：

### 1. analyze_simple.py - 简单关键字搜索

快速查找日志中的关键字记录，适用于初步排查：

```python
# 修改搜索关键字
keywords = ['未收到ACK', 'Er', 'DC2', 'DC3', '超时', '错误']

# 运行脚本分析最新日志
python templates/analyze_simple.py
```

### 2. analyze_detailed.py - 通信中断详细分析

生成完整的通信中断分析报告，包含：
- ACK超时/未收到ACK错误统计
- DC2连接请求与DC3确认统计
- 中断时间点与重连恢复分析

```bash
# 直接运行，自动分析最新ZLEvents文件
python templates/analyze_detailed.py
```

### 3. analyze_timeline.py - 设备状态时间线分析

分析指定设备的状态变化历史：

```bash
# 分析道岔区段 (设备索引37)
grep -E "8A.*00 25" ZLEvents260201 > device64_frames.txt
python templates/analyze_timeline.py switch device64_frames.txt 37 "道岔区段64"

# 分析信号机 (设备索引66)
grep -E "8A.*00 42" ZLEvents260201 > d12_frames.txt
python templates/analyze_timeline.py signal d12_frames.txt 66 "D12"

# 分析无岔区段
python templates/analyze_timeline.py track ZLEvents260201
```

支持设备类型：
- `switch`: 道岔区段（位置、锁闭、占用状态）
- `signal`: 信号机（颜色、进路转岔、延时解锁）
- `track`: 无岔区段（空闲/占用、锁闭状态）

### 4. analyze_protocol.py - CBI-CTC 通信协议规范检查

检查日志文件是否符合协议规范要求，专注于序号和通信流程分析：

```bash
# 分析日志文件
python templates/analyze_protocol.py ZLEvents260331

# 生成协议检查报告
```

检查内容包括：
- 帧格式验证（帧头 0x7D、帧尾 0x7E、版本号 0x11、CRC-CCITT校验、反转义处理）
- 序号连续性检查（仅数据帧验证，控制帧跳过，与CTC源码 ci_sequencemanager 一致）
- 握手配对检查（DC2/DC3、SDIQ/SDI）
- ACK 响应时间分析
- 通信中断检测（5分钟无通信视为中断）
- 发送超时检测（500ms 无发送视为超时）
- 发送超时检测（500ms 无发送视为超时）

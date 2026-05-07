---
name: hengjun-cbi-parser
version: 2.2.0
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
---

# Hengjun CBI Parser

铁路计算机联锁(CBI)与调度集中(CTC)通信日志分析工具

## 工作流程

### Phase 0: 前置检查

执行任何分析前，先完成以下检查：

```
1. 定位日志文件
   - 联锁日志: 搜索 ZLEvents* 或 Events* 文件
   - CTC日志: 搜索 lgxtcidriver_*.log 文件
   - 典型路径: E:\WorkSpace\站点\ZLEvents\ 或用户提供的路径

2. 确认文件存在
   - 若文件不存在，提示用户提供正确路径
   - 若文件过大(>500MB)，建议先截取关键时间段

3. 确认编码格式
   - ZLEvents: GBK编码
   - lgxtcidriver: UTF-8编码
   - 读取时需指定正确编码避免乱码
```

### Phase 1: 确定分析目标

**🔔 检查点**: 根据用户问题类型选择分析模式

| 用户问题类型 | 分析模式 | 输出内容 |
|-------------|---------|---------|
| "有没有通信中断" | 通信中断分析 | 中断次数、时间、恢复情况 |
| "某个设备状态" | 设备时间线 | 状态变化历史 |
| "帧解析" | 单帧解析 | 帧类型、设备状态 |
| "硬件故障" | 故障分析 | 故障事件、恢复事件 |

### Phase 2: 执行分析

#### 模式A: 通信中断分析（最常用）

```python
# 分析CTC日志中的硬件故障
from templates.hardware_fault_analyzer import CTCLogHardwareFaultAnalyzer

analyzer = CTCLogHardwareFaultAnalyzer("lgxtcidriver_20260507.log")
result = analyzer.analyze()

# 关键指标
fault_count = result['statistics']['total_fault_events']  # 通信中断次数
recovery_count = result['statistics']['total_recovery_events']  # 恢复次数
hw_fault_count = len([e for e in result['fault_events'] if 'hardware_fault' in e['fault_type']])

if hw_fault_count > 0:
    # 🔔 检查点: 发现硬件故障，需要用户确认是否继续深入分析
    print("⚠️ 检测到硬件故障，建议进一步排查")
```

#### 模式B: 设备时间线分析

```python
from templates.analyze_timeline import DeviceTimelineAnalyzer

# 分析道岔/信号机/区段状态变化
analyzer = DeviceTimelineAnalyzer(log_file, code_position_table)
timeline = analyzer.analyze_device("D1")  # 设备名称
```

### Phase 3: 异常处理

| 异常情况 | 处理方式 |
|---------|---------|
| 文件不存在 | 提示用户提供正确路径，列出常见路径格式 |
| 编码错误 | 尝试GBK/UTF-8/GB2312多种编码 |
| 内存不足(大文件) | 分批读取或提示用户使用grep预处理 |
| 分析结果为空 | 检查是否选择了正确的日志文件类型 |

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
- 编码: GBK

### CTC日志 (lgxtcidriver_*.log)
- 格式: `lgxtcidriver_YYYYMMDD_序号.log`
- 内容: 连接状态、故障检测、主备切换、帧数据
- 编码: UTF-8
- 帧数据格式（CVLog输出）：
  - INFO级别: `完整报文: 长度=N 字节, 内容=[XX XX ...]`
  - INFO级别: `DC2帧内容: [XX XX ...]`
  - DEBUG级别: `Timestamp: YYYY-MM-DD HH:MM:SS.MMMMMM, Size: N, Data: XX XX ...`

## 约束

- ACK超时阈值: 500ms（CTC日志中显示1500ms触发中断检测）
- 通信中断定义: 1500ms未收到有效帧
- 故障码参考: `references/Error.sys`
- 码位表参考: `references/lgxtq.zl`

## 模板脚本 (templates/)

### 1. analyze_simple.py - 快速关键字搜索

```bash
# 修改搜索关键字
keywords = ['未收到ACK', 'Er', 'DC2', 'DC3', '超时', '错误']
python templates/analyze_simple.py
```

### 2. analyze_detailed.py - 通信中断详细分析

```bash
python templates/analyze_detailed.py
```

输出包含：
- ACK超时/未收到ACK错误统计
- DC2连接请求与DC3确认统计
- 中断时间点与重连恢复分析

### 3. analyze_timeline.py - 设备状态时间线

```bash
# 道岔区段
grep -E "8A.*00 25" ZLEvents260201 > device64_frames.txt
python templates/analyze_timeline.py switch device64_frames.txt 37 "道岔区段64"

# 信号机
grep -E "8A.*00 42" ZLEvents260201 > d12_frames.txt
python templates/analyze_timeline.py signal d12_frames.txt 66 "D12"
```

### 4. analyze_protocol.py - 协议规范检查

```bash
python templates/analyze_protocol.py ZLEvents260331
```

检查内容：
- 帧格式（帧头0x7D、帧尾0x7E、版本0x11）
- 序号连续性（仅数据帧，控制帧跳过）
- 握手配对（DC2/DC3、SDIQ/SDI）
- ACK响应时间（500ms阈值）
- 通信中断（5分钟无通信）

## 输出格式

完成分析后，按以下格式输出报告：

```
## {分析类型}报告

### 总体统计
- 总帧数: N
- 中断次数: N
- 恢复次数: N

### 详细分析
[具体数据]

### 结论
[基于数据的判断]

### 建议（如有）
[后续行动建议]
```

# Python API 使用说明

> **本文档定位**：详细说明Python API的使用方法，包括码位表加载、日志分析、帧解析、状态解码、数据导出和性能优化等。

## 文档体系关联

| 阶段 | 文档 | 说明 |
|------|------|------|
| 概览 | [01-overview.md](./01-overview.md) | 系统架构和核心概念 |
| 帧格式 | [02-frame-formats.md](./02-frame-formats.md) | 帧类型和结构 |
| 协议定义 | [09-protocol-schema.md](./09-protocol-schema.md) | JSON Schema定义 |
| **本文档** | **10-api-usage.md** | **Python API使用说明（本文档）** |

## 核心模块概览

### 主要类和函数

```python
from hengjun_cbi_parser import (
    # 核心解析类
    CodePositionTable,      # 码位表解析
    CTCLogAnalyzer,        # 日志分析器
    SDCIFrameParser,       # SDCI帧解析器
    SDIFrameParser,        # SDI帧解析器
    
    # 状态解码器
    StateDecoder,          # 设备状态解码
    
    # 分析工具
    analyze_ack_errors,    # ACK错误分析
    CTCLogHardwareFaultAnalyzer,  # 硬件故障分析
    
    # 导出工具
    export_to_json,        # JSON导出
    generate_report        # 报告生成
)
```

## 基础用法

### 1. 码位表加载

```python
from hengjun_cbi_parser import CodePositionTable

# 加载码位表文件
cpt = CodePositionTable("lgxtq.zl")

# 查看设备信息
print(f"总设备数: {len(cpt.objects)}")
print(f"objects表设备数: {len(cpt.objects)}")
print(f"zlobjects表设备数: {len(cpt.zlobjects)}")

# 查找特定设备
device = cpt.get_device_by_name("64")
if device:
    print(f"设备64: 索引={device.index}, 类型={device.device_type}")

# 按索引查找设备
device = cpt.get_device_by_index(37)
if device:
    print(f"索引37: 设备名={device.name}, 类型={device.device_type}")
```

### 2. 日志文件分析

```python
from hengjun_cbi_parser import CTCLogAnalyzer

# 创建分析器
cpt = CodePositionTable("lgxtq.zl")
analyzer = CTCLogAnalyzer("ZLEvents260201", cpt)

# 分析日志
frames = analyzer.analyze()

print(f"解析到 {len(frames)} 个帧")

# 按帧类型统计
frame_stats = {}
for frame in frames:
    frame_type = frame.frame_type
    frame_stats[frame_type] = frame_stats.get(frame_type, 0) + 1

for frame_type, count in sorted(frame_stats.items()):
    print(f"{frame_type}: {count} 个")
```

### 3. 单帧解析

```python
from hengjun_cbi_parser import SDCIFrameParser

# 创建解析器
cpt = CodePositionTable("lgxtq.zl")
parser = SDCIFrameParser(cpt)

# 解析十六进制帧数据
frame_hex = "7D041165BF8A030000B71028817E"
frame_data = bytes.fromhex(frame_hex)

# 解析帧
frame = parser.parse_frame(frame_data, timestamp="2026-02-01 00:00:03")

# 访问帧信息
print(f"帧类型: {frame.frame_type}")
print(f"发送序号: 0x{frame.send_seq:02X}")
print(f"确认序号: 0x{frame.ack_seq:02X}")
print(f"数据长度: {frame.data_length} 字节")
print(f"变化设备数: {len(frame.device_states)}")

# 访问设备状态
for ds in frame.device_states:
    print(f"设备: {ds.device.name}")
    print(f"  索引: {ds.device.index}")
    print(f"  原始状态: 0x{ds.raw_state:02X}")
    print(f"  解码状态: {ds.decoded_state}")
```

## 高级用法

### 1. 设备状态解码

```python
from hengjun_cbi_parser import StateDecoder

# 创建解码器
decoder = StateDecoder()

# 解码道岔区段状态
switch_state = decoder.decode_switch_section(0x19)
print("道岔区段状态:")
print(f"  位置: {switch_state['positions']}")
print(f"  区段占用: {switch_state['section_occupied']}")
print(f"  区段锁闭: {switch_state['section_locked']}")
print(f"  道岔锁闭: {switch_state['switch_locked']}")

# 解码信号机状态
signal_state = decoder.decode_signal(0x42)
print("信号机状态:")
print(f"  颜色: {signal_state['colors']}")
print(f"  进路转岔中: {signal_state['route_switching']}")
print(f"  延时解锁: {signal_state['delayed_unlock']}")

# 解码无岔区段状态
track_state = decoder.decode_track_section(0x03, bit_offset=0)
print("无岔区段状态:")
print(f"  占用: {track_state['occupied']}")
print(f"  锁闭: {track_state['locked']}")
```

### 2. 批量设备分析

```python
from hengjun_cbi_parser import CTCLogAnalyzer, CodePositionTable

def analyze_all_switches(log_file, code_table_file):
    """分析所有道岔区段的状态变化"""
    
    cpt = CodePositionTable(code_table_file)
    analyzer = CTCLogAnalyzer(log_file, cpt)
    frames = analyzer.analyze()
    
    # 按设备分组统计
    device_stats = {}
    
    for frame in frames:
        if frame.frame_type == "SDCI":
            for ds in frame.device_states:
                device = ds.device
                if device.device_type == "switch_section":
                    if device.name not in device_stats:
                        device_stats[device.name] = {
                            'total_changes': 0,
                            'states': {},
                            'first_time': frame.timestamp,
                            'last_time': frame.timestamp
                        }
                    
                    stats = device_stats[device.name]
                    stats['total_changes'] += 1
                    stats['last_time'] = frame.timestamp
                    
                    state_key = f"0x{ds.raw_state:02X}"
                    stats['states'][state_key] = stats['states'].get(state_key, 0) + 1
    
    return device_stats

# 使用示例
stats = analyze_all_switches("ZLEvents260201", "lgxtq.zl")

for device_name, stat in stats.items():
    print(f"\n设备: {device_name}")
    print(f"  状态变化次数: {stat['total_changes']}")
    print(f"  时间范围: {stat['first_time']} - {stat['last_time']}")
    print("  状态分布:")
    for state, count in sorted(stat['states'].items()):
        print(f"    {state}: {count} 次")
```

### 3. ACK错误分析

```python
from hengjun_cbi_parser import analyze_ack_errors

# 分析ACK错误
error_records, error_stats = analyze_ack_errors("ZLEvents260201")

print(f"总ACK错误数: {len(error_records)}")
print("\n按帧类型统计:")
for frame_type, count in sorted(error_stats.items(), key=lambda x: -x[1]):
    print(f"  {frame_type}: {count} 次")

print("\n错误详情 (前10条):")
for i, record in enumerate(error_records[:10], 1):
    print(f"{i:2d}. {record['time']} - {record['frame_type']} - {record['description']}")

# 分析错误时间分布
from collections import defaultdict
import datetime

hourly_errors = defaultdict(int)
for record in error_records:
    try:
        time_obj = datetime.datetime.strptime(record['time'], '%H:%M:%S')
        hour = time_obj.hour
        hourly_errors[hour] += 1
    except ValueError:
        continue

print("\n按小时统计错误:")
for hour in sorted(hourly_errors.keys()):
    print(f"  {hour:02d}:00 - {hourly_errors[hour]} 次")
```

### 4. 硬件故障分析

```python
from hengjun_cbi_parser import CTCLogHardwareFaultAnalyzer

# 创建硬件故障分析器
fault_analyzer = CTCLogHardwareFaultAnalyzer("ZLEvents260201")

# 分析硬件故障
fault_records = fault_analyzer.analyze()

print(f"检测到 {len(fault_records)} 个硬件故障")

# 按故障类型分类
fault_types = {}
for record in fault_records:
    fault_type = record.get('fault_type', 'unknown')
    fault_types[fault_type] = fault_types.get(fault_type, 0) + 1

print("\n故障类型分布:")
for fault_type, count in sorted(fault_types.items()):
    print(f"  {fault_type}: {count} 次")

# 显示故障详情
print("\n故障详情:")
for i, record in enumerate(fault_records[:5], 1):
    print(f"{i}. {record['time']} - {record['fault_type']}")
    print(f"   描述: {record['description']}")
    if 'affected_devices' in record:
        print(f"   影响设备: {', '.join(record['affected_devices'])}")
```

## 数据导出

### 1. JSON导出

```python
from hengjun_cbi_parser import export_to_json, CTCLogAnalyzer

# 分析日志
cpt = CodePositionTable("lgxtq.zl")
analyzer = CTCLogAnalyzer("ZLEvents260201", cpt)
frames = analyzer.analyze()

# 导出为JSON
export_to_json(frames, "analysis_result.json")

# 自定义JSON导出
import json

def export_device_timeline(frames, device_name, output_file):
    """导出特定设备的状态时间线"""
    
    timeline = []
    for frame in frames:
        if frame.frame_type == "SDCI":
            for ds in frame.device_states:
                if ds.device.name == device_name:
                    timeline.append({
                        'timestamp': frame.timestamp.isoformat(),
                        'device_name': ds.device.name,
                        'device_index': ds.device.index,
                        'raw_state': ds.raw_state,
                        'decoded_state': ds.decoded_state
                    })
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)
    
    print(f"导出 {len(timeline)} 条记录到 {output_file}")

# 使用示例
export_device_timeline(frames, "64", "device64_timeline.json")
```

### 2. 报告生成

```python
from hengjun_cbi_parser import generate_report

# 生成文本报告
def generate_custom_report(frames, output_file):
    """生成自定义分析报告"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("CBI-CTC 通信分析报告\n")
        f.write("=" * 50 + "\n\n")
        
        # 基本统计
        f.write(f"总帧数: {len(frames)}\n")
        
        frame_stats = {}
        device_changes = {}
        
        for frame in frames:
            # 帧类型统计
            frame_type = frame.frame_type
            frame_stats[frame_type] = frame_stats.get(frame_type, 0) + 1
            
            # 设备变化统计
            if frame.frame_type == "SDCI":
                for ds in frame.device_states:
                    device_name = ds.device.name
                    device_changes[device_name] = device_changes.get(device_name, 0) + 1
        
        f.write("\n帧类型分布:\n")
        for frame_type, count in sorted(frame_stats.items()):
            f.write(f"  {frame_type}: {count} 个\n")
        
        f.write(f"\n设备状态变化统计 (前10个):\n")
        top_devices = sorted(device_changes.items(), key=lambda x: -x[1])[:10]
        for device_name, count in top_devices:
            f.write(f"  {device_name}: {count} 次变化\n")
        
        # 时间范围
        if frames:
            first_time = frames[0].timestamp
            last_time = frames[-1].timestamp
            f.write(f"\n时间范围: {first_time} - {last_time}\n")
    
    print(f"报告已生成: {output_file}")

# 使用示例
generate_custom_report(frames, "custom_analysis_report.txt")
```

## 性能优化

### 1. 大文件处理

```python
from hengjun_cbi_parser import CTCLogAnalyzer

class StreamingLogAnalyzer:
    """流式日志分析器，适用于大文件"""
    
    def __init__(self, log_file, code_table):
        self.log_file = log_file
        self.cpt = CodePositionTable(code_table)
        self.parser = SDCIFrameParser(self.cpt)
    
    def analyze_streaming(self, callback=None, batch_size=1000):
        """流式分析，避免内存溢出"""
        
        frames = []
        line_count = 0
        
        with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_count += 1
                
                # 解析行
                frame = self._parse_line(line)
                if frame:
                    frames.append(frame)
                
                # 批量处理
                if len(frames) >= batch_size:
                    if callback:
                        callback(frames)
                    frames = []
                
                # 进度报告
                if line_count % 10000 == 0:
                    print(f"已处理 {line_count} 行")
        
        # 处理剩余帧
        if frames and callback:
            callback(frames)
    
    def _parse_line(self, line):
        """解析单行日志"""
        # 实现具体的行解析逻辑
        # 这里简化处理
        if "SDCI" in line:
            # 提取帧数据并解析
            pass
        return None

# 使用示例
def process_batch(frames):
    """批量处理回调函数"""
    print(f"处理批次: {len(frames)} 个帧")
    # 在这里处理帧数据

analyzer = StreamingLogAnalyzer("large_log_file.txt", "lgxtq.zl")
analyzer.analyze_streaming(callback=process_batch, batch_size=500)
```

### 2. 并行处理

```python
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from hengjun_cbi_parser import CTCLogAnalyzer

def analyze_log_chunk(args):
    """分析日志文件块"""
    chunk_file, code_table_file, start_line, end_line = args
    
    # 读取指定行范围
    lines = []
    with open(chunk_file, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f, 1):
            if start_line <= i <= end_line:
                lines.append(line)
            elif i > end_line:
                break
    
    # 分析这个块
    # 这里简化处理，实际需要实现具体逻辑
    return len(lines)

def parallel_analysis(log_file, code_table_file, num_processes=4):
    """并行分析大日志文件"""
    
    # 计算文件行数
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        total_lines = sum(1 for _ in f)
    
    # 分割任务
    chunk_size = total_lines // num_processes
    tasks = []
    
    for i in range(num_processes):
        start_line = i * chunk_size + 1
        end_line = (i + 1) * chunk_size if i < num_processes - 1 else total_lines
        tasks.append((log_file, code_table_file, start_line, end_line))
    
    # 并行执行
    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        results = list(executor.map(analyze_log_chunk, tasks))
    
    print(f"并行处理完成，总共处理 {sum(results)} 行")
    return results

# 使用示例
results = parallel_analysis("large_log.txt", "lgxtq.zl", num_processes=4)
```

## 错误处理

### 1. 异常处理最佳实践

```python
from hengjun_cbi_parser import CTCLogAnalyzer, CodePositionTable
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def safe_analysis(log_file, code_table_file):
    """安全的日志分析，包含完整错误处理"""
    
    try:
        # 加载码位表
        logger.info(f"加载码位表: {code_table_file}")
        cpt = CodePositionTable(code_table_file)
        logger.info(f"成功加载 {len(cpt.objects)} 个设备")
        
    except FileNotFoundError:
        logger.error(f"码位表文件不存在: {code_table_file}")
        return None
    except Exception as e:
        logger.error(f"加载码位表失败: {e}")
        return None
    
    try:
        # 分析日志
        logger.info(f"开始分析日志: {log_file}")
        analyzer = CTCLogAnalyzer(log_file, cpt)
        frames = analyzer.analyze()
        logger.info(f"成功解析 {len(frames)} 个帧")
        
        return frames
        
    except FileNotFoundError:
        logger.error(f"日志文件不存在: {log_file}")
        return None
    except UnicodeDecodeError as e:
        logger.error(f"文件编码错误: {e}")
        logger.info("尝试使用其他编码...")
        # 尝试其他编码
        return None
    except Exception as e:
        logger.error(f"分析失败: {e}")
        return None

# 使用示例
frames = safe_analysis("ZLEvents260201", "lgxtq.zl")
if frames:
    print(f"分析成功，共 {len(frames)} 个帧")
else:
    print("分析失败")
```

### 2. 数据验证

```python
def validate_frame_data(frame):
    """验证帧数据的完整性"""
    
    errors = []
    
    # 检查必要字段
    if not hasattr(frame, 'frame_type'):
        errors.append("缺少帧类型")
    
    if not hasattr(frame, 'timestamp'):
        errors.append("缺少时间戳")
    
    # 检查CRC
    if hasattr(frame, 'crc_valid') and not frame.crc_valid:
        errors.append("CRC校验失败")
    
    # 检查设备状态
    if frame.frame_type == "SDCI":
        if not hasattr(frame, 'device_states'):
            errors.append("SDCI帧缺少设备状态")
        else:
            for ds in frame.device_states:
                if not hasattr(ds, 'device') or not hasattr(ds, 'raw_state'):
                    errors.append(f"设备状态数据不完整")
    
    return errors

# 使用示例
def analyze_with_validation(log_file, code_table_file):
    """带数据验证的分析"""
    
    cpt = CodePositionTable(code_table_file)
    analyzer = CTCLogAnalyzer(log_file, cpt)
    frames = analyzer.analyze()
    
    valid_frames = []
    invalid_count = 0
    
    for frame in frames:
        errors = validate_frame_data(frame)
        if errors:
            invalid_count += 1
            logger.warning(f"帧验证失败 {frame.timestamp}: {', '.join(errors)}")
        else:
            valid_frames.append(frame)
    
    logger.info(f"有效帧: {len(valid_frames)}, 无效帧: {invalid_count}")
    return valid_frames
```

---

**相关文档**:
- 帧格式详解 → [02-frame-formats.md](./02-frame-formats.md)
- 设备分析指南 → [06-device-analysis.md](./06-device-analysis.md)
- 故障排除指南 → [07-interlocking-troubleshooting.md](./07-interlocking-troubleshooting.md)
- 协议定义 → [09-protocol-schema.md](./09-protocol-schema.md)

---

*最后更新: 2026-02-11*
# 联锁日志故障排除指南

> **本文档定位**：专门用于通过联锁系统日志（ZLEvents）分析和解决通信问题，包含常见故障诊断、性能优化和高级分析技术。

## 文档体系关联

| 阶段 | 文档 | 说明 |
|------|------|------|
| 概览 | [01-overview.md](./01-overview.md) | 系统架构和核心概念 |
| 帧格式 | [02-frame-formats.md](./02-frame-formats.md) | 帧类型和结构 |
| 机制 | [03-protocol-mechanisms.md](./03-protocol-mechanisms.md) | 超时、序号、主备 |
| 流程 | [04-communication-process.md](./04-communication-process.md) | 完整通信流程 |
| 工作流 | [05-workflow.md](./05-workflow.md) | 完整分析工作流 |
| 设备 | [06-device-analysis.md](./06-device-analysis.md) | 设备状态解码 |
| **本文档** | **07-interlocking-troubleshooting.md** | **联锁日志故障排查（本文档）** |
| CTC分析 | [08-ctc-analysis.md](./08-ctc-analysis.md) | CTC驱动日志分析 |

## 常见问题诊断

### 1. "未收到ACK" 错误

#### 问题描述
日志中频繁出现 "未收到ACK" 错误，影响通信稳定性。

#### 典型日志模式
```
00:00:02 >> [RSR] 7D 04 11 01 00 AA 02 00 55 55 51 24 7E
00:00:16 Er未收到ACK
```

#### 诊断步骤

**步骤1: 统计错误分布**
```bash
# 统计各帧类型的ACK错误
awk '/>>\[.*\]/{last=$0} /未收到ACK/{print last}' ZLEvents260201 | \
  grep -oP '(?<=\[)[A-Z]+(?=\s*\])' | sort | uniq -c | sort -rn

# 典型输出:
#  45 RSR     ← RSR帧错误最多
#  23 SDCI    ← SDCI帧错误次之
#   8 FIR     ← FIR帧错误较少
```

**步骤2: 分析错误模式**

| 错误模式 | 可能原因 | 解决方案 |
|----------|----------|----------|
| **RSR错误100%** | CTC不响应状态报告 | 检查CTC应用程序 |
| **SDCI错误67%** | CTC处理能力不足 | 优化CTC性能 |
| **所有帧错误** | 网络连接问题 | 检查物理连接 |

**步骤3: 时序分析**
```bash
# 检查错误发生的时间模式
grep "未收到ACK" ZLEvents260201 | awk '{print $1}' | \
  awk -F: '{print $1":"$2}' | sort | uniq -c

# 查找高峰时段
# 如果错误集中在特定时间，可能是负载问题
```

#### 解决方案

**网络层面**:
- 检查RS422电缆连接
- 验证屏蔽接地（CTC侧接地，CBI侧悬浮）
- 测试信号质量和波特率设置

**应用层面**:
- 检查CTC应用程序响应能力
- 监控系统资源使用情况
- 优化数据处理流程

**⚠️ 错误做法**:
- 不要修改500ms ACK超时值（协议固定）
- 不要增加重试次数
- 不要调整心跳间隔

### 2. SDIQ "长等待时间"

#### 问题描述
日志显示SDIQ需要等待很长时间，用户担心异常。

#### 典型日志
```
距离下次SDIQ发送还需等待63632902ms  (17.6 hours)
```

#### 解释
**这是正常现象**：
- SDIQ每24小时发送一次
- 用于日常数据同步
- 不是错误或故障

#### 验证方法
```bash
# 检查SDIQ发送间隔
grep "SDIQ" ZLEvents260201 | awk '{print $1}' | \
  awk 'NR>1{print $1, prev, "间隔:", $1-prev, "秒"} {prev=$1}'

# 正常情况下应该看到约24小时（86400秒）的间隔
```

### 3. DC2/DC3 频繁重试

#### 问题描述
连接握手成功，但随后立即出现数据传输失败。

#### 典型日志模式
```
00:00:02 << [DC2] 7D 04 11 65 BF 12 00 00 12 34 7E
00:00:02 >> [DC3] 7D 04 11 BF 65 13 00 00 56 78 7E
00:00:02 >> [RSR] 7D 04 11 01 00 AA 02 00 55 55 51 24 7E
00:00:16 Er未收到ACK
```

#### 分析
- **握手成功** → 物理层正常
- **数据立即失败** → 逻辑层问题
- **可能原因** → CTC应用程序处理问题

#### 诊断步骤

**步骤1: 验证握手成功率**
```bash
# 统计DC2/DC3配对
grep -E "(DC2|DC3)" ZLEvents260201 | \
  awk '/DC2/{dc2++} /DC3/{dc3++} END{print "DC2:", dc2, "DC3:", dc3, "成功率:", dc3/dc2*100"%"}'
```

**步骤2: 检查握手后立即失败**
```bash
# 查找握手后立即失败的模式
awk '/DC3/{print; getline; if(/未收到ACK/) print "立即失败: " $0}' ZLEvents260201
```

**步骤3: 分析失败的帧类型**
```bash
# 统计握手后失败的帧类型
awk '/DC3/{getline; if(/>>\[.*\]/) {getline; if(/未收到ACK/) print prev}} {prev=$0}' ZLEvents260201 | \
  grep -oP '(?<=\[)[A-Z]+(?=\s*\])' | sort | uniq -c
```

#### 解决方案
- 检查CTC应用程序日志
- 验证CTC系统资源
- 检查数据处理逻辑
- 监控网络延迟

### 4. 设备状态解析错误

#### 问题描述
设备状态值超出预期范围，无法正确解析。

#### 常见错误状态

**道岔区段异常状态**:
```python
# 状态值 0x19 = 二进制 0001 1001
# bit 0 = 1: 定位
# bit 3 = 1: 无表示  
# bit 4 = 1: 占用
# 结果: 占用 + 定位 + 无表示 (位置冲突)
```

#### 诊断方法

**步骤1: 状态值分析**
```python
def analyze_abnormal_state(state_value):
    print(f"状态值: 0x{state_value:02X} (二进制: {state_value:08b})")
    
    # 道岔区段解析
    if state_value & 0x01: print("  bit 0: 定位")
    if state_value & 0x02: print("  bit 1: 反位")
    if state_value & 0x04: print("  bit 2: 无表示")
    if state_value & 0x08: print("  bit 3: 区段锁闭")
    if state_value & 0x10: print("  bit 4: 区段占用")
    if state_value & 0x20: print("  bit 5: 道岔锁闭")
    
    # 检查异常组合
    position_bits = state_value & 0x07
    if bin(position_bits).count('1') > 1:
        print("  ⚠️ 异常: 位置冲突")

# 示例
analyze_abnormal_state(0x19)
```

**步骤2: 历史状态对比**
```bash
# 提取设备的所有状态值
grep -E "8A.*00 25" ZLEvents260201 | \
  grep -oP '00 25 \K[0-9A-F]{2}' | sort | uniq -c | sort -rn

# 分析状态分布，识别异常值
```

#### 解决方案
- 检查设备硬件状态
- 验证传感器工作正常
- 分析状态变化时序
- 对比双机状态一致性

### 5. 数据提取问题

#### 问题1: grep 找不到设备帧

**症状**: `grep -E "8A.*00 25"` 返回空结果

**原因**: 设备索引计算错误

**解决步骤**:
```bash
# 1. 确认设备索引
grep "^,64," lgxtq.zl
# 输出: #,64,37  ← 索引是37

# 2. 转换为十六进制
python -c "print(f'索引37 = 0x{37:02X}')"
# 输出: 索引37 = 0x25

# 3. 验证SDCI帧存在
grep "8A" ZLEvents260201 | head -3
# 如果无输出，说明日志中没有SDCI帧

# 4. 正确的grep命令
grep -E "8A.*00 25" ZLEvents260201
```

#### 问题2: Unicode 编码错误

**症状**: `UnicodeDecodeError: 'utf-8' codec can't decode byte`

**解决方案**:
```python
# 使用错误忽略模式读取文件
with open('ZLEvents260201', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# 或者尝试其他编码
encodings = ['utf-8', 'gbk', 'gb2312', 'latin1']
for encoding in encodings:
    try:
        with open('ZLEvents260201', 'r', encoding=encoding) as f:
            content = f.read()
        print(f"成功使用编码: {encoding}")
        break
    except UnicodeDecodeError:
        continue
```

#### 问题3: 时间范围不连续

**症状**: 状态记录时间有间隔，怀疑数据丢失

**分析方法**:
```bash
# 1. 检查日志文件完整性
wc -l ZLEvents260201
ls -lh ZLEvents260201

# 2. 分析时间间隔
grep -E "8A.*00 25" ZLEvents260201 | awk '{print $1}' > timestamps.txt

# 3. 计算时间间隔
python -c "
import datetime
with open('timestamps.txt') as f:
    times = [line.strip() for line in f if line.strip()]

for i in range(1, len(times)):
    try:
        t1 = datetime.datetime.strptime(times[i-1], '%H:%M:%S')
        t2 = datetime.datetime.strptime(times[i], '%H:%M:%S')
        diff = (t2 - t1).seconds
        if diff > 300:  # 超过5分钟
            print(f'长间隔: {times[i-1]} -> {times[i]} ({diff}秒)')
    except ValueError as e:
        print(f'时间格式错误: {times[i-1]} 或 {times[i]}')
"
```

## 性能问题诊断

### 1. 日志文件过大

#### 问题描述
日志文件几GB大小，处理速度慢。

#### 优化方案

**分段处理**:
```bash
# 按时间段分割日志
awk '/^00:/{hour=substr($1,1,2)} hour=="00"{print > "log_00.txt"} hour=="01"{print > "log_01.txt"}' ZLEvents260201

# 按帧类型分割
grep "8A" ZLEvents260201 > sdci_frames.txt
grep "AA" ZLEvents260201 > rsr_frames.txt
```

**并行处理**:
```bash
# 使用GNU parallel并行处理
parallel -j4 'python analyze_timeline.py switch {} {#} "设备{#}"' ::: device*_frames.txt
```

### 2. 内存使用过高

#### 问题描述
Python脚本处理大文件时内存不足。

#### 优化方案

**流式处理**:
```python
def process_large_file(filename):
    """流式处理大文件，避免内存溢出"""
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        for line_num, line in enumerate(f, 1):
            if line_num % 10000 == 0:
                print(f"已处理 {line_num} 行")
            
            # 处理单行
            if 'SDCI' in line:
                process_sdci_line(line)
            
            # 定期清理内存
            if line_num % 50000 == 0:
                import gc
                gc.collect()
```

**分批处理**:
```python
def process_in_batches(records, batch_size=1000):
    """分批处理记录"""
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        process_batch(batch)
        
        # 清理内存
        del batch
        import gc
        gc.collect()
```

## 故障排除工具

### 1. 快速诊断脚本

```bash
#!/bin/bash
# quick_diagnosis.sh - 快速诊断脚本

echo "=== CBI-CTC 通信诊断 ==="
echo

# 1. 检查日志文件
echo "1. 日志文件信息:"
ls -lh ZLEvents* 2>/dev/null || echo "  未找到日志文件"
echo

# 2. 统计帧类型
echo "2. 帧类型分布:"
grep -oP '\[[A-Z]+\]' ZLEvents* 2>/dev/null | sort | uniq -c | sort -rn
echo

# 3. ACK错误统计
echo "3. ACK错误统计:"
grep "未收到ACK" ZLEvents* 2>/dev/null | wc -l
echo

# 4. 连接状态
echo "4. 连接握手:"
grep -E "(DC2|DC3)" ZLEvents* 2>/dev/null | tail -10
echo

# 5. 最近错误
echo "5. 最近错误:"
grep -E "(Er|错误|异常)" ZLEvents* 2>/dev/null | tail -5
```

### 2. 状态一致性检查

```python
#!/usr/bin/env python3
# consistency_check.py - 双机状态一致性检查

import sys
from collections import defaultdict

def check_consistency(file1, file2, device_index):
    """检查两个主机的设备状态一致性"""
    
    def extract_states(filename):
        states = {}
        hex_index = f"{device_index:04X}"
        pattern = f"8A.*{hex_index[:2]} {hex_index[2:]}"
        
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if pattern in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        time = parts[0]
                        # 提取状态值（假设在特定位置）
                        for i, part in enumerate(parts):
                            if part == hex_index[2:] and i+1 < len(parts):
                                state = int(parts[i+1], 16)
                                states[time] = state
                                break
        return states
    
    states1 = extract_states(file1)
    states2 = extract_states(file2)
    
    # 找到共同时间点
    common_times = set(states1.keys()) & set(states2.keys())
    
    differences = []
    for time in sorted(common_times):
        if states1[time] != states2[time]:
            differences.append({
                'time': time,
                'host1': states1[time],
                'host2': states2[time]
            })
    
    print(f"共同时间点: {len(common_times)}")
    print(f"状态差异: {len(differences)}")
    
    if differences:
        print("\n状态不一致详情:")
        for diff in differences[:10]:  # 显示前10个
            print(f"  {diff['time']}: 主机1=0x{diff['host1']:02X}, 主机2=0x{diff['host2']:02X}")
    else:
        print("✓ 双机状态完全一致")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("用法: python consistency_check.py <主机1日志> <主机2日志> <设备索引>")
        sys.exit(1)
    
    check_consistency(sys.argv[1], sys.argv[2], int(sys.argv[3]))
```

### 3. 网络质量测试

```bash
#!/bin/bash
# network_quality.sh - 网络质量测试

echo "=== 网络质量诊断 ==="

# 1. ACK错误率
total_frames=$(grep -c ">>" ZLEvents260201)
ack_errors=$(grep -c "未收到ACK" ZLEvents260201)
error_rate=$(echo "scale=2; $ack_errors * 100 / $total_frames" | bc)

echo "总帧数: $total_frames"
echo "ACK错误: $ack_errors"
echo "错误率: $error_rate%"

# 2. 错误时间分布
echo -e "\n错误时间分布:"
grep "未收到ACK" ZLEvents260201 | awk '{print substr($1,1,2)}' | sort | uniq -c

# 3. 连接中断检测
echo -e "\n连接中断检测:"
awk '/DC2/{dc2_time=$1} /DC3/{if(dc2_time) {print "握手成功:", dc2_time, "->", $1; dc2_time=""}}' ZLEvents260201 | tail -5

# 4. 建议
if (( $(echo "$error_rate > 5" | bc -l) )); then
    echo -e "\n⚠️ 建议:"
    echo "  - 错误率过高，检查物理连接"
    echo "  - 验证电缆和接地"
    echo "  - 检查CTC应用程序性能"
else
    echo -e "\n✓ 网络质量良好"
fi
```

## 最佳实践

### 1. 预防性维护

**定期检查项目**:
- 每日检查ACK错误率
- 每周分析设备状态异常
- 每月检查双机一致性
- 每季度验证网络质量

**监控脚本**:
```bash
# daily_check.sh
#!/bin/bash
DATE=$(date +%Y%m%d)
LOG_FILE="health_check_$DATE.log"

{
    echo "=== 日常健康检查 $(date) ==="
    
    # ACK错误率
    ack_errors=$(grep -c "未收到ACK" ZLEvents* 2>/dev/null)
    echo "ACK错误数: $ack_errors"
    
    # 异常状态
    python -c "
import re
with open('ZLEvents260201', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()
    abnormal = re.findall(r'8A.*00 25 (1[9A-F]|[2-9A-F][0-9A-F])', content)
    print(f'异常状态数: {len(abnormal)}')
    "
    
    # 建议
    if [ $ack_errors -gt 10 ]; then
        echo "⚠️ 建议检查网络连接"
    else
        echo "✓ 通信状态正常"
    fi
    
} | tee $LOG_FILE
```

### 2. 故障响应流程

**故障等级定义**:

| 等级 | 条件 | 响应时间 | 处理方式 |
|------|------|----------|----------|
| **严重** | ACK错误率>20% | 立即 | 检查物理连接 |
| **警告** | 设备状态异常>50个 | 1小时内 | 分析设备状态 |
| **提醒** | 双机状态不一致 | 4小时内 | 检查同步机制 |

**响应检查清单**:
1. ✅ 检查日志文件完整性
2. ✅ 统计错误分布和模式
3. ✅ 验证物理连接状态
4. ✅ 检查应用程序日志
5. ✅ 测试网络质量
6. ✅ 对比双机状态
7. ✅ 记录处理过程和结果

---

**相关文档**:
- 帧格式详解 → [02-frame-formats.md](./02-frame-formats.md)
- 设备分析指南 → [06-device-analysis.md](./06-device-analysis.md)
- CTC日志分析 → [08-ctc-analysis.md](./08-ctc-analysis.md)
- 协议机制 → [03-protocol-mechanisms.md](./03-protocol-mechanisms.md)

---

*最后更新: 2026-02-11*

### A. ACK错误深度分析

#### A.1 日志格式

**联锁日志典型格式**：
- 帧数据行：`HH:MM:SS >>[帧类型] 帧数据`
- 错误行：`HH:MM:SS Er未收到ACK`

#### A.2 分析方法

```python
import re
from collections import defaultdict

# 日志解析正则
frame_pattern = re.compile(r'(\d{2}:\d{2}:\d{2})\s+>>[^\[]*\[(\w+)\s*\](.+)')
error_pattern = re.compile(r'(\d{2}:\d{2}:\d{2})\s+Er.*ACK')

def analyze_ack_errors(log_file_path):
    """分析ACK错误并识别问题帧类型"""
    error_records = []
    frame_stats = defaultdict(int)
    
    with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # 检查ACK错误
        error_match = error_pattern.search(line)
        if error_match:
            error_time = error_match.group(1)
            
            # 向前查找最多10行以获取关联帧
            prev_frames = []
            for j in range(max(0, i-10), i):
                prev_line = lines[j].strip()
                frame_match = frame_pattern.search(prev_line)
                if frame_match:
                    frame_time, frame_type, frame_data = frame_match.groups()
                    prev_frames.append({
                        'time': frame_time,
                        'type': frame_type,
                        'data': frame_data.strip()
                    })
            
            if prev_frames:
                # 错误前的最后一个帧即为问题帧
                last_frame = prev_frames[-1]
                error_records.append({
                    'error_time': error_time,
                    'frame_time': last_frame['time'],
                    'frame_type': last_frame['type'],
                    'frame_data': last_frame['data']
                })
                frame_stats[last_frame['type']] += 1
    
    return error_records, frame_stats

# 使用示例
log_file = "ZLEvents260201"  # 联锁日志文件
records, stats = analyze_ack_errors(log_file)

print(f"总ACK错误数: {len(records)}")
print("帧类型分布:")
for frame_type, count in sorted(stats.items(), key=lambda x: -x[1]):
    print(f"  {frame_type}: {count}")
```

#### A.3 预期结果

**联锁主机1**：
| 指标 | 数值 |
|------|------|
| 总错误数 | ~37 |
| 帧类型 | 100% RSR (0xAA) |
| 模式 | 所有ACK错误均由RSR帧引起 |

**联锁主机2**：
| 指标 | 数值 |
|------|------|
| 总错误数 | ~21 |
| 帧类型 | 67% SDCI (0x8A), 24% RSR (0xAA), 9% FIR (0x65) |
| 模式 | 多帧类型混合导致ACK错误 |

#### A.4 导致ACK错误的帧类型

| 帧类型 | 代码 | 描述 | ACK错误率 |
|--------|------|------|----------|
| RSR | 0xAA | 状态报告 | 主机1: 100%, 主机2: 24% |
| SDCI | 0x8A | 站场数据变化 | 主机2: 67% |
| FIR | 0x65 | 故障信息报告 | 主机2: 9% |
| ACK | 0x06 | 应答 | 很少出错 |
| SDI | 0x85 | 站场数据 | 很少出错 |

#### A.5 关键发现

1. **RSR帧** 是主机1 ACK错误的主要原因
2. **主机2** 有更多样化的错误帧类型，SDCI占主导
3. **示例**: 04:42:57 的错误由SDCI引起: `7D 04 11 13 08 8A 03 00 00 D4 30 C4 20 7E`
4. 错误发生在发送方在500ms超时内未收到应答

#### A.6 排查要点

| 帧类型 | 检查点 |
|--------|--------|
| **RSR** | 通信链路稳定性、CTC处理延迟 |
| **SDCI** | 接收方是否正确处理变更通知 |
| **FIR** | 初始化序列、故障报告逻辑 |

---

### B. 帧类型分布分析

#### B.1 统计帧类型

```bash
# 统计所有帧类型
awk '/>>\[.*\]/' ZLEvents260201 | \
  grep -oP '(?<=\[)[A-Z]+(?=\s*\])' | \
  sort | uniq -c | sort -rn
```

#### B.2 正常运行时的预期分布

| 帧类型 | 典型占比 | 说明 |
|--------|---------|------|
| ACK | 40-50% | 最常见（心跳） |
| SDCI | 20-30% | 增量更新 |
| RSR | 10-15% | 状态报告 |
| SDI | 5-10% | 全量快照（SDIQ后） |
| DC2/DC3 | <5% | 仅在重连时 |
| BCC | 1-3% | 控制命令 |
| FIR | <1% | 故障报告（罕见） |
| TSQ/TSD | <1% | 每小时时间同步 |

#### B.3 异常模式

| 模式 | 指示问题 |
|------|----------|
| DC2/DC3占比过高(>10%) | 频繁重连尝试 |
| 无SDCI/SDI | 数据流中断 |
| FIR过高 | 系统正在经历故障 |
| 无ACK | 通信中断 |
| 仅RSR | 有状态报告但无数据交换 |

---

### C. 通信序列分析

#### C.1 正常序列

```
00:00:00 << [ACK] ...     CTC心跳
00:00:00 >> [ACK] ...     联锁心跳
00:00:01 << [ACK] ...     CTC心跳
00:00:02 >> [SDCI] ...    数据更新
00:00:02 << [ACK] ...     CTC应答
```

#### C.2 异常序列（ACK丢失）

```
00:00:00 >> [RSR] ...     状态报告
00:00:14 Er未收到ACK      14秒后：超时！
```

#### C.3 异常序列（重复ACK）

```
00:00:00 >> [ACK] ...
00:00:00 << [ACK] ...
00:00:00 << [ACK] ...     重复ACK已发送
```

#### C.4 时间间隔分析

```bash
# 计算事件间间隔
awk '/00:00:/{gsub(/:/," "); print $1*3600 + $2*60 + $3}' log.txt | \
  awk '{if(prev) print $0-prev; prev=$0}'
```

**正常间隔**：
| 事件类型 | 正常间隔 | 异常情况 |
|---------|---------|----------|
| ACK帧 | ~500ms | >1500ms |
| SDCI更新 | 1-5秒 | 持续突发 |
| RSR报告 | 1-10秒 | 过频繁 |
| SDIQ后SDI | 立即 | 延迟>5秒 |

#### C.5 状态转换分析

**RSR状态追踪**：
```bash
grep "RSR" ZLEvents260201 | awk '{print $1, $5}' | head -20
```

**预期模式**：
```
00:00:02 0x55 0x55    # 主机, 允许自律
00:00:03 0x55 0x55    # 主机, 允许自律
00:00:04 0xAA 0x55    # 切换到备机！
00:00:05 0x55 0x55    # 恢复主机
```

**问题模式**：
```
00:00:02 0x55 0x55    # 主机
00:00:03 0xAA 0x55    # 备机（异常！）
00:00:04 0xAA 0x55    # 仍是备机
```

---

### D. 分析检查清单

#### D.1 基础检查
- [ ] 总帧数合理
- [ ] 存在ACK帧（心跳）
- [ ] 数据帧（SDCI/SDI）正常流动
- [ ] 无过多DC2/DC3重试

#### D.2 错误检查
- [ ] 统计"未收到ACK"错误数
- [ ] 识别哪些帧类型出错
- [ ] 检查错误频率趋势
- [ ] 关联错误与系统事件

#### D.3 连接检查
- [ ] DC2/DC3握手成功
- [ ] 无频繁重连尝试
- [ ] 识别硬件故障
- [ ] 记录恢复尝试

#### D.4 状态检查
- [ ] RSR状态一致
- [ ] 无意外的主备切换
- [ ] 记录控制模式转换
- [ ] 时间同步正常工作
# 设备状态分析工作流指南

> **本文档定位**：提供联锁设备状态分析的完整工作流程，涵盖从数据准备到结果分析的各个阶段，包含常用场景的脚本示例。技术细节参考 → [06-device-analysis.md](./06-device-analysis.md)

## 文档体系关联

| 阶段 | 文档 | 说明 |
|------|------|------|
| 概览 | [01-overview.md](./01-overview.md) | 系统架构和核心概念 |
| 帧格式 | [02-frame-formats.md](./02-frame-formats.md) | 帧类型和结构 |
| 机制 | [03-protocol-mechanisms.md](./03-protocol-mechanisms.md) | 超时、序号、主备 |
| 流程 | [04-communication-process.md](./04-communication-process.md) | 完整通信流程 |
| **本文档** | **05-workflow.md** | **分析工作流（本文档）** |
| 参考 | [06-device-analysis.md](./06-device-analysis.md) | 设备状态解码详解 |

## 目录

1. [工作流概述](#工作流概述)
2. [阶段1：数据准备](#阶段1数据准备)
3. [阶段2：设备定位](#阶段2设备定位)
4. [阶段3：数据提取](#阶段3数据提取)
5. [阶段4：状态分析](#阶段4状态分析)
6. [阶段5：结果报告](#阶段5结果报告)
7. [常见场景示例](#常见场景示例)

---

## 工作流概述

```
┌─────────────────────────────────────────────────────────────────────┐
│                        设备状态分析工作流                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │ 数据准备 │───▶│ 设备定位 │───▶│ 数据提取 │───▶│ 状态分析 │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│       │               │               │               │              │
│       ▼               ▼               ▼               ▼              │
│  收集日志文件    查找设备索引    筛选SDCI帧     生成分析报告          │
│  准备码位表      确认设备类型    导出时间线     识别异常模式          │
│                                                                      │
│                          ┌──────────┐                               │
│                          │ 结果报告 │                               │
│                          └──────────┘                               │
│                               │                                      │
│                               ▼                                      │
│                        导出多种格式                                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**标准时间**: 完整工作流约需10-15分钟

---

## 阶段1：数据准备

### 1.1 收集日志文件

**必需文件**:

```
├── lgxtq.zl              # 码位表文件（设备索引映射）
├── 联锁主机1\ZLEvents260201  # 联锁主机1日志
├── 联锁主机2\ZLEvents260201  # 联锁主机2日志
└── CTC\lgxtcidriver_2026-02-01.log    # CTC日志
```

**日志文件命名规范**:

- 联锁日志: `ZLEventsMMDDYY` (月日年)
- CTC日志: `lgxtcidriver_YYYY-MM-DD.log`

### 1.2 验证文件完整性

```bash
# 检查文件是否存在且非空
for file in lgxtq.zl "联锁主机2\ZLEvents260201"; do
  if [ -s "$file" ]; then
    echo "✓ $file 存在且非空"
  else
    echo "✗ $file 不存在或为空"
  fi
done

# 统计日志行数
wc -l ZLEvents*

# 检查日志编码
file ZLEvents*
```

### 1.3 备份原始数据

```bash
# 创建工作目录
mkdir -p analysis_$(date +%Y%m%d)
cd analysis_$(date +%Y%m%d)

# 复制原始日志
cp ../lgxtq.zl .
cp ../ZLEvents* .

# 创建备份
mkdir backup
cp *.zl backup/
cp ZLEvents* backup/
```

---

## 阶段2：设备定位

### 2.1 在码位表中查找设备

```bash
# 查找道岔区段64
grep "^,64," lgxtq.zl
# 输出: #,64,37  ← objects索引是37

# 查找信号机D114
grep "^,D114," lgxtq.zl
# 输出: #,D114,63

# 查找无岔区段DK5
grep "^,DK5," lgxtq.zl
# 输出: #,DK5,312
```

### 2.2 筛选设备类型

```bash
# 道岔区段（纯数字）
grep -E "^#,[0-9]+," lgxtq.zl

# 信号机（D+数字）
grep -E "^#,D[0-9]" lgxtq.zl

# 无岔区段（其他格式）
grep -E "^#,([^D][^,]+,|[D][^0-9]+,)" lgxtq.zl | grep -v "D[0-9]"
```

### 2.3 确认设备类型

| 命名模式 | 设备类型 | 示例 |
|----------|----------|------|
| 纯数字 | 道岔区段 | "64", "10" |
| D+数字 | 信号机 | "D114", "D6" |
| 其他 | 无岔区段 | "DK5", "102/104G" |

> **详细编码规则**: 设备状态字节定义见 [06-device-analysis.md](./06-device-analysis.md)

---

## 阶段3：数据提取

### 3.1 选择数据源

| 主机 | 状态 | 适用场景 |
|------|------|----------|
| 联锁主机1 | 仅RSR帧 | 主备状态检查 |
| 联锁主机2 | 完整SDCI/SDI | **设备状态分析（推荐）** |
| 双机对比 | 两者都需要 | 一致性验证 |

### 3.2 提取SDCI帧

```bash
cd analysis_20260204

# 提取道岔区段64的所有SDCI帧（索引37=0x25）
grep -E "8A.*00 25" "联锁主机2\ZLEvents260201" > device64_frames.txt

# 验证提取结果
wc -l device64_frames.txt
# 输出: 99 device64_frames.txt

# 查看前5条记录
head -5 device64_frames.txt
```

### 3.3 高级提取技巧

```bash
# 提取指定时间范围的帧
awk '$1 >= "00:21:00" && $1 <= "08:09:00"' "联锁主机2\ZLEvents260201" | \
  grep -E "8A.*00 25" > device64_morning.txt

# 提取并按时间排序
grep -E "8A.*00 25" "联锁主机2\ZLEvents260201" | \
  sort -k1 > device64_sorted.txt

# 统计帧数量（按帧类型）
grep "8A" ZLEvents* | awk '{print $5}' | sort | uniq -c
```

### 3.4 验证数据质量

```bash
# 基础验证
python -c "
import sys
with open('device64_frames.txt', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()
    print(f'总记录数: {len(lines)}')
    print(f'SDCI帧数量: {sum(1 for l in lines if \"8A\" in l)}')
"
```

---

## 阶段4：状态分析

### 4.1 使用标准分析脚本

```bash
# 基本分析
python templates/analyze_timeline.py switch device64_frames.txt 37 "道岔区段64"

# 输出到文件
python templates/analyze_timeline.py switch device64_frames.txt 37 "道岔区段64" > report.txt
```

### 4.2 快速状态统计

```bash
# 统计状态分布
python -c "
from templates.analyze_device_timeline import analyze_device_frames
records = analyze_device_frames('device64_frames.txt', 37, '道岔区段64')
state_stats = {}
for rec in records:
    state = f'0x{rec[\"state\"]:02X}'
    state_stats[state] = state_stats.get(state, 0) + 1
for state, count in sorted(state_stats.items(), key=lambda x: -x[1]):
    print(f'{state}: {count}次')
"
```

### 4.3 告警阈值

| 指标 | 正常范围 | 警告 | 严重 |
|------|----------|------|------|
| 四开状态频率 | <5% | 5-10% | >10% |
| 状态变化频率 | <10次/小时 | 10-30次/小时 | >30次/小时 |
| 占用持续时间 | <5分钟 | 5-10分钟 | >10分钟 |

---

## 阶段5：结果报告

### 5.1 生成标准报告

```bash
cat > standard_report.md << EOF
# 道岔区段64状态分析报告

## 基本信息

- 分析日期: $(date +%Y-%m-%d)
- 目标设备: 64 (道岔区段)
- objects索引: 37
- 数据来源: 联锁主机2

## 数据统计

\`\`\`
$(python templates/analyze_timeline.py switch device64_frames.txt 37 "道岔区段64")
\`\`\`

## 分析结论

### 1. 状态分布
- 主要状态: 定位(0x01) 32次，占比32.4%
- 次要状态: 四开(0x19) 29次，占比29.3%

### 2. 异常检测
- 四开状态频繁出现，建议检查转辙机
- 状态变化集中在00:53-00:54时段

### 3. 建议措施
- 安排转辙机检修
- 监控后续24小时状态变化
EOF

cat standard_report.md
```

### 5.2 导出多种格式

```bash
# JSON格式
python -c "
import json
from templates.analyze_device_timeline import analyze_device_frames
records = analyze_device_frames('device64_frames.txt', 37, '道岔区段64')
with open('data.json', 'w', encoding='utf-8') as f:
    json.dump(records, f, ensure_ascii=False, indent=2)
"

# CSV格式
python -c "
import csv
from templates.analyze_device_timeline import analyze_device_frames
records = analyze_device_frames('device64_frames.txt', 37, '道岔区段64')
with open('data.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['时间', '状态值', '占用', '锁闭', '位置', '描述'])
    for rec in records:
        writer.writerow([
            rec['time'],
            f\"0x{rec['state']:02X}\",
            '是' if rec['decoded']['occupied'] else '否',
            '是' if rec['decoded']['locked'] else '否',
            {0: '定位', 1: '反位', 2: '四开', 3: '未知'}.get(rec['decoded']['position']),
            rec['decoded']['desc']
        ])
"
```

---

## 常见场景示例

### 场景1: 日常巡检

```bash
#!/bin/bash
# daily_check.sh - 每日设备状态巡检

echo "=== $(date +%Y-%m-%d) 设备状态巡检 ==="

# 选择道岔区段64进行巡检
echo "\n1. 道岔区段64状态:"
python templates/analyze_timeline.py switch device64_frames.txt 37 "道岔区段64" | \
  grep -A 10 "统计汇总"

# 检查异常状态
echo "\n2. 异常状态检查:"
abnormal=$(python -c "
from templates.analyze_device_timeline import analyze_device_frames
records = analyze_device_frames('device64_frames.txt', 37, '道岔区段64')
for rec in records:
    if rec['state'] in [0x19, 0x1B]:
        print(f\"{rec['time']}: 0x{rec['state']:02X}\")
" 2>/dev/null)

if [ -n "$abnormal" ]; then
    echo "发现异常状态:"
    echo "$abnormal"
else
    echo "✓ 未发现异常状态"
fi

echo "\n巡检完成: $(date +%H:%M:%S)"
```

### 场景2: 故障排查

```python
#!/usr/bin/env python3
# fault_investigation.py
from datetime import datetime
from templates.analyze_device_timeline import analyze_device_frames

def investigate_fault(start_time, end_time):
    """
    故障排查 - 分析指定时间范围内的异常状态
    """
    records = analyze_device_frames('device64_frames.txt', 37, '道岔区段64')

    # 过滤时间范围
    start = datetime.strptime(start_time, '%H:%M:%S')
    end = datetime.strptime(end_time, '%H:%M:%S')

    fault_records = []
    for rec in records:
        rec_time = datetime.strptime(rec['time'], '%H:%M:%S')
        if start <= rec_time <= end:
            fault_records.append(rec)

    print(f"故障时段: {start_time} - {end_time}")
    print(f"记录数: {len(fault_records)}")

    # 分析状态分布
    state_dist = {}
    for rec in fault_records:
        state = f"0x{rec['state']:02X}"
        if state not in state_dist:
            state_dist[state] = {'count': 0, 'desc': rec['decoded']['desc']}
        state_dist[state]['count'] += 1

    print("\n状态分布:")
    for state, info in sorted(state_dist.items(), key=lambda x: -x[1]['count']):
        print(f"  {state}: {info['count']}次 - {info['desc']}")

    # 查找触发因素
    print("\n状态变化时序:")
    for i in range(1, len(fault_records)):
        if fault_records[i]['state'] != fault_records[i-1]['state']:
            print(f"  {fault_records[i]['time']}: "
                  f"{fault_records[i-1]['state']:02X} → {fault_records[i]['state']:02X}")

    return fault_records

if __name__ == "__main__":
    investigate_fault("00:53:00", "00:54:30")
```

### 场景3: 批量设备分析

```bash
#!/bin/bash
# batch_analysis.sh - 批量分析多个设备

# 设备列表（道岔区段）
for name in 64 10 110; do
    echo "=== 分析道岔区段: $name ==="
    index=$(grep "^,$name," lgxtq.zl | cut -d',' -f3)
    hex_index=$(printf "%02X" $index)
    grep -E "8A.*00 $hex_index" "联锁主机2\ZLEvents260201" > "device_${name}_frames.txt"
    python templates/analyze_timeline.py switch "device_${name}_frames.txt" $index "道岔区段$name"
done
```

---

## 总结

**关键要点**：

| 阶段 | 要点 |
|------|------|
| 数据准备 | 确保日志文件完整，备份原始数据 |
| 设备定位 | 正确使用码位表查找设备索引 |
| 数据提取 | 使用正确的grep模式提取SDCI帧 |
| 状态分析 | 使用标准脚本进行分析 |
| 结果报告 | 生成多种格式的报告便于存档和分享 |

**常用命令速查**：

```bash
# 查找设备索引
grep "^,64," lgxtq.zl

# 提取SDCI帧
grep -E "8A.*00 25" ZLEvents260201 > device64_frames.txt

# 分析状态
python templates/analyze_timeline.py switch device64_frames.txt 37 "道岔区段64"
```

**下一步**：

- 设备编码详解 → [06-device-analysis.md](./06-device-analysis.md)
- 协议机制 → [03-protocol-mechanisms.md](./03-protocol-mechanisms.md)
- 帧格式详解 → [02-frame-formats.md](./02-frame-formats.md)
- 故障排查 → [07-interlocking-troubleshooting.md](./07-interlocking-troubleshooting.md)

---

**文档版本**: 1.2
**最后更新**: 2026-02-11

# hengjun-cbi-parser

**快速开始** → [5步上手](#快速开始指南) | **详细文档** → [references/](references/) | **技能入口** → [SKILL.md](SKILL.md)

联锁系统(CBI)与调度集中系统(CTC) SDCI/SDI帧解析器

## 功能亮点

- 解析码位表文件，创建设备映射表
- 支持SDCI帧（0x8A，增量更新）和SDI帧（0x85，全量快照）
- 解码道岔区段、信号机、无岔区段状态
- 生成文本报告和JSON结构化数据

## 快速开始指南

### 5步完成设备状态分析

**目标**：分析道岔区段64在2026年2月1日的状态变化

```bash
# 步骤1: 查找设备索引
grep "^,64," lgxtq.zl
# 输出: #,64,37  ← 设备索引是37

# 步骤2: 提取SDCI帧（索引37 = 0x25）
grep -E "8A.*00 25" "联锁主机2\ZLEvents260201" > device64_frames.txt

# 步骤3: 分析状态时间线
python templates/analyze_timeline.py switch device64_frames.txt 37 "道岔区段64"

# 步骤4: 查看分析报告
# 输出包含99条状态记录，时间范围00:21:17至08:08:45

# 步骤5: 导出JSON（可选）
python -c "
import json
from templates.analyze_device_timeline import analyze_device_frames
records = analyze_device_frames('device64_frames.txt', 37, '道岔区段64')
with open('device64_report.json', 'w', encoding='utf-8') as f:
    json.dump(records, f, ensure_ascii=False, indent=2)
"
```

**输出示例**：
```
================================================================================
设备 37 (0x0025) (道岔区段64) 状态变化时间线
================================================================================

序号   时间         状态值    占用     锁闭     位置
--------------------------------------------------------------------------------
1      00:21:17     0x19      是       否       四开
2      00:21:39     0x01      是       否       定位
...

统计汇总
================================================================================
状态变化总次数: 99
实际状态转换次数: 45
时间范围: 00:21:17 至 08:08:45

状态分布:
  0x01:  32 次 - 占用, 未锁, 定位
  0x19:  29 次 - 占用, 未锁, 四开
  0x02:  12 次 - 空闲, 锁闭, 定位
```

### 常用分析任务速查

| 分析任务 | 命令 | 说明 |
|----------|------|------|
| 分析道岔状态 | `python templates/analyze_timeline.py switch frames.txt 37 "设备名"` | 道岔区段64在索引37 |
| 分析轨道占用 | `python templates/analyze_timeline.py track` | 同时分析两个联锁主机 |
| 查找设备索引 | `grep "设备名" lgxtq.zl` | 在码位表中定位设备 |
| 提取所有SDCI帧 | `grep -E "8A" ZLEvents260201 > sdci_frames.txt` | 导出所有变化帧 |

### 设备索引速查表

| 设备类型 | 命名规则 | 示例 | objects索引范围 |
|----------|----------|------|-----------------|
| 道岔区段 | 纯数字 | 10, 64, 110 | 1-50 |
| 信号机 | D+数字 | D114, D6 | 50-100 |
| 无岔区段 | 其他格式 | DK5, 102/104G | 300+ |

## 实际使用案例

### 案例1: 分析道岔故障

**场景**: 道岔区段64频繁在"定位"和"四开"间切换

```bash
# 1. 查找设备索引 → 2. 提取帧数据 → 3. 分析状态
grep "^,64," lgxtq.zl  # 输出: #,64,37
grep -E "8A.*00 25" "联锁主机2\ZLEvents260201" > device64_frames.txt
python templates/analyze_timeline.py switch device64_frames.txt 37 "道岔区段64"

# 结果显示: 0x19状态（四开）出现29次 ← 故障状态
```

**结论**: 道岔在早高峰期间频繁故障，建议检查转辙机

### 案例2: 追踪列车占用

**场景**: 追踪DK5区段的列车占用情况

```bash
# 查找设备 → 提取数据 → 分析占用时段
grep "^,DK5," lgxtq.zl  # 输出: #,DK5,312 (0x138)
grep -E "8A.*01 38" "联锁主机2\ZLEvents260201" > dk5_frames.txt
python templates/analyze_timeline.py switch dk5_frames.txt 312 "DK5"
```

### 案例3: 双机状态对比

使用 `analyze_timeline.py track` 检查联锁主机1和主机2的状态一致性。

**更多案例和详细分析方法请参考**:
- [references/05-workflow.md](references/05-workflow.md) - 完整的设备分析工作流（含场景示例）
- [references/06-device-analysis.md](references/06-device-analysis.md) - 设备状态解码规则（含Python函数）
- [references/07-interlocking-troubleshooting.md](references/07-interlocking-troubleshooting.md) - 联锁日志故障排除实例

## 常见问题速查

| 问题 | 快速解决 |
|------|----------|
| **grep找不到设备帧** | 检查设备索引转换：`grep "^,64," lgxtq.zl` → 索引37 → `00 25` |
| **Unicode编码错误** | 使用 `encoding='utf-8', errors='ignore'` |
| **时间范围不连续** | 检查日志完整性：`wc -l ZLEvents260201` |
| **状态值异常** | 使用位解析：`0x19 = 0001 1001` → 占用+定位+无表示 |
| **⭐ 如何区分正常重启和异常重连** | 查看CTC日志中的关键标记：`驱动启动后首次读取` vs `检测到硬件故障`。注意：正常重启时若2号机是主机，会先连1号机（检测到备机后断开）再连2号机。详细分析方法见 [references/08-ctc-analysis.md](references/08-ctc-analysis.md) |

**详细故障排除指南**: [references/07-interlocking-troubleshooting.md](references/07-interlocking-troubleshooting.md)

## 进阶学习

| 学习目标 | 推荐文档 |
|----------|----------|
| 系统架构 | [references/01-overview.md](references/01-overview.md) |
| 帧格式详情 | [references/02-frame-formats.md](references/02-frame-formats.md) |
| 设备状态解码 | [references/06-device-analysis.md](references/06-device-analysis.md) |
| 故障排除 | [references/07-interlocking-troubleshooting.md](references/07-interlocking-troubleshooting.md) |
| Python API | [references/10-api-usage.md](references/10-api-usage.md) |
| 协议规范 | [references/09-protocol-schema.md](references/09-protocol-schema.md) |
| 完整工作流 | [references/05-workflow.md](references/05-workflow.md) |

## 版本

1.2.0 (2026-02-11)

**更新日志**:
- 文档结构重组，清晰分层
- 添加快速开始指南
- 新增实际使用案例（道岔故障、列车占用追踪）
- 新增故障排除指南
- **新增**: `references/Error.sys` - FIR帧故障码对照表（43种故障类型中文描述）
- **新增**: `references/08-ctc-analysis.md` - CTC日志深度分析指南（正常重启与异常重连分析，含两种正常重启子情况详细说明）
- **更新**: `references/02-frame-formats.md` - 完善FIR帧格式说明，添加错误类型码详细对照表
- **更新**: `docs/quick-reference.md` - 添加FIR帧故障解析速查
- **更新**: `SKILL.md` - 添加FIR帧说明和Error.sys引用

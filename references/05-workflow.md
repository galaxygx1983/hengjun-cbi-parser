# 分析工作流

## 流程

| 阶段 | 说明 |
|------|------|
| 数据准备 | 收集日志和码位表 |
| 设备定位 | 查找设备索引 |
| 数据提取 | 提取SDCI帧 |
| 状态分析 | 生成分析报告 |
| 结果导出 | JSON/CSV格式 |

## 数据准备

```
├── lgxtq.zl              # 码位表
├── ZLEvents260201        # 联锁日志
└── lgxtcidriver_*.log    # CTC日志
```

## 设备定位

```bash
# 查找设备索引
grep "^,64," lgxtq.zl     # → #,64,37 (索引37)
grep "^,D114," lgxtq.zl   # → #,D114,63
```

| 名称模式 | 类型 |
|----------|------|
| 纯数字 | 道岔区段 |
| D+数字 | 信号机 |
| 其他 | 无岔区段 |

## 数据提取

```bash
# 提取SDCI帧（索引37=0x25）
grep -E "8A.*00 25" ZLEvents260201 > device64_frames.txt
```

## 分析脚本

```python
from parser import DeviceTimelineAnalyzer, CodePositionTable

cpt = CodePositionTable("lgxtq.zl")
analyzer = DeviceTimelineAnalyzer("ZLEvents260201", cpt)
timeline = analyzer.analyze_device("64")
analyzer.generate_timeline_report("64", "report.txt")
```

## 常用场景

| 场景 | 方法 |
|------|------|
| 日常巡检 | analyze_device() |
| 故障排查 | 时间范围过滤 |
| 批量分析 | 循环遍历设备列表 |

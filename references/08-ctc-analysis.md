# CTC日志分析

## 日志格式

```
Device Index: 91
Old State: 0x02
New State: 0x04
```

## 故障检测

| 阶段 | 说明 |
|------|------|
| 1. 超时 | 1500ms无有效帧 |
| 2. 重试 | 发送DC2最多3次 |
| 3. 判定 | 3次DC2无响应→硬件故障 |
| 4. 恢复 | 每6秒发送DC2 |

## 故障事件

| 事件 | 日志标记 |
|------|----------|
| 通信中断 | 超过1500ms未收到有效帧 |
| 硬件故障 | 发送3次DC2后仍未收到DC3 |
| 恢复 | 收到DC3，连接已建立 |

## 正常vs异常重连

| 指标 | 正常重启 | 异常重连 |
|------|----------|----------|
| 触发 | 驱动重启 | 硬件故障 |
| 日志 | 驱动启动后首次读取 | 检测到硬件故障 |
| DC2次数 | 1-2次 | 3+次 |
| 故障模式 | 否 | 是 |

## 日志命令

```bash
# 统计正常重启
grep "驱动启动后首次读取" lgxtcidriver_*.log

# 统计硬件故障
grep "检测到硬件故障" lgxtcidriver_*.log

# 分析重连
awk '/驱动启动后首次读取|检测到硬件故障|收到DC3/' logfile
```

## 分析API

```python
from parser import CTCLogHardwareFaultAnalyzer

analyzer = CTCLogHardwareFaultAnalyzer("lgxtcidriver.log")
result = analyzer.analyze()

print(result['statistics']['total_fault_events'])
```

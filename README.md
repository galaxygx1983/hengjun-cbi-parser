# Hengjun CBI Parser

> 铁路计算机联锁(CBI)与调度集中(CTC)通信日志分析工具

## 功能特性

- 解析铁路联锁系统通信日志
- 支持 CBI/CTC 帧协议解析
- 设备状态解析与故障诊断
- 支持 SDCI/SDI/FIR 协议
- ZLEvents 日志分析
- lgxtcidriver 日志处理

## 支持协议

| 协议 | 说明 |
|------|------|
| SDCI | 联锁通信接口 |
| SDI | 安全通信接口 |
| FIR | 故障检测记录 |
| ZLEvents | 事件日志格式 |

## 快速开始

```python
from hengjun_cbi_parser import CBIParser

# 解析联锁日志
parser = CBIParser()
result = parser.parse_file("cbi_comm.log")
print(result.summary())
```

## 使用场景

1. 分析铁路日志
2. CBI/CTC 日志解析
3. 联锁通信故障排查
4. 帧协议解析
5. 设备状态解析

## 详细文档

查看 [SKILL.md](SKILL.md) 获取完整使用指南。

## 许可证

MIT License
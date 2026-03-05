---
name: hengjun-cbi-parser
description: Use when analyzing railway CBI and CTC communication logs, parsing frame protocols (SDCI, SDI, SDIQ, DC2, DC3, ACK, NACK, FIR, BCC, TSQ, TSD, RSR, ACQ, ACA, VERROR), decoding interlocking device states, or extracting station yard status changes. MUST read reference documents before analysis.
---

# Hengjun CBI Parser

## 核心功能

解析铁路CBI（计算机联锁）与CTC（调度集中）通信日志，支持SDCI/SDI/FIR等多种帧格式解码和设备状态分析。

## 文档地图

| 序号 | 我要... | 日志类型 | 阅读 |
|------|---------|----------|------|
| 01 | **5分钟上手** | - | [README.md](README.md) |
| 02 | 了解系统架构 | - | [references/01-overview.md](references/01-overview.md) |
| 03 | 查看帧格式 | - | [references/02-frame-formats.md](references/02-frame-formats.md) |
| 04 | 理解协议机制 | - | [references/03-protocol-mechanisms.md](references/03-protocol-mechanisms.md) |
| 05 | 了解通信流程 | - | [references/04-communication-process.md](references/04-communication-process.md) |
| 06 | **掌握分析工作流** | 联锁日志 | [references/05-workflow.md](references/05-workflow.md) |
| 07 | **查询设备解码规则** | - | [references/06-device-analysis.md](references/06-device-analysis.md) |
| 08 | **联锁日志故障排查** | 联锁日志 | [references/07-interlocking-troubleshooting.md](references/07-interlocking-troubleshooting.md) |
| 09 | **CTC日志深度分析** | CTC日志 | [references/08-ctc-analysis.md](references/08-ctc-analysis.md) |
| 10 | 查看协议规范 | - | [references/09-protocol-schema.md](references/09-protocol-schema.md) |
| 11 | 使用Python API | - | [references/10-api-usage.md](references/10-api-usage.md) |

### 日志类型区分

**联锁日志（ZLEvents*）**
- 文件格式：`ZLEventsMMDDYY`（如 ZLEvents260201）
- 记录内容：联锁系统发送和接收的帧数据
- 典型标记：`>>[帧类型]`（发送）、`<<[帧类型]`（接收）、`Er未收到ACK`（错误）

**CTC日志（lgxtcidriver_*.log）**
- 文件格式：`lgxtcidriver_YYYYMMDD_序号.log`
- 记录内容：CTC驱动程序的连接状态、故障检测、主备切换
- 典型标记：`驱动启动`、`检测到硬件故障`、`收到DC3，连接已建立`

### 详细场景指南

**何时参考 07-interlocking-troubleshooting.md（联锁日志故障排查）？**

**适用日志**：`ZLEvents*` 联锁日志

当分析联锁日志遇到以下问题时查阅：
- 出现 `"Er未收到ACK"` 错误
- SDIQ 显示长等待时间（如"距离下次SDIQ发送还需等待63632902ms"）
- DC2/DC3 握手频繁重试或失败
- 从联锁帧提取设备状态时出现异常
- 解析设备状态时状态值冲突或超出范围
- grep 命令找不到设备帧数据（索引转换问题）
- 处理大联锁日志文件时内存不足或性能问题

**文档内容包括**：联锁日志常见问题诊断流程、设备状态解析问题排查、性能优化方案、3个联锁日志专用诊断脚本

---

**何时参考 08-ctc-analysis.md（CTC日志深度分析）？**

**适用日志**：`lgxtcidriver_*.log` CTC驱动日志

当分析CTC日志进行以下深度调查时查阅：
- 统计和分析 ACK 超时错误的根本原因（CTC视角）
- 识别硬件故障和通信中断事件
- 区分正常重启与异常重连（故障切换分析）
- 分析CTC与联锁主机/备机的连接历史
- 检测CTC驱动程序检测到的通信时序异常
- 追踪CTC视角下的主备状态切换时间线
- 排查CTC检测到的间歇性通信问题
- 分析CTC故障切换决策过程

**文档内容包括**：CTC日志ACK错误分析方法、CTC硬件故障检测流程、正常/异常重连对比分析、CTC帧分布统计、CTC通信序列分析、CTC日志分析检查清单

## ⚠️ 重要提醒

分析任何帧类型或故障排除时，**必须**先阅读相关参考文档：
- 帧格式详情 → `references/02-frame-formats.md`
- 协议机制 → `references/03-protocol-mechanisms.md`

## 约束说明

- **ACK超时**: 500ms（协议固定，不可修改）
- **数据文件**: [Error.sys](references/Error.sys)（故障代码）、[lgxtq.zl](references/lgxtq.zl)（码位表示例）

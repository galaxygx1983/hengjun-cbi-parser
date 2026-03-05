# 设备状态解码详解

> **本文档定位**：详细说明道岔区段、信号机、无岔区段的状态编码规则和解码方法。完整工作流参考 → [05-workflow.md](./05-workflow.md)

## 文档体系关联

| 阶段 | 文档 | 说明 |
|------|------|------|
| 概览 | [01-overview.md](./01-overview.md) | 系统架构和核心概念 |
| 帧格式 | [02-frame-formats.md](./02-frame-formats.md) | 帧类型和结构 |
| 机制 | [03-protocol-mechanisms.md](./03-protocol-mechanisms.md) | 超时、序号、主备 |
| 流程 | [04-communication-process.md](./04-communication-process.md) | 完整通信流程 |
| 工作流 | [05-workflow.md](./05-workflow.md) | 完整分析工作流 |
| **本文档** | **06-device-analysis.md** | **设备状态解码详解（本文档）** |

---

## 设备类型识别

### 命名规则

| 命名模式 | 设备类型 | 示例 | objects索引范围 |
|----------|----------|------|-----------------|
| 纯数字 | 道岔区段 | "10", "64", "110" | 1-50 |
| D+数字 | 信号机 | "D114", "D6" | 50-100 |
| 其他格式 | 无岔区段 | "DK5", "102/104G" | 300+ |

### 索引类型

| 格式 | 所属表 | 用途 | 示例 |
|------|--------|------|------|
| `#,name,index` | [objects] | SDCI帧解析 | 设备"64" → 索引37 |
| `#,name,byte_index,bit_offset` | [zlobjects] | SDI缓冲区映射 | 104/110G → 字节324，位4 |

### SDCI帧索引格式

- 2字节大端序
- 索引37 → `00 25` (37 = 0x25)
- 索引63 → `00 3F` (63 = 0x3F)
- 索引312 → `01 38` (312 = 0x138)

---

## 道岔区段状态解码

### 位定义

| Bit | 含义 | 值 | 说明 |
|-----|------|-----|------|
| 0 | 定位 | 1=定位 | 道岔位置 |
| 1 | 反位 | 1=反位 | 道岔位置 |
| 2 | 无表示 | 1=无表示 | 道岔位置 |
| 3 | 区段锁闭 | 1=锁闭 | 区段状态 |
| 4 | 区段占用 | 1=占用 | 区段状态 |
| 5 | 道岔锁闭 | 1=锁闭 | 道岔状态 |
| 6-7 | 保留 | - | 未使用 |

### 位置编码（Bit 0-2）

| 状态值 | 二进制 | 含义 | 说明 |
|--------|--------|------|------|
| 0x01 | 001 | 定位 | 正常位置 |
| 0x02 | 010 | 反位 | 反向位置 |
| 0x04 | 100 | 无表示 | 位置不明 |
| 0x03 | 011 | 定位+反位 | 组合状态 |
| 0x05 | 101 | 定位+无表示 | 组合状态 |
| 0x07 | 111 | 全部组合 | 异常状态 |

### 典型状态值

| 状态值 | 占用 | 区段锁闭 | 道岔锁闭 | 位置 | 说明 |
|--------|------|----------|----------|------|------|
| 0x00 | 否 | 否 | 否 | 定位 | 空闲未锁 |
| 0x01 | 是 | 否 | 否 | 定位 | 列车通过 |
| 0x02 | 否 | 是 | 否 | 反位 | 进路锁闭 |
| 0x03 | 是 | 是 | 否 | 定位 | 占用锁闭 |
| 0x08 | 否 | 否 | 否 | 反位 | 空闲未锁 |
| 0x19 | 是 | 否 | 否 | 定位+无表示 | **位置异常** |
| 0x28 | 否 | 是 | 是 | 无表示 | 道岔锁闭 |

### Python解码函数

```python
def decode_switch_section(state_byte):
    """解码道岔区段状态字节"""
    # 位置解码（bit 0-2）
    position_bits = state_byte & 0x07
    positions = []
    if position_bits & 0x01: positions.append("定位")
    if position_bits & 0x02: positions.append("反位")
    if position_bits & 0x04: positions.append("无表示")
    
    # 区段状态（bit 3-4）
    section_locked = bool(state_byte & 0x08)  # bit 3
    section_occupied = bool(state_byte & 0x10)  # bit 4
    
    # 道岔锁闭（bit 5）
    switch_locked = bool(state_byte & 0x20)  # bit 5
    
    return {
        "positions": positions,
        "section_locked": section_locked,
        "section_occupied": section_occupied,
        "switch_locked": switch_locked
    }

# 示例
state = 0x19  # 二进制: 0001 1001
result = decode_switch_section(state)
# 输出: {"positions": ["定位", "无表示"], "section_locked": False, 
#        "section_occupied": True, "switch_locked": False}
```

---

## 信号机状态解码

### 位定义

| Bit | 含义 | 值 | 说明 |
|-----|------|-----|------|
| 0 | 灯丝断丝 | 1=断丝 | 故障状态 |
| 1 | 蓝 | 1=蓝灯 | 灯色 |
| 2 | 白 | 1=白灯 | 灯色 |
| 3 | 红 | 1=红灯 | 灯色 |
| 4 | 绿 | 1=绿灯 | 灯色 |
| 5 | 黄/2黄/引白组合 | 1=组合 | 复合灯色 |
| 6 | 进路转岔过程中 | 1=转岔中 | 进路状态 |
| 7 | 延时解锁 | 1=延时中 | 解锁状态 |

### 灯色解码（Bit 0-5）

| 状态值 | 二进制 | 灯色 | 说明 |
|--------|--------|------|------|
| 0x00 | 00000000 | 灭 | 无显示 |
| 0x02 | 00000010 | 蓝 | 调车禁止 |
| 0x04 | 00000100 | 白 | 调车允许 |
| 0x08 | 00001000 | 红 | 停车 |
| 0x10 | 00010000 | 绿 | 开放正线 |
| 0x11 | 00010001 | 黄 | 开放侧线 |
| 0x12 | 00010010 | 2黄 | 开放侧线预告 |
| 0x13 | 00010011 | 引白 | 引导开放 |

### 典型状态值

| 状态值 | 灯色 | 进路转岔 | 延时解锁 | 说明 |
|--------|------|----------|----------|------|
| 0x02 | 蓝 | 否 | 否 | 正常蓝灯 |
| 0x04 | 白 | 否 | 否 | 正常白灯 |
| 0x08 | 红 | 否 | 否 | 正常红灯 |
| 0x10 | 绿 | 否 | 否 | 正常绿灯 |
| 0x11 | 黄 | 否 | 否 | 正常黄灯 |
| 0x42 | 蓝 | 是 | 否 | 进路转岔中 |
| 0x88 | 红 | 否 | 是 | 延时解锁中 |

### Python解码函数

```python
def decode_signal(state_byte):
    """解码信号机状态字节"""
    # 灯色解码
    colors = []
    if state_byte & 0x01: colors.append("灯丝断丝")
    if state_byte & 0x02: colors.append("蓝")
    if state_byte & 0x04: colors.append("白")
    if state_byte & 0x08: colors.append("红")
    if state_byte & 0x10: colors.append("绿")
    if state_byte & 0x20: colors.append("黄/2黄/引白组合")
    
    # 状态解码
    route_switching = bool(state_byte & 0x40)  # bit 6
    delayed_unlock = bool(state_byte & 0x80)   # bit 7
    
    return {
        "colors": colors,
        "route_switching": route_switching,
        "delayed_unlock": delayed_unlock
    }
```

---

## 无岔区段状态解码

### 低4位模式 (bit_offset=0)

| Bit | 含义 | 值 |
|-----|------|-----|
| 0 | 区段锁闭 | 1=锁闭 |
| 1 | 区段占用 | 1=占用 |
| 2-3 | 保留 | - |

### 高4位模式 (bit_offset=4)

| Bit | 含义 | 值 |
|-----|------|-----|
| 4 | 区段锁闭 | 1=锁闭 |
| 5 | 区段占用 | 1=占用 |
| 6-7 | 保留 | - |

### Python解码函数

```python
def decode_track_section(state_byte, bit_offset=0):
    """解码无岔区段状态字节"""
    if bit_offset == 0:  # 低4位模式
        locked = bool(state_byte & 0x01)    # bit 0
        occupied = bool(state_byte & 0x02)  # bit 1
    else:  # 高4位模式 (bit_offset=4)
        locked = bool(state_byte & 0x10)    # bit 4
        occupied = bool(state_byte & 0x20)  # bit 5
    
    return {
        "locked": locked,
        "occupied": occupied
    }

# 示例
# 低4位模式
state = 0x03  # 二进制: 0000 0011
result = decode_track_section(state, 0)
# 输出: {"locked": True, "occupied": True}

# 高4位模式
state = 0x30  # 二进制: 0011 0000
result = decode_track_section(state, 4)
# 输出: {"locked": True, "occupied": True}
```

---

## 异常状态速查

### 道岔区段异常

| 状态值 | 模式 | 可能原因 |
|--------|------|----------|
| 0x07 | 定位+反位+无表示 | 转辙机故障 |
| 0x19 | 定位+无表示+占用 | 位置丢失但列车占用 |
| 0x1B | 反位+无表示+占用 | 位置丢失但列车占用 |

### 信号机异常

| 状态值 | 模式 | 可能原因 |
|--------|------|----------|
| 0x01 | 灯丝断丝 | 灯泡故障 |
| 0x42 | 蓝+进路转岔 | 转岔过程中开放信号 |
| 0x88 | 红+延时解锁 | 信号关闭后延时 |

### 告警阈值

| 指标 | 正常范围 | 警告 | 严重 |
|------|----------|------|------|
| 四开状态频率 | <5% | 5-10% | >10% |
| 状态变化频率 | <10次/小时 | 10-30次/小时 | >30次/小时 |
| 占用持续时间 | <5分钟 | 5-10分钟 | >10分钟 |

---

## 相关文档

- 分析工作流 → [05-workflow.md](./05-workflow.md)
- 帧格式详解 → [02-frame-formats.md](./02-frame-formats.md)
- 协议机制 → [03-protocol-mechanisms.md](./03-protocol-mechanisms.md)
- 故障排查 → [07-interlocking-troubleshooting.md](./07-interlocking-troubleshooting.md)

---

**文档版本**: 1.2
**最后更新**: 2026-02-11

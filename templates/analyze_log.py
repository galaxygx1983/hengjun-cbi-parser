#!/usr/bin/env python
# -*- coding: gbk -*-
import os
import sys

# 找到最新的ZLEvents文件
media_dir = r'C:\Users\galax\.copaw\media'
files = [f for f in os.listdir(media_dir) if 'ZLEvents260211' in f and f.endswith('.bin')]

if not files:
    print("未找到ZLEvents260211文件")
    sys.exit(1)

files.sort(key=lambda x: os.path.getmtime(os.path.join(media_dir, x)), reverse=True)
latest_file = os.path.join(media_dir, files[0])

print(f"正在分析文件: {files[0]}")
print(f"文件大小: {os.path.getsize(latest_file)} bytes")

# 读取文件
with open(latest_file, 'rb') as f:
    content = f.read()

# 尝试解码
try:
    text = content.decode('gbk', errors='ignore')
except:
    text = content.decode('utf-8', errors='ignore')

lines = text.split('\n')
print(f"总行数: {len(lines)}")

# 分析通信中断
print("\n" + "="*60)
print("通信中断分析")
print("="*60)

# 查找关键事件
ack_errors = []      # 未收到ACK
dc2_frames = []      # DC2连接请求
dc3_frames = []      # DC3连接确认
timeout_events = []  # 超时事件
error_events = []    # 其他错误

for i, line in enumerate(lines):
    line = line.strip()
    if not line:
        continue
    
    # 查找未收到ACK
    if '未收到ACK' in line or ('Er' in line and 'ACK' in line):
        ack_errors.append((i+1, line))
    
    # 查找DC2帧（连接请求）
    if 'DC2' in line:
        dc2_frames.append((i+1, line))
    
    # 查找DC3帧（连接确认）
    if 'DC3' in line:
        dc3_frames.append((i+1, line))
    
    # 查找超时
    if '超时' in line or 'timeout' in line.lower():
        timeout_events.append((i+1, line))
    
    # 查找其他错误
    if '错误' in line or 'Error' in line or ('Er' in line and '未收到' in line):
        if (i+1, line) not in ack_errors:
            error_events.append((i+1, line))

# 输出结果
print(f"\n1. ACK错误/未收到ACK: {len(ack_errors)} 次")
if ack_errors:
    print("   详细记录:")
    for line_no, line in ack_errors[:10]:
        print(f"   行{line_no}: {line}")

print(f"\n2. DC2连接请求帧: {len(dc2_frames)} 次")
if dc2_frames:
    print("   详细记录:")
    for line_no, line in dc2_frames[:10]:
        print(f"   行{line_no}: {line}")

print(f"\n3. DC3连接确认帧: {len(dc3_frames)} 次")
if dc3_frames:
    print("   详细记录:")
    for line_no, line in dc3_frames[:10]:
        print(f"   行{line_no}: {line}")

print(f"\n4. 超时事件: {len(timeout_events)} 次")
if timeout_events:
    print("   详细记录:")
    for line_no, line in timeout_events[:10]:
        print(f"   行{line_no}: {line}")

# 判断结论
print("\n" + "="*60)
print("分析结论")
print("="*60)

has_interruption = len(ack_errors) > 0 or len(timeout_events) > 0
has_reconnection = len(dc2_frames) > 0 and len(dc3_frames) > 0

if has_interruption:
    print(f"✅ 存在通信中断!")
    print(f"   - ACK错误: {len(ack_errors)} 次")
    print(f"   - 超时事件: {len(timeout_events)} 次")
else:
    print(f"✓ 未发现明显的通信中断")

if has_reconnection:
    print(f"✅ 检测到系统自动重连:")
    print(f"   - DC2连接请求: {len(dc2_frames)} 次")
    print(f"   - DC3连接确认: {len(dc3_frames)} 次")

print("\n" + "="*60)

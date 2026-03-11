import os

media_dir = r'C:\Users\galax\.copaw\media'
files = [f for f in os.listdir(media_dir) if 'ZLEvents260211' in f]
files.sort(key=lambda x: os.path.getmtime(os.path.join(media_dir, x)), reverse=True)
latest = os.path.join(media_dir, files[0])

with open(latest, 'rb') as f:
    content = f.read()

text = content.decode('gbk', errors='ignore')
lines = text.split('\n')

print("=" * 70)
print("ZLEvents260211 通信中断分析报告")
print("=" * 70)
print(f"文件: {files[0]}")
print(f"总行数: {len(lines)}")
print()

# 查找所有关键事件
ack_errors = []
dc2_frames = []
dc3_frames = []

for i, line in enumerate(lines):
    line = line.strip()
    if not line:
        continue
    
    if '未收到ACK' in line or ('Er' in line and 'ACK' in line):
        ack_errors.append((i+1, line))
    
    if 'DC2' in line:
        dc2_frames.append((i+1, line))
    
    if 'DC3' in line:
        dc3_frames.append((i+1, line))

print("=" * 70)
print("1. 通信中断事件")
print("=" * 70)
print(f"发现 {len(ack_errors)} 次ACK超时/未收到ACK错误:\n")

for line_no, line in ack_errors:
    print(f"  行 {line_no}: {line}")

print()
print("=" * 70)
print("2. 连接重连事件")
print("=" * 70)
print(f"DC2连接请求: {len(dc2_frames)} 次")
print(f"DC3连接确认: {len(dc3_frames)} 次\n")

print("DC2/DC3帧详情:")
for i, (line_no, line) in enumerate(dc2_frames):
    print(f"  DC2 行 {line_no}: {line}")
    if i < len(dc3_frames):
        print(f"  DC3 行 {dc3_frames[i][0]}: {dc3_frames[i][1]}")
    print()

print("=" * 70)
print("3. 分析结论")
print("=" * 70)

if len(ack_errors) > 0:
    print("✅ 存在通信中断!")
    print(f"   - 共发生 {len(ack_errors)} 次ACK超时")
    print()
    
    # 分析中断时间
    for i, (line_no, line) in enumerate(ack_errors):
        time_str = line.split()[0] if ' ' in line else "未知"
        print(f"   中断 {i+1}: 时间 {time_str}, 位于第 {line_no} 行")
        
        # 查找对应的DC2/DC3重连
        for dc2_line, dc2_content in dc2_frames:
            if dc2_line > line_no:
                dc2_time = dc2_content.split()[0] if ' ' in dc2_content else "未知"
                print(f"            -> 于 {dc2_time} 发起重连 (DC2)")
                break
    
    print()
    print("✅ 系统自动进行了重连恢复")
else:
    print("✓ 未发现通信中断")

print()
print("=" * 70)

import os

media_dir = r'C:\Users\galax\.copaw\media'
files = [f for f in os.listdir(media_dir) if 'ZLEvents260211' in f]
print("找到文件:", len(files))

if files:
    files.sort(key=lambda x: os.path.getmtime(os.path.join(media_dir, x)), reverse=True)
    latest = os.path.join(media_dir, files[0])
    print("分析文件:", files[0])
    
    with open(latest, 'rb') as f:
        content = f.read()
    
    text = content.decode('gbk', errors='ignore')
    lines = text.split('\n')
    print("总行数:", len(lines))
    
    # 搜索关键字
    keywords = ['未收到ACK', 'Er', 'DC2', 'DC3', '超时', '错误']
    found = []
    for i, line in enumerate(lines):
        for kw in keywords:
            if kw in line:
                found.append((i+1, line.strip()))
                break
    
    print("\n找到", len(found), "条相关记录")
    if found:
        print("\n=== 通信中断相关记录 ===")
        for line_no, line in found[:30]:
            print(f"{line_no}: {line}")

#!/usr/bin/env python3
"""导入聊天记录 JSON 到 SQLite

用法:
    python3 import_db.py [chat.json] [chat.db]

不传参数时默认使用当前目录下的 chat.json / chat.db
"""
import json, sqlite3, os, sys, time

SRC = 'chat.json'
DB  = 'chat.db'


def main():
    global SRC, DB
    if len(sys.argv) > 1:
        SRC = sys.argv[1]
    if len(sys.argv) > 2:
        DB = sys.argv[2]

    if not os.path.exists(SRC):
        print(f'找不到源文件：{SRC}')
        print('用法：python3 import_db.py [chat.json] [chat.db]')
        sys.exit(1)

    t0 = time.time()
    if os.path.exists(DB): os.remove(DB)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.executescript('''
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=MEMORY;
        CREATE TABLE msg (
            id       TEXT,
            seq      INTEGER,
            ts       INTEGER,
            tstr     TEXT,
            sender   TEXT,
            mtype    TEXT,
            text     TEXT,
            recalled INTEGER,
            system   INTEGER,
            hasres   INTEGER,
            restype  TEXT
        );
    ''')

    # 只解析 messages 数组，用流式方式跳过前面的元数据
    with open(SRC, 'r', encoding='utf-8') as f:
        # 定位 "messages":[ 之后
        buf = f.read(65536)
        while '"messages"' not in buf:
            more = f.read(65536)
            if not more: break
            buf += more
        idx = buf.index('"messages"')
        # 找到数组起始 [
        i = buf.index('[', idx)
        f.seek(i + 1)
        rest = buf[i+1:]
        # 手工拼接：把已读剩余部分 + 后续流 交给一个生成器解析
        dec = json.JSONDecoder()

    # 由于 messages 是标准 JSON 数组，直接整体 json.load 也可行（144MB, 31万条）
    # 实测内存足够，改用整体加载以获得速度
    print('读取 JSON ...', flush=True)
    with open(SRC, 'r', encoding='utf-8') as f:
        d = json.load(f)
    msgs = d['messages']
    print(f'  消息数 {len(msgs):,}  用时 {time.time()-t0:.1f}s', flush=True)

    rows, seen = [], set()
    n_dup = n_sys0 = 0
    for x in msgs:
        mid = x.get('id')
        if mid in seen:
            n_dup += 1; continue
        seen.add(mid)
        s = x.get('sender') or {}
        name = s.get('name')
        content = x.get('content') or {}
        text = content.get('text') or ''
        res = content.get('resources') or []
        restype = ','.join(sorted({r.get('type','') for r in res if isinstance(r,dict)}))
        rows.append((mid, x.get('seq'), x.get('timestamp'), x.get('time'),
                     name, x.get('type'), text,
                     1 if x.get('recalled') else 0,
                     1 if x.get('system') else 0,
                     1 if res else 0, restype))
        if name == '0': n_sys0 += 1

    c.executemany('INSERT INTO msg VALUES (?,?,?,?,?,?,?,?,?,?,?)', rows)
    conn.commit()
    print(f'  去重跳过 {n_dup}  写入 {len(rows):,}  (sender=0 有 {n_sys0})', flush=True)

    c.executescript('''
        CREATE INDEX idx_ts ON msg(ts);
        CREATE INDEX idx_sender ON msg(sender);
        CREATE INDEX idx_type ON msg(mtype);
    ''')
    conn.commit()

    # 验证
    print('\n=== 入库验证 ===')
    for q,label in [
        ('SELECT COUNT(*) FROM msg','总条数'),
        ("SELECT COUNT(*) FROM msg WHERE mtype='type_1'",'文本条数'),
        ("SELECT COUNT(*) FROM msg WHERE recalled=1",'撤回'),
        ("SELECT COUNT(*) FROM msg WHERE system=1",'系统'),
        ("SELECT COUNT(*) FROM msg WHERE hasres=1",'带资源'),
        ("SELECT MIN(tstr) FROM msg",'最早'),
        ("SELECT MAX(tstr) FROM msg",'最晚'),
        ("SELECT SUM(LENGTH(text)) FROM msg",'总文本字符'),
    ]:
        print(f'  {label}: {c.execute(q).fetchone()[0]}')

    db_size = os.path.getsize(DB)/1024/1024
    print(f'\n数据库大小: {db_size:.1f} MB   总用时 {time.time()-t0:.1f}s')
    conn.close()

main()

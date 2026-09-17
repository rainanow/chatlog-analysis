#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据核对脚本（通用版）—— 换窗口/换会话后第一件事跑这个

两种用法：

  1) 首次使用：固化基准指纹
     python3 verify.py --init [chat.json] [chat.db]
     把当前文件的全部关键数字算出来，存进 fingerprint.json。
     以后再跑就以此为准。

  2) 日常核对：比对指纹
     python3 verify.py [chat.json] [chat.db]
     重算并与 fingerprint.json 对比，输出 ✅ / ⚠️。
     对不上说明文件变了或记错了，此时不要开始分析。

设计目的：防止"凭记忆写数字"导致的错误结论。
         任何在分析中引用的数字，都应该能在这里被验证。
"""
import json, sqlite3, os, sys

FP = 'fingerprint.json'


def calc(json_path, db_path):
    """把所有需要核对的关键数字算出来"""
    r = {}

    if os.path.exists(json_path):
        r['json_size_mb'] = round(os.path.getsize(json_path) / 1024 / 1024, 2)
        with open(json_path, 'r', encoding='utf-8') as f:
            d = json.load(f)

        ms = d.get('messages', [])
        ids = [m.get('id') for m in ms]
        r['messages_len'] = len(ms)
        r['unique_ids'] = len(set(ids))
        r['dup_ids'] = len(ids) - len(set(ids))
        r['system_json'] = sum(1 for m in ms if m.get('system'))
        r['recalled_json'] = sum(1 for m in ms if m.get('recalled'))

        st = d.get('statistics', {}) or {}
        r['statistics_total'] = st.get('totalMessages')
        r['statistics_system'] = (st.get('messageTypes') or {}).get('system')
        r['duration_days'] = (st.get('timeRange') or {}).get('durationDays')
        r['senders'] = {s['name']: s['messageCount'] for s in st.get('senders', [])}

        ci = d.get('chatInfo', {}) or {}
        r['self_name'] = ci.get('selfName')
        r['peer_name'] = ci.get('name')
        r['chat_type'] = ci.get('type')
        r['meta_name'] = (d.get('metadata') or {}).get('name')

    if os.path.exists(db_path):
        con = sqlite3.connect(db_path)
        c = con.cursor()
        r['db_count'] = c.execute('SELECT COUNT(*) FROM msg').fetchone()[0]
        r['sender_0'] = c.execute("SELECT COUNT(*) FROM msg WHERE sender='0'").fetchone()[0]
        r['system_table'] = c.execute('SELECT COUNT(*) FROM msg WHERE system=1').fetchone()[0]
        r['recalled_table'] = c.execute('SELECT COUNT(*) FROM msg WHERE recalled=1').fetchone()[0]
        mn, mx = c.execute('SELECT MIN(tstr),MAX(tstr) FROM msg').fetchone()
        r['db_time_min'], r['db_time_max'] = mn, mx
        try:
            r['recall_table'] = c.execute('SELECT COUNT(*) FROM recall').fetchone()[0]
        except Exception:
            r['recall_table'] = None
        # 各发送者条数
        r['db_senders'] = {n: v for n, v in c.execute(
            "SELECT sender,COUNT(*) FROM msg GROUP BY sender ORDER BY 2 DESC").fetchall()}
        con.close()

    return r


def show(r, label):
    print(f'\n【{label}】')
    order = [
        ('json_size_mb', 'JSON 大小 (MB)'),
        ('meta_name', '导出工具'),
        ('chat_type', '会话类型'),
        ('self_name', '我方'),
        ('peer_name', '对方'),
        ('messages_len', 'messages 数组长度'),
        ('unique_ids', '唯一 id'),
        ('dup_ids', '重复 id'),
        ('statistics_total', 'statistics 总数'),
        ('db_count', 'DB 总条数'),
        ('sender_0', "sender='0'"),
        ('system_json', 'system:true (JSON)'),
        ('system_table', 'system=1 (DB)'),
        ('statistics_system', 'statistics.system'),
        ('recalled_json', 'recalled:true (JSON)'),
        ('recalled_table', 'recalled=1 (DB)'),
        ('recall_table', 'recall 表'),
        ('duration_days', '跨度 (天)'),
        ('db_time_min', '最早'),
        ('db_time_max', '最晚'),
    ]
    for k, name in order:
        if k in r and r[k] is not None:
            print(f'  {name:26} {r[k]}')
    if r.get('senders'):
        print(f'  {"statistics 发送者":26} {r["senders"]}')
    if r.get('db_senders'):
        tot = sum(v for k, v in r['db_senders'].items() if k != '0')
        parts = []
        for k, v in r['db_senders'].items():
            pct = f'{v*100/tot:.2f}%' if (k != '0' and tot) else '-'
            parts.append(f'{k}={v} ({pct})')
        print(f'  {"DB 发送者":26} {", ".join(parts)}')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    init = '--init' in sys.argv

    jp = args[0] if len(args) > 0 else 'chat.json'
    dp = args[1] if len(args) > 1 else 'chat.db'

    print('=' * 64)
    print('聊天记录数据核对')
    print('=' * 64)

    if not os.path.exists(jp) and not os.path.exists(dp):
        print(f'\n⚠️  找不到 {jp} 或 {dp}\n')
        print('   请按以下顺序操作：')
        print('   1) 把导出的 JSON 重命名为 chat.json，放在本目录')
        print('   2) 运行 python3 import_db.py  生成 chat.db')
        print('   3) 运行 python3 verify.py --init  固化指纹')
        print('   4) 以后每次分析前运行 python3 verify.py 核对')
        print('\n   也可指定路径：python3 verify.py <json> <db>')
        return

    cur = calc(jp, dp)

    if init or not os.path.exists(FP):
        if not init and not os.path.exists(FP):
            print(f'\n⚠️  没有 {FP}，自动进入固化模式')
        show(cur, '当前文件实际值')
        with open(FP, 'w', encoding='utf-8') as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)
        print(f'\n✅ 已固化到 {FP}')
        print('   以后运行 python3 verify.py 会与此对比')
        print('=' * 64)
        return

    with open(FP, 'r', encoding='utf-8') as f:
        base = json.load(f)

    # 对比
    diffs = []
    for k in sorted(set(base) | set(cur)):
        b, v = base.get(k), cur.get(k)
        if b == v:
            continue
        diffs.append((k, b, v))

    if not diffs:
        print(f'\n✅ 全部 {len(base)} 项与 {FP} 一致，可以开始分析')
        show(cur, '关键数字')
    else:
        print(f'\n⚠️  发现 {len(diffs)} 项差异：\n')
        print(f'  {"字段":26} {"基准值":>16} {"当前值":>16}')
        print('  ' + '-' * 60)
        for k, b, v in diffs:
            print(f'  {k:26} {str(b):>16} {str(v):>16}')
        print('\n  → 先查清差异来源（文件变了？记错了？），再开始分析')
        print('  → 若确认新文件是正确的，用 --init 重新固化')

    print('=' * 64)


if __name__ == '__main__':
    main()

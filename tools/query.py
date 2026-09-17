#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chat.db 检索工具（通用版）

用法：python3 query.py <命令> [参数]

命令：
  day    YYYY-MM-DD              某天全部文字消息（自动去噪去重）
  range  "起" "止"                跨天原始记录
  kw     词1,词2                  全库关键词检索
  theme  <主题名>                 预设主题检索
  themes                         列出主题
  stat   YYYY-MM                  月度统计
  hour   YYYY-MM-DD               某天小时分布
  top                            全库概览
  peaks                           找异常高值（含文字占比，防斗图误判）
  silent  天数                     找长沉默断点

配置：themes.txt  自定义主题词，格式「主题名: 词1,词2,词3」
     不提供则使用内置通用主题。
"""
import sqlite3, sys, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('CHAT_DB') or os.path.join(HERE, 'chat.db')

DEFAULT_THEMES = {
    '心理':     ['抑郁', '焦虑', '躁郁', '双相', '躯体化', '心理', '情绪', '崩溃', '压力'],
    '就医':     ['去医院', '看病', '挂号', '医保', '医生', '检查', '吃药', '开药', '复诊'],
    '关系':     ['喜欢', '爱', '想见', '见面', '异地', '分手', '吵架', '生气', '原谅'],
    '分离':     ['离开', '走了', '再见', '最后', '结束', '回不去'],
    '自我否定': ['没用', '对不起', '抱歉', '都是我', '失败', '做不到', '不配'],
    '求助':     ['帮我', '求助', '撑不住', '受不了', '不敢', '害怕', '没人'],
    '否认防御': ['没事', '不用', '没必要', '不用管我', '我自己来'],
}

NOISE_PREFIX = ('[图片', '[戳一戳', '[表情', '[视频', '[语音', '[文件',
                '[合并转发', '[卡片消息', '请使用最新版手机')


def load_themes():
    t = dict(DEFAULT_THEMES)
    p = os.path.join(HERE, 'themes.txt')
    if os.path.exists(p):
        with open(p, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or ':' not in line:
                    continue
                name, words = line.split(':', 1)
                kws = [w.strip() for w in re.split('[,，]', words) if w.strip()]
                if kws:
                    t[name.strip()] = kws
    return t


def render(rows, limit=200):
    out = []
    for tstr, sender, text in rows:
        text = (text or '').replace('\n', ' / ')
        if text.startswith(NOISE_PREFIX) or 'xml version' in text:
            continue
        if len(text.strip()) < 2:
            continue
        if len(text) > limit:
            text = text[:limit] + '…'
        out.append(f'{tstr[:16]} [{sender}] {text}')
    return out


def dedup(lines):
    out = []
    for l in lines:
        body = l.split('] ', 1)[-1]
        if not out or out[-1].split('] ', 1)[-1] != body:
            out.append(l)
    return out


def cmd_day(cur, d):
    rows = cur.execute(
        "SELECT tstr,sender,text FROM msg WHERE tstr LIKE ? AND system=0 ORDER BY ts",
        (d + '%',)).fetchall()
    lines = dedup(render(rows))
    print(f'# {d}  原始 {len(rows)} 条 → 去噪去重后 {len(lines)} 条')
    print('\n'.join(lines))


def cmd_range(cur, a, b):
    rows = cur.execute(
        "SELECT tstr,sender,text FROM msg WHERE tstr>=? AND tstr<=? AND system=0 ORDER BY ts",
        (a, b)).fetchall()
    print('\n'.join(render(rows)))


def cmd_kw(cur, kws):
    kws = [k for k in re.split('[,，]', kws) if k]
    where = ' OR '.join(['text LIKE ?'] * len(kws))
    params = ['%' + k + '%' for k in kws]
    rows = cur.execute(
        f"SELECT tstr,sender,text FROM msg WHERE system=0 AND ({where}) ORDER BY ts",
        params).fetchall()
    rows = [r for r in rows
            if '合并转发' not in (r[2] or '') and 'xml version' not in (r[2] or '')]
    lines = render(rows, limit=160)
    print(f'# 命中 {len(rows)} 条（去噪后展示 {len(lines)} 条）')
    print('\n'.join(lines))


def cmd_theme(cur, name):
    themes = load_themes()
    if name not in themes:
        print('可用主题：' + ', '.join(themes))
        return
    print(f'# 主题「{name}」：{" / ".join(themes[name])}')
    cmd_kw(cur, ','.join(themes[name]))


def cmd_stat(cur, ym):
    n = cur.execute("SELECT COUNT(*) FROM msg WHERE tstr LIKE ?", (ym + '%',)).fetchone()[0]
    rows = cur.execute(
        "SELECT sender,COUNT(*) FROM msg WHERE tstr LIKE ? GROUP BY sender ORDER BY 2 DESC",
        (ym + '%',)).fetchall()
    days = cur.execute(
        "SELECT COUNT(DISTINCT substr(tstr,1,10)) FROM msg WHERE tstr LIKE ? AND system=0",
        (ym + '%',)).fetchone()[0]
    tot = sum(v for k, v in rows if k != '0')
    print(f'{ym}: 共 {n} 条，{days} 个活跃日，日均 {n // max(days,1)} 条')
    for s, c in rows:
        pct = f'{c*100/tot:.1f}%' if (s != '0' and tot) else '-'
        print(f'  {s}: {c}  ({pct})')


def cmd_hour(cur, d):
    for h, c in cur.execute(
            "SELECT substr(tstr,12,2) h, COUNT(*) FROM msg "
            "WHERE tstr LIKE ? AND system=0 GROUP BY h ORDER BY h",
            (d + '%',)).fetchall():
        print(f'{h}:00  {c:>5}  {"█" * min(c // 10, 60)}')


def cmd_top(cur):
    n = cur.execute('SELECT COUNT(*) FROM msg').fetchone()[0]
    mn, mx = cur.execute('SELECT MIN(tstr),MAX(tstr) FROM msg').fetchone()
    days = cur.execute('SELECT COUNT(DISTINCT substr(tstr,1,10)) FROM msg').fetchone()[0]
    print(f'总条数 {n:,}')
    print(f'时间范围 {mn} ~ {mx}')
    print(f'活跃天数 {days}')
    print('\n按年：')
    for y, c in cur.execute(
            "SELECT substr(tstr,1,4) y,COUNT(*) FROM msg GROUP BY y ORDER BY y").fetchall():
        print(f'  {y}  {c:>8,}  {"█" * min(c // 2000, 50)}')
    print('\n按人：')
    rows = cur.execute("SELECT sender,COUNT(*) FROM msg GROUP BY sender ORDER BY 2 DESC").fetchall()
    tot = sum(v for k, v in rows if k != '0')
    for s, c in rows:
        pct = f'{c*100/tot:.1f}%' if (s != '0' and tot) else '-'
        print(f'  {s}  {c:>8,}  ({pct})')


def cmd_peaks(cur):
    print('=== 单日消息 TOP 15 ===')
    print('（有效文字 = 排除图片/表情等占位消息，占比低说明是刷屏）')
    rows = cur.execute(
        "SELECT substr(tstr,1,10) d,COUNT(*) c FROM msg WHERE system=0 "
        "GROUP BY d ORDER BY c DESC LIMIT 15").fetchall()
    for d, c in rows:
        # 有效文字：不是附件占位，且有实际内容
        txt = cur.execute(
            "SELECT COUNT(*) FROM msg WHERE tstr LIKE ? AND hasres=0 "
            "AND LENGTH(TRIM(COALESCE(text,'')))>=2", (d + '%',)).fetchone()[0]
        pct = txt * 100 // max(c, 1)
        flag = '  ← 刷屏' if pct < 30 else ''
        print(f'  {d}  {c:>6}  有效文字 {txt:>6} ({pct}%){flag}')
    print('\n=== 单月消息量 ===')
    for m, c in cur.execute(
            "SELECT substr(tstr,1,7) m,COUNT(*) c FROM msg WHERE system=0 "
            "GROUP BY m ORDER BY m").fetchall():
        print(f'  {m}  {c:>7,}  {"█" * min(c // 1000, 60)}')


def cmd_silent(cur, n):
    n = int(n)
    print(f'=== 相邻消息间隔 > {n} 天的断点 ===')
    rows = cur.execute(
        "SELECT tstr,ts,LAG(tstr) OVER (ORDER BY ts),LAG(ts) OVER (ORDER BY ts) "
        "FROM msg WHERE system=0 ORDER BY ts").fetchall()
    cnt = 0
    for tstr, ts, prev, prevts in rows:
        if prevts and (ts - prevts) > n * 86400000:
            print(f'  {prev[:16]}  →  {tstr[:16]}   间隔 {(ts-prevts)/86400000:.1f} 天')
            cnt += 1
    print('  （无）' if cnt == 0 else f'  共 {cnt} 处')


def main():
    if not os.path.exists(DB):
        print(f'找不到数据库：{DB}')
        print('请先运行 import_db.py 生成 chat.db')
        sys.exit(1)
    con = sqlite3.connect(DB)
    con.execute('PRAGMA temp_store=MEMORY')
    cur = con.cursor()

    if len(sys.argv) < 2:
        print(__doc__)
        con.close()
        return
    cmd, a = sys.argv[1], sys.argv[2:]

    try:
        if cmd == 'day' and a:            cmd_day(cur, a[0])
        elif cmd == 'range' and len(a) >= 2: cmd_range(cur, a[0], a[1])
        elif cmd == 'kw' and a:           cmd_kw(cur, a[0])
        elif cmd == 'theme' and a:        cmd_theme(cur, a[0])
        elif cmd == 'themes':
            for k, v in load_themes().items():
                print(f'{k:10} {", ".join(v)}')
        elif cmd == 'stat' and a:         cmd_stat(cur, a[0])
        elif cmd == 'hour' and a:         cmd_hour(cur, a[0])
        elif cmd == 'top':                cmd_top(cur)
        elif cmd == 'peaks':              cmd_peaks(cur)
        elif cmd == 'silent' and a:       cmd_silent(cur, a[0])
        else:                             print(__doc__)
    finally:
        con.close()


if __name__ == '__main__':
    main()

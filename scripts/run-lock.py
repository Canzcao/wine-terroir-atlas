# coding: utf-8
"""采集轮次的互斥锁：防止两个自动化轮次同时写 catalog / 台账 / 采集包。

用法：
  python3 scripts/run-lock.py acquire [--ttl-min 100]   # 退出码 0 = 拿到锁；3 = 上一轮仍在跑（BUSY）
  python3 scripts/run-lock.py release
  python3 scripts/run-lock.py status

锁文件：work/.collector.lock（JSON：pid / host / startedAt / ttlMinutes / round）
TTL 过期视为僵尸锁（上一轮被杀没来得及 release），acquire 会接管并打印 STALE-OVERRIDE。
"""
import argparse
import json
import os
import socket
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'work' / '.collector.lock'
TZ = ZoneInfo('Asia/Shanghai')


def now():
    return datetime.now(TZ)


def read_lock():
    if not LOCK.exists():
        return None
    try:
        return json.loads(LOCK.read_text())
    except Exception:
        return {'pid': None, 'startedAt': None, 'raw': LOCK.read_text()[:200]}


def acquire(ttl_min, round_name):
    cur = read_lock()
    if cur and cur.get('startedAt'):
        try:
            started = datetime.fromisoformat(cur['startedAt'])
            age_min = (now() - started).total_seconds() / 60
        except Exception:
            age_min = 0
        if age_min < (cur.get('ttlMinutes') or ttl_min):
            print('BUSY 上一轮仍在跑：round=%s startedAt=%s age=%.0fmin ttl=%smin'
                  % (cur.get('round'), cur.get('startedAt'), age_min, cur.get('ttlMinutes')))
            return 3
        print('STALE-OVERRIDE 接管僵尸锁：round=%s startedAt=%s age=%.0fmin > ttl %smin'
              % (cur.get('round'), cur.get('startedAt'), age_min, cur.get('ttlMinutes')))
    elif cur:
        print('STALE-OVERRIDE 锁文件不可解析，接管：%s' % cur.get('raw', '')[:80])
    if not LOCK.parent.exists():
        LOCK.parent.mkdir(parents=True)
    LOCK.write_text(json.dumps({
        'pid': os.getpid(), 'host': socket.gethostname(),
        'startedAt': now().isoformat(timespec='seconds'),
        'ttlMinutes': ttl_min, 'round': round_name or '',
    }, ensure_ascii=False, indent=1))
    print('OK 已拿到锁（ttl %dmin）' % ttl_min)
    return 0


def release():
    if LOCK.exists():
        LOCK.unlink()
        print('锁已释放')
    else:
        print('没有锁文件，无需释放')
    return 0


def status():
    cur = read_lock()
    if not cur:
        print('空闲：没有锁文件')
        return 0
    print(json.dumps(cur, ensure_ascii=False, indent=1))
    if cur.get('startedAt'):
        try:
            age = (now() - datetime.fromisoformat(cur['startedAt'])).total_seconds() / 60
            print('已持有 %.0f 分钟（ttl %s）' % (age, cur.get('ttlMinutes')))
        except Exception:
            pass
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['acquire', 'release', 'status'])
    ap.add_argument('--ttl-min', type=int, default=100)
    ap.add_argument('--round', default='')
    a = ap.parse_args()
    if a.action == 'acquire':
        sys.exit(acquire(a.ttl_min, a.round))
    if a.action == 'release':
        sys.exit(release())
    sys.exit(status())


if __name__ == '__main__':
    main()

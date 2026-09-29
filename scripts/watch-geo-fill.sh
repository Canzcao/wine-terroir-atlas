#!/usr/bin/env bash
# 守望三条坐标补全通道：等三个结果文件都「停止增长」后退出，并打印快照。
#
# 为什么要这个脚本：后台任务在这个沙箱里 pgrep 看不到（返回 0），
# 靠 ps 更不行（operation not permitted）。唯一可靠的进度来源就是结果 JSON 的条数。
#
# 用法: bash scripts/watch-geo-fill.sh [静默判定秒数=180] [总上限分钟=170] [打印间隔秒=150]
set -u
cd "$(dirname "$0")/.."

QUIET=${1:-180}
CAP_MIN=${2:-170}
EVERY=${3:-150}
FILES="work/geo-fill-results.json work/geo-fill-web-results.json work/geo-fill-addr-results.json"

# Python 解释器：优先 $PY，其次常见托管目录，最后 PATH
detect_py() {
  if [ -n "${PY:-}" ]; then echo "$PY"; return; fi
  local p
  for p in "$HOME"/.workbuddy/binaries/python/versions/*/python.exe \
           "$HOME"/.workbuddy/binaries/python/envs/default/Scripts/python.exe; do
    [ -f "$p" ] && { echo "$p"; return; }
  done
  command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python
}
PY="$(detect_py)"

snapshot() {
  "$PY" - <<'PY'
import json
rows, sig = [], []
for f, label, cap in [('work/geo-fill-results.json', 'OSM ', 784),
                      ('work/geo-fill-web-results.json', 'web ', 470),
                      ('work/geo-fill-addr-results.json', 'addr', 784)]:
    try:
        d = json.load(open(f))
    except Exception:
        rows.append('  %s  未生成' % label); sig.append('-1'); continue
    m = sum(1 for x in d if x.get('status') == 'matched')
    pr = sum(1 for x in d if x.get('tier') == 'precise')
    ap = sum(1 for x in d if x.get('locationApproximate') is True)
    rows.append('  %s %4d/%d  命中 %3d（门牌 %d / 约略 %d）%s'
                % (label, len(d), cap, m, pr, ap, '  跑完' if len(d) >= cap else ''))
    sig.append(str(len(d)))
print('SIG %s' % ','.join(sig))
print('\n'.join(rows))
PY
}

start=$(date +%s)
last=""; quiet_start=$start; n=0
while :; do
  now=$(date +%s); elapsed=$(( (now - start) / 60 )); n=$((n + 1))
  cur=$(snapshot); sig=$(printf '%s' "$cur" | sed -n 's/^SIG //p')
  if [ "$n" -eq 1 ] || [ $(( n % 5 )) -eq 0 ]; then
    echo "--- $(date '+%H:%M') 已跑 ${elapsed} 分钟（采样 #${n}）---"
    printf '%s\n' "$cur" | sed '/^SIG /d'
  fi
  if [ "$sig" != "$last" ]; then last="$sig"; quiet_start=$now; fi
  quiet=$(( now - quiet_start ))
  if [ "$quiet" -ge "$QUIET" ]; then echo "== 结果文件连续 ${quiet}s 无增长，判定收束 =="; break; fi
  if [ "$elapsed" -ge "$CAP_MIN" ]; then echo "== 触及 ${CAP_MIN} 分钟上限 =="; break; fi
  sleep 30
done
echo "===== 最终快照（总耗时 $(( ($(date +%s) - start) / 60 )) 分钟）====="
snapshot | sed '/^SIG /d'

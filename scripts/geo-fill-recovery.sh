#!/usr/bin/env bash
# 坐标补全的收尾恢复轮：
#   ① 地址通道重跑被 Nominatim 限流的条目（记了 ERR 的那些）
#   ② OSM 名称通道补跑「今天新增的那批」（中国/格鲁吉亚/日本）——
#      它们的地址里没有 5 位邮编，地址通道抽不出地名，走名称通道更靠谱
#   ③ 把切片结果并回 OSM 主结果文件，供 merge-geo-fill.py 统一读取
#
# 串行跑，避免又把自己限流（并发 2 个进程时 ERR 会飙到 115 条）。
set -u
cd "$(dirname "$0")/.."
# Python 解释器：优先 $PY，其次常见托管目录，最后 PATH。
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

echo "===== ① 地址通道：重跑 ERR 条目 ====="
"$PY" -u scripts/fill-missing-winery-geo-addr.py /tmp/geo-missing.json \
      work/geo-fill-addr-results.json --redo-errors 2>&1 | tail -20

echo
echo "===== ② OSM 通道：补跑新增批次 ====="
"$PY" - <<'PY'
import json
from pathlib import Path
src = json.loads(Path('/tmp/geo-missing-tail.json').read_text())
batch = [x for x in src if x['id'].startswith(('winery-china', 'winery-georgia', 'winery-japan'))]
Path('/tmp/geo-missing-newbatch.json').write_text(json.dumps(batch, ensure_ascii=False, indent=1))
print('切片 %d 条：%s' % (len(batch), ', '.join(x['id'] for x in batch[:4]) + ' …'))
PY
"$PY" -u scripts/fill-missing-winery-geo.py /tmp/geo-missing-newbatch.json \
      work/geo-fill-results-newbatch.json 2>&1 | tail -40

echo
echo "===== ③ 切片结果并回 OSM 主结果文件 ====="
"$PY" - <<'PY'
import json
from pathlib import Path
main = Path('work/geo-fill-results.json')
extra = Path('work/geo-fill-results-newbatch.json')
rows = json.loads(main.read_text())
have = {r['id'] for r in rows}
add = 0
if extra.exists():
    for r in json.loads(extra.read_text()):
        if r['id'] not in have:
            rows.append(r); have.add(r['id']); add += 1
main.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
m = sum(1 for r in rows if r.get('status') == 'matched')
print('OSM 主结果 %d 条（并入 %d，命中 %d）' % (len(rows), add, m))
PY

echo
echo "===== 最终统计 ====="
"$PY" - <<'PY'
import json
for f, label in [('work/geo-fill-results.json', 'OSM '),
                 ('work/geo-fill-web-results.json', 'web '),
                 ('work/geo-fill-addr-results.json', 'addr')]:
    d = json.load(open(f))
    m = [x for x in d if x.get('status') == 'matched']
    print('%s %4d 条  命中 %3d（门牌 %d / 约略 %d）'
          % (label, len(d), len(m),
             sum(1 for x in m if x.get('tier') == 'precise'),
             sum(1 for x in m if x.get('locationApproximate') is True)))
PY

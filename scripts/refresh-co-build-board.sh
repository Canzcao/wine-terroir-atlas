#!/usr/bin/env bash
# 刷新「待共建清单」并发布上线。
#
# 用途：采集流水线**每轮收束后**调用一次，保证线上的待共建表格跟着资料库走。
#       也可人工随时跑。幂等、可重复执行。
#
# 用法：
#   bash scripts/refresh-co-build-board.sh              # 生成 + 部署
#   bash scripts/refresh-co-build-board.sh --no-deploy  # 只生成数据，不部署
#
# 采集自动化里只需这一行（把 $BAN 指向本仓库根即可）：
#   bash scripts/refresh-co-build-board.sh
set -euo pipefail

# 仓库根 = 本脚本的上级目录；可用 $BAN 覆盖
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BAN="${BAN:-$REPO_ROOT}"
DEPLOY_DIR="${DEPLOY_DIR:-$REPO_ROOT}"
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
PY="${PY:-$(detect_py)}"
DO_DEPLOY=1
SKIP_MEDIA=0
for arg in "$@"; do
  case "$arg" in
    --no-deploy) DO_DEPLOY=0 ;;
    --skip-media) SKIP_MEDIA=1 ;;
  esac
done

# ── 第 0 步：把采集到的图片并回资料库并发布 ────────────────────────────────
# 为什么放在最前面：看板的「图片」列读的是 entity-photos.json，而图片上站要经过
#   采集清单 → catalog-seed.json → publish-entity-photos.py → <deploy>/photos
# 中间那一步（manifest → catalog）历史上一直缺失，导致磁盘上 8 千多张图只有
# 2 千多张真的上了站。这里补上，保证**每轮收束后图片自动跟着上站**。
# 合并脚本幂等、发布脚本按 mtime 增量，重复跑很便宜。
if [ "$SKIP_MEDIA" -eq 1 ]; then
  echo "==> 0/3 已跳过图片合并与发布（--skip-media）"
else
  echo "==> 0/3 合并采集图片清单并生成缩略图"
  cd "$BAN"
  if "$PY" scripts/merge-collected-media.py; then
    # 只留一行汇总：脚本尾部的 missing / ambiguous 明细太长，收尾日志不需要
    "$PY" scripts/publish-entity-photos.py | grep -E '^实体 |^缩略图 →' || true
  else
    echo "   ⚠️ 图片合并失败（种子库未被改动，脚本会自行报错）。跳过发布，继续刷新看板。" >&2
  fi
fi

echo "==> 1/3 重算看板数据（读 catalog-seed / country-rotation / collection-progress / entity-photos）"
cd "$BAN"
"$PY" scripts/build-co-build-board.py

# 落盘后用生成的 JSON 自检：条目数 > 0 且三类都在
"$PY" - <<'PYEOF'
import json, sys
from pathlib import Path
import os
p = Path(os.environ.get('BAN', '.')) / 'public' / 'co-build-data.json'
d = json.loads(p.read_text(encoding='utf-8'))
t = d['totals']
assert t['records'] > 1000, '记录数异常：%s' % t['records']
assert len(d['regionGaps']) > 0, '产区缺口为空，看板会没有内容'
assert len(d['wineryGaps']) > 0, '酒庄缺口为空'
assert len(d['queueRounds']) == 19, '轮转队列应为 19 国，实际 %d' % len(d['queueRounds'])
print('   自检通过：记录 %d ｜ 待补产区 %d ｜ 待补酒庄 %d ｜ 未采集产区 %d ｜ 队列 %d 国'
      % (t['records'], len(d['regionGaps']), len(d['wineryGaps']),
         t['pendingRegions'], len(d['queueRounds'])))
PYEOF

if [ "$DO_DEPLOY" -eq 0 ]; then
  echo "==> 已跳过部署（--no-deploy）。数据文件：$BAN/public/co-build-data.json"
  exit 0
fi

echo "==> 3/3 部署上线"
cd "$DEPLOY_DIR"
./deploy/deploy.sh

echo "==> 完成。共建看板： ${PUBLIC_URL:-http://localhost:3020}/community?view=gaps"

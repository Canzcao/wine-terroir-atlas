#!/usr/bin/env bash
# =============================================================================
# 风土图鉴 · 一键构建并发布到腾讯云（Windows / Git Bash 版）
#
#   bash deploy/deploy.local.sh              # 全量：构建 + 自检 + 同步 + 重启
#   bash deploy/deploy.local.sh --skip-build # 跳过本地构建（产物刚构建过）
#   bash deploy/deploy.local.sh --dry-run    # 只打印计划，不碰服务器
#   bash deploy/deploy.local.sh --full       # 强制全量传 photos（不用增量）
#
# 与 mac 版 deploy/deploy.sh 的区别（都是因为 Windows 上没有的东西）：
#   1. 本机【没有 rsync】→ 改用 `tar | ssh tar` 传输，photos 走**增量**（只传新增）
#   2. 原脚本的 SRC / NODE_BIN / NPM_BIN 是 mac 绝对路径 → 这里全部探测式解析
#   3. 原脚本的 SSH_KEY 默认 ~/.ssh/terroir_deploy（本机没有）→ 回落到 ~/.ssh/id_ed25519
#   4. 冒烟测试在本机需要绕过沙箱 → 由调用方（WorkBuddy）加 dangerouslyDisableSandbox
#
# 绝不碰 VINCODE 主站（wineapp / 8868）的任何文件与进程；只操作
#   /opt/terroir-atlas 与 pm2 应用 terroir-atlas（端口 3020）。
# =============================================================================

set -euo pipefail

# --- 0. 基础路径（可被环境变量覆盖）-----------------------------------------
LOCAL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 采集工程根目录。优先用 $SRC；否则判定脚本所在仓库根是否为采集工程，再回落。
detect_src() {
  if [ -n "${SRC:-}" ]; then echo "$SRC"; return; fi
  # 本脚本位于 <repo>/deploy/，仓库根即候选一
  local cands=(
    "$LOCAL"
    "$HOME/WorkBuddy/2026-09-12/ban"
  )
  local c
  for c in "${cands[@]}"; do
    [ -f "$c/scripts/build.mjs" ] && { echo "$c"; return; }
  done
  echo ""
}
SRC="$(detect_src)"

# ★ 部署目标必须由环境变量提供（开源版不含任何具体服务器地址）
#   例：SERVER=root@your.server.ip bash deploy/deploy.local.sh
SERVER="${SERVER:?请设置 SERVER，例如 SERVER=root@1.2.3.4}"
REMOTE_DIR="${REMOTE_DIR:-/opt/terroir-atlas}"
APP_NAME="${APP_NAME:-terroir-atlas}"
APP_PORT="${APP_PORT:-3020}"
PUBLIC_URL="${PUBLIC_URL:-http://localhost:3020}"

# --- 1. 工具链探测（★ 不写死版号：版号目录会变）------------------------------
# node / npm：取 ~/.workbuddy/binaries/node/versions 下版本号最大的那个
detect_node() {
  if [ -n "${NODE_BIN:-}" ]; then echo "$NODE_BIN"; return; fi
  local base="$HOME/.workbuddy/binaries/node/versions"
  local p
  for p in $(ls -1d "$base"/*/ 2>/dev/null | grep -v '/current/' | sort -Vr); do
    [ -x "${p%/}/node.exe" ] && { echo "${p%/}/node.exe"; return; }
    [ -x "${p%/}/node" ]     && { echo "${p%/}/node";     return; }
  done
  command -v node 2>/dev/null || echo ""
}
detect_npm() {
  if [ -n "${NPM_BIN:-}" ]; then echo "$NPM_BIN"; return; fi
  local base="$HOME/.workbuddy/binaries/node/versions"
  local p
  for p in $(ls -1d "$base"/*/ 2>/dev/null | grep -v '/current/' | sort -Vr); do
    [ -f "${p%/}/npm" ] && { echo "${p%/}/npm"; return; }
  done
  command -v npm 2>/dev/null || echo ""
}
NODE_BIN="$(detect_node)"
NPM_BIN="$(detect_npm)"

# 用 npm 同目录下的 node 更稳（避免两个不同版本混用）
NODE_DIR="$(dirname "$NODE_BIN" 2>/dev/null || true)"
NODE_RUN="$NODE_BIN"

# python：用于 photos 增量差集（必须原生 Windows python，不能用 msys 的）
detect_py() {
  if [ -n "${PY:-}" ]; then echo "$PY"; return; fi
  local base="$HOME/.workbuddy/binaries/python/versions"
  local p
  for p in $(ls -1d "$base"/*/ 2>/dev/null | grep -v '/current/' | sort -Vr); do
    [ -f "${p%/}/python.exe" ] && { echo "${p%/}/python.exe"; return; }
  done
  command -v python 2>/dev/null || echo ""
}
PY="$(detect_py)"

# ★ tar：必须用 Windows 自带的 bsdtar 绝对路径。
#   修过 PATH 之后 PortableGit 的 usr/bin 排在 System32 前面，敲 `tar` 命中的是
#   GNU tar —— 它会把 `C:/...` 当远程主机，报 `Cannot connect to C: resolve failed`。
TAR_BIN="${TAR_BIN:-/c/Windows/System32/tar.exe}"
[ -x "$TAR_BIN" ] || TAR_BIN="$(command -v tar)"

# ★ SSH 私钥：mac 用的是 ~/.ssh/terroir_deploy（本机没有），回落 id_ed25519
detect_key() {
  if [ -n "${SSH_KEY:-}" ]; then echo "$SSH_KEY"; return; fi
  local k
  for k in "$HOME/.ssh/terroir_deploy" "$HOME/.ssh/id_ed25519" "$HOME/.ssh/id_rsa"; do
    [ -f "$k" ] && { echo "$k"; return; }
  done
  echo ""
}
SSH_KEY="$(detect_key)"
SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20)

# --- 2. 参数 ---------------------------------------------------------------
DO_BUILD=1
DO_SYNC=1
FULL_PHOTOS=0
for arg in "$@"; do
  case "$arg" in
    --skip-build) DO_BUILD=0 ;;
    --dry-run)    DO_SYNC=0 ;;
    --full)       FULL_PHOTOS=1 ;;
    -h|--help)
      # 只打脚本头部那段说明，到第二个 ==== 分隔线为止
      awk 'NR>1 && /^# =====/{n++; if(n==2) exit} NR>1 && /^#/{sub(/^# ?/,""); print}' "${BASH_SOURCE[0]}"
      exit 0 ;;
    *) echo "未知参数：$arg（-h 看用法）" >&2; exit 2 ;;
  esac
done

# --- 3. 前置校验（找不到就停下来，绝不猜）------------------------------------
fail() { echo "❌ $*" >&2; exit 1; }

echo "风土图鉴 · Windows 部署"
echo "  采集工程 SRC   = ${SRC:-<未找到>}"
echo "  部署工程 LOCAL = $LOCAL"
echo "  目标           = $SERVER:$REMOTE_DIR  (pm2: $APP_NAME, 端口 $APP_PORT)"
echo "  node           = ${NODE_BIN:-<未找到>}"
echo "  npm            = ${NPM_BIN:-<未找到>}"
echo "  python         = ${PY:-<未找到>}"
echo "  tar            = $TAR_BIN"
echo "  ssh key        = ${SSH_KEY:-<未找到>}"
echo

[ -n "$SRC" ]      || fail "找不到采集工程（含 scripts/build.mjs）。用 SRC=/path/to/ban 指定。"
[ -n "$NODE_BIN" ] || fail "找不到 node。用 NODE_BIN=/path/to/node.exe 指定。"
[ -n "$SSH_KEY" ]  || fail "找不到 SSH 私钥。用 SSH_KEY=/path/to/key 指定。"
[ -f "$LOCAL/deploy/deploy.sh" ] || fail "$LOCAL 不像部署工程（缺 deploy/deploy.sh）。"

ssh "${SSH_OPTS[@]}" "$SERVER" 'true' 2>/dev/null || fail "SSH 连不上 $SERVER（检查网络/私钥）。"

# --- 4. 构建 ---------------------------------------------------------------
if [ "$DO_BUILD" -eq 1 ]; then
  echo "==> 1/5 构建站点（含最新 data/catalog-seed.json、entity-photos.json）"
  [ -n "$NPM_BIN" ] || fail "需要 npm 才能构建；或用 --skip-build 跳过。"
  cd "$SRC"
  # ★ 不写 `npm run build`：package.json 里的 build 是 `node scripts/build.mjs`，
  #   直接调 node 可以完全绕开 npm 在 Git Bash 下的 .cmd 包装问题。
  "$NODE_RUN" scripts/build.mjs
  # ★ 当 SRC 与 LOCAL 是同一目录（本机恢复 Canonical 布局）时，
  #   `cp a a` 会以 "are the same file" 报错并因 set -e 直接中断整个部署。
  #   此时文件已经就位，跳过即可。
  if [ "$(cd "$SRC" && pwd)" = "$(cd "$LOCAL" && pwd)" ]; then
    echo "    SRC 与 LOCAL 同目录，产物已在位，跳过 cp"
  else
    cp dist/server/index.js "$LOCAL/dist/server/index.js"
  fi
  echo "    Worker 产物: $(du -h "$LOCAL/dist/server/index.js" | cut -f1)"
else
  echo "==> 1/5 已跳过构建（--skip-build）"
fi

# --- 5. 本地自检 -----------------------------------------------------------
echo "==> 2/5 本地自检（smoke_test.mjs）"
cd "$LOCAL"
# ⚠️ 冒烟测试要起本地 HTTP 服务，在 WorkBuddy 沙箱里会被拦。
#    从 WorkBuddy 调用本脚本时，必须给 Bash 工具加 dangerouslyDisableSandbox。
set +e
"$NODE_RUN" --no-warnings smoke_test.mjs
SMOKE=$?
set -e
if [ "$SMOKE" -ne 0 ]; then
  fail "冒烟测试未通过（退出码 $SMOKE）。已中止，服务器未被改动。"
fi

# --- 6. 同步代码 -----------------------------------------------------------
if [ "$DO_SYNC" -eq 0 ]; then
  echo "==> 3/5~5/5 已跳过同步与重启（--dry-run）"
  echo "    产物已就绪：$LOCAL/dist/server/index.js"
  exit 0
fi

echo "==> 3/5 同步代码与运行层 → $SERVER:$REMOTE_DIR"
ssh "${SSH_OPTS[@]}" "$SERVER" "mkdir -p '$REMOTE_DIR/var'"
# 代码/运行层是「整体覆盖」语义：连同 deploy 脚本一起推上去，服务器端保持与本地一致。
# 用 tar 管道而非 rsync（本机没有 rsync）。体积小（~22M），每次全传也很快。
"$TAR_BIN" czf - \
  dist server.mjs ecosystem.config.cjs package.json deploy README.md \
  | ssh "${SSH_OPTS[@]}" "$SERVER" "cd '$REMOTE_DIR' && tar xzf -"
echo "    远端 index.js: $(ssh "${SSH_OPTS[@]}" "$SERVER" "ls -la '$REMOTE_DIR/dist/server/index.js'" | awk '{printf "%.1f MB\n", $5/1048576}')"

# --- 7. 同步 photos（增量）-------------------------------------------------
echo "==> 4/5 同步 photos（增量）"

# ★ 本机可能不持有 photos/ 树（照片以远端为权威源；本地只做边界/代码时
#   根本没有这个目录）。此时 find 会报 ENOENT 并以 set -e 中断整个部署——
#   后果是代码已传上去、pm2 却还没重启，线上处于"文件新、进程旧"的中间态。
#   所以这里必须显式跳过，并明确告知远端照片保持原样。
if [ ! -d "$LOCAL/photos" ]; then
  echo "    本机没有 photos/ 目录 → 跳过（远端照片保持原样，不删不改）"
  FULL_PHOTOS=0
  SKIP_PHOTOS=1
else
  SKIP_PHOTOS=0
  PHOTOS_LOCAL_N=$(cd "$LOCAL" && find photos -type f | wc -l)
  echo "    本地 $PHOTOS_LOCAL_N 个文件"
fi

if [ "$SKIP_PHOTOS" -eq 1 ]; then
  :
elif [ "$FULL_PHOTOS" -eq 1 ]; then
  echo "    --full：全量传输"
  "$TAR_BIN" czf - photos | ssh "${SSH_OPTS[@]}" "$SERVER" "cd '$REMOTE_DIR' && tar xzf -"
else
  [ -n "$PY" ] || fail "photos 增量需要 python；或用 --full 全量。用 PY=/path/to/python.exe 指定。"

  TMPL="$LOCAL/work_local_photos.txt"
  TMPR="$LOCAL/work_remote_photos.txt"
  TMPU="$LOCAL/work_photos_upload.txt"
  TMPU_LF="$LOCAL/work_photos_upload_lf.txt"
  TMPTGZ="$LOCAL/work_photos.tgz"
  # shellcheck disable=SC2064
  trap "rm -f '$TMPL' '$TMPR' '$TMPU' '$TMPU_LF' '$TMPU_LF.tmp' '$TMPTGZ' '$LOCAL/work_tar.log'" EXIT

  (cd "$LOCAL" && find photos -type f | sed 's|^photos/||') | sort > "$TMPL"
  ssh "${SSH_OPTS[@]}" "$SERVER" "cd '$REMOTE_DIR' && find photos -type f | sed 's|^photos/||'" \
    2>/dev/null | sort > "$TMPR"

  # ★ 用 Python set 求差集，不用 comm：comm 依赖 LC_COLLATE，
  #   本机（中文 Windows）排序规则与远端不一致，会报 "input is not in sorted order"
  #   并给出**错误结果**（这是静默错误里最危险的一种）。
  "$PY" - "$TMPL" "$TMPR" "$TMPU" <<'PYEOF'
import sys
from pathlib import Path
lp, rp, op = (Path(a) for a in sys.argv[1:4])
L = {x for x in lp.read_text(encoding='utf-8').split() if x}
R = {x for x in rp.read_text(encoding='utf-8').split() if x}
diff = sorted(L - R)
op.write_text('\n'.join(diff) + ('\n' if diff else ''), encoding='utf-8')
print(f'    远端 {len(R)} 个 / 需上传 {len(diff)} 个'
      + (f'（远端多出 {len(R - L)} 个旧残留，未自动删除）' if R - L else ''))
PYEOF

  if [ ! -s "$TMPU" ]; then
    echo "    没有新增图片，跳过。"
  else
    # ★★ CRLF 陷阱：清单若是 Windows 行尾，tar -T 会把 \r 当成文件名的一部分，
    #    报 `Cannot stat: photos/x.jpg\r`；更坑的是若把 stderr 重定向掉，
    #    包会只有几十字节却"成功"，远端文件数**完全不变**。
    #    所以：① 强制转 LF  ② 打包后校验体积  ③ 不抑制 stderr。
    tr -d '\r' < "$TMPU" > "$TMPU_LF"
    sed 's|^|photos/|' "$TMPU_LF" > "$TMPU_LF.tmp" && mv "$TMPU_LF.tmp" "$TMPU_LF"

    cd "$LOCAL"
    # ⚠️ 这里【不能】用 `tar ... 2>/dev/null` 或 `| grep ... || true` 收尾：
    #    那会把 tar 的失败一起吞掉，包只有几十字节也照样往下走。
    #    改为：先写日志文件，再看退出码，再校验包体积。
    if ! "$TAR_BIN" czf "$TMPTGZ" -T "$TMPU_LF" > "$LOCAL/work_tar.log" 2>&1; then
      echo "    tar 报错（前 5 行）："
      head -5 "$LOCAL/work_tar.log" | sed 's/^/      /'
      rm -f "$LOCAL/work_tar.log"
      fail "打包失败，已中止（服务器未被改动）。"
    fi
    rm -f "$LOCAL/work_tar.log"

    TGZ_BYTES=$(stat -c %s "$TMPTGZ" 2>/dev/null || echo 0)
    if [ "$TGZ_BYTES" -lt 10000 ]; then
      fail "图片包只有 ${TGZ_BYTES} 字节，明显不对（清单行尾或路径有问题）。已中止。"
    fi
    echo "    包体 $(awk "BEGIN{printf \"%.1f\", $TGZ_BYTES/1048576}") MB，上传中…"

    ssh "${SSH_OPTS[@]}" "$SERVER" "cd '$REMOTE_DIR' && tar xzf -" < "$TMPTGZ"

    AFTER=$(ssh "${SSH_OPTS[@]}" "$SERVER" "cd '$REMOTE_DIR' && find photos -type f | wc -l" | tr -d '\r')
    echo "    远端 photos: $AFTER 个（本地 $PHOTOS_LOCAL_N 个）"
    if [ "$AFTER" -lt "$PHOTOS_LOCAL_N" ]; then
      echo "    ⚠️ 远端仍少于本地：可能有文件没落地（tar 静默失败？）。再跑一次或 --full。"
    fi
  fi
fi

# --- 8. 属主 / 重启 / 探活 / 公网复验 --------------------------------------
echo "==> 5/5 修正属主、重启进程并探活"
ssh "${SSH_OPTS[@]}" "$SERVER" "chown -R root:root '$REMOTE_DIR' 2>/dev/null || true; \
  cd '$REMOTE_DIR' && \
  (pm2 restart '$APP_NAME' --update-env 2>/dev/null || pm2 start ecosystem.config.cjs) && \
  pm2 save >/dev/null 2>&1 || true; \
  sleep 3; \
  curl -s --max-time 8 -o /dev/null -w '    本机 /healthz -> %{http_code}\n' http://127.0.0.1:$APP_PORT/healthz"

# ★ 这里如实报「catalog 的 JSON 字节数」，不谎称是记录条数。
#   （曾写 `wc -c` 却标成「条数」，12 MB 的字节数被误读成 1200 万条记录。）
echo -n "    本机 /api/catalog 体积 -> "
ssh "${SSH_OPTS[@]}" "$SERVER" \
  "curl -s --max-time 20 http://127.0.0.1:$APP_PORT/api/catalog | wc -c" | tr -d '\r'
echo "    （字节；要条数看下面的公网复验）"

echo
echo "==> 公网复验 $PUBLIC_URL"
FAILED=0
for p in / /healthz /api/catalog /entity-photos.json /co-build-data.json; do
  code=$(curl -s --max-time 25 -o /dev/null -w '%{http_code}' "$PUBLIC_URL$p" 2>/dev/null || echo 000)
  case "$code" in
    200) mark="OK  " ;;
    000) mark="WARN" ;;   # 本机 curl 走代理时会给 000，不代表线上坏了
    *)   mark="FAIL"; FAILED=$((FAILED + 1)) ;;
  esac
  printf '  [%s] %s  %s\n' "$mark" "$code" "$p"
done

# ★ 边界文件是「被 base64 嵌进 dist/server/index.js」的那一份，
#   线上是从嵌入产物解出来的——所以必须直接从公网取回来数一遍，
#   否则无法证明新边界真的上线了（本地文件对不代表线上对）。
#   这里用远端 curl 拿字节数 + 本地解析条数，避免本机代理干扰。
if [ -n "$PY" ]; then
  echo
  echo -n "  线上 region-boundaries.geojson -> "
  ssh "${SSH_OPTS[@]}" "$SERVER" \
    "curl -s --max-time 30 http://127.0.0.1:$APP_PORT/region-boundaries.geojson" \
    > "$LOCAL/work_boundaries_check.geojson" 2>/dev/null || true
  "$PY" - "$LOCAL/work_boundaries_check.geojson" "$SRC/public/region-boundaries.geojson" <<'PYEOF' || true
import json, sys
from pathlib import Path
def feats(p):
    d = json.loads(Path(p).read_text(encoding='utf-8'))
    return d.get('features') or []
try:
    on = feats(sys.argv[1]); lo = feats(sys.argv[2])
    onb = Path(sys.argv[1]).stat().st_size
    print(f"{len(on)} 条 / {onb} 字节")
    if len(on) != len(lo):
        print(f"  ⚠️ 与本地不一致：本地 {len(lo)} 条 vs 线上 {len(on)} 条（线上仍是旧产物？）")
    else:
        print(f"  ✅ 与本地一致（{len(lo)} 条边界全部上线）")
except Exception as e:
    print(f"<解析失败：{e}>")
PYEOF
  rm -f "$LOCAL/work_boundaries_check.geojson"
fi

# 真实数据结构（不是字节数）：从线上拉 catalog 数一遍，与本地 seed 对账
if [ -n "$PY" ]; then
  echo
  echo -n "  线上 catalog 记录数 -> "
  curl -s --max-time 30 "$PUBLIC_URL/api/catalog" > "$LOCAL/work_catalog_check.json" 2>/dev/null || true
  "$PY" - "$LOCAL/work_catalog_check.json" "$SRC/data/catalog-seed.json" <<'PYEOF' || true
import json, sys, collections
from pathlib import Path
try:
    online = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    ents = online.get('entities') or []
    kinds = collections.Counter(e.get('kind') for e in ents)
    print(f"{len(ents)} 条  " + ' '.join(f'{k}={v}' for k, v in sorted(kinds.items())))
    seed = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
    if len(seed) != len(ents):
        print(f"  ⚠️ 与本地 seed 不一致：本地 {len(seed)} 条 vs 线上 {len(ents)} 条")
    else:
        print(f"  ✅ 与本地 seed 一致（{len(seed)} 条）")
except Exception as e:
    print(f"<解析失败：{e}>")
PYEOF
  rm -f "$LOCAL/work_catalog_check.json"
fi

echo
if [ "$FAILED" -eq 0 ]; then
  echo "✅ 完成。线上地址： $PUBLIC_URL"
else
  echo "⚠️ 完成，但有 $FAILED 个端点返回非 200。线上地址： $PUBLIC_URL"
fi
echo "   共建看板：       $PUBLIC_URL/community?view=gaps"
echo
echo "提示：本机 curl 若出现 HTTP 000（WARN），通常是本地代理拦了；"
echo "      换 'ssh $SERVER \"curl -s -o /dev/null -w %{http_code} http://127.0.0.1:$APP_PORT/healthz\"' 复核。"

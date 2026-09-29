#!/usr/bin/env bash
# 风土图鉴 · 服务器端一次性初始化（幂等，可重复执行）
#
# 目标环境实测：
#   OpenCloudOS 9.6 / 系统 nginx 1.29.8 (/etc/nginx/conf.d/) / 宝塔面板 11.8.0（不参与本部署）
#   系统 node v20.18.1  ->  node:sqlite 需要 >=22.5，故另装 /opt/node22
#   pm2 7.0.3（现有应用 wineapp，端口 8868）
#   已占用端口：22 25 80 443 8868 8888  ->  本项目用 3020
#
# 用法： bash /opt/terroir-atlas/deploy/server-setup.sh

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/terroir-atlas}"
APP_NAME="terroir-atlas"
# ★ 域名由环境变量提供（开源版不含具体域名）
DOMAIN="${DOMAIN:?请设置 DOMAIN，例如 DOMAIN=atlas.example.com}"
PORT="${PORT:-3020}"
NODE_DIR="/opt/node22"
CERT_DIR="/etc/nginx/ssl"
NGINX_CONF="/etc/nginx/conf.d/${DOMAIN}.conf"

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

say "0/6 环境体检"
. /etc/os-release 2>/dev/null || true
echo "  系统        : ${PRETTY_NAME:-unknown}"
echo "  系统 node   : $(node -v 2>/dev/null || echo 未安装)（主站 wineapp 在用，不要动）"
echo "  应用目录    : $APP_DIR"
echo "  目标端口    : $PORT"

say "1/6 确认独立 Node 运行时"
if [ ! -x "$NODE_DIR/bin/node" ]; then
  echo "  未找到 $NODE_DIR，从腾讯云镜像安装…"
  V=$(curl -s --max-time 30 https://mirrors.cloud.tencent.com/nodejs-release/index.json \
      | tr '{' '\n' | grep -o '"version":"v22\.[0-9.]*"' | head -1 | sed 's/.*"v\(22\.[0-9.]*\)".*/\1/')
  [ -n "$V" ] || { echo "  ✗ 无法获取 Node 22 版本号，请检查出网"; exit 1; }
  curl -sL --max-time 600 -o /tmp/node22.tar.xz \
    "https://mirrors.cloud.tencent.com/nodejs-release/v${V}/node-v${V}-linux-x64.tar.xz"
  rm -rf "$NODE_DIR"; mkdir -p "$NODE_DIR"
  tar -xJf /tmp/node22.tar.xz -C "$NODE_DIR" --strip-components=1
  rm -f /tmp/node22.tar.xz
fi
"$NODE_DIR/bin/node" -v | sed 's/^/  已就绪: Node /'
"$NODE_DIR/bin/node" -e 'require("node:sqlite")' 2>/dev/null \
  && echo "  node:sqlite 可用 ✓" \
  || { echo "  ✗ node:sqlite 不可用，版本过低"; exit 1; }

say "2/6 准备数据目录"
mkdir -p "$APP_DIR/var/bucket" /var/www/certbot
echo "  $APP_DIR/var （SQLite 库 + 附件桶 + 日志）"

say "3/6 源站证书（自签名，沿用主站同一套模式）"
mkdir -p "$CERT_DIR"
if [ ! -f "$CERT_DIR/${DOMAIN}.crt" ]; then
  openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
    -keyout "$CERT_DIR/${DOMAIN}.key" -out "$CERT_DIR/${DOMAIN}.crt" \
    -subj "/CN=${DOMAIN}" -addext "subjectAltName=DNS:${DOMAIN}" >/dev/null 2>&1
  chmod 600 "$CERT_DIR/${DOMAIN}.key"
  echo "  已生成 ${CERT_DIR}/${DOMAIN}.crt（10 年有效）"
else
  echo "  证书已存在，跳过"
fi
echo "  访客看到的是 Cloudflare 边缘证书，此证书只用于 CF -> 源站这一段"

say "4/6 安装 nginx 站点配置"
if [ -f "$APP_DIR/deploy/nginx-${DOMAIN}.conf" ]; then
  cp "$APP_DIR/deploy/nginx-${DOMAIN}.conf" "$NGINX_CONF"
  echo "  已写入 $NGINX_CONF"
else
  echo "  ✗ 找不到 $APP_DIR/deploy/nginx-${DOMAIN}.conf"; exit 1
fi
nginx -t
systemctl reload nginx
echo "  nginx 已重载（wineapp 的配置未改动）"

say "5/6 启动应用进程"
cd "$APP_DIR"
mkdir -p var
if pm2 describe "$APP_NAME" >/dev/null 2>&1; then
  pm2 restart "$APP_NAME" --update-env
else
  pm2 start ecosystem.config.cjs
fi
pm2 save >/dev/null 2>&1 || true
sleep 3

say "6/6 探活"
code=$(curl -s --max-time 10 -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/healthz" || echo 000)
echo "  Node 直连   http://127.0.0.1:${PORT}/healthz  -> ${code}"
code=$(curl -s --max-time 10 -o /dev/null -w '%{http_code}' -H "Host: ${DOMAIN}" http://127.0.0.1/ || echo 000)
echo "  nginx :80   Host=${DOMAIN}                  -> ${code}（301 表示已跳 HTTPS，正常）"
code=$(curl -sk --max-time 10 -o /dev/null -w '%{http_code}' -H "Host: ${DOMAIN}" https://127.0.0.1/ || echo 000)
echo "  nginx :443  Host=${DOMAIN}                  -> ${code}（200 即成功）"

cat <<EOF

─────────────────────────────────────────────
完成。当前状态：
  · 应用进程   pm2 '$APP_NAME'（Node $(basename $NODE_DIR) / 端口 $PORT / 仅 127.0.0.1）
  · 主站进程   pm2 'wineapp'（未改动）
  · nginx      $NGINX_CONF（未改动 wineapp.conf）
  · 数据目录   $APP_DIR/var

还差一步：在 DNS 服务商处加 A 记录，把 ${DOMAIN} 指向你的服务器 IP。
DNS 生效后即可用 https://${DOMAIN}/community?lang=zh 访问。

常用命令：
  pm2 logs $APP_NAME --lines 50     看日志
  pm2 restart $APP_NAME             重启
  bash $APP_DIR/deploy/deploy.sh    本地改完代码后重新发布
─────────────────────────────────────────────
EOF

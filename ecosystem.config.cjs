// pm2 进程配置：与 VINCODE 主站（wineapp）完全独立，互不影响
//   - 独立应用名 terroir-atlas（主站是 wineapp）
//   - 独立端口 3020（主站是 8868），且只监听 127.0.0.1
//   - 独立 Node 运行时 /opt/node22（系统 /usr/local/bin/node 是 v20，node:sqlite 需要 >=22.5）
//
// 启动： cd /opt/terroir-atlas && pm2 start ecosystem.config.cjs
module.exports = {
  apps: [
    {
      name: 'terroir-atlas',
      script: 'server.mjs',
      cwd: __dirname,
      // 关键：用独立安装的 Node 22，绝对不动主站的 Node 20
      interpreter: '/opt/node22/bin/node',
      node_args: '--no-warnings',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      max_memory_restart: '400M',
      env: {
        NODE_ENV: 'production',
        PORT: 3020,
        HOST: '127.0.0.1',
        DATA_DIR: './var',
      },
      error_file: './var/pm2-error.log',
      out_file: './var/pm2-out.log',
      merge_logs: true,
      time: true,
    },
  ],
};

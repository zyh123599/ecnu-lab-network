#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
  echo '请用 sudo bash scripts/install-systemd.sh 运行。' >&2
  exit 1
fi
command -v systemctl >/dev/null
/usr/bin/python3 -c 'import sys; assert sys.version_info >= (3,8), "需要 Python 3.8+"'
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
install -d -m 755 /opt/ecnu-lab-network
install -d -m 700 /etc/ecnu-lab-network
install -m 644 "$source_dir/ecnunet.py" "$source_dir/protocol.py" "$source_dir/LICENSE" /opt/ecnu-lab-network/
if [[ ! -f /etc/ecnu-lab-network/config.json ]]; then
  /usr/bin/python3 /opt/ecnu-lab-network/ecnunet.py init -c /etc/ecnu-lab-network/config.json
fi
# Validate existing credentials without printing their contents or contacting the network.
/usr/bin/python3 -c 'import sys; from pathlib import Path; sys.path.insert(0,"/opt/ecnu-lab-network"); from ecnunet import load_config; load_config(Path("/etc/ecnu-lab-network/config.json"))'
cat > /etc/systemd/system/ecnu-lab-network.service <<'UNIT'
[Unit]
Description=ECNU lab server campus network authentication
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
DynamicUser=yes
LoadCredential=config:/etc/ecnu-lab-network/config.json
ExecStart=/usr/bin/python3 -u /opt/ecnu-lab-network/ecnunet.py watch --interval 300
Restart=on-failure
RestartSec=60
RestartPreventExitStatus=2 4
RuntimeDirectory=ecnu-lab-network
RuntimeDirectoryMode=0700
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
echo '安装完成（尚未启动）。运行以下命令启用开机登录与自动重连：'
echo 'sudo systemctl enable --now ecnu-lab-network'
echo '看日志：sudo journalctl -u ecnu-lab-network -n 30 --no-pager'

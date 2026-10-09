# 华师大实验室服务器联网工具

让Linux服务器，通过命令行登录华东师范大学校园网；配置一次后，可以开机自动登录、掉线自动重连。

**可以把它理解成：替服务器打开校园网登录页、填入账号密码、点击登录。**

适用：接在华师大校园网内、使用 `login.ecnu.edu.cn` 深澜认证的 Linux 服务器。默认 `ac_id=1`，来自参考项目。


## 能做什么

| 功能 | 用处 |
| --- | --- |
| 手动登录 | 服务器没有浏览器也能认证 |
| 查看状态 | 确认校园认证在线还是离线 |
| 中文诊断 | 分开检查 DNS、校园认证和外网探测 |
| 自动重连 | 默认每 5 分钟检查一次，离线时登录 |
| 开机运行 | 用 systemd 托管，关闭 SSH 窗口后仍运行 |
| 无第三方依赖 | 只需要 Python 3.8+，不用 pip 安装 |

它不修改服务器 IP、DNS、网卡或路由，不提供代理。网线没插好、学校欠费/限额、特定网站访问受限，都需要分别处理。

## 一、把文件放到服务器

### 服务器能访问 GitHub 时

在仓库页面点击 **Code → Download ZIP** 下载；或者拿到仓库地址后运行 `git clone 仓库地址`。进入包含 `ecnunet.py` 的目录。

### 服务器完全没外网时

1. 在你自己的 Windows 电脑下载本项目 ZIP 并解压。
2. 把整个项目文件夹上传到服务器。
3. 在服务器终端进入文件夹，例如：

```bash
cd /ai/workspace/ecnu-lab-network
python3 --version
python3 ecnunet.py --help
```

文件夹名字可能带 `-main`，以实际名字为准。若版本是 Python 3.8 或更高，可以直接使用；Ubuntu 22.04 的系统 Python 通常符合要求。**不需要显卡，不影响 CUDA 环境，不需要安装 requests。**

如果连 SSH 都连接不上，需要通过机房控制台、管理口或现场操作把文件放进去；本工具无法隔空修复网络。

## 二、第一次手动登录

以下命令都在项目目录中执行。

**1. 保存账号密码：**

```bash
python3 ecnunet.py init
```

按提示输入学校的校园网账号及密码。输入密码时屏幕不显示字符，这是正常的。

账号保存到当前 Linux 用户的 `~/.config/ecnu-lab-network/config.json`。文件权限自动设为 `600`，只允许所有者读写；管理员 root 仍能读取。密码为本地明文。

**2. 登录：**

```bash
python3 ecnunet.py login
```

看到“校园网登录成功，已核验在线状态”才表示登录接口返回成功，并且随后查询确认了本账号在线。

**3. 查看状态和连接情况：**

```bash
python3 ecnunet.py status
python3 ecnunet.py doctor
```

`status` 只看校园认证；`doctor` 还会尝试两个外网 HTTPS 探测点。探测成功只能说明至少一个探测点可达；探测失败也不一定代表整个外网都断了。

可再试一个你实际需要的网站，例如：

```bash
curl --noproxy '*' -I --connect-timeout 10 --max-time 20 https://www.baidu.com
```

## 三、开机自动登录、掉线重连

**建议实验室只由一位管理员配置一次系统服务。** 不要同时开多个 watch、cron 或其他校园网登录脚本，避免互相抢登录。

以下方式面向 Ubuntu 22.04 等使用 systemd 247+ 的 Linux 系统。需要 sudo 权限。没有 sudo 权限时看下一节。

```bash
sudo bash scripts/install-systemd.sh
```

首次安装会再次询问校园网账号密码。这里的配置专供系统服务使用，与前面普通用户保存的配置分开。

安装后，执行：

```bash
sudo systemctl enable --now ecnu-lab-network
sudo systemctl status ecnu-lab-network --no-pager
sudo journalctl -u ecnu-lab-network -n 30 --no-pager
```

- `enable --now`：现在运行，并在以后开机时自动运行。
- `status`：查看后台程序有没有运行。显示 `active (running)` 不等于网络已经通了，还要看日志。
- `journalctl`：查看它最近检查/登录的结果。

正常情况下每 300 秒检查一次。网络故障时延长等待到 600/900 秒；恢复后回到 300 秒。学校拒绝认证时立即退出，不反复尝试账号密码；修正账号、欠费或终端限制等问题后再手动重启服务。

**关掉 MobaXterm/SSH 后，系统服务仍会运行。**

常用维护命令：

```bash
# 暂停自动重连；不会主动登出当前校园网
sudo systemctl stop ecnu-lab-network

# 恢复自动重连
sudo systemctl start ecnu-lab-network

# 修改配置后重启，使新配置生效
sudo systemctl restart ecnu-lab-network

# 取消开机启动，并停止当前进程
sudo systemctl disable --now ecnu-lab-network
```

程序安装在 `/opt/ecnu-lab-network`，服务配置在 `/etc/systemd/system/ecnu-lab-network.service`，账号文件在 `/etc/ecnu-lab-network/config.json`。服务使用 systemd 临时用户和凭据机制运行，不以 root 运行登录程序。

如果安装后更新了源码，需要重新运行安装脚本，然后 `sudo systemctl restart ecnu-lab-network`。安装脚本保留已有账号配置。

## 四、没有 sudo 权限

可以在前台运行自动重连：

```bash
python3 ecnunet.py watch --interval 300
```

按 `Ctrl+C` 停止，不会主动登出校园网。关闭 SSH 窗口可能使它停止；已有 tmux 的服务器可以把它放在 tmux 中运行，但这不提供开机自启。长期开机托管请找管理员使用上一节的 systemd 服务。

## 五、常见问题

| 现象 | 通俗解释和处理 |
| --- | --- |
| `校园认证离线` | 尚未通过学校认证，先执行 `login` |
| 无法访问校园认证接口 | 先看网线/校园网路由、DNS、系统时间和证书；不一定是密码错 |
| 认证被拒绝 | 核对账号密码、欠费/冻结、终端数限制，以及登录页 `ac_id`；程序不会猜具体原因 |
| 此 IP 已由其他账号登录 | 可能是同一服务器或共享出口上的其他用户，找管理员确认，不自动顶掉对方 |
| 认证在线，但网站打不开 | 可能是外网出口、网站、DNS或代理问题；反复登录通常无助 |
| 两个探测点都失败 | 探测点可能不可用；手动试你需要的国内网站 |
| `active (running)`，但没网 | 这只说明程序活着；看 `journalctl` 的认证结果 |
| service 失败退出 | 看日志。配置错误/认证被拒绝会停止；处理后手动 restart |
| 配置权限错误 | 执行 `chmod 600 配置文件路径`；不要把账号文件放进共享可读目录 |
| 接口状态无法识别 | 程序停止盲目登录，可能学校更新了接口；需要适配，不能据此判断密码错误 |
| root 和普通用户表现不同 | 两者默认配置路径不同；用 `-c` 明确指定配置，或检查系统服务自己的配置 |

**服务器配置过 Clash/Mihomo、`http_proxy` 或 `https_proxy`？** 本工具的认证和探测不读取这些代理环境变量，避免把校园网认证发往代理服务器。但系统级透明代理、VPN、策略路由仍可能影响连接，本工具不会替你修改它们。

**登录页不是 `ac_id=1`？** 用浏览器打开学校登录页，核实网址参数后再配置，例如：

```bash
python3 ecnunet.py init -c ~/.config/ecnu-lab-network/another.json --ac-id 2
python3 ecnunet.py login -c ~/.config/ecnu-lab-network/another.json
```

这里的 `2` 只是参数示例，不代表你的校区必须填 2。如果学校使用不同认证系统/域名，本版本不能直接套用；不要随意把凭据发送给其他地址。

## 六、换密码、退出和卸载

普通用户换密码：先停止 watch，把旧配置移走，再重新初始化。路径按你实际使用的配置调整：

```bash
mv ~/.config/ecnu-lab-network/config.json ~/.config/ecnu-lab-network/config.json.bak
python3 ecnunet.py init
python3 ecnunet.py login
```

系统服务换密码：

```bash
sudo systemctl stop ecnu-lab-network
sudo mv /etc/ecnu-lab-network/config.json /etc/ecnu-lab-network/config.json.bak
sudo python3 /opt/ecnu-lab-network/ecnunet.py init -c /etc/ecnu-lab-network/config.json
sudo systemctl start ecnu-lab-network
```

确认新配置有效后，删除自己的 `.bak` 密码备份，避免遗忘。`init` 不会覆盖现有文件。

主动退出校园网可能立刻断开 SSH，且会影响这台服务器上的其他使用者。只有确定要断网时才运行：

```bash
# 若装过系统服务，先停止它，避免退出后又自动登录
sudo systemctl stop ecnu-lab-network
# 普通用户配置对应的退出命令
python3 ecnunet.py logout --yes
# 若只有系统服务配置，改用：
# sudo python3 /opt/ecnu-lab-network/ecnunet.py logout --yes -c /etc/ecnu-lab-network/config.json
```

卸载系统服务（不主动断开当前认证）：

```bash
sudo systemctl disable --now ecnu-lab-network
sudo rm -f /etc/systemd/system/ecnu-lab-network.service
sudo systemctl daemon-reload
sudo rm -rf /opt/ecnu-lab-network
```

上面保留账号文件。确认以后不用了，再删除 `/etc/ecnu-lab-network` 和你自己 `~/.config/ecnu-lab-network` 中的账号文件；注意不要误删其他目录。

## 七、验证范围与开发说明

```bash
python3 -m unittest discover -s tests -v
```

测试使用虚构账号和模拟接口，不需要校园网络。覆盖编码、响应解析、凭据权限、登录核验、拒绝认证、错误脱敏、重试退避及退出保护。源码级协议一致性对照记录见 [docs/VALIDATION.md](docs/VALIDATION.md)。

退出码：`0` 成功，`1` 离线/诊断未全部通过，`2` 配置或用法错误，`3` 网络/接口异常，`4` 认证拒绝或账号冲突，`130` 用户取消。

实机验收建议：手动登录 → status/doctor → 实际下载 → 后台服务日志 → 在有管理口/现场保障的维护窗口测试重启后的自启。不要为测试而在远程连接中拔网线或随便登出。

需要反馈问题时，提供命令、退出码和脱敏后的提示即可；不要提供账号文件、密码、完整认证请求 URL 或学校返回的完整个人信息。

## 来源与许可证

基于 [RISEN-B/ECNU-Network-CLI](https://github.com/RISEN-B/ECNU-Network-CLI) 的 SRun 协议实现改编，沿用 GPL-3.0-or-later。完整说明见 [NOTICE.md](NOTICE.md)，许可证见 [LICENSE](LICENSE)。本项目不是学校官方服务。

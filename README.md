# ECNU Lab Network

华东师范大学校园网命令行客户端，用于 Linux 服务器登录、掉线重连和开机自启。

需要 Python 3.8 或更高版本，无第三方依赖。服务器须接入学校网络，认证地址为 `login.ecnu.edu.cn`。

## 使用

在 GitHub 页面点击 **Code → Download ZIP**，解压后将文件夹上传到服务器。以下命令均在项目目录执行。

首次使用，保存校园网账号和密码：

```bash
python3 ecnunet.py init
```
<img width="900" height="87" alt="image" src="https://github.com/user-attachments/assets/390dd984-a2cc-4219-bbc1-8130f7911690" />

密码输入时不显示字符。配置保存在 `~/.config/ecnu-lab-network/config.json`，权限为 `600`。密码以明文保存在本机，请勿上传或分享该文件。

登录并检查网络：

```bash
python3 ecnunet.py login
```
```bash
python3 ecnunet.py doctor
```
<img width="900" height="78" alt="image" src="https://github.com/user-attachments/assets/8209685d-a0bd-4206-8f0a-b5f2a3d775bb" />

`login` 成功后会再次查询在线状态；已登录时不会重复认证。`doctor` 检查校园认证、外网探测点和百度 HTTPS，分别输出结果。

| 命令 | 用途 |
| --- | --- |
| `init` | 保存账号密码 |
| `login` | 登录校园网 |
| `status` | 查看校园认证状态 |
| `doctor` | 检查网络连接 |
| `watch` | 定期检查，离线后重连 |
| `logout --yes` | 退出校园网，可能中断 SSH |

复制命令时，只复制代码框内的内容，不要带上 `root@...#` 提示符或运行结果。

## 自动重连

前台运行，每 5 分钟检查一次：

```bash
python3 ecnunet.py watch --interval 300
```

按 `Ctrl+C` 停止。关闭 SSH 后需要继续运行，或需要开机自启时，使用下面的系统服务。

### 安装系统服务

适用于 systemd 247+，例如 Ubuntu 22.04。需要管理员权限；root 用户可以省略 `sudo`。建议先确认手动登录成功。

```bash
sudo bash scripts/install-systemd.sh
sudo systemctl enable --now ecnu-lab-network
```

首次安装会询问账号密码，单独保存到 `/etc/ecnu-lab-network/config.json`。安装脚本不会覆盖已有配置。

查看运行情况：

```bash
sudo systemctl status ecnu-lab-network --no-pager
sudo journalctl -u ecnu-lab-network -n 30 --no-pager
```

`active (running)` 表示服务在运行，登录结果以日志为准。同一服务器只保留一个自动登录程序。

临时停止或重新启动：

```bash
sudo systemctl stop ecnu-lab-network
sudo systemctl start ecnu-lab-network
```

正常检查间隔为 300 秒；网络异常时延长至 600、900 秒，恢复后回到 300 秒。认证被拒绝时停止重试，处理账号问题后执行 `sudo systemctl restart ecnu-lab-network`。

## 连接检查

校园认证在线后，可以单独测试百度：

```bash
curl --noproxy '*' --connect-timeout 10 --max-time 20 -sS -o /dev/null -w 'HTTP=%{http_code}\n' https://www.baidu.com/
```

`HTTP=200` 表示请求成功；`HTTP=000` 表示未收到 HTTP 响应，具体原因看 curl 报错。其他状态码表示收到了响应，但请求未必成功。

本工具不使用环境变量中的 HTTP/HTTPS 代理；系统级透明代理和路由仍会影响连接。校园认证在线不代表所有网站均可访问，单个网站失败不会触发重新登录。

| 问题 | 处理 |
| --- | --- |
| 认证被拒绝 | 检查密码、账号状态、终端数限制及 `ac_id` |
| 无法访问认证接口 | 检查校园网连接、DNS、系统时间和证书 |
| 已由其他账号登录 | 先与服务器管理员确认在线账号 |
| 无法识别认证状态 | 运行 `doctor`，查看脱敏状态摘要 |
| `not_online_error` 无法识别 | 更新代码；当前版本已兼容 |
| 配置权限错误 | 将账号文件权限设为 `600` |
| `command not found` 或 Bash 语法错误 | 检查是否把终端提示符、中文输出也粘贴成了命令 |

换密码、更新、退出和卸载见 [维护说明](docs/MAINTENANCE.md)。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

2026-10-09 已在一台校园服务器上确认手动登录、在线查询和外网探测可用。开机自启及断线重连尚未完成实机验证。测试范围见 [验证记录](docs/VALIDATION.md)。

## 来源

认证协议改编自 [RISEN-B/ECNU-Network-CLI](https://github.com/RISEN-B/ECNU-Network-CLI)，按 GPL-3.0-or-later 发布。详见 [NOTICE.md](NOTICE.md) 和 [LICENSE](LICENSE)。本项目为非官方客户端。

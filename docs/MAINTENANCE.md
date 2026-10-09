# 维护说明

## 文件位置

| 文件 | 路径 |
| --- | --- |
| 手动登录配置 | `~/.config/ecnu-lab-network/config.json` |
| 系统服务配置 | `/etc/ecnu-lab-network/config.json` |
| 系统服务程序 | `/opt/ecnu-lab-network/` |
| systemd 单元 | `/etc/systemd/system/ecnu-lab-network.service` |

`~` 指当前 Linux 用户的主目录，root 与普通用户的默认配置不同。系统服务使用独立配置，并通过 systemd 凭据机制交给临时用户运行。

账号文件为明文，权限设为 `600`；root 仍可读取。分享日志时不要附带账号文件或完整认证请求 URL。

## 更换账号或密码

先停止正在运行的 `watch`。手动登录配置按以下方式更换：

```bash
mv ~/.config/ecnu-lab-network/config.json ~/.config/ecnu-lab-network/config.json.bak
python3 ecnunet.py init
python3 ecnunet.py login
```

系统服务配置：

```bash
sudo systemctl stop ecnu-lab-network
sudo mv /etc/ecnu-lab-network/config.json /etc/ecnu-lab-network/config.json.bak
sudo python3 /opt/ecnu-lab-network/ecnunet.py init -c /etc/ecnu-lab-network/config.json
sudo systemctl start ecnu-lab-network
```

`init` 不覆盖已有文件。若 `.bak` 已存在，先为本次备份另取文件名。新配置确认有效后，删除不再需要的密码备份。

## 更新程序

ZIP 下载的目录需重新下载并替换源码；通过 git 克隆的目录可运行 `git pull`。账号文件默认在项目目录之外，更新源码不影响配置。

如果安装过系统服务，更新项目目录后还需重新安装并重启服务：

```bash
sudo bash scripts/install-systemd.sh
sudo systemctl restart ecnu-lab-network
```

## 自定义配置

使用其他配置文件：

```bash
python3 ecnunet.py login -c /path/to/config.json
```

默认 `ac_id=1`。仅在确认学校登录页使用其他值时修改，例如：

```bash
python3 ecnunet.py init -c ~/.config/ecnu-lab-network/another.json --ac-id 2
python3 ecnunet.py login -c ~/.config/ecnu-lab-network/another.json
```

`2` 仅为示例。认证域名固定为 `login.ecnu.edu.cn`，不适用于其他认证系统。

## 退出校园网

退出可能断开 SSH，并影响同一服务器的其他使用者。先停止自动重连，再退出：

```bash
sudo systemctl stop ecnu-lab-network
python3 ecnunet.py logout --yes
```

没有安装系统服务时，省略第一条。若使用的是系统服务账号配置，退出命令改为：

```bash
sudo python3 /opt/ecnu-lab-network/ecnunet.py logout --yes -c /etc/ecnu-lab-network/config.json
```

单独停止服务或按 `Ctrl+C` 结束 watch，不会主动退出校园网。

## 卸载系统服务

```bash
sudo systemctl disable --now ecnu-lab-network
sudo rm -f /etc/systemd/system/ecnu-lab-network.service
sudo systemctl daemon-reload
sudo rm -rf /opt/ecnu-lab-network
```

这些命令保留账号配置。确认不再使用后，再删除 `/etc/ecnu-lab-network` 和个人配置目录中的账号文件。

## 退出码

| 值 | 含义 |
| --- | --- |
| 0 | 命令成功 |
| 1 | 认证离线，或 doctor 的认证/外网探测未全部通过 |
| 2 | 配置、参数或本地文件错误 |
| 3 | 网络或接口异常 |
| 4 | 认证被拒绝或账号冲突 |
| 130 | 用户取消 |

`doctor` 的退出码取决于校园认证和原有的两个外网探测点。百度结果单独显示，不参与退出码判断。HTTP 200 只表示请求成功，程序不检查首页内容。

# 来源与许可证

`protocol.py` 中的 SRun 编码、哈希和校验和函数改编自 [RISEN-B/ECNU-Network-CLI](https://github.com/RISEN-B/ECNU-Network-CLI) 的 `ecnunet-cli.py`，对应 Git blob：

```
e658fc9c964e595aa260f59007c06c9879e343a7
```

上游协议实现参考了 [iskoldt-X/SRUN-authenticator](https://github.com/iskoldt-X/SRUN-authenticator)。本项目沿用 GPL-3.0-or-later，完整许可证见 [LICENSE](LICENSE)。

主要修改：提取协议函数，以 Python 标准库替代 requests；重写命令行与状态判断；增加请求超时、配置权限检查、自动重连、systemd 安装脚本及连接诊断。

认证请求保留 TLS 证书校验，禁用自动重定向和环境代理。实机测试范围见 [验证记录](docs/VALIDATION.md)。

# 来源与修改说明

本项目是面向 Linux 实验室服务器的衍生实现，以 GPL-3.0-or-later 发布。

- 参考项目：https://github.com/RISEN-B/ECNU-Network-CLI
- `protocol.py` 的 SRun 编码、哈希和校验和函数改编自上游 `ecnunet-cli.py`，Git blob SHA：`e658fc9c964e595aa260f59007c06c9879e343a7`。
- 上游协议实现致谢：https://github.com/iskoldt-X/SRUN-authenticator
- 保留完整 GPL v3 许可证于 `LICENSE`。
- 2026-10-08 修改：提取协议函数；重写命令行、网络传输与状态判断；移除 requests 依赖；加入超时、禁止代理及重定向、文件权限检查、受控重试、systemd 配置及中文使用说明。

这不是学校官方软件。协议兼容性来自上游源码，尚需在目标校园服务器验证。

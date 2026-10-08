# SPDX-License-Identifier: GPL-3.0-or-later
# Adapted from RISEN-B/ECNU-Network-CLI, ecnunet-cli.py
# Upstream blob SHA: e658fc9c964e595aa260f59007c06c9879e343a7
# Upstream acknowledgements: iskoldt-X/SRUN-authenticator
# Changes: extracted protocol helpers for a standard-library-only server client.
import hashlib
import hmac
import json
import math


class SrunProtocol:
    _AC_ID = "1"
    _N = "200"
    _TYPE = "1"
    _ENC_VER = "srun_bx1"
    _SRUN_BASE64_ALPHABET = "LVoJPiCN2R8G90yg+hmFHuacZ1OWMnrsSTXkYpUq/3dlbfKwv6xztjI7DeBE45QA"

    def __init__(self, username, password, ip, challenge, ac_id="1"):
        self._username = username
        self._password = password
        self._client_ip = ip
        self._challenge_token = challenge
        self._AC_ID = ac_id

    def _custom_base64_encode(self, data: str) -> str:
        """
        SRun 自定义 Base64 编码
        
        Args:
            data: 待编码字符串
            
        Returns:
            编码后的字符串
        """
        result = []
        padding = len(data) % 3
        if padding:
            data += "\0" * (3 - padding)

        for i in range(0, len(data), 3):
            chunk = data[i:i + 3]
            # 合并三个字符为 24 位整数
            combined = (ord(chunk[0]) << 16) | (ord(chunk[1]) << 8) | ord(chunk[2])
            # 拆分为四个 6 位索引
            result.extend([
                self._SRUN_BASE64_ALPHABET[(combined >> 18)],
                self._SRUN_BASE64_ALPHABET[(combined >> 12) & 63],
                self._SRUN_BASE64_ALPHABET[(combined >> 6) & 63],
                self._SRUN_BASE64_ALPHABET[combined & 63]
            ])

        # 处理填充
        if padding == 1:
            result[-1] = "="
            result[-2] = "="
        elif padding == 2:
            result[-1] = "="

        return "".join(result)

    def _xencode(self, message: str, key: str) -> str:
        """
        SRun 自定义加密算法 (BX1)
        
        Args:
            message: 明文消息
            key: 加密密钥
            
        Returns:
            加密后的字符串
        """
        if not message:
            return ""

        def _ord_at(s: str, index: int) -> int:
            """安全获取字符串指定位置的 ASCII 值"""
            return ord(s[index]) if index < len(s) else 0

        def _serialize(s: str, include_length: bool) -> list:
            """将字符串序列化为 32 位整数列表"""
            length = len(s)
            words = []
            # 每 4 个字符合并为一个 32 位整数
            for i in range(0, length, 4):
                word = (
                    _ord_at(s, i) |
                    (_ord_at(s, i + 1) << 8) |
                    (_ord_at(s, i + 2) << 16) |
                    (_ord_at(s, i + 3) << 24)
                )
                words.append(word)
            if include_length:
                words.append(length)
            return words

        def _deserialize(words: list, include_length: bool) -> str:
            """将 32 位整数列表反序列化为字符串"""
            length = len(words)
            total_chars = (length - 1) << 2
            if include_length:
                actual_length = words[length - 1]
                if actual_length < total_chars - 3 or actual_length > total_chars:
                    return ""
                total_chars = actual_length

            chars = []
            for word in words:
                chars.extend([
                    chr(word & 0xFF),
                    chr((word >> 8) & 0xFF),
                    chr((word >> 16) & 0xFF),
                    chr((word >> 24) & 0xFF)
                ])
            return "".join(chars[:total_chars]) if include_length else "".join(chars)

        # 序列化消息和密钥
        msg_words = _serialize(message, True)
        key_words = _serialize(key, False)
        if len(key_words) < 4:
            key_words = key_words + [0] * (4 - len(key_words))
        n = len(msg_words) - 1
        z = msg_words[n]
        y = msg_words[0]
        c = 0x86014019 | 0x183639A0
        m = 0
        e = 0
        p = 0
        q = math.floor(6 + 52 / (n + 1))
        d = 0
        while 0 < q:
            d = d + c & (0x8CE0D9BF | 0x731F2640)
            e = d >> 2 & 3
            p = 0
            while p < n:
                y = msg_words[p + 1]
                m = z >> 5 ^ y << 2
                m = m + ((y >> 3 ^ z << 4) ^ (d ^ y))
                m = m + (key_words[(p & 3) ^ e] ^ z)
                msg_words[p] = msg_words[p] + m & (0xEFB8D130 | 0x10472ECF)
                z = msg_words[p]
                p = p + 1
            y = msg_words[0]
            m = z >> 5 ^ y << 2
            m = m + ((y >> 3 ^ z << 4) ^ (d ^ y))
            m = m + (key_words[(p & 3) ^ e] ^ z)
            msg_words[n] = msg_words[n] + m & (0xBB390742 | 0x44C6F8BD)
            z = msg_words[n]
            q = q - 1

        return _deserialize(msg_words, False)

    def _calculate_md5_password(self) -> str:
        """
        计算密码的 MD5 哈希值
        
        Returns:
            密码的 MD5 哈希（十六进制小写）
        """
        return hmac.new(self._challenge_token.encode(), self._password.encode(), hashlib.md5).hexdigest()

    def _calculate_checksum(self, md5_password: str, encoded_info: str) -> str:
        """
        计算请求校验和 (chksum)
        
        Args:
            md5_password: 密码的 MD5 哈希
            encoded_info: 加密后的 info 字段（含 {SRBX1} 前缀）
            
        Returns:
            SHA1 校验和
        """
        checksum_parts = [
            self._challenge_token, self._username,
            self._challenge_token, md5_password,
            self._challenge_token, self._AC_ID,
            self._challenge_token, self._client_ip,
            self._challenge_token, self._N,
            self._challenge_token, self._TYPE,
            self._challenge_token, encoded_info
        ]
        checksum_string = "".join(checksum_parts)
        return hashlib.sha1(checksum_string.encode()).hexdigest()

    def _build_user_info(self) -> str:
        """
        构建用户信息 JSON 字符串（无空格、紧凑格式）
        
        Returns:
            用户信息 JSON 字符串
        """
        info_dict = {
            "username": self._username,
            "password": self._password,  # 注意：此处为明文密码
            "ip": self._client_ip,
            "acid": self._AC_ID,
            "enc_ver": self._ENC_VER
        }
        # 使用紧凑 JSON 格式（无空格，与 JS 的 JSON.stringify 一致）
        return json.dumps(info_dict, separators=(",", ":"))



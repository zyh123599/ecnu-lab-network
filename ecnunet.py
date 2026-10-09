#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""ECNU lab server network client. Python 3.8+, standard library only."""
import argparse
import fcntl
import getpass
from http.client import HTTPException
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler, Request

from protocol import SrunProtocol

PORTAL = 'https://login.ecnu.edu.cn'
PROBES = ('https://connectivitycheck.platform.hicloud.com/generate_204',
          'https://www.gstatic.com/generate_204')
MAX_RESPONSE = 65536


class ClientError(Exception):
    code = 3


class ConfigError(ClientError):
    code = 2


class AuthError(ClientError):
    code = 4


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse_response(text, callback):
    text = text.strip()
    if text.startswith('{'):
        payload = text
    else:
        match = re.fullmatch(re.escape(callback) + r'\s*\((.*)\)\s*;?', text, re.S)
        if not match:
            raise ClientError('认证页返回格式异常，可能是接口改变或请求被拦截。')
        payload = match.group(1)
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        raise ClientError('认证页返回的 JSON 无法解析。') from None
    if not isinstance(data, dict):
        raise ClientError('认证页返回的数据不是对象。')
    return data


def portal_state(data):
    if data.get('error') == 'ok' and data.get('user_name') and data.get('online_ip'):
        return 'online'
    if data.get('error') in ('not_online', 'not_online_error'):
        return 'offline'
    return 'unknown'


def status_summary(data):
    """Only expose short status codes and field presence, never raw responses."""
    summary = {}
    for key in ('error', 'error_msg', 'ecode', 'res', 'status', 'code'):
        if key not in data:
            continue
        value = data[key]
        text = str(value)
        summary[key] = text if isinstance(value, (str, int)) and re.fullmatch(r'[A-Za-z_]{1,48}|-?\d{1,6}', text) else '<内容已隐藏>'
    for key in ('client_ip', 'online_ip', 'user_name'):
        summary[key + '_present'] = bool(data.get(key))
    return summary


def default_config():
    cred = os.environ.get('CREDENTIALS_DIRECTORY')
    return Path(cred) / 'config' if cred else Path.home() / '.config/ecnu-lab-network/config.json'


def load_config(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'r', encoding='utf-8') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise ConfigError('配置必须是普通文件，且仅所有者可读写；请执行 chmod 600 配置文件。')
            if info.st_uid not in (0, os.geteuid()):
                raise ConfigError('配置文件所有者不正确。')
            if info.st_size > MAX_RESPONSE:
                raise ConfigError('配置文件过大。')
            data = json.load(stream)
    except (OSError, ValueError):
        raise ConfigError('无法读取配置。请先运行 init，或检查路径、文件权限及 JSON 格式。') from None
    if not isinstance(data, dict):
        raise ConfigError('配置必须是 JSON 对象。')
    if any(not isinstance(data.get(k), str) or not data[k] for k in ('username', 'password')):
        raise ConfigError('配置中缺少账号或密码。')
    if not re.fullmatch(r'[0-9]+', str(data.get('ac_id', '1'))):
        raise ConfigError('ac_id 必须为数字。')
    return data


def save_config(path, username, password, ac_id):
    if not username or not password:
        raise ConfigError('账号和密码不能为空。')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive creation: never overwrite credentials or follow an existing symlink.
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        raise ConfigError('配置已存在或目录不可写。需要更换账号时，请先将旧配置移走。') from None
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump({'username': username, 'password': password, 'ac_id': ac_id}, stream, ensure_ascii=True)
        stream.write('\n')
    print('配置已保存（权限 600）。')


class Client:
    def __init__(self, config=None, timeout=10):
        self.config = config or {}
        self.timeout = timeout
        # Campus login must use the server's own route, never an environment proxy.
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, endpoint, params=None):
        callback = 'ecnu_' + str(time.time_ns())
        query = dict(params or {}, callback=callback, _=int(time.time() * 1000))
        req = Request(PORTAL + '/cgi-bin/' + endpoint + '?' + urlencode(query),
                      headers={'User-Agent': 'ECNU-Lab-Network/0.1',
                               'Referer': PORTAL + '/srun_portal_pc?ac_id=' + str(self.config.get('ac_id', '1'))})
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise ClientError('认证响应过大，已停止。')
                return parse_response(raw.decode('utf-8'), callback)
        except (HTTPError, URLError, OSError, UnicodeError, ssl.SSLError, ValueError, HTTPException):
            # Do not log exceptions: urllib exceptions can contain credential-bearing URLs.
            raise ClientError('认证接口连接失败，请检查网络、DNS、系统时间和证书。') from None

    def status(self):
        return self.request('rad_user_info')

    def internet(self):
        for url in PROBES:
            try:
                with self.opener.open(Request(url), timeout=self.timeout) as response:
                    if response.status == 204:
                        return True
            except (HTTPError, URLError, OSError, ssl.SSLError, HTTPException):
                pass
        return False

    def baidu_status(self):
        """Independent HTTPS GET; never use a site failure to force re-login."""
        try:
            with self.opener.open(Request('https://www.baidu.com/'), timeout=self.timeout) as response:
                return response.status
        except HTTPError as exc:
            return exc.code
        except (URLError, OSError, ssl.SSLError, HTTPException):
            return None

    def login(self):
        info = self.status()
        state = portal_state(info)
        if state == 'online':
            if info['user_name'] != self.config['username']:
                raise AuthError('当前 IP 已由其他账号登录，请联系管理员确认。')
            return 'already_online'
        if state != 'offline':
            raise ClientError('无法识别认证状态，未提交登录。请运行 doctor 查看详情。')
        ip = info.get('client_ip', '')
        try:
            ipaddress.ip_address(ip)
        except (ValueError, TypeError):
            raise ClientError('认证接口没有给出有效的客户端 IP。') from None
        challenge = self.request('get_challenge', {'username': self.config['username'], 'ip': ip})
        if str(challenge.get('ecode')) != '0' or not isinstance(challenge.get('challenge'), str) or not challenge['challenge']:
            raise ClientError('无法获取认证令牌，请稍后重试。')
        p = SrunProtocol(self.config['username'], self.config['password'], ip,
                         challenge['challenge'], str(self.config.get('ac_id', '1')))
        encoded = '{SRBX1}' + p._custom_base64_encode(p._xencode(p._build_user_info(), p._challenge_token))
        md5 = p._calculate_md5_password()
        result = self.request('srun_portal', {
            'action': 'login', 'username': p._username, 'password': '{MD5}' + md5,
            'os': 'Linux', 'name': 'Linux', 'double_stack': '0',
            'chksum': p._calculate_checksum(md5, encoded), 'info': encoded,
            'ac_id': p._AC_ID, 'ip': ip, 'n': p._N, 'type': p._TYPE})
        if str(result.get('ecode')) != '0':
            raise AuthError('认证被拒绝。请核对账号密码、账号状态、终端数限制及 ac_id；自动重试已停止。')
        verified = self.status()
        if portal_state(verified) != 'online' or verified['user_name'] != self.config['username']:
            raise ClientError('登录后未查到本账号在线，请稍后运行 status。')
        return 'logged_in'

    def logout(self):
        info = self.status()
        if portal_state(info) == 'offline':
            print('当前已经离线。')
            return
        if portal_state(info) != 'online':
            raise ClientError('无法确认在线账号，未执行退出。')
        if info['user_name'] != self.config['username']:
            raise AuthError('当前在线账号与配置不一致，未执行退出。')
        result = self.request('srun_portal', {
            'action': 'logout', 'username': self.config['username'],
            'ip': info['online_ip'], 'ac_id': str(self.config.get('ac_id', '1'))})
        if str(result.get('ecode')) != '0':
            raise AuthError('退出被认证服务器拒绝。')
        if portal_state(self.status()) != 'offline':
            raise ClientError('退出请求已提交，但尚未确认离线。')
        print('已退出校园网。')


def log(message):
    print(time.strftime('[%Y-%m-%d %H:%M:%S] ') + message, flush=True)


def watch(client, interval):
    delay = interval
    while True:
        try:
            result = client.login()
            log('已重新登录校园网。' if result == 'logged_in' else '校园认证在线。')
            delay = interval
        except AuthError:
            raise  # Never repeatedly submit rejected credentials.
        except ClientError as exc:
            log(str(exc) + ' 稍后重试。')
            delay = min(delay * 2, 900)
        time.sleep(delay)


def diagnostic(client):
    print('检查网络连接：')
    try:
        socket.getaddrinfo('login.ecnu.edu.cn', 443)
        print('认证域名 DNS：正常')
    except OSError:
        print('认证域名 DNS：解析失败')
    try:
        info = client.status()
        state = portal_state(info)
        print('校园认证：' + {'online': '在线', 'offline': '离线', 'unknown': '无法识别响应'}[state])
        if state == 'unknown':
            print('脱敏状态摘要：' + json.dumps(status_summary(info), ensure_ascii=False))
            print('状态未识别，未执行登录。')
    except ClientError as exc:
        print('校园认证：' + str(exc))
        state = 'unknown'
    reachable = client.internet()
    print('外网探测：' + ('至少一个探测点可达' if reachable else '两个探测点均未通过'))
    baidu = client.baidu_status()
    if baidu == 200:
        print('百度 HTTPS：HTTP 200')
    elif baidu is None:
        print('百度 HTTPS：未收到响应，请检查 DNS、连接和证书。')
    else:
        print(f'百度 HTTPS：HTTP {baidu}')
    print('以上请求未使用环境代理。')
    return 0 if state == 'online' and reachable else 1


def positive_timeout(value):
    number = int(value)
    if not 1 <= number <= 60:
        raise argparse.ArgumentTypeError('超时应为 1–60 秒')
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description='华师大实验室服务器校园网登录工具')
    parser.add_argument('command', choices=['init', 'login', 'status', 'doctor', 'watch', 'logout'])
    parser.add_argument('-c', '--config', type=Path, default=default_config(), help='配置路径')
    parser.add_argument('--timeout', type=positive_timeout, default=10, help='每次网络请求超时秒数，默认 10')
    parser.add_argument('--interval', type=int, default=300, help='watch 正常检查间隔，默认 300 秒')
    parser.add_argument('--ac-id', default='1', help='init 使用的 ac_id，默认 1')
    parser.add_argument('--yes', action='store_true', help='确认 logout 会使服务器断网')
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            if not re.fullmatch(r'[0-9]+', args.ac_id):
                raise ConfigError('ac_id 必须为数字。')
            save_config(args.config, input('校园网账号（学号/工号）：').strip(),
                        getpass.getpass('校园网密码（输入时不显示）：'), args.ac_id)
            return 0
        if args.command in ('status', 'doctor'):
            client = Client(timeout=args.timeout)
            if args.command == 'doctor':
                return diagnostic(client)
            state = portal_state(client.status())
            print({'online': '校园认证在线。',
                   'offline': '校园认证离线。', 'unknown': '校园认证状态无法确定。'}[state])
            return {'online': 0, 'offline': 1, 'unknown': 3}[state]
        if args.command == 'logout' and not args.yes:
            raise ConfigError('退出可能中断远程连接。确认后使用 logout --yes；请先停止自动重连服务。')
        if args.command == 'watch' and not 30 <= args.interval <= 900:
            raise ConfigError('检查间隔应为 30–900 秒。')
        client = Client(load_config(args.config), args.timeout)
        if args.command == 'login':
            result = client.login()
            print('校园认证在线。' if result == 'already_online' else '登录成功，校园认证在线。')
        elif args.command == 'logout':
            client.logout()
        else:
            # Lock scoped to the local OS user; prevents duplicate watch processes for this user.
            lockdir = Path(os.environ.get('RUNTIME_DIRECTORY', str(Path.home() / '.cache/ecnu-lab-network')))
            lockdir.mkdir(mode=0o700, parents=True, exist_ok=True)
            lockfd = os.open(lockdir / 'watch.lock', os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            with os.fdopen(lockfd, 'w') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ConfigError('当前用户已有自动重连进程。') from None
                watch(client, args.interval)
        return 0
    except ClientError as exc:
        print('错误：' + str(exc), file=sys.stderr)
        return exc.code
    except (EOFError, KeyboardInterrupt):
        print('\n已取消。', file=sys.stderr)
        return 130
    except OSError:
        print('错误：本地文件或系统操作失败，请检查权限及路径。', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())

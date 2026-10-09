import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from ecnunet import (AuthError, Client, ClientError, ConfigError, NoRedirect,
                     load_config, main, parse_response, portal_state, save_config, watch,
                     status_summary, diagnostic)
from protocol import SrunProtocol

CFG = {'username': 'test-user', 'password': 'test-%-密 码', 'ac_id': '1'}
OFF = {'error': 'not_online', 'client_ip': '10.1.2.3'}
ON = {'error': 'ok', 'user_name': 'test-user', 'online_ip': '10.1.2.3'}


class ProtocolTests(unittest.TestCase):
    def test_md5_and_checksum(self):
        import hashlib
        import hmac
        p = SrunProtocol('u', 'p', '10.0.0.1', 'token')
        md5 = p._calculate_md5_password()
        self.assertEqual(md5, hmac.new(b'token', b'p', hashlib.md5).hexdigest())
        parts = ['u', md5, '1', '10.0.0.1', '200', '1', 'encoded']
        self.assertEqual(p._calculate_checksum(md5, 'encoded'),
                         hashlib.sha1(''.join('token' + x for x in parts).encode()).hexdigest())

    def test_base64_against_standard_translation(self):
        import base64
        import string
        p = SrunProtocol('u', 'p', '', '')
        table = str.maketrans(string.ascii_uppercase + string.ascii_lowercase + string.digits + '+/', p._SRUN_BASE64_ALPHABET)
        for raw in (b'', b'a', b'ab', b'abc', bytes(range(256))):
            self.assertEqual(p._custom_base64_encode(raw.decode('latin1')), base64.b64encode(raw).decode().translate(table))

    def test_user_info_special_password(self):
        p = SrunProtocol('u', CFG['password'], '10.1.2.3', 'token')
        self.assertEqual(json.loads(p._build_user_info())['password'], CFG['password'])


class ResponseTests(unittest.TestCase):
    def test_baidu_success_uses_https_get_and_timeout(self):
        c = Client(timeout=7)
        c.opener.open = Mock()
        response = Mock(status=200)
        c.opener.open.return_value.__enter__ = Mock(return_value=response)
        c.opener.open.return_value.__exit__ = Mock(return_value=False)
        self.assertEqual(c.baidu_status(), 200)
        args, kwargs = c.opener.open.call_args
        self.assertEqual(args[0].full_url, 'https://www.baidu.com/')
        self.assertEqual(args[0].get_method(), 'GET')
        self.assertEqual(kwargs['timeout'], 7)

    def test_baidu_http_and_transport_failures_are_distinct(self):
        from urllib.error import HTTPError
        c = Client()
        for code in (302, 403, 500):
            c.opener.open = Mock(side_effect=HTTPError('https://www.baidu.com/', code, 'error', {}, None))
            self.assertEqual(c.baidu_status(), code)
        c.opener.open = Mock(side_effect=URLError('secret detail'))
        self.assertIsNone(c.baidu_status())

    def test_status_summary_keeps_codes_not_identity(self):
        summary = status_summary({'error': 'not_online_error', 'ecode': 0,
                                  'client_ip': '10.2.3.4', 'user_name': 'private-user',
                                  'password': 'SECRET', 'challenge': 'TOKEN'})
        self.assertEqual(summary['error'], 'not_online_error')
        self.assertEqual(summary['ecode'], '0')
        for value in ('10.2.3.4', 'private-user', 'SECRET', 'TOKEN'):
            self.assertNotIn(value, str(summary))

    def test_status_summary_hides_free_text(self):
        for value in ('user=123456789 password=SECRET', {'password': 'SECRET'}, '123456789', 'https://host/?token=SECRET'):
            self.assertEqual(status_summary({'error_msg': value})['error_msg'], '<内容已隐藏>')

    def test_doctor_unknown_prints_summary_without_login(self):
        c = Mock()
        c.status.return_value = {'error': 'unrecognized_state', 'client_ip': '10.2.3.4'}
        c.internet.return_value = False
        c.baidu_status.return_value = None
        output = io.StringIO()
        with patch('ecnunet.socket.getaddrinfo'), contextlib.redirect_stdout(output):
            self.assertEqual(diagnostic(c), 1)
        c.login.assert_not_called()
        self.assertIn('unrecognized_state', output.getvalue())
        self.assertNotIn('10.2.3.4', output.getvalue())

    def test_json_and_jsonp(self):
        for value in ('{"error":"ok"}', 'cb({"error":"ok"});', ' cb(\n{"error":"ok"}\n) '):
            self.assertEqual(parse_response(value, 'cb'), {'error': 'ok'})

    def test_reject_malformed_and_callback_mismatch(self):
        for value in ('<html>login</html>', 'evil({"error":"ok"})', 'cb([])', 'cb({broken})', 'cb({});evil()'):
            with self.assertRaises(ClientError):
                parse_response(value, 'cb')

    def test_states_do_not_guess(self):
        self.assertEqual(portal_state(ON), 'online')
        self.assertEqual(portal_state(OFF), 'offline')
        for data in ({}, {'error': 'ok'}, {'error': 'fail'}, {'error': 'not_online-ish'}):
            self.assertEqual(portal_state(data), 'unknown')

    def test_no_redirect(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com'))

    def test_network_errors_do_not_leak_query(self):
        c = Client()
        c.opener.open = Mock(side_effect=URLError('https://host/?password=SECRET'))
        with self.assertRaises(ClientError) as caught:
            c.status()
        self.assertNotIn('SECRET', str(caught.exception))

    def test_request_has_timeout_and_encoded_params(self):
        c = Client(timeout=7)
        response = Mock()
        response.read.return_value = b'{"error":"not_online"}'
        c.opener.open = Mock()
        c.opener.open.return_value.__enter__ = Mock(return_value=response)
        c.opener.open.return_value.__exit__ = Mock(return_value=False)
        c.request('get_challenge', {'username': 'a&b'})
        args, kwargs = c.opener.open.call_args
        self.assertEqual(kwargs['timeout'], 7)
        self.assertIn('username=a%26b', args[0].full_url)
        self.assertTrue(args[0].full_url.startswith('https://login.ecnu.edu.cn/'))

    def test_proxy_environment_disabled(self):
        with patch.dict(os.environ, {'https_proxy': 'http://127.0.0.1:1'}):
            c = Client()
            self.assertFalse(any(getattr(h, 'proxies', None) for h in c.opener.handlers))


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'config.json'

    def save(self):
        with contextlib.redirect_stdout(io.StringIO()):
            save_config(self.path, CFG['username'], CFG['password'], '1')

    def test_round_trip_and_mode(self):
        self.save()
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(load_config(self.path), CFG)

    def test_refuses_overwrite(self):
        self.save()
        before = self.path.read_bytes()
        with self.assertRaises(ConfigError):
            self.save()
        self.assertEqual(before, self.path.read_bytes())

    def test_refuses_world_readable(self):
        self.save()
        self.path.chmod(0o644)
        with self.assertRaises(ConfigError):
            load_config(self.path)

    def test_refuses_symlink(self):
        self.save()
        other = self.path.with_name('link.json')
        other.symlink_to(self.path)
        with self.assertRaises(ConfigError):
            load_config(other)

    def test_invalid_json_redacted(self):
        self.path.write_text('SECRET')
        self.path.chmod(0o600)
        with self.assertRaises(ConfigError) as caught:
            load_config(self.path)
        self.assertNotIn('SECRET', str(caught.exception))


class LoginTests(unittest.TestCase):
    def test_observed_ecnu_offline_response_can_login(self):
        observed = {'error': 'not_online_error', 'res': 'not_online_error',
                    'ecode': '0', 'client_ip': '10.1.2.3',
                    'online_ip': '10.1.2.3', 'user_name': ''}
        self.assertEqual(portal_state(observed), 'offline')
        c = self.client([observed, {'ecode': 0, 'challenge': 'test-token'},
                         {'ecode': 0}, ON])
        self.assertEqual(c.login(), 'logged_in')
        self.assertEqual(c.request.call_count, 4)

    def client(self, replies):
        c = Client(CFG)
        c.request = Mock(side_effect=replies)
        return c

    def test_login_and_verify(self):
        c = self.client([OFF, {'ecode': 0, 'challenge': 'challenge12345678'}, {'ecode': 0}, ON])
        self.assertEqual(c.login(), 'logged_in')
        params = c.request.call_args_list[2].args[1]
        self.assertTrue(params['password'].startswith('{MD5}'))
        self.assertNotIn(CFG['password'], str(params))
        self.assertTrue(params['info'].startswith('{SRBX1}'))
        self.assertEqual(params['ip'], '10.1.2.3')

    def test_online_does_not_submit(self):
        c = self.client([ON])
        self.assertEqual(c.login(), 'already_online')
        self.assertEqual(c.request.call_count, 1)

    def test_other_account_not_overridden(self):
        c = self.client([dict(ON, user_name='other')])
        with self.assertRaises(AuthError):
            c.login()
        self.assertEqual(c.request.call_count, 1)

    def test_unknown_does_not_submit(self):
        c = self.client([{'error': 'new_response'}])
        with self.assertRaises(ClientError):
            c.login()
        self.assertEqual(c.request.call_count, 1)

    def test_invalid_ip_does_not_submit(self):
        c = self.client([dict(OFF, client_ip='not-an-ip')])
        with self.assertRaises(ClientError):
            c.login()
        self.assertEqual(c.request.call_count, 1)

    def test_rejection_stops(self):
        c = self.client([OFF, {'ecode': '0', 'challenge': 'token'}, {'ecode': 1, 'error_msg': 'SECRET'}])
        with self.assertRaises(AuthError) as caught:
            c.login()
        self.assertNotIn('SECRET', str(caught.exception))

    def test_success_requires_online_verification(self):
        c = self.client([OFF, {'ecode': 0, 'challenge': 'token'}, {'ecode': 0}, OFF])
        with self.assertRaises(ClientError):
            c.login()

    def test_logout_other_account_refused(self):
        c = self.client([dict(ON, user_name='other')])
        with self.assertRaises(AuthError):
            c.logout()
        self.assertEqual(c.request.call_count, 1)

    def test_logout_verified(self):
        c = self.client([ON, {'ecode': 0}, OFF])
        with contextlib.redirect_stdout(io.StringIO()):
            c.logout()
        self.assertEqual(c.request.call_count, 3)

    def test_logout_confirmation(self):
        with contextlib.redirect_stderr(io.StringIO()), patch('ecnunet.load_config') as read:
            self.assertEqual(main(['logout']), 2)
            read.assert_not_called()


class WatchTests(unittest.TestCase):
    def test_auth_error_no_retry(self):
        c = Mock()
        c.login.side_effect = AuthError('rejected')
        with patch('ecnunet.time.sleep') as sleep, self.assertRaises(AuthError):
            watch(c, 300)
        sleep.assert_not_called()

    def test_backoff_capped_and_reset(self):
        c = Mock()
        c.login.side_effect = [ClientError('network'), ClientError('network'), 'already_online', AuthError('stop')]
        with patch('ecnunet.time.sleep') as sleep, contextlib.redirect_stdout(io.StringIO()), self.assertRaises(AuthError):
            watch(c, 300)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [600, 900, 300])

    def test_interval_rejected_before_network(self):
        with contextlib.redirect_stderr(io.StringIO()), patch('ecnunet.load_config') as read:
            self.assertEqual(main(['watch', '--interval', '0']), 2)
            read.assert_not_called()

class RegressionTests(unittest.TestCase):
    def test_upstream_protocol_vectors(self):
        vectors = json.loads(Path(__file__).with_name('protocol_vectors.json').read_text())
        for v in vectors:
            with self.subTest(username=v['username'], challenge=v['challenge']):
                p = SrunProtocol(v['username'], v['password'], v['ip'], v['challenge'])
                encoded = '{SRBX1}' + p._custom_base64_encode(p._xencode(p._build_user_info(), p._challenge_token))
                self.assertEqual(encoded, v['encoded'])
                self.assertEqual(p._calculate_md5_password(), v['md5'])
                self.assertEqual(p._calculate_checksum(v['md5'], encoded), v['checksum'])

    def test_remote_disconnect_becomes_safe_error(self):
        from http.client import RemoteDisconnected
        c = Client()
        c.opener.open = Mock(side_effect=RemoteDisconnected('secret response'))
        with self.assertRaises(ClientError) as caught:
            c.status()
        self.assertNotIn('secret response', str(caught.exception))


if __name__ == '__main__':
    unittest.main()

# -*- coding: utf-8 -*-
"""途鸽 API 工具函数单元测试（无需 Odoo 运行时）。"""
import unittest

from odoo.addons.esim_tuge.services.tuge_api import (
    build_sign_source,
    compute_sign,
    parse_tuge_datetime,
    parse_token_payload,
    verify_sign,
    data_amount_to_gb,
)


class TestTugeAPIUtils(unittest.TestCase):

    def test_parse_tuge_datetime(self):
        result = parse_tuge_datetime('2025-08-27T09:00:00Z')
        self.assertEqual(result, '2025-08-27 09:00:00')

    def test_data_amount_to_gb(self):
        self.assertEqual(data_amount_to_gb(1, 'GB'), 1.0)
        self.assertAlmostEqual(data_amount_to_gb(500, 'MB'), 0.49, places=2)

    def test_sign_algorithm_document_example(self):
        """与文档 5 节示例一致的签名计算。"""
        secret = 'test_secret'
        params = {
            'foo': '1',
            'bar': '2',
            'foo_bar': '3',
            'foobar': '4',
            'sign': 'xxx',
            'file': b'ignored',
        }
        source = build_sign_source(params, secret)
        self.assertEqual(source, 'test_secretbar2foo1foo_bar3foobar4test_secret')
        sign = compute_sign(params, secret)
        self.assertEqual(len(sign), 32)

    def test_verify_sign_match(self):
        secret = 'mysecret'
        params = {'code': '0000', 'msg': 'success', 'timestamp': '2025-01-01T00:00:00Z'}
        params['sign'] = compute_sign(params, secret)
        self.assertTrue(verify_sign(params, secret))

    def test_verify_sign_fail(self):
        params = {'code': '0000', 'sign': 'invalid'}
        self.assertFalse(verify_sign(params, 'secret'))

    def test_parse_token_payload_nested_data(self):
        result = {
            'code': '0000',
            'data': {'accessToken': 'abc123', 'expires': 86400},
        }
        token = parse_token_payload(result)
        self.assertEqual(token['accessToken'], 'abc123')
        self.assertEqual(token['expires'], 86400)

    def test_parse_token_payload_top_level(self):
        result = {
            'code': '0000',
            'accessToken': 'top-level-token',
            'expires': 3600,
        }
        token = parse_token_payload(result)
        self.assertEqual(token['accessToken'], 'top-level-token')


if __name__ == '__main__':
    unittest.main()

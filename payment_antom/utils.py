# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""Antom 签名工具。

签名/验签逻辑与 global-open-sdk-python 1.4.x 完全对齐。
参考: https://github.com/alipay/global-open-sdk-python
"""

import base64
import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote_plus

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

_logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 时间
# ------------------------------------------------------------------

def get_iso8601_time() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串，与 SDK date_tools 一致。"""
    return datetime.fromtimestamp(int(__import__('time').time()), tz=timezone.utc).isoformat()


# ------------------------------------------------------------------
# PEM 构建
# ------------------------------------------------------------------

_PEM_LINE_WIDTH = 64
_PRIVATE_KEY_BEGIN = '-----BEGIN RSA PRIVATE KEY-----'
_PRIVATE_KEY_END = '-----END RSA PRIVATE KEY-----'
_PUBLIC_KEY_BEGIN = '-----BEGIN PUBLIC KEY-----'
_PUBLIC_KEY_END = '-----END PUBLIC KEY-----'


def _normalize_base64(raw: str) -> str:
    """去除所有空白字符并按 64 字符/行折行。"""
    cleaned = re.sub(r'\s+', '', raw)
    return '\n'.join(
        cleaned[i:i + _PEM_LINE_WIDTH]
        for i in range(0, len(cleaned), _PEM_LINE_WIDTH)
    )


def _add_pem_markers(key: str, begin: str, end: str) -> str:
    """确保 PEM 字符串包含正确的 header/footer（与 SDK __add_start_end 一致）。"""
    if begin not in key:
        key = begin + '\n' + key
    if end not in key:
        key = key + '\n' + end
    return key


def build_private_key_pem(raw_key: str) -> str:
    """构建 RSA 私钥 PEM（PKCS#1 格式，与 SDK 一致）。

    SDK 使用 '-----BEGIN RSA PRIVATE KEY-----' 包装。
    同时支持用户直接粘贴完整 PEM 或裸 Base64。
    """
    key = raw_key.strip()
    if key.startswith('-----'):
        return key
    body = _normalize_base64(key)
    return f"{_PRIVATE_KEY_BEGIN}\n{body}\n{_PRIVATE_KEY_END}"


def build_public_key_pem(raw_key: str) -> str:
    """构建 RSA 公钥 PEM。"""
    key = raw_key.strip()
    if key.startswith('-----'):
        return key
    body = _normalize_base64(key)
    return f"{_PUBLIC_KEY_BEGIN}\n{body}\n{_PUBLIC_KEY_END}"


# ------------------------------------------------------------------
# 签名内容构造
# ------------------------------------------------------------------

def gen_sign_content(
    http_method: str, path: str, client_id: str, time_string: str, content: str,
) -> str:
    """构造待签名内容（与 SDK gen_sign_content 完全一致）。

    格式: POST /ams/api/v1/payments/pay\\nCLIENT_ID.TIME.BODY
    """
    return f"{http_method} {path}\n{client_id}.{time_string}.{content}"


# ------------------------------------------------------------------
# 签名 & 验签
# ------------------------------------------------------------------

def sign_request(
    path: str, client_id: str, request_time: str, body: str, private_key_pem: str,
) -> str:
    """对请求进行 SHA256withRSA 签名（与 SDK sign 一致）。

    :return: URL 编码后的签名字符串
    """
    sign_content = gen_sign_content('POST', path, client_id, request_time, body)
    private_key_pem = _add_pem_markers(
        private_key_pem, _PRIVATE_KEY_BEGIN, _PRIVATE_KEY_END,
    )

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode('utf-8'), password=None,
    )
    signature_bytes = private_key.sign(
        sign_content.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    b64_sig = base64.b64encode(signature_bytes).decode('utf-8')
    return quote_plus(b64_sig, encoding='utf-8')


def verify_signature(
    path: str,
    client_id: str,
    response_time: str,
    body: str,
    signature_value: str,
    public_key_pem: str,
) -> bool:
    """验证响应/通知的 RSA 签名（与 SDK verify 一致）。"""
    signature_value = unquote_plus(signature_value)
    verify_content = gen_sign_content('POST', path, client_id, response_time, body)
    public_key_pem = _add_pem_markers(public_key_pem, _PUBLIC_KEY_BEGIN, _PUBLIC_KEY_END)

    try:
        sig_bytes = base64.b64decode(signature_value)
        public_key = serialization.load_pem_public_key(
            public_key_pem.encode('utf-8'),
        )
        public_key.verify(
            sig_bytes,
            verify_content.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        _logger.warning("Antom signature verification failed.", exc_info=True)
        return False


# ------------------------------------------------------------------
# Signature header 解析
# ------------------------------------------------------------------

def parse_signature_header(header: str) -> str:
    """从 Signature header 中提取签名值（与 SDK __parse_header 一致）。

    SDK 直接 split("signature=") 取最后一段。
    Header 格式: algorithm=RSA256,keyVersion=1,signature=<value>
    """
    if not header:
        return ''
    parts = header.split('signature=')
    return parts[-1] if len(parts) > 1 else ''

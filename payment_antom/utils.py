# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import logging
from urllib.parse import quote, unquote

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

_logger = logging.getLogger(__name__)


def sign_request(
    uri: str, client_id: str, request_time: str, body: str, private_key_pem: str
) -> str:
    """使用商户 RSA 私钥对请求进行 SHA256withRSA 签名。

    签名内容格式: POST <uri>\n<client_id>.<request_time>.<body>
    See https://docs.antom.com/ac/ams/digital_signature

    :param uri: API 路径，如 /ams/api/v1/payments/pay
    :param client_id: 商户 Client ID
    :param request_time: 请求时间戳（毫秒级字符串）
    :param body: 请求体 JSON 字符串
    :param private_key_pem: PEM 格式的 RSA 私钥内容
    :return: URL 编码后的签名字符串
    """
    content = f"POST {uri}\n{client_id}.{request_time}.{body}"

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode('utf-8'), password=None
    )
    signature_bytes = private_key.sign(
        content.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    b64_signature = base64.b64encode(signature_bytes).decode('utf-8')
    return quote(b64_signature, safe='')


def verify_signature(
    uri: str,
    client_id: str,
    response_time: str,
    body: str,
    signature_value: str,
    public_key_pem: str,
) -> bool:
    """使用 Antom 平台公钥验证响应/通知的 RSA 签名。

    验证内容格式: POST <uri>\n<client_id>.<response_time>.<body>
    See https://docs.antom.com/ac/ams/digital_signature

    :param uri: API 路径
    :param client_id: Client ID（来自响应/通知 header）
    :param response_time: 响应/通知时间（来自 header）
    :param body: 响应/通知体原始 JSON 字符串
    :param signature_value: URL 编码的签名值（从 Signature header 提取）
    :param public_key_pem: PEM 格式的 Antom 平台公钥
    :return: 签名是否有效
    """
    content = f"POST {uri}\n{client_id}.{response_time}.{body}"

    try:
        decoded_sig = unquote(signature_value)
        sig_bytes = base64.b64decode(decoded_sig)

        public_key = serialization.load_pem_public_key(
            public_key_pem.encode('utf-8')
        )
        public_key.verify(
            sig_bytes,
            content.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        _logger.warning("Antom signature verification failed.", exc_info=True)
        return False


def parse_signature_header(header: str) -> dict:
    """解析 Antom Signature header 为字典。

    Header 格式: algorithm=RSA256, keyVersion=1, signature=<url_encoded_value>
    """
    result = {}
    if not header:
        return result
    for part in header.split(','):
        part = part.strip()
        if '=' in part:
            key, _, value = part.partition('=')
            result[key.strip()] = value.strip()
    return result


def build_antom_private_key_pem(raw_key: str) -> str:
    """将裸 RSA 私钥内容包装为标准 PEM 格式。

    如果用户粘贴的是不带 header/footer 的纯 Base64 字符串，自动补全 PEM 格式。
    """
    key = raw_key.strip()
    if key.startswith('-----'):
        return key
    return f"-----BEGIN PRIVATE KEY-----\n{key}\n-----END PRIVATE KEY-----"


def build_antom_public_key_pem(raw_key: str) -> str:
    """将裸 RSA 公钥内容包装为标准 PEM 格式。"""
    key = raw_key.strip()
    if key.startswith('-----'):
        return key
    return f"-----BEGIN PUBLIC KEY-----\n{key}\n-----END PUBLIC KEY-----"

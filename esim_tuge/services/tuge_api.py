# -*- coding: utf-8 -*-
"""
途鸽科技 eSIM OpenAPI 客户端（纯 HTTP，无 ORM 依赖）。

鉴权：OAuth Bearer Token（/oauth/token，有效期约 24h）。
回调验签：MD5(secret + 排序后的 key+value 拼接 + secret)。
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

import requests

_logger = logging.getLogger(__name__)

# Odoo fields.Datetime 要求的格式
_ODOO_DT_FORMAT = '%Y-%m-%d %H:%M:%S'

SIGN_FIELD = 'sign'

# API 成功码
CODE_SUCCESS = '0000'
CODE_TOKEN_INVALID = '2003'

# 流量单位换算到 GB
_DATA_UNIT_TO_GB = {
    'GB': 1.0,
    'MB': 1 / 1024,
    'KB': 1 / (1024 * 1024),
}


class TugeAPIError(Exception):
    """途鸽 API 调用异常"""

    def __init__(
        self,
        code: str,
        msg: str,
        sub_code: str = '',
        sub_msg: str = '',
    ):
        self.code = code
        self.msg = msg
        self.sub_code = sub_code
        self.sub_msg = sub_msg
        detail = msg
        if sub_code or sub_msg:
            detail = f"{msg} [{sub_code}] {sub_msg}".strip()
        super().__init__(f"[{code}] {detail}")


def parse_tuge_datetime(value: str) -> str | None:
    """将途鸽 UTC 时间（yyyy-MM-dd'T'HH:mm:ss'Z'）转为 Odoo datetime 字符串。"""
    if not value:
        return None
    normalized = value.replace('Z', '+00:00') if value.endswith('Z') else value
    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime(_ODOO_DT_FORMAT)
    except (ValueError, TypeError):
        pass
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f'):
        try:
            return datetime.strptime(value.replace('Z', ''), fmt).strftime(_ODOO_DT_FORMAT)
        except ValueError:
            continue
    _logger.warning("无法解析途鸽时间格式: %s", value)
    return None


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _flatten_params(
    params: dict,
    parent_key: str,
    key_value_list: list[str],
) -> None:
    """递归展开嵌套 dict，生成 key+value 字符串列表（用于验签）。"""
    for key, value in params.items():
        if key == SIGN_FIELD:
            continue
        if _is_empty_value(value):
            continue
        current_key = f"{parent_key}.{key}" if parent_key else key
        if isinstance(value, dict):
            _flatten_params(value, current_key, key_value_list)
        elif isinstance(value, (list, tuple)):
            # 列表按 JSON 字符串参与签名（与途鸽 flatten 行为对齐）
            key_value_list.append(f"{current_key}{json.dumps(value, separators=(',', ':'), ensure_ascii=False)}")
        else:
            key_value_list.append(f"{current_key}{value}")


def build_sign_source(params: dict, secret: str) -> str:
    """构建待 MD5 的签名字符串：secret + 排序后的 keyvalue + secret。"""
    key_value_list: list[str] = []
    _flatten_params(params, '', key_value_list)
    key_value_list.sort()
    key_value_str = ''.join(key_value_list)
    return f"{secret}{key_value_str}{secret}"


def compute_sign(params: dict, secret: str) -> str:
    """计算回调/请求签名（小写 hex MD5）。"""
    sign_source = build_sign_source(params, secret)
    return hashlib.md5(sign_source.encode('utf-8')).hexdigest()


def verify_sign(params: dict, secret: str) -> bool:
    """校验途鸽回调签名。"""
    expected = params.get(SIGN_FIELD, '')
    if not expected or not secret:
        return False
    computed = compute_sign(params, secret)
    return computed.lower() == str(expected).lower()


def parse_token_payload(result: dict) -> dict:
    """
    从 OAuth 响应提取 TokenInfo。

    文档约定为 data.accessToken；部分环境可能在顶层返回 token 字段。
    """
    if not isinstance(result, dict):
        return {}

    payloads: list[dict] = []
    data = result.get('data')
    if isinstance(data, dict):
        payloads.append(data)
    payloads.append(result)

    for payload in payloads:
        access_token = (
            payload.get('accessToken')
            or payload.get('access_token')
            or payload.get('token')
        )
        if not access_token:
            continue
        expires = payload.get('expires', payload.get('expire', 86400))
        try:
            expires_int = int(expires)
        except (TypeError, ValueError):
            expires_int = 86400
        return {'accessToken': str(access_token), 'expires': expires_int}
    return {}


def data_amount_to_gb(amount: float | int | str, unit: str) -> float:
    """将 dataTotal + dataUnit 转为 GB。"""
    try:
        amount_f = float(amount)
    except (TypeError, ValueError):
        return 0.0
    multiplier = _DATA_UNIT_TO_GB.get((unit or 'GB').upper(), 1.0)
    return round(amount_f * multiplier, 2)


class TugeAPI:
    """途鸽 eSIM OpenAPI 客户端。"""

    DEFAULT_TIMEOUT = 30
    TOKEN_ENDPOINT = '/oauth/token'
    REFRESH_ENDPOINT = '/oauth/refreshToken'

    def __init__(
        self,
        account_id: str,
        secret: str,
        base_url: str,
        access_token: str = '',
    ):
        self.account_id = account_id
        self.secret = secret
        self.base_url = base_url.rstrip('/')
        self.access_token = access_token

    def get_token(self) -> dict:
        """获取新 accessToken。返回 {accessToken, expires}。"""
        url = f"{self.base_url}{self.TOKEN_ENDPOINT}"
        payload = {
            'accountId': self.account_id,
            'secret': self.secret,
        }
        return self._request_oauth(url, payload)

    def refresh_token(self) -> dict:
        """刷新 token（值不变，延长有效期）。"""
        url = f"{self.base_url}{self.REFRESH_ENDPOINT}"
        payload = {
            'accountId': self.account_id,
            'accessToken': self.access_token,
        }
        return self._request_oauth(url, payload)

    def _request_oauth(self, url: str, payload: dict) -> dict:
        """OAuth 请求：解析完整响应体中的 token。"""
        result = self._post_json(url, payload, use_auth=False)
        code = str(result.get('code', ''))
        if code != CODE_SUCCESS:
            msg = result.get('msg') or result.get('message') or 'Unknown error'
            sub_code = str(result.get('subCode', '') or '')
            sub_msg = str(result.get('subMsg', '') or '')
            raise TugeAPIError(code, msg, sub_code, sub_msg)

        token_data = parse_token_payload(result)
        if not token_data.get('accessToken'):
            _logger.error(
                "Tuge OAuth 成功但未解析到 accessToken，响应键: %s, data类型: %s",
                list(result.keys()),
                type(result.get('data')).__name__,
            )
            raise TugeAPIError(
                'NO_TOKEN',
                '授权响应中未包含 accessToken，请核对 Account ID、Secret 与 API 基础 URL',
            )
        return token_data

    def _post_json(
        self,
        url: str,
        payload: dict,
        use_auth: bool = True,
    ) -> dict:
        """POST 请求并返回完整 JSON 响应（不剥离 data）。"""
        body = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        headers = {
            'Content-Type': 'application/json;charset=UTF-8',
        }
        if use_auth:
            if not self.access_token:
                raise TugeAPIError(CODE_TOKEN_INVALID, 'Access token is missing')
            headers['Authorization'] = f'Bearer {self.access_token}'

        _logger.info("Tuge API POST %s", url)
        try:
            resp = requests.post(
                url, data=body.encode('utf-8'), headers=headers, timeout=self.DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            _logger.error("Tuge API HTTP error on %s: %s", url, e)
            raise TugeAPIError('HTTP_ERROR', str(e)) from e

        try:
            return resp.json()
        except ValueError as e:
            _logger.error("Tuge API 非 JSON 响应: %s", resp.text[:500])
            raise TugeAPIError('INVALID_JSON', '响应不是有效 JSON') from e

    def _post_raw(
        self,
        url: str,
        payload: dict,
        use_auth: bool = True,
        retry_on_token: bool = True,
    ) -> dict:
        """发送 POST 并解析顶层 code，成功时返回 data 段。"""
        result = self._post_json(url, payload, use_auth=use_auth)
        code = str(result.get('code', ''))
        if code == CODE_SUCCESS:
            return result.get('data') or {}

        msg = result.get('msg') or result.get('message') or 'Unknown error'
        sub_code = str(result.get('subCode', '') or '')
        sub_msg = str(result.get('subMsg', '') or '')
        if code == CODE_TOKEN_INVALID and use_auth and retry_on_token:
            raise TugeAPIError(code, msg, sub_code, sub_msg)
        raise TugeAPIError(code, msg, sub_code, sub_msg)

    def _post(self, endpoint: str, payload: dict, retry_on_token: bool = True) -> dict:
        """调用业务 API（Bearer 鉴权）。"""
        url = f"{self.base_url}{endpoint}"
        try:
            return self._post_raw(url, payload, use_auth=True, retry_on_token=retry_on_token)
        except TugeAPIError as e:
            if e.code == CODE_TOKEN_INVALID and retry_on_token:
                raise
            raise

    # ── 产品 ─────────────────────────────────────────────

    def list_products(
        self,
        page_num: int = 1,
        page_size: int = 100,
        lang: str = 'zh-CN',
        product_type: str = '',
        card_type: str = '',
    ) -> dict:
        """分页查询套餐。返回 {total, list}。"""
        payload: dict = {
            'pageNum': page_num,
            'pageSize': min(page_size, 100),
            'lang': lang,
        }
        if product_type:
            payload['productType'] = product_type
        if card_type:
            payload['cardType'] = card_type
        return self._post('/eSIMApi/v2/products/list', payload)

    def get_product_detail(self, product_code: str, lang: str = 'zh-CN') -> dict:
        return self._post('/eSIMApi/v2/products/detail', {
            'productCode': product_code,
            'lang': lang,
        })

    def get_card(self, card_type: str) -> dict:
        return self._post('/eSIMApi/v2/card', {'cardType': card_type})

    # ── 订单 ─────────────────────────────────────────────

    def create_order(
        self,
        product_code: str,
        channel_order_no: str,
        idempotency_key: str,
        start_date: str | None = None,
        email: str | None = None,
    ) -> dict:
        """常规 eSIM 下单。返回 {orderNo}。"""
        payload: dict = {
            'productCode': product_code,
            'channelOrderNo': channel_order_no,
            'idempotencyKey': idempotency_key,
        }
        if start_date:
            payload['startDate'] = start_date
        if email:
            payload['email'] = email
        return self._post('/eSIMApi/v2/order/create', payload)

    def renew_order(
        self,
        product_code: str,
        iccid: str,
        channel_order_no: str,
        idempotency_key: str,
        start_date: str | None = None,
        email: str | None = None,
    ) -> dict:
        payload: dict = {
            'productCode': product_code,
            'iccid': iccid,
            'channelOrderNo': channel_order_no,
            'idempotencyKey': idempotency_key,
        }
        if start_date:
            payload['startDate'] = start_date
        if email:
            payload['email'] = email
        return self._post('/eSIMApi/v2/order/renew', payload)

    def query_orders(
        self,
        order_no: str = '',
        iccid: str = '',
        channel_order_no: str = '',
        lang: str = 'zh-CN',
    ) -> dict:
        """按条件查询订单。返回 {list: [...]}。"""
        payload: dict = {'lang': lang}
        if order_no:
            payload['orderNo'] = order_no
        if iccid:
            payload['iccid'] = iccid
        if channel_order_no:
            payload['channelOrderNo'] = channel_order_no
        return self._post('/eSIMApi/v2/order/orders', payload)

    def list_orders(
        self,
        page_num: int = 1,
        page_size: int = 100,
        order_status: str = '',
        lang: str = 'zh-CN',
    ) -> dict:
        payload: dict = {
            'pageNum': page_num,
            'pageSize': min(page_size, 100),
            'lang': lang,
        }
        if order_status:
            payload['orderStatus'] = order_status
        return self._post('/eSIMApi/v2/order/list', payload)

    def order_usage(self, order_no: str) -> dict:
        return self._post('/eSIMApi/v2/order/usage', {'orderNo': order_no})

    def terminate_order(self, order_no: str, iccid: str) -> dict:
        return self._post('/eSIMApi/v2/order/terminate', {
            'orderNo': order_no,
            'iccid': iccid,
        })

    def topup_create(
        self,
        order_no: str,
        purchase_type: int,
        idempotency_key: str,
    ) -> dict:
        return self._post('/eSIMApi/v2/order/topup/create', {
            'orderNo': order_no,
            'purchaseType': purchase_type,
            'idempotencyKey': idempotency_key,
        })

    # ── Profile / 账户 ───────────────────────────────────

    def iccid_profile(self, iccid: str) -> dict:
        return self._post('/eSIMApi/v2/iccid/profile', {'iccid': iccid})

    def account_balance(self, account_type: str = '') -> dict:
        payload = {}
        if account_type:
            payload['type'] = account_type
        return self._post('/eSIMApi/v2/account/balance', payload)

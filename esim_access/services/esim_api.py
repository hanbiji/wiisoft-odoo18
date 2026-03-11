# -*- coding: utf-8 -*-
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone

import requests

_logger = logging.getLogger(__name__)

# API 价格单位为万分之一美元，需除以 10000 转换为标准货币单位
PRICE_DIVISOR = 10000
# 流量单位为字节，需除以此值转换为 GB
VOLUME_DIVISOR = 1073741824

# Odoo fields.Datetime 要求的格式
_ODOO_DT_FORMAT = '%Y-%m-%d %H:%M:%S'


def parse_api_datetime(value: str) -> str | None:
    """将 API 返回的 ISO 8601 时间（如 2026-09-07T13:09:52+0000）转为 Odoo datetime 字符串"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime(_ODOO_DT_FORMAT)
    except (ValueError, TypeError):
        pass
    # 兜底：手动处理 +0000 格式（Python < 3.11 的 fromisoformat 不支持）
    for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S.%f%z', '%Y-%m-%dT%H:%M:%S'):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime(_ODOO_DT_FORMAT)
        except ValueError:
            continue
    _logger.warning("无法解析 API 时间格式: %s", value)
    return None


class EsimAccessAPIError(Exception):
    """eSIM Access API 调用异常"""

    def __init__(self, error_code: str, error_msg: str):
        self.error_code = error_code
        self.error_msg = error_msg
        super().__init__(f"[{error_code}] {error_msg}")


class EsimAccessAPI:
    """eSIM Access API 客户端，封装认证签名和所有端点调用"""

    DEFAULT_TIMEOUT = 30

    def __init__(self, access_code: str, secret_key: str, base_url: str):
        self.access_code = access_code
        self.secret_key = secret_key
        self.base_url = base_url.rstrip('/')

    def _generate_signature(self, request_id: str, timestamp: str, body: str) -> str:
        """
        HMAC SHA256 签名：signData = timestamp + requestId + accessCode + body
        """
        sign_data = f"{timestamp}{request_id}{self.access_code}{body}"
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            sign_data.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest().upper()
        return signature

    def _make_request(self, endpoint: str, payload: dict) -> dict:
        """发送 POST 请求到 API 端点，处理认证和错误"""
        url = f"{self.base_url}/{endpoint}"
        body = json.dumps(payload, separators=(',', ':'))
        request_id = uuid.uuid4().hex
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))

        signature = self._generate_signature(request_id, timestamp, body)
        headers = {
            'Content-Type': 'application/json',
            'RT-AccessCode': self.access_code,
            'RT-RequestID': request_id,
            'RT-Timestamp': timestamp,
            'RT-Signature': signature,
        }

        _logger.info("eSIM API request: %s %s", endpoint, body)

        try:
            resp = requests.post(url, data=body, headers=headers, timeout=self.DEFAULT_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            _logger.error("eSIM API HTTP error on %s: %s", endpoint, e)
            raise EsimAccessAPIError('HTTP_ERROR', str(e)) from e

        result = resp.json()
        _logger.info("eSIM API response: %s success=%s", endpoint, result.get('success'))

        if not result.get('success'):
            error_code = result.get('errorCode', 'UNKNOWN')
            error_msg = result.get('errorMessage') or result.get('errorMsg') or 'Unknown error'
            _logger.warning("eSIM API error on %s: [%s] %s", endpoint, error_code, error_msg)
            raise EsimAccessAPIError(error_code, error_msg)

        return result.get('obj', {})

    # ── 套餐查询 ─────────────────────────────────────────────

    def get_package_list(
        self,
        location_code: str = '',
        package_type: str = 'BASE',
        package_code: str = '',
        slug: str = '',
        iccid: str = '',
        data_type: str = '',
    ) -> list[dict]:
        """
        查询可用套餐列表。
        - location_code: Alpha-2 ISO 国家代码，!RG=区域, !GL=全球
        - package_type: BASE=普通套餐(默认), TOPUP=充值套餐
        - package_code: 与 TOPUP 搭配查看指定套餐的充值包
        - slug: packageCode 的别名
        - iccid: 与 TOPUP 搭配查看指定 eSIM 的可用充值包
        - data_type: 1=固定流量, 2=日通
        """
        payload = {
            'locationCode': location_code,
            'type': package_type,
            'packageCode': package_code,
            'slug': slug,
            'iccid': iccid,
        }
        if data_type:
            payload['dataType'] = data_type
        result = self._make_request('open/package/list', payload)
        return result.get('packageList', [])

    # ── 下单 ─────────────────────────────────────────────────

    def place_order(
        self,
        transaction_id: str,
        package_info_list: list[dict],
        amount: int = 0,
    ) -> dict:
        """
        下单购买 eSIM（支持批量多套餐）。
        - transaction_id: 唯一交易 ID，最长 50 字符，重试需保持不变
        - package_info_list: 套餐列表，每项包含:
            packageCode/slug (必填), count (必填),
            price (可选, 万分之一美元), periodNum (可选, 每日套餐天数 1-365)
        - amount: 可选，总金额（万分之一美元），用于价格校验
        """
        payload: dict = {
            'transactionId': transaction_id,
            'packageInfoList': package_info_list,
        }
        if amount:
            payload['amount'] = amount
        return self._make_request('open/esim/order', payload)

    # ── 查询 eSIM 档案（统一查询端点） ─────────────────────────

    def query_esim(
        self,
        order_no: str = '',
        iccid: str = '',
        start_time: str = '',
        end_time: str = '',
        page_num: int = 1,
        page_size: int = 50,
    ) -> dict:
        """
        统一查询 eSIM 档案（新订单获取 & 已有 eSIM 状态查询）。
        - order_no: 按订单号查询，返回该订单的全部 eSIM（批量）
        - iccid: 按 ICCID 查询，返回单个 eSIM
        - start_time/end_time: ISO UTC 时间范围查询
        - page_num: 页码 [1, 10000]
        - page_size: 每页条数 [5, 500]
        返回 {'esimList': [...], 'pager': {'pageNum', 'pageSize', 'total'}}
        """
        payload: dict = {
            'pager': {
                'pageNum': page_num,
                'pageSize': page_size,
            },
        }
        if order_no:
            payload['orderNo'] = order_no
        if iccid:
            payload['iccid'] = iccid
        if start_time:
            payload['startTime'] = start_time
        if end_time:
            payload['endTime'] = end_time
        return self._make_request('open/esim/query', payload)

    # ── 充值 ─────────────────────────────────────────────────

    def top_up(
        self,
        iccid: str,
        package_code: str,
        transaction_id: str,
        amount: int,
    ) -> dict:
        """
        为已有 eSIM 充值续费。
        - amount: 充值金额（万分之一美元单位）
        """
        payload = {
            'iccid': iccid,
            'packageCode': package_code,
            'transactionId': transaction_id,
            'amount': amount,
        }
        return self._make_request('topUp', payload)

    # ── 取消订单 ─────────────────────────────────────────────

    def cancel_order(self, order_no: str) -> dict:
        """取消未安装的 eSIM 订单，余额退回账户"""
        return self._make_request('cancel', {'orderNo': order_no})

    # ── 吊销 eSIM ────────────────────────────────────────────

    def revoke_esim(self, iccid: str) -> dict:
        """永久禁用 eSIM（防欺诈/防盗用）"""
        return self._make_request('revoke', {'iccid': iccid})

    # ── 挂起 eSIM ────────────────────────────────────────────

    def suspend_esim(self, iccid: str) -> dict:
        """临时挂起 eSIM"""
        return self._make_request('suspend', {'iccid': iccid})

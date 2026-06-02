# -*- coding: utf-8 -*-
import json
import logging
import time

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..services.tuge_api import TugeAPI, TugeAPIError, CODE_TOKEN_INVALID, data_amount_to_gb

_logger = logging.getLogger(__name__)

PROVIDER_SELECTION = [
    ('access', 'eSIM Access'),
    ('tuge', '途鸽 Tuge'),
]

TUGE_PRODUCT_TYPE_SELECTION = [
    ('DAILY_PACK', '日包'),
    ('DATA_PACK', '流量包'),
]

TUGE_ACTIVE_TYPE_SELECTION = [
    ('AUTO_ACTIVATE', '自动激活'),
    ('ACTIVATE_ON_ORDER', '指定激活'),
]

TUGE_PERIOD_TYPE_SELECTION = [
    ('0', '24小时'),
    ('1', '自然日'),
]

# Token 提前 5 分钟刷新
_TOKEN_REFRESH_MARGIN_SEC = 300


class EsimPackage(models.Model):
    _inherit = 'esim.package'

    provider = fields.Selection(
        PROVIDER_SELECTION,
        string="供应商",
        default='access',
        required=True,
        index=True,
    )
    tuge_card_type = fields.Char(string="途鸽卡类型", index=True)
    tuge_product_type = fields.Selection(
        TUGE_PRODUCT_TYPE_SELECTION,
        string="途鸽产品类型",
    )
    tuge_active_type = fields.Selection(
        TUGE_ACTIVE_TYPE_SELECTION,
        string="途鸽激活方式",
    )
    tuge_usage_period = fields.Integer(string="途鸽激活使用期")
    tuge_validity_period = fields.Integer(string="途鸽订单有效期(天)")
    tuge_period_type = fields.Selection(
        TUGE_PERIOD_TYPE_SELECTION,
        string="途鸽周期类型",
    )

    def _get_tuge_config(self) -> dict:
        """读取途鸽 API 配置参数。"""
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'account_id': (ICP.get_param('tuge.account_id', '') or '').strip(),
            'secret': (ICP.get_param('tuge.secret', '') or '').strip(),
            'base_url': (
                ICP.get_param(
                    'tuge.base_url',
                    'https://enterpriseapisandbox.tugegroup.com:8070/openapi',
                )
                or ''
            ).strip().rstrip('/'),
            'markup': float(ICP.get_param('tuge.default_markup', '1.3')),
        }

    def _get_tuge_cached_token(self) -> tuple[str, bool]:
        """
        读取缓存 token。
        返回 (token, needs_refresh)。
        """
        ICP = self.env['ir.config_parameter'].sudo()
        token = ICP.get_param('tuge.access_token', '')
        expire_str = ICP.get_param('tuge.token_expire_at', '0')
        try:
            expire_at = float(expire_str)
        except (TypeError, ValueError):
            expire_at = 0.0
        now = time.time()
        if token and expire_at > now + _TOKEN_REFRESH_MARGIN_SEC:
            return token, False
        return token, True

    def _store_tuge_token(self, access_token: str, expires_sec: int) -> None:
        """缓存 token 与过期时间戳。"""
        ICP = self.env['ir.config_parameter'].sudo()
        expire_at = time.time() + max(int(expires_sec) - _TOKEN_REFRESH_MARGIN_SEC, 60)
        ICP.set_param('tuge.access_token', access_token)
        ICP.set_param('tuge.token_expire_at', str(expire_at))

    @api.model
    def _get_tuge_api_client(self, force_new_token: bool = False) -> TugeAPI:
        """构建途鸽 API 客户端（含 token 获取/刷新）。"""
        config = self._get_tuge_config()
        if not config['account_id'] or not config['secret']:
            raise UserError(_("请先在设置中配置途鸽 API 凭证（Account ID 与 Secret）"))

        token, needs_refresh = self._get_tuge_cached_token()
        client = TugeAPI(
            config['account_id'],
            config['secret'],
            config['base_url'],
            access_token=token,
        )

        if force_new_token or needs_refresh or not token:
            try:
                if token and not force_new_token:
                    data = client.refresh_token()
                else:
                    data = client.get_token()
            except TugeAPIError as refresh_err:
                if token and not force_new_token:
                    _logger.info("途鸽 refreshToken 失败，改走 get_token: %s", refresh_err)
                    data = client.get_token()
                else:
                    raise UserError(_("途鸽授权失败: %s") % refresh_err) from refresh_err
            new_token = data.get('accessToken', '')
            expires = int(data.get('expires', 86400))
            if not new_token:
                raise UserError(_(
                    "途鸽授权失败：未返回 accessToken。请检查设置中的 Account ID、Secret，"
                    "以及 API 基础 URL 是否为 …/openapi（沙箱示例: "
                    "https://enterpriseapisandbox.tugegroup.com:8070/openapi）"
                ))
            client.access_token = new_token
            self._store_tuge_token(new_token, expires)
        return client

    def _tuge_api_call_with_token_retry(self, call_fn):
        """执行 API 调用，token 失效时刷新并重试一次。"""
        client = self._get_tuge_api_client()
        try:
            return call_fn(client)
        except TugeAPIError as e:
            if e.code != CODE_TOKEN_INVALID:
                raise
            client = self._get_tuge_api_client(force_new_token=True)
            return call_fn(client)

    def action_sync_tuge_packages(self):
        """套餐列表页：手动同步途鸽套餐。"""
        if not self.env.user.has_group('esim_access.group_esim_manager'):
            raise UserError(_("只有 eSIM 管理员可以执行此操作。"))
        count = self._sync_tuge_packages_from_api()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("途鸽套餐同步完成"),
                'message': _("共同步 %d 个套餐") % count,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    @api.model
    def _map_tuge_product_to_vals(self, pkg: dict, markup: float) -> dict:
        """将途鸽 ProductInfo 映射为 esim.package 字段值。"""
        code = pkg.get('productCode', '')
        net_price = float(pkg.get('netPrice', 0) or 0)
        data_limited = pkg.get('dataLimited', 'N')
        data_total = pkg.get('dataTotal', 0) or 0
        data_unit = pkg.get('dataUnit', 'GB') or 'GB'
        volume_gb = data_amount_to_gb(data_total, data_unit) if data_limited == 'Y' else 0.0

        countries = pkg.get('countryCodeList') or []
        if isinstance(countries, list):
            location = ','.join(countries)
        else:
            location = str(countries)

        topup_list = pkg.get('topupInfoList') or []
        description_parts = []
        if pkg.get('ruleDesc'):
            description_parts.append(pkg['ruleDesc'])
        if topup_list:
            description_parts.append(
                _("加油包: %s") % json.dumps(topup_list, ensure_ascii=False)
            )

        period_type = pkg.get('periodType')
        period_type_str = str(period_type) if period_type is not None else False

        return {
            'package_code': code,
            'name': pkg.get('productName', code),
            'provider': 'tuge',
            'cost_price': net_price,
            'sale_price': round(net_price * markup, 2),
            'retail_price': net_price,
            'currency_code': 'USD',
            'volume': volume_gb,
            'duration': pkg.get('usagePeriod', 0) or 0,
            'duration_unit': 'DAY',
            'unused_valid_time': pkg.get('validityPeriod', 0) or 0,
            'location': location,
            'description': '\n'.join(description_parts) if description_parts else False,
            'package_type': 'BASE',
            'support_topup': bool(topup_list),
            'speed': pkg.get('highSpeed', '') or pkg.get('limitSpeed', ''),
            'fup_policy': pkg.get('ruleDesc', ''),
            'tuge_card_type': pkg.get('cardType', ''),
            'tuge_product_type': pkg.get('productType', ''),
            'tuge_active_type': pkg.get('activeType', ''),
            'tuge_usage_period': pkg.get('usagePeriod', 0) or 0,
            'tuge_validity_period': pkg.get('validityPeriod', 0) or 0,
            'tuge_period_type': period_type_str,
            'raw_price': 0,
            'last_sync_date': fields.Datetime.now(),
        }

    @api.model
    def _sync_tuge_packages_from_api(self, lang: str = 'zh-CN') -> int:
        """从途鸽 API 分页同步全部套餐。"""
        config = self._get_tuge_config()
        markup = config['markup']
        page_num = 1
        page_size = 100
        total_synced = 0

        def fetch_page(client: TugeAPI) -> dict:
            return client.list_products(
                page_num=page_num,
                page_size=page_size,
                lang=lang,
            )

        while True:
            try:
                result = self._tuge_api_call_with_token_retry(fetch_page)
            except TugeAPIError as e:
                _logger.error("途鸽套餐同步失败: %s", e)
                raise UserError(_("途鸽套餐同步失败: %s") % e) from e

            product_list = result.get('list') or []
            if not product_list:
                break

            for pkg in product_list:
                code = pkg.get('productCode', '')
                if not code:
                    continue
                vals = self._map_tuge_product_to_vals(pkg, markup)
                existing = self.search([
                    ('package_code', '=', code),
                    ('provider', '=', 'tuge'),
                ], limit=1)
                if existing:
                    existing.write(vals)
                else:
                    self.create(vals)
                total_synced += 1

            api_total = int(result.get('total', 0) or 0)
            if page_num * page_size >= api_total or len(product_list) < page_size:
                break
            page_num += 1

        _logger.info("途鸽套餐同步完成，共处理 %d 条", total_synced)
        return total_synced

    @api.model
    def _cron_sync_tuge_packages(self) -> None:
        """定时任务：同步途鸽套餐。"""
        self._sync_tuge_packages_from_api()

    def _get_api_client(self):
        """按供应商返回 API 客户端；空记录集或未指定途鸽时走 Access。"""
        if len(self) == 1 and self.provider == 'tuge':
            return self._get_tuge_api_client()
        return super()._get_api_client()

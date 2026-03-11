# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..services.esim_api import EsimAccessAPI, EsimAccessAPIError, PRICE_DIVISOR, VOLUME_DIVISOR

_logger = logging.getLogger(__name__)

DURATION_UNIT_SELECTION = [
    ('DAY', '天'),
    ('MONTH', '月'),
]

PACKAGE_TYPE_SELECTION = [
    ('normal', '普通套餐'),
    ('topup', '充值套餐'),
]


class EsimPackage(models.Model):
    _name = 'esim.package'
    _description = 'eSIM 套餐'
    _order = 'location, volume, duration'

    package_code = fields.Char(string="套餐编码", required=True, index=True)
    name = fields.Char(string="套餐名称", required=True)
    cost_price = fields.Float(string="成本价", digits=(12, 2), help="API 原始价格（标准货币单位）")
    sale_price = fields.Float(string="售价", digits=(12, 2), help="加价后的零售价格")
    currency_code = fields.Char(string="货币", default='USD')
    volume = fields.Float(string="流量 (GB)", digits=(10, 2))
    duration = fields.Integer(string="有效期")
    duration_unit = fields.Selection(DURATION_UNIT_SELECTION, string="有效期单位", default='DAY')
    unused_valid_time = fields.Integer(string="未激活有效天数")
    location = fields.Char(string="覆盖地区", help="国家/地区代码，逗号分隔")
    description = fields.Text(string="描述")
    package_type = fields.Selection(PACKAGE_TYPE_SELECTION, string="类型", default='normal')
    active_type = fields.Integer(string="激活方式")
    is_published = fields.Boolean(string="门户展示", default=False)
    active = fields.Boolean(string="启用", default=True)
    last_sync_date = fields.Datetime(string="最后同步时间", readonly=True)

    # API 原始价格（万分之一单位），用于调用 API 下单时传递
    raw_price = fields.Integer(string="API 原始价格", help="API 返回的原始价格值")

    _sql_constraints = [
        ('package_code_uniq', 'UNIQUE(package_code)', '套餐编码不能重复'),
    ]

    def _compute_display_name(self):
        for rec in self:
            unit = dict(DURATION_UNIT_SELECTION).get(rec.duration_unit, '')
            rec.display_name = f"{rec.name} ({rec.volume}GB/{rec.duration}{unit})"

    def _get_api_client(self) -> EsimAccessAPI:
        """从系统参数构建 API 客户端"""
        ICP = self.env['ir.config_parameter'].sudo()
        access_code = ICP.get_param('esim_access.access_code', '')
        secret_key = ICP.get_param('esim_access.secret_key', '')
        base_url = ICP.get_param('esim_access.api_base_url', 'https://api.esimaccess.com/api/v1')

        if not access_code or not secret_key:
            raise UserError(_("请先在设置中配置 eSIM Access API 凭证"))

        return EsimAccessAPI(access_code, secret_key, base_url)

    def action_sync_packages(self):
        """套餐列表页面手动触发同步"""
        count = self._sync_packages_from_api()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("套餐同步完成"),
                'message': _("共同步 %d 个套餐") % count,
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def _sync_packages_from_api(self, location_code: str = '') -> int:
        """从 API 同步套餐到本地数据库，返回同步数量"""
        api_client = self._get_api_client()
        ICP = self.env['ir.config_parameter'].sudo()
        markup = float(ICP.get_param('esim_access.default_markup', '1.3'))

        try:
            packages = api_client.get_package_list(location_code=location_code)
        except EsimAccessAPIError as e:
            _logger.error("套餐同步失败: %s", e)
            raise UserError(_("套餐同步失败: %s") % e.error_msg) from e

        now = fields.Datetime.now()
        synced_codes = set()
        for pkg in packages:
            code = pkg.get('packageCode', '')
            if not code:
                continue
            synced_codes.add(code)

            is_topup = code.startswith('TOPUP_')
            raw_price = pkg.get('price', 0)
            cost_price = raw_price / PRICE_DIVISOR
            volume_bytes = pkg.get('volume', 0)
            volume_gb = round(volume_bytes / VOLUME_DIVISOR, 2)

            vals = {
                'package_code': code,
                'name': pkg.get('name', ''),
                'cost_price': cost_price,
                'sale_price': round(cost_price * markup, 2),
                'currency_code': pkg.get('currencyCode', 'USD'),
                'volume': volume_gb,
                'duration': pkg.get('duration', 0),
                'duration_unit': pkg.get('durationUnit', 'DAY'),
                'unused_valid_time': pkg.get('unusedValidTime', 0),
                'location': pkg.get('location', ''),
                'description': pkg.get('description', ''),
                'package_type': 'topup' if is_topup else 'normal',
                'active_type': pkg.get('activeType', 0),
                'raw_price': raw_price,
                'last_sync_date': now,
            }

            existing = self.search([('package_code', '=', code)], limit=1)
            if existing:
                existing.write(vals)
            else:
                self.create(vals)

        _logger.info("套餐同步完成，共处理 %d 个套餐", len(synced_codes))
        return len(synced_codes)

    @api.model
    def _cron_sync_packages(self) -> None:
        """定时任务入口：同步套餐"""
        self._sync_packages_from_api()

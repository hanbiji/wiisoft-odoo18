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
    ('BASE', '普通套餐'),
    ('TOPUP', '充值套餐'),
]

DATA_TYPE_SELECTION = [
    ('1', '固定流量'),
    ('2', '每日限额(降速)'),
    ('3', '每日限额(断网)'),
    ('4', '每日不限量'),
]

SMS_STATUS_SELECTION = [
    ('0', '不支持 SMS'),
    ('1', 'API 和手机 SMS'),
    ('2', '仅 API SMS'),
]


class EsimPackage(models.Model):
    _name = 'esim.package'
    _description = 'eSIM 套餐'
    _order = 'location, volume, duration'

    package_code = fields.Char(string="套餐编码", required=True, index=True)
    slug = fields.Char(string="别名 (Slug)", index=True)
    name = fields.Char(string="套餐名称", required=True)
    cost_price = fields.Float(string="成本价", digits=(12, 2), help="API 原始价格（标准货币单位）")
    sale_price = fields.Float(string="售价", digits=(12, 2), help="加价后的零售价格")
    retail_price = fields.Float(string="建议零售价", digits=(12, 2), help="平台建议零售价")
    currency_code = fields.Char(string="货币", default='USD')
    volume = fields.Float(string="流量 (GB)", digits=(10, 2))
    duration = fields.Integer(string="有效期")
    duration_unit = fields.Selection(DURATION_UNIT_SELECTION, string="有效期单位", default='DAY')
    unused_valid_time = fields.Integer(string="未激活有效天数")
    location = fields.Char(string="覆盖地区", help="Alpha-2 ISO 国家代码，逗号分隔")
    description = fields.Text(string="描述")
    package_type = fields.Selection(PACKAGE_TYPE_SELECTION, string="类型", default='BASE')
    data_type = fields.Selection(DATA_TYPE_SELECTION, string="流量类型")
    sms_status = fields.Selection(SMS_STATUS_SELECTION, string="SMS 支持")
    active_type = fields.Integer(string="激活方式", help="1=首次安装激活, 2=首次联网激活")
    speed = fields.Char(string="网络速度")
    ip_export = fields.Char(string="流量出口国")
    support_topup = fields.Boolean(string="支持充值", help="该套餐是否支持充值续费")
    fup_policy = fields.Char(string="公平使用政策", help="高速流量耗尽后的限速策略")
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

    def _set_portal_publish_state(self, is_published: bool) -> dict:
        """批量更新门户展示状态，并在列表页刷新结果。"""
        if not self:
            raise UserError(_("请先选择要修改的套餐。"))

        self.write({'is_published': is_published})
        target_status = _("展示") if is_published else _("隐藏")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("批量更新成功"),
                'message': _("已将 %d 个套餐设置为门户%s。") % (len(self), target_status),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def action_publish_to_portal(self) -> dict:
        """批量设为门户展示。"""
        return self._set_portal_publish_state(True)

    def action_unpublish_from_portal(self) -> dict:
        """批量取消门户展示。"""
        return self._set_portal_publish_state(False)

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
            raw_retail = pkg.get('retailPrice', 0)
            support_topup_val = pkg.get('supportTopUpType')

            vals = {
                'package_code': code,
                'slug': pkg.get('slug', ''),
                'name': pkg.get('name', ''),
                'cost_price': cost_price,
                'sale_price': round(cost_price * markup, 2),
                'retail_price': raw_retail / PRICE_DIVISOR if raw_retail else 0,
                'currency_code': pkg.get('currencyCode', 'USD'),
                'volume': volume_gb,
                'duration': pkg.get('duration', 0),
                'duration_unit': pkg.get('durationUnit', 'DAY'),
                'unused_valid_time': pkg.get('unusedValidTime', 0),
                'location': pkg.get('location', ''),
                'description': pkg.get('description', ''),
                'package_type': 'TOPUP' if is_topup else 'BASE',
                'data_type': str(pkg['dataType']) if pkg.get('dataType') else False,
                'sms_status': str(pkg['smsStatus']) if pkg.get('smsStatus') is not None else False,
                'active_type': pkg.get('activeType', 0),
                'speed': pkg.get('speed', ''),
                'ip_export': pkg.get('ipExport', ''),
                'support_topup': support_topup_val == 2 if support_topup_val else False,
                'fup_policy': pkg.get('fupPolicy', ''),
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

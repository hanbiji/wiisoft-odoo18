# -*- coding: utf-8 -*-
import logging
from urllib.parse import quote

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..services.tuge_api import TugeAPIError, parse_tuge_datetime, data_amount_to_gb

_logger = logging.getLogger(__name__)

# 途鸽 profileStatus（订单维度）→ 内部 state
_TUGE_PROFILE_STATUS_MAP = {
    'activated': 'active',
    'downloaded': 'ready',
    'nodownload': 'ready',
    'ungenerated': 'pending',
    'failed': 'pending',
    'downloadfail': 'pending',
    'disabled': 'suspended',
    'unavailable': 'expired',
    'unvaliable': 'expired',
    'deleted': 'revoked',
}

# 途鸽 iccid profile state（安装状态）
_TUGE_ICCID_STATE_MAP = {
    'Enabled': 'active',
    'Installed': 'active',
    'Downloaded': 'ready',
    'Released': 'ready',
    'Disabled': 'suspended',
    'Deleted': 'revoked',
    'Unavailable': 'expired',
    'Error': 'pending',
}

# 途鸽 orderStatus
_TUGE_ORDER_STATUS_MAP = {
    'NOTACTIVE': 'ready',
    'ACTIVATED': 'ready',
    'INUSE': 'active',
    'USED': 'expired',
    'EXPIRED': 'expired',
    'ABANDON': 'cancelled',
    'TERMINATION': 'revoked',
}


class EsimProfile(models.Model):
    _inherit = 'esim.profile'

    provider = fields.Selection(
        related='order_id.provider',
        string="供应商",
        store=True,
        readonly=True,
    )
    tuge_order_status = fields.Char(string="途鸽订单状态", readonly=True)

    @api.model
    def _tuge_qr_barcode_url(self, qr_code: str) -> str:
        """用 Odoo 条码接口生成可展示的 QR 图片 URL。"""
        if not qr_code:
            return ''
        encoded = quote(qr_code, safe='')
        return f'/report/barcode/?barcode_type=QR&value={encoded}&width=200&height=200'

    @api.model
    def _derive_tuge_state(
        self,
        profile_status: str = '',
        iccid_state: str = '',
        order_status: str = '',
    ) -> str:
        """综合途鸽状态字段推导内部 profile state。"""
        if order_status:
            mapped = _TUGE_ORDER_STATUS_MAP.get(order_status.upper())
            if mapped in ('expired', 'cancelled', 'revoked'):
                return mapped
        if iccid_state:
            mapped = _TUGE_ICCID_STATE_MAP.get(iccid_state)
            if mapped:
                return mapped
        if profile_status:
            mapped = _TUGE_PROFILE_STATUS_MAP.get(profile_status.lower())
            if mapped:
                return mapped
        return 'pending'

    @api.model
    def _map_tuge_order_info(self, order_info: dict) -> dict:
        """将途鸽 OrderInfo（回调/查单）映射为 profile 字段。"""
        card_info = order_info.get('cardInfo') or {}
        iccid = order_info.get('iccid') or card_info.get('iccid', '')
        qr_code = order_info.get('qrCode', '')
        profile_status = order_info.get('profileStatus', '')
        order_status = order_info.get('orderStatus', '')

        vals = {
            'qr_code': qr_code,
            'qr_code_url': self._tuge_qr_barcode_url(qr_code),
            'imsi': order_info.get('imsi') or card_info.get('imsi', ''),
            'tuge_order_status': order_status,
            'esim_status': order_status or profile_status,
            'smdp_status': profile_status,
            'state': self._derive_tuge_state(profile_status, '', order_status),
        }

        expired = parse_tuge_datetime(order_info.get('activatedEndTime', ''))
        if expired:
            vals['expired_time'] = expired

        data_limited = order_info.get('dataLimited')
        if data_limited == 'Y':
            total = order_info.get('dataTotal')
            unit = order_info.get('dataUnit', 'GB')
            if total is not None:
                vals['total_volume'] = data_amount_to_gb(total, unit)

        return vals

    @api.model
    def _map_tuge_iccid_profile(self, profile_data: dict) -> dict:
        """将途鸽 /iccid/profile 响应映射为 profile 更新字段。"""
        iccid_state = profile_data.get('state', '')
        vals = {
            'imsi': profile_data.get('imsi', ''),
            'eid': profile_data.get('eid', ''),
            'smdp_status': iccid_state,
            'state': self._derive_tuge_state('', iccid_state, ''),
        }
        install_time = parse_tuge_datetime(profile_data.get('installTime', ''))
        if install_time:
            vals['expired_time'] = vals.get('expired_time') or install_time
        return vals

    def _is_tuge_profile(self) -> bool:
        self.ensure_one()
        return self.order_id.provider == 'tuge' or (
            self.package_id and self.package_id.provider == 'tuge'
        )

    def action_refresh_status(self) -> None:
        tuge_profiles = self.filtered(lambda p: p._is_tuge_profile())
        other_profiles = self - tuge_profiles

        package_model = self.env['esim.package']
        for profile in tuge_profiles:
            if not profile.iccid or profile.iccid.startswith('TUGE-PENDING-'):
                continue

            # 刷新安装状态
            def do_profile(client):
                return client.iccid_profile(profile.iccid)

            try:
                iccid_data = package_model._tuge_api_call_with_token_retry(do_profile)
                vals = self._map_tuge_iccid_profile(iccid_data)
                profile.write(vals)
            except TugeAPIError as e:
                profile.message_post(body=_("途鸽 Profile 刷新失败: %s") % e.msg)

            # 刷新流量（需主订单号）
            order = profile.order_id
            if order and order.api_order_no:
                def do_usage(client):
                    return client.order_usage(order.api_order_no)

                try:
                    usage = package_model._tuge_api_call_with_token_retry(do_usage)
                    update_vals = {}
                    if usage.get('dataTotal'):
                        try:
                            total_mb = float(usage['dataTotal'])
                            update_vals['total_volume'] = round(total_mb / 1024, 2)
                        except (TypeError, ValueError):
                            pass
                    if usage.get('dataUsage'):
                        try:
                            used_mb = float(usage['dataUsage'])
                            update_vals['used_volume'] = round(used_mb / 1024, 2)
                        except (TypeError, ValueError):
                            pass
                    if update_vals:
                        profile.write(update_vals)
                except TugeAPIError as e:
                    _logger.debug("途鸽流量查询跳过 profile=%s: %s", profile.iccid, e)

        if other_profiles:
            return super(EsimProfile, other_profiles).action_refresh_status()

    def action_cancel_profile(self) -> None:
        tuge_profiles = self.filtered(lambda p: p._is_tuge_profile())
        other_profiles = self - tuge_profiles

        package_model = self.env['esim.package']
        for profile in tuge_profiles:
            order = profile.order_id
            if not order or not order.api_order_no:
                raise UserError(_("无法终止：缺少途鸽订单号"))
            if profile.state == 'cancelled':
                raise UserError(_("该 eSIM 已取消"))

            def do_terminate(client):
                return client.terminate_order(order.api_order_no, profile.iccid)

            try:
                package_model._tuge_api_call_with_token_retry(do_terminate)
            except TugeAPIError as e:
                raise UserError(_("途鸽终止套餐失败: %s") % e.msg) from e

            profile.write({
                'state': 'cancelled',
                'esim_status': 'TERMINATION',
            })
            profile.message_post(body=_("途鸽套餐已终止"))

        if other_profiles:
            return super(EsimProfile, other_profiles).action_cancel_profile()

    def action_suspend(self) -> None:
        tuge_profiles = self.filtered(lambda p: p._is_tuge_profile())
        if tuge_profiles:
            raise UserError(_("途鸽 eSIM 不支持挂起操作"))
        return super().action_suspend()

    def action_revoke(self) -> None:
        tuge_profiles = self.filtered(lambda p: p._is_tuge_profile())
        if tuge_profiles:
            raise UserError(_("途鸽 eSIM 不支持吊销操作，可使用「终止套餐」"))
        return super().action_revoke()

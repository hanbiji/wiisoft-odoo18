# -*- coding: utf-8 -*-
import re
from datetime import datetime
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # 联系人类别
    mall_contact_type = fields.Selection([
        ('tenant', '租户'),
        ('operator', '运营公司(人)'),
        ('property_company', '物业公司'),
        ('intermediary', '中介'),
        ('landlord', '房东'),
    ], string='联系人类别')
    # 身份证号
    id_card = fields.Char('身份证号', tracking=True)
    # 身份证照片
    id_card_front = fields.Image('身份证正面', max_width=1920, max_height=1080, help='上传身份证人像面照片')
    id_card_back = fields.Image('身份证反面', max_width=1920, max_height=1080, help='上传身份证国徽面照片')

    @api.constrains('id_card')
    def _check_id_card(self):
        """验证中国身份证号码"""
        for record in self:
            if record.id_card:
                self._validate_chinese_id_card(record.id_card)

    def _validate_chinese_id_card(self, id_card):
        """
        验证18位中国身份证号码
        规则：
        1. 长度必须为18位
        2. 前17位必须为数字，第18位为数字或X
        3. 第7-14位为有效的出生日期（YYYYMMDD）
        4. 第18位校验码必须正确
        """
        # 去除空格并转大写
        id_card = id_card.strip().upper()
        
        # 1. 长度检查
        if len(id_card) != 18:
            raise ValidationError('身份证号码必须为18位。')
        
        # 2. 格式检查：前17位数字，第18位数字或X
        pattern = r'^\d{17}[\dX]$'
        if not re.match(pattern, id_card):
            raise ValidationError('身份证号码格式错误：前17位必须为数字，第18位为数字或X。')
        
        # 3. 出生日期有效性检查
        birth_date_str = id_card[6:14]
        try:
            birth_date = datetime.strptime(birth_date_str, '%Y%m%d')
            # 检查日期是否在合理范围内（1900年至今）
            if birth_date.year < 1900 or birth_date > datetime.now():
                raise ValidationError('身份证号码中的出生日期无效。')
        except ValueError:
            raise ValidationError('身份证号码中的出生日期格式错误。')
        
        # 4. 校验码验证
        # 加权因子
        weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        # 校验码对应值
        check_codes = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']
        
        # 计算前17位加权和
        weighted_sum = sum(int(id_card[i]) * weights[i] for i in range(17))
        # 取模得到校验码索引
        check_index = weighted_sum % 11
        # 获取期望的校验码
        expected_check_code = check_codes[check_index]
        
        # 比较校验码
        if id_card[17] != expected_check_code:
            raise ValidationError(
                f'身份证号码校验码错误，期望为 {expected_check_code}，实际为 {id_card[17]}。'
            )

    # 重命名字段以避免与标准type字段冲突
    industry_type = fields.Selection([
        ('retail', '零售'),
        ('catering', '餐饮'),
        ('service', '服务'),
        ('hostel', '酒店'),
        ('other_industry', '其他'),  # 改为other_industry避免与标准type字段的'other'选项冲突
    ], string='行业类型')

    leasing_contract_ids = fields.One2many('mall.leasing.contract', 'partner_id', string='关联租赁合同')
    communication_ids = fields.One2many('mall.communication', 'partner_id', string='沟通日志')
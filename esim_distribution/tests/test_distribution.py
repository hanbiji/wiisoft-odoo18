# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestEsimDistribution(TransactionCase):

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.basic_tier = cls.env.ref('esim_distribution.tier_basic')
        cls.silver_tier = cls.env.ref('esim_distribution.tier_silver')
        cls.silver_tier.write({
            'min_sales_amount': 1,
            'min_referral_count': 1,
        })
        cls.distributor_partner = cls.env['res.partner'].create({
            'name': 'Distributor Partner',
            'email': 'distributor@example.com',
        })
        cls.customer_partner = cls.env['res.partner'].create({
            'name': 'Referred Customer',
            'email': 'customer@example.com',
        })
        cls.package = cls.env['esim.package'].create({
            'package_code': 'DIST_TEST_PACKAGE',
            'name': 'Distribution Test Package',
            'sale_price': 100,
            'raw_price': 1000000,
            'package_type': 'BASE',
        })
        cls.distributor = cls.env['esim.distributor'].create({
            'partner_id': cls.distributor_partner.id,
            'state': 'approved',
            'tier_id': cls.basic_tier.id,
        })

    def test_bind_referrer_once(self) -> None:
        self.customer_partner._bind_referrer_once(self.distributor)
        self.assertEqual(self.customer_partner.referrer_distributor_id, self.distributor)

        other_partner = self.env['res.partner'].create({'name': 'Other Distributor'})
        other_distributor = self.env['esim.distributor'].create({
            'partner_id': other_partner.id,
            'state': 'approved',
            'tier_id': self.basic_tier.id,
        })
        self.customer_partner._bind_referrer_once(other_distributor)
        self.assertEqual(self.customer_partner.referrer_distributor_id, self.distributor)

    def test_order_done_generates_and_settles_commission(self) -> None:
        self.customer_partner._bind_referrer_once(self.distributor)
        order = self.env['esim.order'].create({
            'partner_id': self.customer_partner.id,
            'package_id': self.package.id,
            'quantity': 1,
        })

        order.write({'state': 'done'})

        commission = self.env['esim.commission'].search([('order_id', '=', order.id)])
        self.assertEqual(len(commission), 1)
        self.assertEqual(commission.state, 'pending')
        self.assertEqual(commission.commission_rate, self.basic_tier.commission_rate)
        self.assertEqual(commission.commission_amount, 5)
        self.assertEqual(commission.currency_id, order.currency_id)

        commission.action_settle()

        self.assertEqual(commission.state, 'settled')
        self.assertEqual(
            self.distributor_partner._esim_get_balance(order.currency_id),
            5,
        )
        self.assertEqual(self.distributor.tier_id, self.silver_tier)

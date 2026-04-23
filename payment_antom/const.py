# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Antom API 网关域名，按区域和环境区分
# See https://docs.antom.com/ac/ams/api_fund
GATEWAY_URLS = {
    'asia': {
        'production': 'https://open-sea-global.alipay.com',
        'sandbox': 'https://open-sea-global.alipay.com',
    },
    'na_us': {
        'production': 'https://open.antglobal-us.com',
        'sandbox': 'https://open.antglobal-us.com',
    },
    'na_other': {
        'production': 'https://open-na-global.alipay.com',
        'sandbox': 'https://open-na-global.alipay.com',
    },
    'europe': {
        'production': 'https://open-de-global.alipay.com',
        'sandbox': 'https://open-de-global.alipay.com',
    },
}

# API 路径
# 正式环境: /ams/api/v1/...
# Sandbox 环境: /ams/sandbox/api/v1/...
#
# createPaymentSession 用于 Hosted Checkout 场景（productScene=CHECKOUT_PAYMENT），
# 由 Antom 托管收银台，自动展示商户开通的全部支付方式供买家选择；
# 相比 /v1/payments/pay，本接口无需也不应提交 paymentMethod，
# 避免把具体支付方式与商户业务耦合。
API_PATH_CREATE_SESSION = '/v1/payments/createPaymentSession'
API_PATH_INQUIRY = '/v1/payments/inquiryPayment'

# Antom paymentStatus -> Odoo transaction state 映射
# See https://docs.antom.com/ac/ams/api
PAYMENT_STATUS_MAPPING = {
    'done': ('SUCCESS',),
    'pending': ('PROCESSING',),
    'cancel': ('CANCELLED',),
    'error': ('FAIL',),
}

# Antom Cashier Payment 支持的币种
# See https://docs.antom.com/ac/cashierpay/overview
SUPPORTED_CURRENCIES = (
    'USD', 'EUR', 'GBP', 'SGD', 'HKD', 'JPY', 'KRW',
    'AUD', 'NZD', 'CAD', 'CHF', 'SEK', 'NOK', 'DKK',
    'THB', 'PHP', 'MYR', 'IDR', 'INR', 'PKR', 'BDT',
    'BRL', 'MXN', 'CLP', 'COP', 'PEN', 'ARS',
    'TWD', 'VND', 'MMK', 'CNY', 'AED', 'SAR', 'QAR',
    'KWD', 'BHD', 'OMR', 'EGP', 'ZAR', 'TRY', 'PLN',
    'CZK', 'HUF', 'RON', 'BGN', 'HRK', 'RUB',
)

# 安装时默认激活的支付方式
DEFAULT_PAYMENT_METHOD_CODES = {
    'antom',
}

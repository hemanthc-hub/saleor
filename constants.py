import os
from dotenv import load_dotenv
load_dotenv()

api_url = os.environ.get("GRAPHQL_API_URL", "https://www.hegmakart.com/graphql/")
saleor_account_redirect_url = os.environ.get(
    "SALEOR_ACCOUNT_REDIRECT_URL", "http://localhost:3000"
)
saleor_channel = os.environ.get("SALEOR_CHANNEL", "default-channel").strip() or "default-channel"
hegma_auth_token = os.environ.get("HEGMA_AUTH_TOKEN", "")
hegma_password = os.environ.get("HEGMA_PASSWORD", "")
hegma_enc_password = os.environ.get("HEGMA_ENC_PASSWORD", "")

razorpay_url = os.environ.get("RAZORPAY_URL", "https://api.razorpay.com/v1/orders")
razorpay_auth_token = os.environ.get("RAZORPAY_AUTH_TOKEN", "")
razorpay_auth_key = os.environ.get("RAZORPAY_KEY_ID", "")
razorpay_auth_value = os.environ.get("RAZORPAY_KEY_SECRET", "")

msg91_auth_key = os.environ.get("MSG91_AUTH_KEY", "")
msg91OtpDleId = os.environ.get("MSG91_OTP_DLE_ID", "1307165234397419583")
msg91OrderDleId = os.environ.get("MSG91_ORDER_DLE_ID", "1307165234361126499")
msg91OrderCodDleId = os.environ.get("MSG91_ORDER_COD_DLE_ID", "1307165951829477290")
msg91CancelDleId = os.environ.get("MSG91_CANCEL_DLE_ID", "1307171169100455845")

keyReplaceOtp = '{otp}'
keyReplaceOrderNo = '{order_no}'
keyReplaceOrderDate = '{order_date}'
keyReplaceOrderTotalPrice = '{order_total_price}'
keyReplaceName = '{name}'
keyReplaceAddress = '{address}'
keyReplaceCountry = '{country}'
keyReplaceProductUrl = '{product_url}'
keyReplaceProductName = '{product_name}'
keyReplaceProductQuantity = '{product_quantity}'
keyReplaceProductPrice = '{product_price}'
keyReplaceTotalQuantity = '{total_quantity}'
keyReplaceSubTotalPrice = '{subtotal_price}'
keyReplaceShippingPrice = '{shipping_price}'
keyReplaceDiscountedPrice = '{discount_price}'
keyReplaceWeightedPrice = '{weighted_price}'
keyReplaceRemark = '{remark}'

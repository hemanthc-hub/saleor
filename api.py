from dotenv import load_dotenv
load_dotenv()  # loads /Hegma/backend/.env into os.environ before anything else
import flask

import razorpay
from flask import request, jsonify
from flask_cors import CORS, cross_origin
from flask_mail import Mail, Message
from random import randint
from datetime import datetime, timezone
from flask import copy_current_request_context
import os
import smtplib
import ssl
import json
import time
import uuid
# third-party HTTP client library
import requests
import db
import emailConstants
import constants
import hmac
import hashlib
import threading
import urllib.parse
from logger import get_logger, set_correlation_id

log = get_logger()

app = flask.Flask(__name__)
app.url_map.strict_slashes = False
mail = Mail(app)  # instantiate the mail class
cors = CORS(app, allow_headers="*")
app.config["DEBUG"] = False


# Register Admin Ops Microservices
from admin_ops.routes.orders import orders_bp
from admin_ops.routes.catalog import catalog_bp
from admin_ops.routes.dashboard import dashboard_bp
from admin_ops.database import db as admin_db

DB_USER = os.environ.get("DB_USER_NAME", "postgres")
DB_PASS = os.environ.get("DB_PASSWORD", "admin")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "dev_hegma")

if DB_PASS:
    app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
admin_db.init_app(app)

# Ensure tables are created
with app.app_context():
    admin_db.create_all()

app.register_blueprint(orders_bp, url_prefix="/api/admin")
app.register_blueprint(dashboard_bp, url_prefix="/api/admin")
app.register_blueprint(catalog_bp, url_prefix="/api/admin")

from admin_ops.routes.reviews import reviews_bp
app.register_blueprint(reviews_bp, url_prefix="/api")

from admin_ops.routes.audit import audit_bp
app.register_blueprint(audit_bp, url_prefix="/api/admin")

from admin_ops.routes.related import related_bp
app.register_blueprint(related_bp, url_prefix="/api/admin")

from admin_ops.routes.emails import emails_bp
app.register_blueprint(emails_bp, url_prefix="/api")

from admin_ops.routes.delivery import delivery_bp
app.register_blueprint(delivery_bp, url_prefix="/api")


# configuration of mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = 'no-reply@hegmakart.com'
app.config['MAIL_PASSWORD'] = 'bkzcidvrvctmfxez'
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
mail = Mail(app)

# ── Correlation ID + Request Lifecycle Middleware ──────────────────────────────

@app.before_request
def _before_request():
    """Extract or generate a Correlation ID and record request start time."""
    cid = request.headers.get("X-Correlation-ID") or f"req-{uuid.uuid4().hex[:12]}"
    set_correlation_id(cid)
    flask.g.start_time = time.monotonic()
    flask.g.correlation_id = cid
    log.info(
        f"{request.method} {request.path} started",
        event="request_started",
        http_method=request.method,
        path=request.path,
        remote_addr=request.remote_addr,
    )


@app.after_request
def _after_request(response):
    """Log every completed HTTP request with method, path, status, and duration."""
    duration_ms = round((time.monotonic() - flask.g.start_time) * 1000, 2)
    level = "WARNING" if response.status_code >= 400 else "INFO"
    log.log(
        level,
        f"{request.method} {request.path} → {response.status_code} ({duration_ms}ms)",
        event="request_completed",
        http_method=request.method,
        path=request.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    # Echo the Correlation ID back so callers can trace their request
    response.headers["X-Correlation-ID"] = flask.g.correlation_id
    return response


@app.errorhandler(Exception)
def _handle_exception(e):
    """Log unhandled route exceptions to structured logger with traceback."""
    log.exception(
        f"Unhandled exception during {request.method} {request.path}: {e}",
        event="unhandled_exception",
        http_method=request.method,
        path=request.path,
    )
    return jsonify({"error": "Internal Server Error", "message": str(e)}), 500


# client = razorpay.Client(auth=(constants.razorpay_auth_key, constants.razorpay_auth_value))


@app.route('/', methods=['GET'])
def home():
    return '''<h1>Distant Reading Archive</h1>
<p>A prototype API for distant reading of science fiction novels.</p>'''


# Call to send email
@app.route('/api/v1/bulkEnquiry', methods=['POST'])
@cross_origin()
def bulkEnquiry():

	record = json.loads(request.data)
	message = 'Hello,\n\nYou have received a new Bulk Enquiry as per below details -\n'
	message += 'Name: ' + record["name"]
	message += '\nEmail: ' + record["email"]
	message += '\nPhone: ' + record["phone"]
	message += '\nPin: ' + record["pinCode"]
	message += '\nProduct: ' + record["productName"]
	message += '\nExpected Price: ' + record["price"]
	message += '\nQuantity: ' + record["quantity"]
	message += '\n\nThanks'

	subject = 'New Bulk Enquiry Received for ' + record["productName"]
	sendEmail(message, subject, ['order@hegmakart.com'])
	return sendHtmlEmail(emailConstants.adminMessage.replace(constants.keyReplaceProductName, record["productName"]).replace(constants.keyReplaceProductQuantity, record["quantity"]).replace(constants.keyReplaceProductPrice, record["price"]), 'Thank you for your enquiry on Hegmakart', [record["email"]])

# Call to send otp sms
@app.route('/api/v1/newsletterSubscription', methods=['POST'])
@cross_origin()
def newsletterSubscription():
	msg = 'success'
	record = request.get_json(silent=True) or json.loads(request.data or '{}')
	emailId = record.get("email_id")
	if not emailId:
		return "email_id is required", 400
	dateTime = datetime.now()
	db.insertNewsLetterSubscription(emailId,dateTime)
	return msg

# Call to send otp sms
@app.route('/api/v1/sendOTP', methods=['POST'])
@cross_origin()
def sendOtp():
	msg = ''
	record = json.loads(request.data)
	if record["mobile"] == '':
		log.warning(
			"OTP request rejected — empty mobile",
			event="otp_request_invalid",
			reason="empty_mobile",
		)
		return msg

	otp = str(random_with_N_digits(6))
	db.insertMobileOtp(record["mobile"], otp)
	message = 'Dear user, Your Login OTP is ' + otp + ' ~ Hegmakart'
	if len(record["mobile"]) == 10:
		log.info(
			"Dispatching OTP via SMS",
			event="otp_dispatch_sms",
			user_identifier=record["mobile"],
			channel="sms",
		)
		try:
			sendSMS(record["mobile"], message, constants.msg91OtpDleId)
			log.info(
				"OTP SMS dispatched successfully",
				event="otp_dispatch_success",
				user_identifier=record["mobile"],
				channel="sms",
			)
		except Exception as e:
			log.warning(
				"OTP SMS delivery failed",
				event="otp_delivery_failed",
				user_identifier=record["mobile"],
				channel="sms",
				provider_response=str(e),
			)
	else:
		log.info(
			"Dispatching OTP via email",
			event="otp_dispatch_email",
			user_identifier=record["mobile"],
			channel="email",
		)
		try:
			emailMessage = emailConstants.emailHead + emailConstants.emailLoginBody.replace(constants.keyReplaceOtp, otp) + emailConstants.emailFooter
			sendHtmlEmail(emailMessage, "Login OTP", [record["mobile"]])
			log.info(
				"OTP email dispatched successfully",
				event="otp_dispatch_success",
				user_identifier=record["mobile"],
				channel="email",
			)
		except Exception as e:
			log.warning(
				"OTP email delivery failed",
				event="otp_delivery_failed",
				user_identifier=record["mobile"],
				channel="email",
				provider_response=str(e),
			)

	msg = 'sent'
	return msg

# Call to otp verify sms
@app.route('/api/v1/verifyOTP', methods=['POST'])
@cross_origin()
def verifyOtp():

	record = json.loads(request.data)
	mobile = record["mobile"]
	otp = record["otp"]
	if record["mobile"] == '' or record["otp"] == '':
		info = {
			"field": '1',
			"message": "Please enter valid Parameters."
		}
		return jsonify(info)  # returning a JSON response

	count = db.verifyMobileOtp(mobile, otp)
	if count == 0:
		log.warning(
			"OTP verification failed — invalid OTP",
			event="otp_verify_failed",
			user_identifier=mobile,
			reason="invalid_otp",
		)
		info = {
			"field": '1',
			"message": "Please enter valid OTP."
		}
		return jsonify(info)

	log.info(
		"OTP verified successfully",
		event="otp_verify_success",
		user_identifier=mobile,
	)
	api_url = constants.api_url
	log.debug("GraphQL API URL", event="graphql_url", api_url=api_url)
	if len(mobile) == 10:
		email = mobile + '@hegmakart.com'
		record1 = db.accountUserData(mobile)
	else:
		email = mobile
		record1 = db.accountUserEmailData(mobile)

	if not record1:
		log.info(
			"Registering new user via GraphQL",
			event="user_register_attempt",
			user_identifier=mobile,
			email=email,
		)
		resData = """
		mutation RegisterAccount($input: AccountRegisterInput!) {
			accountRegister(input: $input) {
				errors { field message }
				user { email }
			}
		}
		"""
		registration_input = {
			'email': email,
			'password': constants.hegma_password,
			'redirectUrl': constants.saleor_account_redirect_url,
		}
		registration_input['channel'] = (
			constants.saleor_channel
			or record.get('channel')
			or 'default-channel'
		)
		create_row_data = {
			'query': resData,
			'variables': {'input': registration_input}
		}
		response = requests.post(
            api_url, json=create_row_data,
            headers={'Content-Type': 'application/json'}
        )
		res = response.json()
		registration = (res.get("data") or {}).get("accountRegister")
		registration_errors = (
			registration.get("errors", []) if registration
			else res.get("errors", [])
		)
		if registration and not registration_errors:
			if len(mobile) == 10:
				db.updateUserMobile(mobile, email)
			else:
				db.activateUserEmail(email)
			log.info("New user registered", event="user_register_success", email=email)
		else:
			first_error = registration_errors[0] if registration_errors else {}
			err_msg = first_error.get("message", "Saleor did not return registration data.")
			err_field = first_error.get("field")
			is_already_registered = (
				first_error.get("code") == "UNIQUE"
				or "already exists" in err_msg.lower()
				or "already registered" in err_msg.lower()
			)
			if is_already_registered:
				log.info("User already exists in Saleor, proceeding with authentication", email=email)
				if len(mobile) == 10:
					db.updateUserPassword(mobile)
					db.updateUserMobile(mobile, email)
				else:
					db.updateUserEmailPassword(email, constants.hegma_enc_password)
					db.activateUserEmail(email)
			else:
				log.error(
					"User registration failed",
					event="user_register_failed",
					user_identifier=mobile,
					error=err_msg,
					error_field=err_field,
				)
				info = {
					"field": '1',
					"message": err_msg,
					"error_field": err_field,
				}
				return jsonify(info)
	else:
		email = record1[0]
		if len(mobile) == 10:
			db.updateUserPassword(mobile)
			db.updateUserMobile(mobile, email)
		else:
			db.updateUserEmailPassword(email, constants.hegma_enc_password)
			db.activateUserEmail(email)

	log.info(
		"Requesting auth token from GraphQL",
		event="auth_token_request",
		user_identifier=mobile,
		email=email,
	)
	resData = "mutation TokenAuth {tokenCreate(email: \"" + email + "\", password: \"" + constants.hegma_password + "\") {errors {field,message},token,refreshToken,user {id,firstName,lastName,email}}}"
	create_row_data = {'query': resData}
	response = requests.post(
        api_url, json=create_row_data,
        headers={'Content-Type': 'application/json'}
    )
	res = json.loads(response.text)
	token_create = (res.get("data") or {}).get("tokenCreate") or {}
	token_errors = token_create.get("errors", [])
	if token_create.get("token") and len(token_errors) == 0:
		db.updateMobileOTPStatus(mobile, otp)
		log.info(
			"Auth token issued successfully",
			event="auth_token_success",
			user_identifier=mobile,
			email=email,
			user_id=token_create["user"]["id"],
		)
		info = {
			"api_status": 'true',
			"refreshToken": token_create["refreshToken"],
			"token": token_create["token"],
			"user": {
				"id": token_create["user"]["id"],
				"firstName": token_create["user"]["firstName"],
				"lastName": token_create["user"]["lastName"],
				"email": token_create["user"]["email"]
			}
		}
		db.updateUserEmailPassword(email, "")
		return jsonify(info)
	else:
		err_msg = (
			token_errors[0].get("message") if token_errors
			else (res.get("errors", [{}])[0].get("message") if res.get("errors") else "Authentication failed.")
		)
		log.warning(
			"Auth token creation failed",
			event="auth_token_failed",
			user_identifier=mobile,
			email=email,
			error=err_msg,
		)
		info = {
			"field": '1',
			"message": err_msg,
		}
		return jsonify(info)

# Call to razor pay initialization
@app.route('/api/v1/razorpayInit', methods=['POST'])
@cross_origin()
def razorpayInit():
	razorPayId = ''
	record = json.loads(request.data)
	checkoutToken = record["checkout_token"]
	if checkoutToken == '':
		log.warning(
			"razorpayInit rejected — empty checkout token",
			event="payment_init_invalid",
			reason="empty_checkout_token",
		)
		return razorPayId

	log.info(
		"Initiating Razorpay payment order",
		event="payment_init_started",
		checkout_token=checkoutToken,
	)
	api_url = constants.api_url
	resData = '{checkout(token: \"' + checkoutToken + \
	                     '\") {id,totalPrice{gross{amount}}}}'
	create_row_data = {'query': resData}
	response = requests.post(
        api_url, json=create_row_data,
        headers={'Content-Type': 'application/json',
            'Authorization': constants.hegma_auth_token}
    )
	res = json.loads(response.text)
	log.debug("Checkout GraphQL response received", event="checkout_fetched", checkout_token=checkoutToken)
	if res["data"]["checkout"]["id"] != '':
		checkoutId = res["data"]["checkout"]["id"]
		amount = res["data"]["checkout"]["totalPrice"]["gross"]["amount"]
		create_row_data = {
			"amount": amount * 100,
			"currency": 'INR',
			"receipt": checkoutToken
		}
		api_url = constants.razorpay_url
		response = requests.post(
			api_url, json=create_row_data,
			headers={'Content-Type': 'application/json',
			    'Authorization': constants.razorpay_auth_token}
		)
		res = json.loads(response.text)
		razorPayId = res["id"]
		log.info(
			"Razorpay order created",
			event="payment_order_created",
			razorpay_order_id=razorPayId,
			amount_inr=amount,
			checkout_token=checkoutToken,
		)
		api_url = constants.api_url
		resData = 'mutation {updatePrivateMetadata(id:\"' + checkoutId + \
		                                           '\", input:[{key:\"razor_order\",value:\"' + \
		                                               razorPayId + \
		                                                   '\"}]) {errors{message}}}'
		create_row_data = {'query': resData}
		response = requests.post(
			api_url, json=create_row_data,
			headers={'Content-Type': 'application/json',
			    'Authorization': constants.hegma_auth_token}
		)
		res = json.loads(response.text)
		print(res)

	return razorPayId

# Call to complete razor pay payment
@app.route('/api/v1/razorpayComplete', methods=['POST'])
@cross_origin()
def razorpayComplete():
	msg = ''
	record = json.loads(request.data)
	checkoutToken = record["checkout_token"]
	if checkoutToken == '' or record["razorpay_payment_id"] == '' or record["razorpay_order_id"] == '' or record["razorpay_signature"] == '':
		return msg

	api_url = constants.api_url
	resData = '{checkout(token: \"' + checkoutToken + \
	                     '\") {id,privateMetadata{key,value},metadata{key,value}}}'
	create_row_data = {'query': resData}
	response = requests.post(
        api_url, json=create_row_data,
        headers={'Content-Type': 'application/json',
            'Authorization': constants.hegma_auth_token}
    )
	res = json.loads(response.text)
	print(res)
	if res["data"]["checkout"]["id"] != '':
		checkoutId = res["data"]["checkout"]["id"]
		metaArr = res["data"]["checkout"]["privateMetadata"]
		for item in metaArr:
			if item["key"] == 'razor_order':
				razor_order = item["value"]

		razorPaymentId = record["razorpay_payment_id"]
		razorOrderId = record["razorpay_order_id"]
		razorSignature = record["razorpay_signature"]

		message = razor_order + "|" + razorPaymentId
		generated_signature = hmac.new(bytes(constants.razorpay_auth_value, 'latin-1'),
		                               msg=bytes(message, 'latin-1'), digestmod=hashlib.sha256).hexdigest()

		if (generated_signature == razorSignature):
			resData = 'mutation {orderCreateFromCheckout(id:\"' + checkoutId + '\") 		{order{id,number,userEmail,user{id},created,total{gross{amount}},shippingAddress{firstName,lastName,streetAddress1,streetAddress2,city,cityArea,country{country},postalCode,phone},lines{variantName,weightedShipping,productName,quantity,thumbnail{url},unitPrice{gross{amount}}},shippingPrice{gross{amount}},discounts{amount{amount}},subtotal{gross{amount}}},errors{code,message}}}'
			create_row_data = {'query': resData}
			response = requests.post(
				api_url, json=create_row_data,
				headers={'Content-Type': 'application/json',
				    'Authorization': constants.hegma_auth_token}
			)
			res = json.loads(response.text)
			print(res)
			if len(res["data"]["orderCreateFromCheckout"]["errors"]) == 0:
				orderId = res["data"]["orderCreateFromCheckout"]["order"]["id"]
				orderNo = res["data"]["orderCreateFromCheckout"]["order"]["number"]
				orderDate = res["data"]["orderCreateFromCheckout"]["order"]["created"][0:10]
				name = res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["firstName"] + \
				    " " + \
				        res["data"][	"orderCreateFromCheckout"]["order"]["shippingAddress"]["lastName"]
				address = res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["streetAddress1"] + \
				    " " + \
				        res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["streetAddress2"]
				country = res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["city"] + ", " + \
				    res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["country"]["country"] + \
				        " " + \
				            res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["postalCode"]
				lines = res["data"]["orderCreateFromCheckout"]["order"]["lines"]
				productData = ''
				totalQuantity = 0
				weightedShipping = 0
				shippingamount = res["data"]["orderCreateFromCheckout"]["order"]["shippingPrice"]["gross"]["amount"]
				subtotalamount = res["data"]["orderCreateFromCheckout"]["order"]["subtotal"]["gross"]["amount"]
				discountamount = '0'
				mobile = res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["phone"]
				mobile = mobile[3:len(mobile)]
				email = res["data"]["orderCreateFromCheckout"]["order"]["userEmail"]
				amount = res["data"]["orderCreateFromCheckout"]["order"]["total"]["gross"]["amount"]
				msg = 'Dear User, your order with the order ID ' + orderNo + \
				    ' has been successfully placed and the payment of Rs ' + \
				        str(amount) + ' has been received. ~ Hegmakart'
				# bccrecipients = ['anuj@qmmtech.com']
				recipients = [email,'order@hegmakart.com']
				sendSMS(mobile, msg, constants.msg91OrderDleId)
				emailMessage = emailConstants.emailHead + emailConstants.emailOrderBody1 + emailConstants.emailOrderBodySummary.replace(constants.keyReplaceOrderNo, orderNo).replace(constants.keyReplaceOrderDate, orderDate).replace(constants.keyReplaceOrderTotalPrice, str(
				    amount)) + emailConstants.emailOrderBodyShippingAddress.replace(constants.keyReplaceName, name).replace(constants.keyReplaceAddress, address).replace(constants.keyReplaceCountry, country) + emailConstants.emailOrderBodyProductHeader
				for line in lines:
					amt = line["unitPrice"]["gross"]["amount"]
					wgtShippPrc = None
					try:
						wgtShippPrc = line["weightedShipping"]
					except:
						wgtShippPrc = ''
					if(wgtShippPrc is not None):
						wgtamt = float(wgtShippPrc) * line["quantity"]
						amt = amt - float(wgtShippPrc)
						weightedShipping = weightedShipping + wgtamt

					productData = productData + emailConstants.emailOrderBodyProductData.replace(constants.keyReplaceProductUrl, line["thumbnail"]["url"]).replace(
					    constants.keyReplaceProductName, line["variantName"]).replace(constants.keyReplaceProductQuantity, str(line["quantity"])).replace(constants.keyReplaceProductPrice, str('%.2f' % amt))
					totalQuantity = totalQuantity + line["quantity"]

				subtotalamount =  str('%.2f' % (float(subtotalamount) - weightedShipping)) 
				emailMessage = emailMessage + productData
				emailMessage = emailMessage + emailConstants.emailOrderBodyProductTotal.replace(constants.keyReplaceTotalQuantity, str(totalQuantity)).replace(constants.keyReplaceSubTotalPrice, str(subtotalamount)).replace(constants.keyReplaceShippingPrice, str(shippingamount)).replace(constants.keyReplaceWeightedPrice, str(weightedShipping)).replace(constants.keyReplaceDiscountedPrice, str(discountamount)).replace(constants.keyReplaceOrderTotalPrice, str(amount)) + emailConstants.emailFooter
				sendHtmlEmail(emailMessage, 'Order Placed Successfully', recipients)
				reference = razorPaymentId + "|" + razorOrderId + "|" + razorSignature
				resData = 'mutation {orderMarkAsPaid(id: \"' + orderId + '\", transactionReference: \"' + reference + '\") {errors{message}}}'
				create_row_data = {'query': resData}
				response = requests.post(
					api_url, json=create_row_data,
					headers={'Content-Type': 'application/json',
				    'Authorization': constants.hegma_auth_token}
				)
				res = json.loads(response.text)
				print(res)
				msg = 'Success'
		
	return msg
	
# Call to complete razor pay payment
@app.route('/api/v1/razorpayCompleteCod', methods=['POST'])
@cross_origin()
def razorpayCompleteCod():
	msg = ''
	record = json.loads(request.data)
	checkoutToken = record["checkout_token"]
	if checkoutToken == '':
		return msg

	api_url = constants.api_url
	resData = '{checkout(token: \"' + checkoutToken + \
	                     '\") {id,privateMetadata{key,value},metadata{key,value}}}'
	create_row_data = {'query': resData}
	response = requests.post(
        api_url, json=create_row_data,
        headers={'Content-Type': 'application/json',
            'Authorization': constants.hegma_auth_token}
    )
	res = json.loads(response.text)
	print(res)
	if res["data"]["checkout"]["id"] != '':
		checkoutId = res["data"]["checkout"]["id"]
		resData = 'mutation {orderCreateFromCheckout(id:\"' + checkoutId + '\") 		{order{id,number,userEmail,user{id},created,total{gross{amount}},shippingAddress{firstName,lastName,streetAddress1,streetAddress2,city,cityArea,country{country},postalCode,phone},lines{variantName,weightedShipping,productName,quantity,thumbnail{url},unitPrice{gross{amount}}},shippingPrice{gross{amount}},discounts{amount{amount}},subtotal{gross{amount}}},errors{code,message}}}'
		create_row_data = {'query': resData}
		response = requests.post(
			api_url, json=create_row_data,
			headers={'Content-Type': 'application/json',
				'Authorization': constants.hegma_auth_token}
		)
		res = json.loads(response.text)
		print(res)
		if len(res["data"]["orderCreateFromCheckout"]["errors"]) == 0:
			orderNo = res["data"]["orderCreateFromCheckout"]["order"]["number"]
			orderDate = res["data"]["orderCreateFromCheckout"]["order"]["created"][0:10]
			name = res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["firstName"] + \
				" " + \
				    res["data"][	"orderCreateFromCheckout"]["order"]["shippingAddress"]["lastName"]
			address = res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["streetAddress1"] + \
				" " + \
				    res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["streetAddress2"]
			country = res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["city"] + ", " + \
				res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["country"]["country"] + \
				    " " + \
				        res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["postalCode"]
			lines = res["data"]["orderCreateFromCheckout"]["order"]["lines"]
			productData = ''
			totalQuantity = 0
			weightedShipping = 0
			shippingamount = res["data"]["orderCreateFromCheckout"]["order"]["shippingPrice"]["gross"]["amount"]
			subtotalamount = res["data"]["orderCreateFromCheckout"]["order"]["subtotal"]["gross"]["amount"]
			discountamount = '0'
			mobile = res["data"]["orderCreateFromCheckout"]["order"]["shippingAddress"]["phone"]
			mobile = mobile[3:len(mobile)]
			email = res["data"]["orderCreateFromCheckout"]["order"]["userEmail"]
			amount = res["data"]["orderCreateFromCheckout"]["order"]["total"]["gross"]["amount"]
			msg = 'Dear User, your order with the order ID ' + orderNo + ' has been successfully placed and the payment of Rs ' + str(amount) + ' should be paid on delivery ~ Hegmakart'
			# bccrecipients = ['anuj@qmmtech.com']
			recipients = [email,'order@hegmakart.com']
			sendSMS(mobile, msg, constants.msg91OrderCodDleId)
			emailMessage = emailConstants.emailHead + emailConstants.emailOrderBody1 + emailConstants.emailOrderBodySummary.replace(constants.keyReplaceOrderNo, orderNo).replace(constants.keyReplaceOrderDate, orderDate).replace(constants.keyReplaceOrderTotalPrice, str(amount)) + emailConstants.emailOrderBodyShippingAddress.replace(constants.keyReplaceName, name).replace(constants.keyReplaceAddress, address).replace(constants.keyReplaceCountry, country) + emailConstants.emailOrderBodyProductHeader
			for line in lines:
				amt = line["unitPrice"]["gross"]["amount"]
				wgtShippPrc = None
				try:
					wgtShippPrc = line["weightedShipping"]
				except:
					wgtShippPrc = ''
				if(wgtShippPrc is not None):
					wgtamt = float(wgtShippPrc) * line["quantity"]
					amt = amt - float(wgtShippPrc)
					weightedShipping = weightedShipping + wgtamt

				productData = productData + emailConstants.emailOrderBodyProductData.replace(constants.keyReplaceProductUrl, line["thumbnail"]["url"]).replace(constants.keyReplaceProductName, line["variantName"]).replace(constants.keyReplaceProductQuantity, str(line["quantity"])).replace(constants.keyReplaceProductPrice, str('%.2f' % amt))
				totalQuantity = totalQuantity + line["quantity"]

			subtotalamount =  str('%.2f' % (float(subtotalamount) - weightedShipping)) 
			emailMessage = emailMessage + productData
			emailMessage = emailMessage + emailConstants.emailOrderBodyProductTotal.replace(constants.keyReplaceTotalQuantity, str(totalQuantity)).replace(constants.keyReplaceSubTotalPrice, str(subtotalamount)).replace(constants.keyReplaceShippingPrice, str(shippingamount)).replace(constants.keyReplaceWeightedPrice, str(weightedShipping)).replace(constants.keyReplaceDiscountedPrice, str(discountamount)).replace(constants.keyReplaceOrderTotalPrice, str(amount)) + emailConstants.emailFooter
			sendHtmlEmail(emailMessage, 'Order Placed Successfully', recipients)
			msg = 'Success'
		
	return msg
	
# Call to update order status
@app.route('/api/v1/updateOrder', methods=['POST'])
@cross_origin()
def updateOrder():
	msg = ''
	try:
		record = json.loads(request.data)
		token = record.get("token", "")
		status = record.get("status", "")
		orderId = record.get("order_id", "")
		db.updateOrderStatus(orderId, status)
		msg = 'success'
		log.info(f"Order {orderId} updated to status {status}", event="update_order_db_success", order_id=orderId, status=status)
		api_url = constants.api_url
		resData = '{me{id,email,isStaff}}'
		create_row_data = {'query': resData}
		try:
			response = requests.post(
				api_url, json=create_row_data,
				headers={'Content-Type': 'application/json',
				'Authorization': 'JWT ' + token},
				timeout=10
			)
			res = json.loads(response.text)
			log.debug(f"GraphQL staff verification response: {res}", event="graphql_staff_check")
			if res.get("data") and res["data"].get("me") is not None:
				if res["data"]["me"].get("isStaff"):
					log.info(f"Verified staff email: {res['data']['me']['email']}", event="staff_verification")
					db.updateOrderStatus(orderId, status)
					msg = 'success'
		except requests.exceptions.RequestException as req_err:
			log.error(f"HTTP error during GraphQL staff verification request: {req_err}", event="update_order_graphql_error")
		except Exception as parse_err:
			log.error(f"Error processing GraphQL response: {parse_err}", event="update_order_parse_error")
	except Exception as e:
		log.error(f"Error in updateOrder: {e}", event="update_order_error")
		msg = 'error'
			
	return msg
	
# Call to update line order status
@app.route('/api/v1/updateLineOrder', methods=['POST'])
@cross_origin()
def updateLineOrder():
	msg = ''
	try:
		record = json.loads(request.data)
		token = record.get("token", "")
		status = record.get("status", "")
		orderLineId = record.get("order_line_id", "")
		orderId = record.get("order_id", "")
		dateTime = datetime.now()
		db.updateOrderLineStatus(orderLineId, status, orderId, dateTime)
		msg = 'success'
		log.info(f"Order line {orderLineId} (Order {orderId}) updated to status {status}", event="update_line_order_db_success", order_line_id=orderLineId, order_id=orderId, status=status)
		
		try:
			send_shipment_notification_email(orderId, orderLineId)
		except Exception as notif_err:
			log.error(f"Failed to send shipment notification email: {notif_err}", event="shipment_notification_error", order_id=orderId, order_line_id=orderLineId)
	except Exception as e:
		log.error(f"Error in updateLineOrder: {e}", event="update_line_order_error")
		msg = 'error'
			
	return msg
	
# Call to update product review
@app.route('/api/v1/updateProductReview', methods=['POST'])
@cross_origin()
def updateProductReview():
	msg = 'success'
	record = json.loads(request.data)
	productName = record["product_name"]
	rating = record["rating"]
	review = record["review"]
	orderNumber = record["order_number"]
	reviewTime = datetime.now()
	data = db.getOrderData(orderNumber,productName)
	productId = data[2]
	userId = data[1]
	orderId = data[0]
	db.insertProductReview(productId,rating,userId,review,orderId,reviewTime)
	avgRating = db.getProductData(productId)
	db.updateProductRating(productId, avgRating)		
	return msg

# Call to order review
@app.route('/api/v1/getOrderReviewData', methods=['POST'])
@cross_origin()
def getOrderReviewData():
	record = json.loads(request.data)
	orderNumber = record["order_number"]
	data = db.getOrderReviewData(orderNumber)	
	formatted_data = [{'rating': row[0], 'review': row[1], 'productName': row[2]} for row in data]
	return jsonify(formatted_data)

# Call to product review
@app.route('/api/v1/getProductReviewData', methods=['POST'])
@cross_origin()
def getProductReviewData():
	record = json.loads(request.data)
	slug = record["product_slug"]
	data = db.getProductReviewData(slug)
	formatted_data = [{'rating': row[0], 'review': row[1], 'reviewTime': row[2], 'firstName': row[3], 'lastName': row[4]} for row in data]		
	return formatted_data

# Call to product brand list
@app.route('/api/v1/productBrandList', methods=['POST'])
@cross_origin()
def productBrandList():
	record = json.loads(request.data)
	brandName = record["brand_name"]
	data = db.getProductBrandData(brandName)	
	formatted_data = [{'name': row[0]} for row in data]	
	return formatted_data

# Call to apply bulk discounts
@app.route('/api/v1/bulkDiscounts', methods=['POST'])
@cross_origin()
def bulkDiscounts():
	msg = ''
	record = json.loads(request.data)
	variantId = record["variant_id"]
	if variantId == '':
		return msg
		
	api_url = constants.api_url
	resData = '{vouchers(first:50,filter:{metadata:{key:\"variant\",value:\"' + variantId + '\"}}){edges{node{id,code,minCheckoutItemsQuantity,channelListings{channel{name},discountValue},discountValueType}}}}'
	create_row_data = {'query': resData}
	response = requests.post(
        api_url, json=create_row_data,
        headers={'Content-Type': 'application/json',
            'Authorization': constants.hegma_auth_token}
    )
	res = json.loads(response.text)
	print(res)		
	return res
	
# Call to get product details
@app.route('/api/v1/productDetails', methods=['POST'])
@cross_origin()
def productDetails():
	msg = ''
	record = json.loads(request.data)
	productId = record["product_id"]
	if productId == '':
		return msg
		
	api_url = constants.api_url
	resData = '{product(id: \"' + productId + '\", channel: \"default-channel\") {id,purchaseNote,name,description,seoDescription,rating,productType{id,hasVariants},category{name,id,slug,level,parent{name}},thumbnail{url},attributes{attribute{id,name},values{id,name,file{url}}},pricing{priceRangeUndiscounted{start{net{amount}}},priceRange{start{net{amount},gross{amount}}}},media{url},variants{id,weightedShipping,originalPrice,name,media{url},quantityAvailable,pricing{price{net{amount}},priceUndiscounted{net{amount}}}}}}'
	create_row_data = {'query': resData}
	response = requests.post(
        api_url, json=create_row_data,
        headers={'Content-Type': 'application/json',
            'Authorization': constants.hegma_auth_token}
    )
	res = json.loads(response.text)
	print(res)	
	variantArr = res["data"]["product"]["variants"]
	for item in variantArr:
		resData = '{vouchers(first:50,filter:{metadata:{key:\"variant\",value:\"' + item["id"] + '\"}}){edges{node{id,code,minCheckoutItemsQuantity,channelListings{channel{name},discountValue},discountValueType}}}}'
		create_row_data = {'query': resData}
		response = requests.post(
			api_url, json=create_row_data,
			headers={'Content-Type': 'application/json',
				'Authorization': constants.hegma_auth_token}
		)
		res1 = json.loads(response.text)
		print(res1)
		arr1 = res1["data"]["vouchers"]["edges"]
		vouArr = []
		for item1 in arr1:
			voucherText = 'Buy ' + str(item1["node"]["minCheckoutItemsQuantity"]) + ' or above and save '
			discountValue = 0
			arr2 = item1["node"]["channelListings"]
			for item2 in arr2:
				if(item2["channel"]["name"] == 'Hegma Channel'):
					discountValue = item2["discountValue"]
					
			if(item1["node"]["discountValueType"] == 'PERCENTAGE'):
				voucherText = voucherText + str(discountValue) + '%'
			else:
				voucherText = voucherText + "Rs " + str(discountValue)
			info = {
				"voucherText": voucherText
			}
			print(info)
			vouArr.append(info)	
		y = {
			"voucherTextArr": vouArr
		}
		item.update(y) 
	return res
	
# Call to check postal code
@app.route('/api/v1/checkPostalCode', methods=['POST'])
@cross_origin()
def checkPostalCode():
	msg = ''
	record = json.loads(request.data)
	postalCode = record["postal_code"]
	if postalCode == '':
		return msg
		
	postalCode = float(postalCode)
	api_url = constants.api_url
	resData = '{shippingZones(first:50){edges{node{id,name,shippingMethods{id,name,postalCodeRules{inclusionType,start,end}}}}}}'
	create_row_data = {'query': resData}
	response = requests.post(
        api_url, json=create_row_data,
        headers={'Content-Type': 'application/json',
            'Authorization': constants.hegma_auth_token}
    )
	res = json.loads(response.text)
	print(res)	
	status = False
	arr = res["data"]["shippingZones"]["edges"]
	for item in arr:
		arr1 = item["node"]["shippingMethods"]
		for item1 in arr1:
			arr2 = item1["postalCodeRules"]
			if(len(arr2) == 0):
				status = True
				break
			for item2 in arr2:	
				if (item2["inclusionType"] == 'INCLUDE'):
					start = float(item2["start"])
					end = float(item2["end"])
					if (postalCode >= start and postalCode <= end):
						status = True
						break
				if (item2["inclusionType"] == 'EXCLUDE'):
					start = float(item2["start"])
					end = float(item2["end"])
					if (not(postalCode >= start and postalCode <= end)):
						status = True
						break	
	if(status):
		msg = 'Success'
	return msg
	
# Call to set password
@app.route('/api/v1/setpassword', methods=['POST'])
@cross_origin()
def setpassword():
	msg = ''
	record = json.loads(request.data)
	newPassword = record["new_password"]
	token = record["token"]
	if token == '' or newPassword == '':
		return msg
		
	api_url = constants.api_url
	resData = '{me{id,email}}'
	create_row_data = {'query': resData}
	response = requests.post(
        api_url, json=create_row_data,
        headers={'Content-Type': 'application/json',
            'Authorization': 'JWT ' + token}
    )
	res = json.loads(response.text)
	print(res)	
	isValid = False
	try:
		me = res["data"]["me"]["email"]
		isValid = True
	except:
		isValid = False
	
	if (isValid):
		email = res["data"]["me"]["email"]
		db.updateUserEmailPassword(email, constants.hegma_enc_password)
		resData = 'mutation{passwordChange(newPassword: \"' + newPassword + '\", oldPassword: \"' + constants.hegma_password + '\") {user{id},errors{message}}}'
		create_row_data = {'query': resData}
		response = requests.post(
			api_url, json=create_row_data,
			headers={'Content-Type': 'application/json',
				'Authorization': 'JWT ' + token}
		)
		res = json.loads(response.text)
		print(res)
		if len(res["data"]["passwordChange"]["errors"]) == 0:
			msg = 'Success'
	return msg
	
# Call to update details
@app.route('/api/v1/updateUserDetails', methods=['POST'])
@cross_origin()
def updateUserDetails():
	msg = ''
	record = json.loads(request.data)
	newemail = record["email"]
	token = record["token"]
	mobile = record["mobile"]
	firstName = record["first_name"]
	lastName = record["last_name"]
	if token == '' or newemail == '' or mobile == '' or firstName == '' or lastName == '':
		return msg
		
	api_url = constants.api_url
	resData = '{me{id,email}}'
	create_row_data = {'query': resData}
	response = requests.post(
        api_url, json=create_row_data,
        headers={'Content-Type': 'application/json',
            'Authorization': 'JWT ' + token}
    )
	res = json.loads(response.text)
	print(res)	
	isValid = False
	try:
		me = res["data"]["me"]["email"]
		isValid = True
	except:
		isValid = False
	
	if (isValid):
		email = res["data"]["me"]["email"]
		if(email != newemail):
			record1 = db.accountUserEmailData(newemail)
			print(record1)
			if record1 is not None:
				msg = 'invalid email'
				return msg
				
		collision = db.checkAndReconcileMobile(mobile, email)
		if collision is not None:
			log.warning("Mobile update rejected — mobile already registered", event="update_user_invalid_mobile", mobile=mobile, existing_email=collision)
			msg = 'invalid mobile'
			return msg

		db.updateUserDetails(newemail, mobile, firstName, lastName, email)
		msg = 'Success'
	return msg
	
# Call to get mobile
@app.route('/api/v1/getMobile', methods=['POST'])
@cross_origin()
def getMobile():
	msg = ''
	record = json.loads(request.data)
	email = record["email"]
	if email == '':
		return msg
		
	record1 = db.getMobile(email)
	return record1[0]

# Call to get mobile
@app.route('/api/v1/getEmail', methods=['POST'])
@cross_origin()
def getEmail():
	msg = ''
	record = json.loads(request.data)
	mobile = record["mobile"]
	if mobile == '':
		return msg
		
	record1 = db.accountUserData(mobile)
	return record1[0]
	
# Call to cancel order
@app.route('/api/v1/cancelOrder', methods=['POST'])
@cross_origin()
def cancelOrder():
	msg = ''
	record = json.loads(request.data)
	orderId = record["order_id"]
	token = record["token"]
	lines = record["lines"]
	remark = record["remark"]
	action = record["action"]
	productName = record["productName"]
	created = record["created"]
	changeQuantity = record["changeQuantity"]
	status = True
	if orderId == '' or token == '':
		return msg
	
	api_url = constants.api_url
	remark1 = ""
	if(action == 'Cancellation'):
		remark1 = "Customer requested cancellation of " + productName + "."
		if remark != '':
			remark1 = remark1 + " Note: " + remark
  
	else:
		remark1 = "Customer requested return of " + changeQuantity + " items(" + productName + ")."
		if remark != '':
			remark1 = remark1 + " Note: " + remark
	
	print(remark1)
	resData = 'mutation{orderAddNote(order:\"' + orderId + '\",input:{ message: \"' + remark1 + '\",}){ errors{message}}}'
	create_row_data = {'query': resData}
	response = requests.post(
        api_url, json=create_row_data,
        headers={'Content-Type': 'application/json',
		'Authorization': constants.hegma_auth_token}
    )
	res = json.loads(response.text)
	print(res)
 
	resData = '{me{orders(first:100){edges{node{id,created,userEmail,number,total{gross{amount}},shippingAddress{firstName,lastName,streetAddress1,streetAddress2,city,cityArea,country{country},postalCode,phone},lines{id,variantName,weightedShipping,productName,quantity,thumbnail{url},unitPrice{gross{amount}}},fulfillments{lines{orderLine{id,quantityToFulfill}}}}}}}}'
	create_row_data = {'query': resData}
	response = requests.post(
        api_url, json=create_row_data,
        headers={'Content-Type': 'application/json',
		'Authorization': 'JWT ' + token}
    )
	res = json.loads(response.text)
	print(res)
	if(action == 'Cancellation'):
		for values in res["data"]["me"]["orders"]["edges"]:
			if(values["node"]["id"] == orderId):
				for fulfilments in values["node"]["fulfillments"]:
					for value2 in fulfilments["lines"]:
						if(lines == value2["orderLine"]["id"]):
							status = False
								
	else:
		for values in res["data"]["me"]["orders"]["edges"]:
			if(values["node"]["id"] == orderId):
				for fulfilments in values["node"]["fulfillments"]:
					for value2 in fulfilments["lines"]:
						if(value2["orderLine"]["quantityToFulfill"] > 0):
							status = False
								
	if(status):
		for values in res["data"]["me"]["orders"]["edges"]:
			if(values["node"]["id"] == orderId):
				orderNo = values["node"]["number"]
				orderDate = values["node"]["created"][0:10]
				name = values["node"]["shippingAddress"]["firstName"] + \
					" " + \
						values["node"]["shippingAddress"]["lastName"]
				address = values["node"]["shippingAddress"]["streetAddress1"] + \
					" " + \
						values["node"]["shippingAddress"]["streetAddress2"]
				country = values["node"]["shippingAddress"]["city"] + ", " + \
					values["node"]["shippingAddress"]["country"]["country"] + \
						" " + \
							values["node"]["shippingAddress"]["postalCode"]
				lines1 = values["node"]["lines"]
				email = values["node"]["userEmail"]
				amount = values["node"]["total"]["gross"]["amount"]
				productData = ''
				emailBody = ''
				if(action == 'Cancellation'):
					emailBody = emailConstants.emailOrderBody2
					subject = 'Cancellation request received for order ' + orderNo
					db.updateOrderStatusToCanceled(orderNo)
					db.updateOrderLineStatusToCanceled(orderNo, productName)
					mobileNo = db.getMobile(email)
					message = 'Your order ' + orderNo + ' has been cancelled. We apologize for any inconvenience. For assistance, contact us on +91-8553666877 ~Hegmakart. Thank you.'
					mobileNo = str(mobileNo).split('\'')[1]
					sendSMS(str(mobileNo), message, constants.msg91CancelDleId)
				elif(action == 'replace'):
					emailBody = emailConstants.emailOrderBody4
					subject = 'Replace request received for order ' + orderNo
					db.updateOrderStatusToReturned(orderNo)
					db.updateOrderLineStatusToReplace(orderNo, productName, created, changeQuantity)
				else:
					emailBody = emailConstants.emailOrderBody3
					subject = 'Return request received for order ' + orderNo
					db.updateOrderStatusToReturned(orderNo)
					db.updateOrderLineStatusToReturned(orderNo, productName, created, changeQuantity)
				
				emailMessage = emailConstants.emailHead + emailBody.replace(constants.keyReplaceRemark, remark) + emailConstants.emailOrderBodySummary.replace(constants.keyReplaceOrderNo, orderNo).replace(constants.keyReplaceOrderDate, orderDate).replace(constants.keyReplaceOrderTotalPrice, str(amount)) + emailConstants.emailOrderBodyShippingAddress.replace(constants.keyReplaceName, name).replace(constants.keyReplaceAddress, address).replace(constants.keyReplaceCountry, country) + emailConstants.emailOrderBodyProductHeader
				for line in lines1:
					if(lines == line["id"]):
						amt = line["unitPrice"]["gross"]["amount"]
						wgtShippPrc = None
						try:
							wgtShippPrc = line["weightedShipping"]
						except:
							wgtShippPrc = ''
						if(wgtShippPrc is not None):
							amt = amt - float(wgtShippPrc)
						if(action == 'Cancellation'):
							changeQuantity = line["quantity"]

						productData = productData + emailConstants.emailOrderBodyProductData.replace(constants.keyReplaceProductUrl, line["thumbnail"]["url"]).replace(constants.keyReplaceProductName, line["variantName"]).replace(constants.keyReplaceProductQuantity, str(changeQuantity)).replace(constants.keyReplaceProductPrice, str('%.2f' % amt))
					
				emailMessage = emailMessage + productData + emailConstants.emailFooter
				sendHtmlEmail(emailMessage, subject, [email])
				sendHtmlEmail(emailMessage, subject, ['order@hegmakart.com'])
				msg = 'Success'
	return msg

def send_shipment_notification_email(order_id, order_line_id):
	"""Internal helper to handle shipment delivery notifications directly without HTTP loopbacks."""
	log.info(
		f"Processing shipment delivery email notification for order {order_id}, line item {order_line_id}",
		event="send_shipment_notification",
		order_id=order_id,
		order_line_id=order_line_id,
	)
	try:
		api_url = constants.api_url
		resData = '{order(id: \"' + str(order_id) + '\") {id,number,userEmail,created,total{gross{amount}},shippingAddress{firstName,lastName,streetAddress1,streetAddress2,city,country{country},postalCode},lines{id,variantName,quantity,thumbnail{url},unitPrice{gross{amount}}},shippingPrice{gross{amount}},subtotal{gross{amount}}}}'
		create_row_data = {'query': resData}
		response = requests.post(
			api_url, json=create_row_data,
			headers={'Content-Type': 'application/json', 'Authorization': constants.hegma_auth_token},
			timeout=10
		)
		if response.status_code != 200:
			log.warning(f"GraphQL returned status {response.status_code} when querying order {order_id}", event="shipment_graphql_warning")
			return False
			
		res = json.loads(response.text)
		order_data = res.get("data", {}).get("order")
		if not order_data:
			log.warning(f"Order {order_id} not found in GraphQL response", event="shipment_order_not_found")
			return False
			
		email = order_data.get("userEmail")
		if not email:
			log.warning(f"No email associated with order {order_id}", event="shipment_no_email")
			return False
			
		orderNo = str(order_data.get("number", ""))
		orderDate = str(order_data.get("created", ""))[:10]
		
		shipping_addr = order_data.get("shippingAddress") or {}
		name = f"{shipping_addr.get('firstName', '')} {shipping_addr.get('lastName', '')}".strip()
		address = f"{shipping_addr.get('streetAddress1', '')} {shipping_addr.get('streetAddress2', '')}".strip()
		country_dict = shipping_addr.get("country", {})
		country_name = country_dict.get("country", "") if isinstance(country_dict, dict) else str(country_dict)
		country = f"{shipping_addr.get('city', '')}, {country_name} {shipping_addr.get('postalCode', '')}".strip()
		
		amount = str(order_data.get("total", {}).get("gross", {}).get("amount", "0"))
		shippingamount = str(order_data.get("shippingPrice", {}).get("gross", {}).get("amount", "0"))
		subtotalamount = str(order_data.get("subtotal", {}).get("gross", {}).get("amount", "0"))
		
		emailMessage = emailConstants.emailHead + emailConstants.emailShipmentBody + emailConstants.emailOrderBodySummary.replace(
			constants.keyReplaceOrderNo, orderNo).replace(
			constants.keyReplaceOrderDate, orderDate).replace(
			constants.keyReplaceOrderTotalPrice, amount) + emailConstants.emailOrderBodyShippingAddress.replace(
			constants.keyReplaceName, name).replace(
			constants.keyReplaceAddress, address).replace(
			constants.keyReplaceCountry, country) + emailConstants.emailOrderBodyProductHeader

		productData = ''
		totalQuantity = 0
		lines = order_data.get("lines") or []
		for line in lines:
			amt = float(line.get("unitPrice", {}).get("gross", {}).get("amount", 0))
			qty = int(line.get("quantity", 0))
			thumb_url = line.get("thumbnail", {}).get("url", "") if line.get("thumbnail") else ""
			variant_name = line.get("variantName", "")
			
			productData += emailConstants.emailOrderBodyProductData.replace(
				constants.keyReplaceProductUrl, thumb_url).replace(
				constants.keyReplaceProductName, variant_name).replace(
				constants.keyReplaceProductQuantity, str(qty)).replace(
				constants.keyReplaceProductPrice, str('%.2f' % amt))
			totalQuantity += qty

		emailMessage += productData
		emailMessage += emailConstants.emailOrderBodyProductTotal.replace(
			constants.keyReplaceTotalQuantity, str(totalQuantity)).replace(
			constants.keyReplaceSubTotalPrice, subtotalamount).replace(
			constants.keyReplaceShippingPrice, shippingamount).replace(
			constants.keyReplaceWeightedPrice, '0').replace(
			constants.keyReplaceDiscountedPrice, '0').replace(
			constants.keyReplaceOrderTotalPrice, amount) + emailConstants.emailFooter

		recipients = [email, 'order@hegmakart.com']
		sendHtmlEmail(emailMessage, f"Your Order #{orderNo} Has Been Shipped - HegmaKart", recipients)
		log.info(f"Shipment delivery email successfully dispatched to {email} for order #{orderNo}", event="shipment_email_success", order_id=order_id)
		return True
	except Exception as e:
		log.error(f"Error executing send_shipment_notification_email: {e}", event="shipment_email_exec_error", order_id=order_id)
		return False

# Call to send shipment details notification
@app.route('/api/v1/email/shipmentDetails', methods=['POST'])
@cross_origin()
def shipmentDetails():
	try:
		record = json.loads(request.data)
		order_id = record.get("id", "")
		user_email = record.get("user_email", "")
		log.info(f"Shipment details requested for order {order_id} to {user_email}", event="shipment_details_api")
		if order_id:
			send_shipment_notification_email(order_id, "")
		return 'Success'
	except Exception as e:
		log.error(f"Error handling shipmentDetails request: {e}", event="shipment_details_error")
		return 'Error'
	
def sendSMS(mobile, message, dleId):
	
	s  = 'https://control.msg91.com/api/sendhttp.php?'
	s += 'authkey=' + constants.msg91_auth_key
	s += '&mobiles=+91' + mobile
	s += '&message=' + message
	s += '&route=4'
	s += '&sender=iHEGMA'
	s += '&DLT_TE_ID=' + dleId
	log.debug(
		"Sending SMS via MSG91",
		event="sms_dispatch",
		mobile=mobile,
	)
	try:
		return requests.get(s, timeout=10).content
	except Exception as e:
		log.error(f"Error sending SMS via MSG91: {e}", event="sms_dispatch_error", mobile=mobile)
		return b""
	
def random_with_N_digits(n):
    range_start = 10**(n-1)
    range_end = (10**n)-1
    return randint(range_start, range_end)
	
def send_async(message, subject, recipients):
	msg = Message(
                subject,
                sender ='no-reply@hegmakart.com',
                recipients = recipients
               )
	msg.body = message
	@copy_current_request_context
	def send_message(msg):
		mail.send(msg)
	
	sender = threading.Thread(name='mail_sender', target=send_message, args=(msg,))
	sender.start()
	
def sendEmail(message, subject, recipients):
	msg = Message(
                subject,
                sender ='no-reply@hegmakart.com',
                recipients = recipients
               )
	msg.body = message
	with app.app_context():
		mail.send(msg)
	return 'Sent'
	
def sendHtmlEmail(message, subject, recipients):
	msg = Message(
                subject,
                sender ='no-reply@hegmakart.com',
                recipients = recipients
               )
	msg.html = message
	with app.app_context():
		mail.send(msg)
	return 'Sent'
	
def sendHtmlBccEmail(message, subject, recipients, bccReciepients):
	msg = Message(
                subject,
                sender ='no-reply@hegmakart.com',
                recipients = recipients,
				bcc = bccReciepients
               )
	msg.html = message
	with app.app_context():
		mail.send(msg)
	return 'Sent'

@app.route('/hegma/v1/hegma/getCheckoutToken', methods=['POST'])
@cross_origin()
def getCheckoutToken():
	try:
		req_data = request.get_json()
		token = req_data.get('token', '')
		guest_cart_token = req_data.get('guestCartToken', '')
		
		if not token:
			return flask.Response("", status=200, mimetype='text/plain')
			
		# Decode the JWT token payload manually (no verification needed just to read the ID/email)
		parts = token.split('.')
		if len(parts) != 3:
			return flask.Response("", status=200, mimetype='text/plain')
			
		payload_b64 = parts[1]
		payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
		import base64
		payload_bytes = base64.urlsafe_b64decode(payload_b64)
		payload = json.loads(payload_bytes)
		
		email = payload.get('email')
		user_id = payload.get('user_id') or payload.get('id')
		
		if not email and not user_id:
			return flask.Response("", status=200, mimetype='text/plain')
			
		# Query DB for old active cart
		cart_token = db.getActiveCheckoutToken(email, user_id)
		
		if cart_token and guest_cart_token and cart_token != guest_cart_token:
			# Merge guest cart into old user cart
			db.mergeGuestCart(guest_cart_token, cart_token)
		
		return flask.Response(cart_token, status=200, mimetype='text/plain')
		
	except Exception as e:
		log.error(f"Error in getCheckoutToken: {e}")
		return flask.Response("", status=200, mimetype='text/plain')

if __name__ == '__main__':
    is_debug = os.environ.get("DEBUG", "False").lower() in ("true", "1")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=is_debug)

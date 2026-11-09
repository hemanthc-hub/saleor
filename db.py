import psycopg2
import constants
import os
from logger import get_logger

_log = get_logger()

def getConnection():
	# ── Local dev: set these in backend/.env ──────────────────────────────────
	# DB_NAME=hegma  DB_USER_NAME=hegma  DB_PASSWORD=your_local_pass
	# DB_HOST=localhost  DB_PORT=5432
	# ── Production: injected by the server's environment ─────────────────────
	db_name     = os.environ.get("DB_NAME",      "dev_hegma")
	db_user     = os.environ.get("DB_USER_NAME", "postgres")
	db_password = os.environ.get("DB_PASSWORD",  "admin")
	db_host     = os.environ.get("DB_HOST",      "localhost")
	db_port     = os.environ.get("DB_PORT",      "5432")
	_log.debug(
		f"DB connecting to {db_host}:{db_port}/{db_name} as {db_user}",
		event="db_connect",
		db_host=db_host,
		db_port=db_port,
		db_name=db_name,
		db_user=db_user,
	)
	return psycopg2.connect(
	   database=db_name, user=db_user, password=db_password,
	   host=db_host, port=db_port
	)
	
def insertMobileOtp(mobile, otp):
	
	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_insert_query = """ INSERT INTO otp_authentication (mobile_no, otp, otp_status) VALUES (%s,%s,%s) """
		result = cursor.execute(sql_insert_query, (mobile, otp, 'P'))
		# Commit your changes in the database
		conn.commit()
	finally:
		#Closing the connection
		conn.close()
	
def verifyMobileOtp(mobile, otp):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_select_query = """select * from otp_authentication where mobile_no = %s and otp = %s and otp_status = %s and created_at >= NOW() - INTERVAL '10 minutes'"""
		cursor.execute(sql_select_query, (mobile, otp, 'P'))
		record = cursor.fetchone()
		count = cursor.rowcount
	finally:
		#Closing the connection
		conn.close()
	return count
	
def updateMobileOTPStatus(mobile, otp):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_update_query = """UPDATE otp_authentication SET OTP_STATUS='S' WHERE mobile_no = %s and otp = %s and otp_status = %s"""
		cursor.execute(sql_update_query, (mobile, otp, 'P'))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		#Closing the connection
		conn.close()
	
def accountUserData(mobile):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql = """
			SELECT u.email 
			FROM account_user u 
			LEFT JOIN order_order o ON u.id = o.user_id 
			WHERE u.mobile_no = %s 
			GROUP BY u.id, u.email 
			ORDER BY COUNT(o.id) DESC, u.id ASC 
			LIMIT 1
		"""
		cursor.execute(sql, (mobile,))
		record = cursor.fetchone()
	finally:
		#Closing the connection
		conn.close()
	return record
	
def accountUserEmailData(email):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		cursor.execute("select email from account_user where email = '{0}'".format(email))
		record = cursor.fetchone()
	finally:
		#Closing the connection
		conn.close()
	return record

def checkAndReconcileMobile(mobile, target_email):

	conn = getConnection()
	try:
		cursor = conn.cursor()
		cursor.execute("SELECT id, email FROM account_user WHERE mobile_no = %s AND email != %s", (mobile, target_email))
		records = cursor.fetchall()
		if not records:
			return None

		for r in records:
			existing_id, existing_email = r[0], r[1]
			cursor.execute("SELECT COUNT(*) FROM order_order WHERE user_id = %s", (existing_id,))
			order_count = cursor.fetchone()[0]
			cursor.execute("SELECT COUNT(*) FROM checkout_checkout WHERE user_id = %s", (existing_id,))
			cart_count = cursor.fetchone()[0]

			# Preserve accounts with existing orders, active checkouts, or registered non-temp emails
			if order_count > 0 or cart_count > 0 or not existing_email.endswith('@hegmakart.com'):
				return existing_email

			# Clean up empty zero-order temporary default accounts so genuine updates succeed without duplication
			cursor.execute("UPDATE account_user SET mobile_no = NULL WHERE id = %s", (existing_id,))
		
		conn.commit()
		return None
	finally:
		conn.close()
	

def updateUserPassword(mobile):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_update_query = """UPDATE account_user SET password = %s WHERE mobile_no = %s"""
		cursor.execute(sql_update_query, (constants.hegma_enc_password, mobile))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		#Closing the connection
		conn.close()
	
def updateUserEmailPassword(email, password):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_update_query = """UPDATE account_user SET password = %s WHERE email = %s"""
		cursor.execute(sql_update_query, (password, email))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		#Closing the connection
		conn.close()
	
def updateUserMobile(mobile, email):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_update_query = """UPDATE account_user SET mobile_no = %s, is_active = true WHERE email = %s"""
		cursor.execute(sql_update_query, (mobile, email))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		#Closing the connection
		conn.close()

def activateUserEmail(email):

	conn = getConnection()
	try:
		cursor = conn.cursor()
		sql_update_query = """UPDATE account_user SET is_active = true WHERE email = %s"""
		cursor.execute(sql_update_query, (email,))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		conn.close()
	
def updateOrderStatus(orderId, status):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_update_query = """UPDATE order_order SET status='processing' WHERE number = {0}"""
		cursor.execute(sql_update_query.format(orderId))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		#Closing the connection
		conn.close()

def updateOrderStatusToCanceled(orderId):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_update_query = """UPDATE order_order SET status='cancellation requested' WHERE number = {0}"""
		cursor.execute(sql_update_query.format(orderId))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		#Closing the connection
		conn.close()

def updateOrderLineStatusToCanceled(orderId, productName):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_update_query = """UPDATE order_orderline SET user_status='Cancellation Requested' WHERE order_id = (select id from order_order WHERE number = {0}) and product_name = '{1}'"""
		cursor.execute(sql_update_query.format(orderId, productName))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		#Closing the connection
		conn.close()

def updateOrderStatusToReturned(orderId):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_update_query = """UPDATE order_order SET status='return requested' WHERE number = {0}"""
		cursor.execute(sql_update_query.format(orderId))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		#Closing the connection
		conn.close()

def updateOrderLineStatusToReturned(orderId, productName, created, changeQuantity):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_update_query = """UPDATE order_fulfillmentline SET user_status='Return Requested', change_quantity = {0} WHERE order_line_id = (select id from order_orderline WHERE order_id = (select id from order_order WHERE number = {1}) and product_name = '{2}') and fulfillment_id = (select id from order_fulfillment where created_at = '{3}' and order_id = (select id from order_order WHERE number = {4}))"""
		cursor.execute(sql_update_query.format(changeQuantity, orderId, productName, created, orderId))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		#Closing the connection
		conn.close()

def updateOrderLineStatusToReplace(orderId, productName, created, changeQuantity):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_update_query = """UPDATE order_fulfillmentline SET user_status='Replace Requested', change_quantity = {0} WHERE order_line_id = (select id from order_orderline WHERE order_id = (select id from order_order WHERE number = {1}) and product_name = '{2}') and fulfillment_id = (select id from order_fulfillment where created_at = '{3}' and order_id = (select id from order_order WHERE number = {4}))"""
		cursor.execute(sql_update_query.format(changeQuantity, orderId, productName, created, orderId))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		#Closing the connection
		conn.close()

def updateOrderLineStatus(orderLineId, status, orderId, dateTime):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_update_query = """UPDATE order_fulfillment set status='delivered', fulfillment_date = '{0}' WHERE fulfillment_order ={1} and order_id=(select id from order_order where number={2})"""
		cursor.execute(sql_update_query.format(dateTime, orderLineId, orderId))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		#Closing the connection
		conn.close()
	
def updateUserDetails(newemail, mobile, firstName, lastName, email):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_update_query = """UPDATE account_user SET email = %s, mobile_no = %s, first_name = %s, last_name = %s WHERE email = %s"""
		cursor.execute(sql_update_query, (newemail, mobile, firstName, lastName, email))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		#Closing the connection
		conn.close()
	
def getMobile(email):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		cursor.execute("select mobile_no from account_user where email = '{0}'".format(email))
		record = cursor.fetchone()
	finally:
		#Closing the connection
		conn.close()
	return record

def insertProductReview(productId, rating, userId, review, orderId, reviewTime):
	
	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_insert_query = """ INSERT INTO product_productreview (product_id, rating, user_id, review, order_id, review_time) VALUES (%s,%s,%s,%s,%s,%s) """
		result = cursor.execute(sql_insert_query, (productId, rating, userId, review, orderId, reviewTime))
		# Commit your changes in the database
		conn.commit()
	finally:
		#Closing the connection
		conn.close()
    
def getProductData(productId):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		cursor.execute("select AVG(rating) from product_productreview where product_id = '{0}'".format(productId))
		record = cursor.fetchone()
	finally:
		#Closing the connection
		conn.close()
	return record
    
def updateProductRating(productId, avgRating):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_update_query = """UPDATE product_product SET rating = %s WHERE id = %s"""
		cursor.execute(sql_update_query, (avgRating, productId))
		conn.commit()
		count = cursor.rowcount
		print(count, "Record Updated successfully ")
	finally:
		#Closing the connection
		conn.close()
	
def getOrderReviewData(orderNumber):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		cursor.execute("select ppr.rating, ppr.review, ppv.name from order_order oo, order_orderline ool, product_productvariant ppv, product_productreview ppr where oo.id = ool.order_id and ool.variant_id = ppv.id and ppr.product_id = ppv.product_id and oo.id=ppr.order_id and oo.number = '{0}'".format(orderNumber))
		record = cursor.fetchall()
	finally:
		#Closing the connection
		conn.close()
	return record

def getProductReviewData(slug):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		cursor.execute("select ppr.rating, ppr.review, to_char(ppr.review_time, 'DD Mon yyyy HH24:MI:SS') reviewTime, au.first_name, au.last_name from account_user au, product_product pp, product_productreview ppr where au.id = ppr.user_id and ppr.product_id = pp.id and pp.slug = '{0}'".format(slug))
		record = cursor.fetchall()
	finally:
		#Closing the connection
		conn.close()
	return record

def getOrderData(orderNumber, productName):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		cursor.execute("select oo.id, oo.user_id, ppv.product_id from order_order oo, order_orderline ool, product_productvariant ppv where oo.id = ool.order_id and ool.variant_id = ppv.id and oo.number = '{0}' and ppv.name = '{1}'".format(orderNumber,productName))
		record = cursor.fetchone()
	finally:
		#Closing the connection
		conn.close()
	return record

def getProductBrandData(brandName):

	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		cursor.execute("select distinct(name) from attribute_attributevalue where attribute_id = (select id from attribute_attribute where slug = 'manufacturer') and LOWER(name) LIKE LOWER('{0}') LIMIT 5".format('%' + brandName + '%'))
		record = cursor.fetchall()
	finally:
		#Closing the connection
		conn.close()
	return record

def insertNewsLetterSubscription(emailId, dateTime):
	
	conn = getConnection()
	try:
		#Creating a cursor object using the cursor() method
		cursor = conn.cursor()
		sql_insert_query = """ INSERT INTO email_emailsubscription (email_id, timestamp) VALUES (%s,%s) """
		result = cursor.execute(sql_insert_query, (emailId, dateTime))
		# Commit your changes in the database
		conn.commit()
	finally:
		#Closing the connection
		conn.close()

# def getActiveCheckoutToken(email, user_id=None):
# 	conn = getConnection()
# 	try:
# 		cursor = conn.cursor()
# 		conditions = []
# 		params = []
# 		if email:
# 			conditions.append("email = %s")
# 			params.append(email)
# 		if user_id:
# 			conditions.append("user_id = %s")
# 			params.append(user_id)
			
# 		if not conditions:
# 			return ""
			
# 		query = "SELECT token FROM checkout_checkout WHERE (" + " OR ".join(conditions) + ") ORDER BY last_change DESC LIMIT 1"
# 		cursor.execute(query, tuple(params))
# 		record = cursor.fetchone()
# 		if record:
# 			return str(record[0])
# 		return ""
# 	except Exception as e:
# 		_log.error(f"Error getting checkout token: {e}")
# 		return ""
# 	finally:
# 		conn.close()

# def mergeGuestCart(guest_cart_token, user_cart_token):
# 	if not guest_cart_token or not user_cart_token or guest_cart_token == user_cart_token:
# 		return
# 	conn = getConnection()
# 	try:
# 		cursor = conn.cursor()
		
# 		# Get user cart lines
# 		cursor.execute("SELECT id, variant_id, quantity FROM checkout_checkoutline WHERE checkout_id = %s", (user_cart_token,))
# 		user_lines = cursor.fetchall()
# 		user_variants = {row[1]: (row[0], row[2]) for row in user_lines}
		
# 		# Get guest cart lines
# 		cursor.execute("SELECT id, variant_id, quantity FROM checkout_checkoutline WHERE checkout_id = %s", (guest_cart_token,))
# 		guest_lines = cursor.fetchall()
		
# 		for g_line_id, g_variant_id, g_qty in guest_lines:
# 			if g_variant_id in user_variants:
# 				u_line_id, u_qty = user_variants[g_variant_id]
# 				new_qty = u_qty + g_qty
# 				cursor.execute("UPDATE checkout_checkoutline SET quantity = %s WHERE id = %s", (new_qty, u_line_id))
# 				cursor.execute("DELETE FROM checkout_checkoutline WHERE id = %s", (g_line_id,))
# 			else:
# 				cursor.execute("UPDATE checkout_checkoutline SET checkout_id = %s WHERE id = %s", (user_cart_token, g_line_id))
				
# 		# Delete guest cart session
# 		cursor.execute("DELETE FROM checkout_checkout WHERE token = %s", (guest_cart_token,))
		
# 		conn.commit()
# 	except Exception as e:
# 		_log.error(f"Error merging guest cart: {e}")
# 		conn.rollback()
# 	finally:
# 		conn.close()

def mergeGuestCart(guest_cart_token, user_cart_token):
	if not guest_cart_token or not user_cart_token or guest_cart_token == user_cart_token:
		return
	conn = getConnection()
	try:
		cursor = conn.cursor()
		
		# Get user cart lines
		cursor.execute("SELECT id, variant_id, quantity FROM checkout_checkoutline WHERE checkout_id = %s", (user_cart_token,))
		user_lines = cursor.fetchall()
		user_variants = {row[1]: (row[0], row[2]) for row in user_lines}
		
		# Get guest cart lines
		cursor.execute("SELECT id, variant_id, quantity FROM checkout_checkoutline WHERE checkout_id = %s", (guest_cart_token,))
		guest_lines = cursor.fetchall()
		
		for g_line_id, g_variant_id, g_qty in guest_lines:
			if g_variant_id in user_variants:
				u_line_id, u_qty = user_variants[g_variant_id]
				new_qty = u_qty + g_qty
				cursor.execute("UPDATE checkout_checkoutline SET quantity = %s WHERE id = %s", (new_qty, u_line_id))
				cursor.execute("DELETE FROM checkout_checkoutline WHERE id = %s", (g_line_id,))
			else:
				cursor.execute("UPDATE checkout_checkoutline SET checkout_id = %s WHERE id = %s", (user_cart_token, g_line_id))
				
		# Delete guest cart session
		cursor.execute("DELETE FROM checkout_checkout WHERE token = %s", (guest_cart_token,))
		
		conn.commit()
	except Exception as e:
		_log.error(f"Error merging guest cart: {e}")
		conn.rollback()
	finally:
		conn.close()

def getActiveCheckoutToken(email, user_id=None):
	conn = getConnection()
	try:
		cursor = conn.cursor()
		conditions = []
		params = []
		if email:
			conditions.append("email = %s")
			params.append(email)
		if user_id:
			# Decode GraphQL Base64 ID (e.g. "VXNlcjoyNDg2" -> "User:2486" -> 2486) if needed
			try:
				if isinstance(user_id, str) and not user_id.isdigit():
					import base64
					decoded = base64.b64decode(user_id + "=" * ((4 - len(user_id) % 4) % 4)).decode('utf-8')
					if ':' in decoded:
						user_id = decoded.split(':')[-1]
				user_id = int(user_id)
				conditions.append("user_id = %s")
				params.append(user_id)
			except Exception as decode_err:
				_log.warning(f"Could not convert user_id {user_id} to integer: {decode_err}")
				
		if not conditions:
			return ""
			
		cond_str = " OR ".join([f"c.{c}" for c in conditions])
		query = f"""
			SELECT c.token, COUNT(cl.id) as item_count 
			FROM checkout_checkout c
			LEFT JOIN checkout_checkoutline cl ON cl.checkout_id = c.token
			WHERE ({cond_str}) 
			GROUP BY c.token, c.last_change 
			ORDER BY item_count DESC, c.last_change DESC 
			LIMIT 1
		"""
		cursor.execute(query, tuple(params))
		record = cursor.fetchone()
		if record:
			return str(record[0])
		return ""
	except Exception as e:
		_log.error(f"Error getting checkout token: {e}")
		return ""
	finally:
		conn.close()

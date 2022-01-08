# frappe imports
import frappe

# third party imports
import razorpay

# standard imports
import hmac
import hashlib
import requests
from collections import namedtuple
from functools import partial
from typing import Callable, Dict
from uuid import uuid4


'''
TODO:
	- payment links
	- subscriptions
	- refunds

Flow:
	- Everthing starts with a payment link
	- Then payment is initiated on that link

For every payment link created we get an order id and payment link id
When the payment is made successfully on the payment link, we get the payment id

NOTE: Razorpay's wrapper library doesn't have the implementation for:
	- payment link (in v1.2.0)
	- fetching all customers (not even in master)
'''

Auth = namedtuple("Auth", ["api_key", "api_secret"])


class RazorpayPayment:
	def __init__(self, api_key: str, api_secret: str):
		self.auth = Auth(api_key, api_secret)
		self.base_api_url = "https://api.razorpay.com/v1/"
		self.validate_razorpay_creds()

		# only initialize razorpay's client if the validation succeeds
		self.rzp_client = razorpay.Client(auth=(api_key, api_secret))


	def validate_razorpay_creds(self):
		return handle_api_response(
			partial(
				requests.get,
				self.base_api_url + "customers?count=1",
				auth=tuple(self.auth),
				headers={
					"content-type": "application/json"
				}
			)
		)


	def _create_payment_link(
		self,
		amount: int,
		api_endpoint: str,
		*,
		callback_url: str="",
		description: str="",
		expire_by: int=0,
		payer_email: str="",
		payer_phone: str="",
		payer_name: str="",
		reference_id: str="",
		notify_via_email: bool=False,
		notify_via_sms: bool=False,
		notes: Dict[str, str]={}, # kept "Dict" for python < v3.9 (ref: https://docs.python.org/3/library/typing.html#typing.Dict)
		**kwargs
	):
		'''
		ref: https://razorpay.com/docs/api/payment-links/#create-payment-link

		Further customizations:
			- ref: https://razorpay.com/docs/api/payment-links/customise/
		'''

		if not amount or amount < 1:
			frappe.throw(
				frappe._("Amount (INT) is required for creating a payment link !")
			)

		# razorpay assumes amount precision upto 2 places
		# and needs it to be specified as a whole (int)
		amount *= 100

		return handle_api_response(
			partial(
				requests.post,
				self.base_api_url + api_endpoint,
				auth=tuple(self.auth),
				json={
					"amount": amount,
					"callback_url": callback_url or frappe.utils.get_url("razorpay_payment_status"),
					"callback_method": "get",
					"currency": "INR",
					"customer": {
						"name": payer_name,
						"email": payer_email,
						"phone": payer_phone
					},
					"description": description,
					"expire_by": expire_by,
					"notify": {
						"sms": notify_via_sms,
						"email": notify_via_email
					},
					"reference_id": reference_id or str(uuid4()), # use this ref id in razorpay log
					"notes": notes # anything can be put in this as a key value pair
				},
				headers={
					"Content-type": "application/json"
				}
			)
		)


	def get_or_create_payment_link(
		self,
		payment_link_id: str="",
		**kwargs
	):
		api_endpoint = "payment_links"

		if payment_link_id:
			#ref: https://razorpay.com/docs/api/payment-links/#specific-payment-links-by-id

			return handle_api_response(
				partial(
					requests.get,
					f"{self.base_api_url}/{api_endpoint}/{payment_link_id}",
					auth=tuple(self.auth),
					headers={
						"content-type": "application/json"
					}
				)
			)

		return self._create_payment_link(api_endpoint=api_endpoint, **kwargs)


	def get_payment(self, payment_id: str):
		if not payment_id:
			frappe.throw(
				frappe._(
					"Please Provide Payment ID "
					"for fetching the respective payment !"
				)
			)

		return handle_api_response(
			partial(self.rzp_client.payment.fetch, payment_id)
		)


	def refund_payment(self, payment_id: str, refund_amt: int=0):
		# NOTE: Refund amount should be less than/equal to the payment amount
		if not payment_id:
			frappe.throw(
				frappe._(
					"Please Provide Payment ID for which the amount needs to be refunded !"
				)
			)

		if not refund_amt:
			# refund is done in full by default
			_func = partial(self.rzp_client.payment.refund, payment_id)
		else:
			refund_amt *= 100
			_func = partial(self.rzp_client.payment.refund, payment_id, refund_amt)

		return handle_api_response(_func)


	def verify_payment_signature(
		self,
		*,
		razorpay_payment_link_id: str,
		razorpay_payment_link_reference_id: str,
		razorpay_payment_link_status: str,
		razorpay_payment_id: str,
		razorpay_signature: str,
		raise_err: bool=False
	):
		message = razorpay_payment_link_id + "|" + \
			razorpay_payment_link_reference_id + "|" + \
			razorpay_payment_link_status + "|" + \
			razorpay_payment_id

		secret = bytes(self.auth.api_secret, "utf-8")
		msg = bytes(message, "utf-8")

		if not hmac.compare_digest(
			hmac.new(key=secret, msg=msg, digestmod=hashlib.sha256).hexdigest(),
			razorpay_signature
		):
			# if this fails we can say the payment failed
			if raise_err:
				frappe.throw(
					frappe._("Razorpay Payment Signature Verification Failed")
				)

			return False

		return True



def handle_api_response(_func: Callable):
	if not callable(_func):
		return

	# putting try except here to log razorpay's wrapper errors
	try:
		response = _func()
	except Exception as e:
		frappe.log_error(e)
		frappe.throw(
			frappe._("Something Bad Happened !")
		)

	if isinstance(response, requests.Response):
		response = response.json()

		# to get api's errors
		if response.get("error"):
			frappe.log_error(response["error"])
			frappe.throw(
				frappe._(
					response["error"].get("code") +
					"- " +
					response["error"].get("description")
				)
			)

	return response

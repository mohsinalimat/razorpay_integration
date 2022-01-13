# Copyright (c) 2021, Frappe and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class RazorpayPaymentLog(Document):
	pass



@frappe.whitelist()
def update_payment_log_status_to_refund(docname: str) -> None:
	log = frappe.qb.DocType("Razorpay Payment Log")

	frappe.qb.update(
		log
	).set(
		log.status, "Refund"
	).where(
		log.name == docname
	).run()


@frappe.whitelist()
def update_failed_payment_log_status_to_refund() -> str:
	log = frappe.qb.DocType("Razorpay Payment Log")

	frappe.qb.update(
		log
	).set(
		log.status, "Refund"
	).where(
		log.status == "Failed"
	).run()

	return """Changed Status to Refund.
		These jobs will be picked up by the hourly scheduler in its next iteration !!"""

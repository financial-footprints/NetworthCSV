"""Shared PNB handler constants."""

from __future__ import annotations

MAIL_SUBJECTS = ["Your PNB Credit Card Statement for the month"]

TRIM_END = ["********** End of Statement **********"]

DROP_SECTIONS = [
    "*TAD for the month consists of current month purchases, charges, cash advances and amount of BT/EMI due for the month if any. Making only the minimum payment if any month would result in the repayment stretching over subsequent Always get MORE with months with consequent interest payment on your outstanding balance. Please examine your statement immediately upon receipt. If no error is reported within 60 days from the date PNB Credit Cards of statement, the account will be considered correct. Place of supply : PNB, Credit Card Processing Center, Ground Floor, C-24, Sec-58, Noida, Uttar Pradesh 201301, State Code : 09 GSTIN No.: 07AAACP0165G3ZP Registered Address : Punjab National Bank, Plot No. 7, East Block Road, Bhikaji Cama Place, New Delhi, New Delhi, Delhi, 110066 State Code : 07",
    "Presenting Rupay Platinum",
    "PNB GENIE",
    "Scan and download",
    "Always get MORE",
    "Reward points details",
    "Why pay in Rupees",
    "CAUTION :",
    "Please make all Cheque",
]

INVOICE_NO_LABEL = "Invoice No :"

MARKETING_MARKERS = (
    "Presenting Rupay Platinum",
    "Scan below QR",
    "PNB GENIE",
)

V1_INVOICE_NO_MAX_OFFSET = 2500
V2_INVOICE_NO_MIN_OFFSET = 4000

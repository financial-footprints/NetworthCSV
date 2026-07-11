"""BOB EASY credit card handler."""

from __future__ import annotations

from networthcsv.utils.banks import register
from networthcsv.utils.banks.bob.default import BobDefaultHandler


@register("bob", "easy")
class BobEasyHandler(BobDefaultHandler):
    def mail_subjects(self) -> list[str]:
        return [
            "E-statement for your BOB EASY credit card ending in",
            "E-statement for your BOBCARD EASY credit card ending in",
            "E-statement for your BOBCARD RUPAY EASY credit card ending",
            "Duplicate Statement from BOB Card",
        ]

    def drop_sections(self) -> list[str]:
        return [
            "Please register your Mobile No. & E-Mail ID",
            "Please register your Mobile No. and Email ID",
            "Please register your Mobile Number & Email ID",
            "Loan Summary",
            "GO DIGITAL to SELF-SERVICE",
            "YOUR CONVENIENCE IS OUR PRIORITY",
            "Did You Know",
            "SCHEDULE OF CHARGES",
            "IMPORTANT",
            "CIBIL Information",
            "Billing Dispute Resolution",
            "For T&C & details on Fee/charges",
            "Important Security Update for Your BOBCARD",
        ]

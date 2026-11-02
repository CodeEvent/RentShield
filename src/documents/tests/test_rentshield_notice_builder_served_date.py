from django.test import SimpleTestCase

from documents.rentshield.notice_builder import build_notice


class TestNoticeClockRunsFromServiceDate(SimpleTestCase):
    """The statutory 12-month / breach 30-day clock must run from the date
    the notice is SERVED (Law 26/2007 as amended, Art. 25), not the drafting
    date. served_date drives it when present; notice_date is the pre-service
    fallback so drafts still render."""

    def test_statutory_expiry_falls_back_to_notice_date(self):
        d = build_notice({"reason": "sale", "notice_date": "2026-01-01"})
        # 2026-01-01 + 365 days
        self.assertEqual(d["en"]["deadline_value"], "01 January 2027")

    def test_statutory_expiry_uses_served_date_when_set(self):
        d = build_notice(
            {"reason": "sale", "notice_date": "2026-01-01", "served_date": "2026-03-15"},
        )
        # Clock runs from service, not drafting.
        self.assertEqual(d["en"]["deadline_value"], "15 March 2027")
        self.assertIn("15 March 2027", d["en"]["paragraphs"][2])
        self.assertIn("served on 15 March 2026", d["en"]["paragraphs"][2])

    def test_breach_deadline_uses_served_date_when_set(self):
        d = build_notice(
            {
                "reason": "nonpayment",
                "notice_date": "2026-01-01",
                "served_date": "2026-02-01",
            },
        )
        # 2026-02-01 + 30 days
        self.assertEqual(d["en"]["deadline_value"], "03 March 2026")

    def test_breach_deadline_falls_back_to_notice_date(self):
        d = build_notice({"reason": "nonpayment", "notice_date": "2026-02-01"})
        self.assertEqual(d["en"]["deadline_value"], "03 March 2026")

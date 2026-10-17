import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from asao_erp import Client, ErpError, flatten, ops  # noqa: E402

FAKE = [sys.executable, str(Path(__file__).resolve().parent / "fake_cli.py")]


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.log = tempfile.NamedTemporaryFile(delete=False)
        self.log.close()
        os.environ["FAKE_CLI_LOG"] = self.log.name
        self.erp = Client(profile="asao-hq", binary=FAKE, allow_unverified=True)

    def tearDown(self):
        os.unlink(self.log.name)

    def calls(self):
        return [json.loads(line) for line in Path(self.log.name).read_text().splitlines()]

    def executions(self):
        """The calls that run an operation; a client also describes an operation once before reading it."""
        return [call for call in self.calls() if "execute" in call]

    def test_a_read_names_its_operation_profile_and_page(self):
        rows = self.erp.read(ops.sales.quotation_list, [["state", "=", "sale"]], limit=5, offset=10, order="id")
        self.assertEqual([r["id"] for r in rows], [11, 12, 13, 14, 15])
        self.assertEqual(self.executions()[0], ["execute", "--operation", "sales.quotation.list", "--limit", "5", "--offset", "10",
                                           "--order", "id", "--filter", '[["state", "=", "sale"]]', "--profile", "asao-hq",
                                           "--allow-unverified", "--output", "json"])

    def test_iterate_pages_until_a_short_page(self):
        rows = list(self.erp.iterate("sales.quotation.list", page=200))
        self.assertEqual(len(rows), 450)
        self.assertEqual([c[c.index("--offset") + 1] if "--offset" in c else "0" for c in self.executions()], ["0", "200", "400"])

    def test_groups_come_from_the_provider(self):
        groups = self.erp.group("sales.quotation.list", by=["date_order:month"], aggregate=["amount_total:sum"])
        self.assertEqual(groups[0]["count"], 3)
        self.assertIn("--group-by", self.executions()[0])
        self.assertEqual(flatten(groups[0])["date_order:month"], "2026-10-01")

    def test_a_print_returns_or_saves_the_pdf(self):
        self.assertEqual(self.erp.print("finance.invoice.print", 1), b"%PDF-1.4 x")
        with tempfile.TemporaryDirectory() as folder:
            path = self.erp.print("finance.invoice.print", 1, to=Path(folder) / "invoice.pdf")
            self.assertEqual(path.read_bytes(), b"%PDF-1.4 x")

    def test_a_client_reads_unless_made_to_write(self):
        with self.assertRaises(ErpError) as refused:
            self.erp.execute("identity.contact.create", values={"name": "x"})
        self.assertEqual(refused.exception.code, "WRITES_NOT_ALLOWED")
        self.assertFalse(any("execute" in call for call in self.calls()))
        writer = Client(profile="asao-hq", binary=FAKE, allow_writes=True)
        self.assertEqual(writer.execute("identity.contact.create", values={"name": "x"}), {"id": 9, "created": True})

    def test_a_write_named_where_a_read_is_expected_never_runs(self):
        # read(), iterate(), group() and print() run read operations only, on any client: before
        # 16/10/2026 a read of a write operation ran it, even without allow_writes.
        writer = Client(profile="asao-hq", binary=FAKE, allow_writes=True)
        for erp in (self.erp, writer):
            for attempt in (lambda: erp.read("sales.order.confirm", id=42),
                            lambda: list(erp.iterate("finance.invoice.post")),
                            lambda: erp.group("sales.order.confirm"),
                            lambda: erp.print("sales.order.confirm", 42)):
                with self.assertRaises(ErpError) as refused:
                    attempt()
                self.assertEqual(refused.exception.code, "NOT_A_READ")
        self.assertEqual(self.executions(), [])

    def test_a_refusal_is_an_error_with_the_clis_fields(self):
        with self.assertRaises(ErpError) as refused:
            self.erp.read("sales.quotation.list", [["name", "=", "boom"]])
        error = refused.exception
        self.assertEqual((error.code, error.exit_code, error.remediation), ("AERP_VALIDATION_FAILED", 2, "Do not say boom."))

    def test_a_governed_client_acts_as_the_asao_login(self):
        governed = Client(organization="org-1", connection="conn-1", binary=FAKE)
        governed.read("sales.quotation.list", limit=1)
        call = self.executions()[0]
        self.assertEqual(call[:2], ["aerp", "execute"])
        self.assertIn("--organization", call)
        self.assertNotIn("--profile", call)
        self.assertNotIn("--allow-unverified", call)

    def test_a_high_risk_operation_runs_with_a_colleagues_approval(self):
        governed = Client(organization="org-1", binary=FAKE, allow_writes=True)
        approval = governed.request_approval("finance.payment.create", "supplier payment", id=42)
        self.assertEqual(approval["id"], "appr-1")
        self.assertEqual(self.calls()[0][:3], ["aerp", "approval", "request"])
        self.assertIn("--reason", self.calls()[0])
        self.assertEqual(governed.execute("finance.payment.create", approval="appr-1"), {"id": 42, "state": "posted"})
        run = self.calls()[-1]
        self.assertIn("--approval", run)
        self.assertNotIn("--provider-target-id", run)
        with self.assertRaises(ErpError) as refused:
            governed.execute("finance.payment.create", approval="appr-1", id=42)
        self.assertEqual(refused.exception.code, "APPROVAL_INPUT_RESUPPLIED")
        with self.assertRaises(ErpError) as refused:
            Client(profile="p", binary=FAKE, allow_writes=True).request_approval("finance.payment.create", "x")
        self.assertEqual(refused.exception.code, "APPROVAL_NOT_GOVERNED")

    def test_a_review_asks_odoo_cli_and_returns_its_report(self):
        report = self.erp.review(date(2026, 4, 1), "2026-09-30", checks=["O01", "O22"],
                                 params={"O01": {"window_days": 10}})
        self.assertEqual(report["counts"], {"XEM_NGAY": 1})
        self.assertEqual(report["findings"][0]["evidence"][0]["id"], 1)
        call = self.calls()[-1]
        self.assertEqual(call[:2], ["review", "run"])
        for flag, value in (("--profile", "asao-hq"), ("--from", "2026-04-01"), ("--to", "2026-09-30"),
                            ("--param", "O01.window_days=10")):
            self.assertEqual(call[call.index(flag) + 1], value)
        self.assertEqual([call[i + 1] for i, a in enumerate(call) if a == "--check"], ["O01", "O22"])
        self.assertIn("--allow-unverified", call)

    def test_a_governed_review_waits_for_asao_aerp_review(self):
        governed = Client(organization="org-1", binary=FAKE)
        with self.assertRaises(ErpError) as refused:
            governed.review("2026-04-01", "2026-09-30")
        self.assertEqual(refused.exception.code, "REVIEW_NOT_GOVERNED_YET")

    def test_resolve_answers_ids_only(self):
        ids = self.erp.resolve(ops.identity.contact_list, name="Lê Thành", order="id desc", limit=1)
        self.assertEqual(ids, [16])
        self.assertEqual(self.calls()[-1][:9], ["resolve", "--profile", "asao-hq", "--operation", "identity.contact.list",
                                                "--limit", "1", "--name", "Lê Thành"])

    def test_a_write_can_be_judged_at_three_levels(self):
        erp = Client(profile="asao-hq", binary=FAKE, allow_writes=True)
        outcome = erp.execute("finance.invoice.post", id=42, accept=True)
        self.assertEqual(outcome["acceptance"]["level"], "INTENT_VERIFIED")
        self.assertIn("--accept", self.calls()[-1])

    def test_check_files_verdicts_and_precision(self):
        self.assertTrue(self.erp.test_check("X-1.json")["passed"])
        self.assertTrue(self.erp.add_check("X-1.json")["added"])
        self.assertEqual(self.erp.verdict("O23-1a2b3c4d5e6f", real=False, note="team lunch")["verdict"]["verdict"], "false")
        self.assertIn("--false-alarm", self.calls()[-1])
        self.assertEqual(self.erp.precision()[0]["precision"], 0.75)

    def test_flatten_turns_relations_into_names(self):
        self.assertEqual(flatten({"partner_id": [7, "Acme"], "stage": {"id": 2, "display_name": "Won"}}),
                         {"partner_id": "Acme", "stage": "Won"})


if __name__ == "__main__":
    unittest.main()

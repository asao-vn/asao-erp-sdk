import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from asao_erp import routines as rt  # noqa: E402
from asao_erp import templates as tp  # noqa: E402
from asao_erp.__main__ import main, to_toml  # noqa: E402

HERE = Path(__file__).resolve().parent
FAKE = [sys.executable, str(HERE / "fake_cli.py")]
AGENT = [sys.executable, str(HERE / "fake_agent.py")]


def plan_data(output, **extra):
    data = {"profile": "lab", "output": str(output), "agent": "none", "binary": FAKE, "routine": [
        {"id": "ban-hang", "title": "Bán hàng hôm qua", "area": "sales", "every": "daily", "at": "07:30",
         "prompt": "Hôm qua bán thế nào?", "step": [
             {"name": "theo-ngay", "group": "sales.quotation.list", "by": ["date_order:month"], "aggregate": ["amount_total:sum"],
              "filter": [["date_order", ">=", "{yesterday}"], ["date_order", "<", "{today}"]]},
             {"name": "don", "read": "sales.quotation.list", "limit": 5}]},
        {"id": "ra-soat", "title": "Rà soát", "every": "weekly", "on": "mon", "at": "08:00",
         "step": [{"name": "ra-soat", "review": True, "period": "last_week"}]},
        {"id": "len-viec", "title": "Lên việc", "every": "daily", "at": "06:30", "writes": True, "step": [
            {"name": "moi", "ensure_task": {"name": "Việc mới", "project": "Vận hành", "recurring": True, "repeat_unit": "week"}},
            {"name": "cu", "ensure_task": {"name": "Việc cũ", "project": "Vận hành"}}]},
    ]}
    data.update(extra)
    return data


class RoutinesTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.cli_log = self.root / "cli.log"
        self.agent_log = self.root / "agent.log"
        os.environ["FAKE_CLI_LOG"] = str(self.cli_log)
        os.environ["FAKE_AGENT_LOG"] = str(self.agent_log)
        os.environ.pop("FAKE_AGENT_MODE", None)
        self.plan = rt.from_dict(plan_data(self.root / "out"))

    def tearDown(self):
        self.folder.cleanup()

    def calls(self):
        return [json.loads(line) for line in self.cli_log.read_text().splitlines()] if self.cli_log.exists() else []

    # ---- the file -------------------------------------------------------------------------------

    def test_a_file_is_refused_before_anything_runs(self):
        cases = [
            ({"output": "x", "routine": []}, "say which Odoo"),
            (plan_data("x", routine=[{"id": "a", "every": "hourly", "step": [{"read": "x.list"}]}]), "every"),
            (plan_data("x", routine=[{"id": "a", "step": [{"read": "x.list", "filter": [["d", "<", "{tomorrow}"]]}]}]), "unknown date"),
            (plan_data("x", routine=[{"id": "a", "step": [{"execute": "work.task.create", "values": {"name": "x"}}]}]), "writes = true"),
            (plan_data("x", routine=[{"id": "a", "step": [{"read": "x.list", "group": "x.list"}]}]), "exactly one"),
            (plan_data("x", routine=[{"id": "a", "every": "weekly", "on": "monday", "step": [{"read": "x.list"}]}]), "weekday"),
            (plan_data("x", routine=[{"id": "A b", "step": [{"read": "x.list"}]}]), "routine id"),
        ]
        for data, words in cases:
            with self.assertRaises(rt.RoutineError) as refused:
                rt.from_dict(data)
            self.assertIn(words, str(refused.exception))

    def test_every_template_loads_and_round_trips_through_toml(self):
        data = {"profile": "lab", "output": "x", "agent": ["agy1", "-p", "{prompt}"],
                "routine": [tp.as_routine(t, lang) for t in tp.TEMPLATES for lang in ("vi",)]}
        path = self.root / "routines.toml"
        path.write_text(to_toml(data), encoding="utf-8")
        plan = rt.load(path)
        self.assertEqual([r.id for r in plan.routines], [t["id"] for t in tp.TEMPLATES])
        self.assertEqual(plan.agent, ["agy1", "-p", "{prompt}"])
        self.assertTrue(plan.get("len-viec-dinh-ky").writes)

    def test_init_writes_a_file_that_loads(self):
        path = self.root / "r.toml"
        self.assertEqual(main(["routines", "init", "--profile", "lab", "--agent", "codex", "--file", str(path),
                               "--output", str(self.root / "out")]), 0)
        plan = rt.load(path)
        self.assertEqual(plan.agent, "codex")
        self.assertFalse(any(r.writes for r in plan.routines))  # writing templates only when asked by name
        self.assertEqual(main(["routines", "init", "--profile", "lab", "--file", str(path)]), 2)  # never overwritten

    # ---- dates ----------------------------------------------------------------------------------

    def test_dates_are_written_out_for_the_slot_day(self):
        day = date(2026, 3, 31)  # a Tuesday
        self.assertEqual(rt.render(["{today}", "{yesterday}", "{today-7}", "{week_start+4}", "{last_week_start}",
                                    "{month_start}", "{last_month_start}", "{next_month_start}", "{month_start-3m}",
                                    "{today+1m}", "x {today} y"], day),
                         ["2026-03-31", "2026-03-30", "2026-03-24", "2026-04-03", "2026-03-23", "2026-03-01",
                          "2026-02-01", "2026-04-01", "2025-12-01", "2026-04-30", "x 2026-03-31 y"])
        self.assertEqual(rt.period("last_week", day), (date(2026, 3, 23), date(2026, 3, 29)))
        self.assertEqual(rt.period("last_month", day), (date(2026, 2, 1), date(2026, 2, 28)))

    def test_slots_follow_the_schedule(self):
        def routine(**kw):
            return rt._routine({"id": "a", "step": [{"read": "x.list"}], **kw})
        sunday_noon = datetime(2026, 3, 29, 12, 0)
        self.assertEqual(routine(at="07:30").slot(sunday_noon), datetime(2026, 3, 29, 7, 30))
        self.assertEqual(routine(at="13:00").slot(sunday_noon), datetime(2026, 3, 28, 13, 0))
        self.assertEqual(routine(every="weekdays", at="08:00").slot(sunday_noon), datetime(2026, 3, 27, 8, 0))
        self.assertEqual(routine(every="weekly", on="mon", at="08:00").slot(sunday_noon), datetime(2026, 3, 23, 8, 0))
        self.assertEqual(routine(every="monthly", on=31, at="08:00").slot(datetime(2026, 3, 1)), datetime(2026, 2, 28, 8, 0))
        self.assertEqual(routine(every="monthly", on="last", at="08:00").slot(datetime(2026, 3, 31, 9)), datetime(2026, 3, 31, 8, 0))

    # ---- running --------------------------------------------------------------------------------

    def test_a_run_keeps_what_odoo_answered_and_a_computed_summary(self):
        result = self.plan.run("ban-hang", slot=datetime(2026, 10, 15, 7, 30))
        self.assertEqual(result["errors"], 0)
        group = result["steps"][0]
        self.assertEqual(group["filter"], [["date_order", ">=", "2026-10-14"], ["date_order", "<", "2026-10-15"]])
        self.assertEqual(group["totals"], {"count": 3, "amount_total:sum": 1500.0})
        self.assertEqual(result["steps"][1]["count"], 5)
        self.assertFalse(result["steps"][1]["complete"])  # a full page: there may be more
        folder = self.root / "out" / "ban-hang" / "2026-10-15"
        self.assertEqual(json.loads((folder / "result.json").read_text())["routine"], "ban-hang")
        self.assertIn("amount_total:sum: 1,500", (folder / "summary.md").read_text())
        self.assertEqual(result["agent"], {"status": "SKIPPED"})
        index = (self.root / "out" / "index.md").read_text()
        self.assertIn("[2026-10-15T07:30](ban-hang/2026-10-15/summary.md)", index)
        for guide in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            self.assertIn("python -m asao_erp routines run", (self.root / "out" / guide).read_text())
        self.assertTrue(all(c[0] in ("execute", "catalog") for c in self.calls()))  # the CLI only, and reads only

    def test_the_agent_reads_the_data_on_stdin_or_as_its_argument(self):
        result = self.plan.run("ban-hang", slot=datetime(2026, 10, 15, 7, 30), agent=AGENT)
        self.assertEqual(result["agent"]["status"], "OK")
        prompt = self.agent_log.read_text()
        self.assertIn("Hôm qua bán thế nào?", prompt)
        self.assertIn('"routine": "ban-hang"', prompt)
        folder = self.root / "out" / "ban-hang" / "2026-10-15"
        self.assertIn("Đã đọc", (folder / "analysis.md").read_text())
        self.assertEqual((folder / "prompt.md").read_text(), prompt)
        self.plan.run("ban-hang", slot=datetime(2026, 10, 16, 7, 30), agent=AGENT + ["--arg", "{prompt}"])
        self.assertIn("Hôm qua bán thế nào?", self.agent_log.read_text())

    def test_an_agent_that_fails_or_is_missing_leaves_the_result_intact(self):
        os.environ["FAKE_AGENT_MODE"] = "FAIL"
        result = self.plan.run("ban-hang", slot=datetime(2026, 10, 15, 7, 30), agent=AGENT)
        self.assertEqual((result["agent"]["status"], result["agent"]["exitCode"]), ("AGENT_FAILED", 3))
        missing = self.plan.run("ban-hang", slot=datetime(2026, 10, 15, 7, 30), agent=["no-such-agent-cli"])
        self.assertEqual(missing["agent"]["status"], "AGENT_NOT_FOUND")
        self.assertTrue((self.root / "out" / "ban-hang" / "2026-10-15" / "result.json").exists())

    def test_a_large_result_is_cut_and_says_so(self):
        data = {"steps": [{"name": "s", "rows": [{"id": i, "name": "x" * 50} for i in range(2000)]}]}
        text = rt._fit(data, 20_000, "vi")
        self.assertLess(len(text.encode()), 20_000)
        self.assertIn("cutForPrompt", text)

    def test_a_review_step_asks_odoo_cli_for_the_period(self):
        result = self.plan.run("ra-soat", slot=datetime(2026, 10, 12, 8, 0))
        self.assertEqual(result["steps"][0]["period"], {"from": "2026-10-05", "to": "2026-10-11"})
        call = self.calls()[-1]
        self.assertEqual(call[:2], ["review", "run"])
        self.assertEqual(call[call.index("--as-of") + 1], "2026-10-12")

    def test_ensure_task_creates_a_missing_task_once_and_leaves_an_open_one(self):
        result = self.plan.run("len-viec", slot=datetime(2026, 10, 15, 6, 30))
        self.assertEqual(result["steps"][0]["task"], {"id": 9, "created": True})
        self.assertEqual(result["steps"][1]["task"], {"id": 1, "created": False})
        creates = [c for c in self.calls() if "work.task.create" in c and c[0] == "execute"]
        self.assertEqual(len(creates), 1)
        self.assertEqual(json.loads(creates[0][creates[0].index("--values") + 1])["repeat_unit"], "week")

    def test_due_runs_each_slot_once_and_not_too_late(self):
        now = datetime(2026, 10, 15, 9, 0)  # a Thursday
        due = [r.id for r, _ in self.plan.due(now)]
        self.assertEqual(due, ["ban-hang", "len-viec"])  # Monday's review is more than three days old
        self.plan.run_due(now)
        self.assertEqual(self.plan.due(now), [])
        self.assertEqual([r.id for r, _ in self.plan.due(datetime(2026, 10, 16, 7, 31))], ["ban-hang", "len-viec"])

    def test_totals_are_per_currency_when_currencies_differ(self):
        groups = [{"currency_id": {"id": 1, "display_name": "USD"}, "amount_residual:sum": 10.5, "count": 1},
                  {"currency_id": {"id": 2, "display_name": "VND"}, "amount_residual:sum": 1000, "count": 2},
                  {"currency_id": {"id": 1, "display_name": "USD"}, "amount_residual:sum": 2, "count": 1}]
        self.assertEqual(rt._totals(groups, ["amount_residual:sum"]),
                         {"count": 4, "amount_residual:sum": {"USD": 12.5, "VND": 1000}})

    def test_install_prints_a_timer_that_calls_due(self):
        path = self.root / "r.toml"
        path.write_text(to_toml(plan_data(self.root / "out")), encoding="utf-8")
        from io import StringIO
        from contextlib import redirect_stdout
        printed = StringIO()
        with redirect_stdout(printed):
            self.assertEqual(main(["routines", "install", "--file", str(path), "--print"]), 0)
        self.assertIn("routines due --file", printed.getvalue())


if __name__ == "__main__":
    unittest.main()

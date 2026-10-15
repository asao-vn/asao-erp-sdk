"""Routines: the checks a business runs every day, week or month, and the agent that reads them.

A routine asks Odoo the same questions on a schedule (sales yesterday, invoices overdue, transfers
late, a books review of last month), keeps what Odoo answered, and hands the answer to the agent
the owner chose to read it: Claude Code, Codex, Gemini CLI, agy, any command, or none. The agent
only reads; what changes Odoo is written in the routine, never improvised by the agent.

Routines live in one file (TOML, or JSON), so a person, a notebook or an agent can write them::

    profile = "cong-ty"            # an odoo-cli profile (or organization = "..." for the asao CLI)
    output = "~/asao-routines"     # where every run is kept
    agent = "claude"               # claude | codex | gemini | agy | none | ["cmd", "arg", "{prompt}"]

    [[routine]]
    id = "cong-no-qua-han"
    title = "Công nợ quá hạn"
    area = "finance"
    every = "daily"                # daily | weekdays | weekly | monthly
    at = "07:30"
    prompt = "Khách nào nợ quá hạn nhiều nhất, khoản nào cần gọi hôm nay?"

      [[routine.step]]
      name = "theo-khach"
      group = "finance.invoice.list"
      by = ["partner_id"]
      aggregate = ["amount_residual:sum"]
      filter = [["move_type", "=", "out_invoice"], ["state", "=", "posted"],
                ["payment_state", "in", ["not_paid", "partial"]], ["invoice_date_due", "<", "{today}"]]

A step is one of: ``read`` (records), ``group`` (Odoo's aggregates), ``review`` (the books review of
a period), ``ensure_task`` (an Odoo task, often a recurring one, created once and never twice) and
``execute`` (any other write). A routine with a write step must say ``writes = true``.

Dates in filters and values are written as ``{today}``, ``{yesterday}``, ``{week_start}``,
``{last_week_start}``, ``{month_start}``, ``{last_month_start}`` and ``{next_month_start}``, moved by
days (``{today-7}``, ``{week_start+4}``) or months (``{month_start-3m}``). They are counted from the day
the routine's slot falls on, not the day it ran late.

Every run is kept in ``<output>/<routine>/<day>/``: ``result.json`` (what Odoo answered),
``summary.md`` (the counts and totals, computed, never written by a model), and, when an agent
reads it, ``prompt.md`` and ``analysis.md``. ``<output>/index.md`` lists each routine's latest run,
and ``AGENTS.md``/``CLAUDE.md``/``GEMINI.md`` there tell an interactive agent how to read them.
"""

from __future__ import annotations

import calendar
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

from .client import Client, ErpError

CADENCES = ("daily", "weekdays", "weekly", "monthly")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
STEP_KINDS = ("read", "group", "review", "ensure_task", "execute")
WRITE_KINDS = frozenset({"ensure_task", "execute"})
PERIODS = ("yesterday", "last_7_days", "last_week", "this_month", "last_month")
#: How late a missed slot still runs: a laptop off at 07:30 runs the daily routine when it wakes, but
#: a monthly one is not run three weeks late.
GRACE = {"daily": timedelta(hours=20), "weekdays": timedelta(hours=20), "weekly": timedelta(days=3),
         "monthly": timedelta(days=7)}
#: The agents a routine can name. A prompt goes on standard input unless the command holds {prompt}.
AGENTS = {
    "claude": ["claude", "-p", "--output-format", "text"],
    "codex": ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "--output-last-message",
              "{answer_file}", "-"],
    "gemini": ["gemini", "--skip-trust", "-p", "Follow the instructions given on standard input."],
    "agy": ["agy", "-p", "{prompt}"],
}
#: An argument holds at most 128 KiB on Linux; a prompt given as one is cut well below that.
ARGUMENT_PROMPT_LIMIT = 100_000
STDIN_PROMPT_LIMIT = 400_000
_PLACEHOLDER = re.compile(r"\{(today|yesterday|week_start|last_week_start|month_start|last_month_start|"
                          r"next_month_start)(?:([+-])(\d+)(m?))?\}")


class RoutineError(ValueError):
    """A routines file that cannot run as written: the message names the routine and the field."""


@dataclass
class Step:
    name: str
    kind: str
    operation: str | None = None
    filter: list | None = None
    by: list[str] = field(default_factory=list)
    aggregate: list[str] = field(default_factory=list)
    limit: int = 50
    order: str | None = None
    period: str | None = None
    values: dict | None = None
    id: int | None = None
    note: str = ""


@dataclass
class Routine:
    id: str
    title: str
    every: str
    steps: list[Step]
    area: str = ""
    at: str = "07:30"
    on: str | int | None = None
    prompt: str = ""
    agent: Any = None
    writes: bool = False
    enabled: bool = True

    def slot(self, now: datetime) -> datetime:
        """The latest moment at or before ``now`` this routine was scheduled for."""
        hour, minute = (int(part) for part in self.at.split(":"))
        today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if self.every == "daily":
            return today if today <= now else today - timedelta(days=1)
        if self.every == "weekdays":
            candidate = today if today <= now else today - timedelta(days=1)
            while candidate.weekday() >= 5:
                candidate -= timedelta(days=1)
            return candidate
        if self.every == "weekly":
            weekday = WEEKDAYS.index(str(self.on or "mon"))
            candidate = today - timedelta(days=(today.weekday() - weekday) % 7)
            return candidate if candidate <= now else candidate - timedelta(days=7)
        year, month = now.year, now.month
        for _ in range(2):
            candidate = today.replace(year=year, month=month, day=_month_day(year, month, self.on))
            if candidate <= now:
                return candidate
            year, month = (year - 1, 12) if month == 1 else (year, month - 1)
        raise AssertionError("unreachable")


@dataclass
class Plan:
    routines: list[Routine]
    profile: str | None = None
    organization: str | None = None
    connection: str | None = None
    output: Path = Path("~/asao-routines")
    agent: Any = "none"
    language: str = "vi"
    agent_timeout: float = 900
    allow_unverified: bool = False
    binary: Any = None
    source: Path | None = None

    def __post_init__(self):
        self.output = Path(os.path.expanduser(str(self.output)))

    # ---- choosing ---------------------------------------------------------------------------

    def get(self, routine_id: str) -> Routine:
        for routine in self.routines:
            if routine.id == routine_id:
                return routine
        raise RoutineError(f"no routine {routine_id!r}; the file has: {', '.join(r.id for r in self.routines)}")

    def due(self, now: datetime | None = None) -> list[tuple[Routine, datetime]]:
        """The routines whose latest slot has come, has not run yet, and is not too late to run."""
        now = now or datetime.now()
        found = []
        for routine in self.routines:
            if not routine.enabled:
                continue
            slot = routine.slot(now)
            if now - slot > GRACE[routine.every]:
                continue
            if self._last_slot(routine) == slot.isoformat(timespec="minutes"):
                continue
            found.append((routine, slot))
        return found

    # ---- running ----------------------------------------------------------------------------

    def run(self, routine: Routine | str, *, slot: datetime | None = None, agent: Any = None,
            client: Client | None = None) -> dict:
        """Run one routine now (for ``slot``, its latest by default) and keep what it found."""
        routine = self.get(routine) if isinstance(routine, str) else routine
        slot = slot or routine.slot(datetime.now())
        erp = client or self.client(writes=routine.writes)
        day = slot.date()
        started = time.monotonic()
        result: dict[str, Any] = {
            "routine": routine.id, "title": routine.title, "area": routine.area, "every": routine.every,
            "slot": slot.isoformat(timespec="minutes"), "ranAt": datetime.now().isoformat(timespec="seconds"),
            "source": self.organization and f"asao organization {self.organization}" or f"odoo-cli profile {self.profile}",
            "steps": [],
        }
        meanings: dict[str, list[dict]] = {}
        for step in routine.steps:
            result["steps"].append(self._run_step(erp, step, day, meanings))
        result["errors"] = sum(1 for s in result["steps"] if s["status"] == "ERROR")
        result["seconds"] = round(time.monotonic() - started, 1)

        folder = self.output / routine.id / day.isoformat()
        folder.mkdir(parents=True, exist_ok=True)
        _write(folder / "result.json", json.dumps(result, ensure_ascii=False, indent=1, default=str))
        _write(folder / "summary.md", summary(result, self.language))
        chosen = agent if agent is not None else (routine.agent if routine.agent is not None else self.agent)
        result["agent"] = analyse(chosen, prompt_for(routine, result, meanings, self.language), folder, self.agent_timeout)
        _write(folder / "result.json", json.dumps(result, ensure_ascii=False, indent=1, default=str))
        self._remember(routine, result, folder)
        self.write_guides()
        return result

    def run_due(self, now: datetime | None = None, *, agent: Any = None) -> list[dict]:
        """Run every routine that is due, in file order; one that fails does not stop the others."""
        results = []
        for routine, slot in self.due(now):
            try:
                results.append(self.run(routine, slot=slot, agent=agent))
            except Exception as failure:  # noqa: BLE001 - a scheduler must go on to the next routine
                results.append({"routine": routine.id, "slot": slot.isoformat(timespec="minutes"),
                                "failed": f"{failure.__class__.__name__}: {failure}"})
        return results

    def client(self, *, writes: bool = False) -> Client:
        if self.organization:
            return Client(organization=self.organization, connection=self.connection, binary=self.binary,
                          allow_writes=writes)
        return Client(profile=self.profile, binary=self.binary, allow_unverified=self.allow_unverified,
                      allow_writes=writes)

    # ---- what a run leaves ------------------------------------------------------------------

    def _run_step(self, erp: Client, step: Step, day: date, meanings: dict) -> dict:
        done: dict[str, Any] = {"name": step.name, "kind": step.kind, "operation": step.operation, "asked": step.note}
        try:
            domain = render(step.filter, day) if step.filter else None
            if domain:
                done["filter"] = domain
            if step.operation and step.kind in ("read", "group") and step.operation not in meanings:
                meanings[step.operation] = _meaning(erp, step.operation)
            if step.kind == "read":
                rows = erp.read(step.operation, domain, limit=step.limit, order=step.order, id=step.id)
                done.update(rows=rows, count=len(rows), complete=len(rows) < step.limit)
            elif step.kind == "group":
                groups = erp.group(step.operation, by=step.by, aggregate=step.aggregate, filter=domain,
                                   limit=step.limit, order=step.order)
                done.update(groups=groups, count=len(groups), totals=_totals(groups, step.aggregate))
            elif step.kind == "review":
                start, end = period(step.period or "last_month", day)
                report = erp.review(start, end, as_of=day)
                done.update(period={"from": start.isoformat(), "to": end.isoformat()}, report=report,
                            count=len(report.get("findings") or []))
            elif step.kind == "ensure_task":
                done.update(_ensure_task(erp, render(step.values, day)))
            elif step.kind == "execute":
                done.update(data=erp.execute(step.operation, id=step.id, values=render(step.values, day)))
            done["status"] = "OK"
        except ErpError as refused:
            done.update(status="ERROR", error={"code": refused.code, "message": refused.message,
                                               "remediation": refused.remediation})
        return done

    def _state_file(self, routine: Routine) -> Path:
        return self.output / routine.id / "latest.json"

    def _last_slot(self, routine: Routine) -> str | None:
        try:
            return json.loads(self._state_file(routine).read_text(encoding="utf-8")).get("slot")
        except (OSError, ValueError):
            return None

    def _remember(self, routine: Routine, result: dict, folder: Path) -> None:
        _write(self._state_file(routine), json.dumps({
            "slot": result["slot"], "ranAt": result["ranAt"], "folder": str(folder), "errors": result["errors"],
            "agent": (result.get("agent") or {}).get("status")}, ensure_ascii=False, indent=1))

    def write_guides(self) -> None:
        """``index.md`` (each routine's latest run) and the guide an interactive agent reads first."""
        self.output.mkdir(parents=True, exist_ok=True)
        vi = self.language == "vi"
        lines = ["# " + ("Việc định kỳ" if vi else "Routines"), ""]
        lines += [("| Việc | Lĩnh vực | Lịch | Lần chạy gần nhất | Lỗi | Phân tích |" if vi else
                   "| Routine | Area | Schedule | Latest run | Errors | Analysis |"), "|---|---|---|---|---|---|"]
        for routine in self.routines:
            try:
                latest = json.loads(self._state_file(routine).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                latest = {}
            run = "-"
            if latest.get("folder"):
                run = f"[{latest['slot']}]({Path(latest['folder']).relative_to(self.output)}/summary.md)"
            lines.append(f"| {routine.title} (`{routine.id}`) | {routine.area} | {schedule_text(routine, vi)} | {run} | "
                         f"{latest.get('errors', '-')} | {latest.get('agent') or '-'} |")
        _write(self.output / "index.md", "\n".join(lines) + "\n")
        guide = _GUIDE_VI if vi else _GUIDE_EN
        source = str(self.source) if self.source else "routines.toml"
        text = guide.format(source=source, output=self.output)
        for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            _write(self.output / name, text)


# ---- loading ----------------------------------------------------------------------------------


def load(path: str | os.PathLike) -> Plan:
    """A routines file (TOML or JSON) as a Plan, checked before anything runs."""
    path = Path(path).expanduser()
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
    else:
        try:
            import tomllib
        except ModuleNotFoundError:  # Python 3.10
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ModuleNotFoundError as missing:
                raise RoutineError("reading TOML needs Python 3.11, or pip install tomli; a .json file works anywhere") from missing
        data = tomllib.loads(text)
    plan = from_dict(data)
    plan.source = path.resolve()
    return plan


def from_dict(data: dict) -> Plan:
    if not data.get("profile") and not data.get("organization"):
        raise RoutineError("say which Odoo: profile = \"...\" (odoo-cli) or organization = \"...\" (asao CLI)")
    routines = [_routine(item) for item in data.get("routine") or data.get("routines") or []]
    seen = set()
    for routine in routines:
        if routine.id in seen:
            raise RoutineError(f"two routines are called {routine.id!r}")
        seen.add(routine.id)
    return Plan(routines=routines, profile=data.get("profile"), organization=data.get("organization"),
                connection=data.get("connection"), output=Path(data.get("output", "~/asao-routines")),
                agent=data.get("agent", "none"), language=data.get("language", "vi"),
                agent_timeout=float(data.get("agent_timeout", 900)),
                allow_unverified=bool(data.get("allow_unverified", False)), binary=data.get("binary"))


def _routine(item: dict) -> Routine:
    rid = str(item.get("id") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", rid):
        raise RoutineError(f"routine id {rid!r}: lower-case letters, digits and dashes")
    every = item.get("every", "daily")
    if every not in CADENCES:
        raise RoutineError(f"{rid}: every = {every!r}; one of {', '.join(CADENCES)}")
    at = str(item.get("at", "07:30"))
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
        raise RoutineError(f"{rid}: at = {at!r}; a time as HH:MM")
    on = item.get("on")
    if every == "weekly" and str(on or "mon") not in WEEKDAYS:
        raise RoutineError(f"{rid}: on = {on!r}; a weekday, one of {', '.join(WEEKDAYS)}")
    if every == "monthly" and on not in (None, "last") and not (isinstance(on, int) and 1 <= on <= 31):
        raise RoutineError(f"{rid}: on = {on!r}; a day of the month (1-31) or \"last\"")
    steps = [_step(rid, raw) for raw in item.get("step") or item.get("steps") or []]
    if not steps:
        raise RoutineError(f"{rid}: a routine needs at least one step")
    writes = bool(item.get("writes", False))
    writing = [s.name for s in steps if s.kind in WRITE_KINDS]
    if writing and not writes:
        raise RoutineError(f"{rid}: steps {', '.join(writing)} change Odoo; say writes = true to let this routine write")
    return Routine(id=rid, title=item.get("title", rid), every=every, steps=steps, area=item.get("area", ""), at=at,
                   on=on, prompt=item.get("prompt", ""), agent=item.get("agent"), writes=writes,
                   enabled=bool(item.get("enabled", True)))


def _step(rid: str, raw: dict) -> Step:
    kinds = [k for k in STEP_KINDS if k in raw]
    if len(kinds) != 1:
        raise RoutineError(f"{rid}: a step names exactly one of {', '.join(STEP_KINDS)}; got {kinds or 'none'}")
    kind = kinds[0]
    name = str(raw.get("name") or kind)
    operation = raw[kind] if kind in ("read", "group", "execute") else ("work.task.create" if kind == "ensure_task" else None)
    if kind in ("read", "group", "execute") and not isinstance(operation, str):
        raise RoutineError(f"{rid}.{name}: {kind} = \"<operation id>\"")
    if kind == "review" and raw.get("period", "last_month") not in PERIODS:
        raise RoutineError(f"{rid}.{name}: period = {raw.get('period')!r}; one of {', '.join(PERIODS)}")
    values = raw[kind] if kind == "ensure_task" else raw.get("values")
    if kind == "ensure_task" and not (isinstance(values, dict) and values.get("name") and values.get("project")):
        raise RoutineError(f"{rid}.{name}: ensure_task = {{ name = \"...\", project = \"...\", ... }}")
    for text in _strings((raw.get("filter"), values)):
        for bad in re.findall(r"\{[^{}]*\}", text):
            if not _PLACEHOLDER.fullmatch(bad):
                raise RoutineError(f"{rid}.{name}: unknown date {bad}")
    return Step(name=name, kind=kind, operation=operation, filter=raw.get("filter"), by=list(raw.get("by") or []),
                aggregate=list(raw.get("aggregate") or []), limit=int(raw.get("limit", 50)), order=raw.get("order"),
                period=raw.get("period"), values=values, id=raw.get("id"), note=raw.get("note", ""))


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


# ---- dates ------------------------------------------------------------------------------------


def _month_day(year: int, month: int, on: Any) -> int:
    last = calendar.monthrange(year, month)[1]
    if on in (None, "first"):
        return 1
    if on == "last":
        return last
    return min(int(on), last)


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return day.replace(year=year, month=month + 1, day=min(day.day, calendar.monthrange(year, month + 1)[1]))


def anchors(day: date) -> dict[str, date]:
    month_start = day.replace(day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    next_month_start = (month_start + timedelta(days=32)).replace(day=1)
    week_start = day - timedelta(days=day.weekday())
    return {"today": day, "yesterday": day - timedelta(days=1), "week_start": week_start,
            "last_week_start": week_start - timedelta(days=7), "month_start": month_start,
            "last_month_start": last_month_start, "next_month_start": next_month_start}


def render(value: Any, day: date) -> Any:
    """Filters and values with their {today}-style dates written out for ``day``."""
    if isinstance(value, str):
        marks = anchors(day)

        def one(match):
            moved = marks[match.group(1)]
            if match.group(2):
                amount = int(match.group(3)) * (1 if match.group(2) == "+" else -1)
                moved = _add_months(moved, amount) if match.group(4) else moved + timedelta(days=amount)
            return moved.isoformat()
        return _PLACEHOLDER.sub(one, value)
    if isinstance(value, dict):
        return {key: render(item, day) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [render(item, day) for item in value]
    return value


def period(name: str, day: date) -> tuple[date, date]:
    """The first and last day of a review period, seen from ``day``."""
    marks = anchors(day)
    if name == "yesterday":
        return marks["yesterday"], marks["yesterday"]
    if name == "last_7_days":
        return day - timedelta(days=7), marks["yesterday"]
    if name == "last_week":
        return marks["last_week_start"], marks["week_start"] - timedelta(days=1)
    if name == "this_month":
        return marks["month_start"], day
    return marks["last_month_start"], marks["month_start"] - timedelta(days=1)


def schedule_text(routine: Routine, vi: bool = True) -> str:
    if routine.every == "daily":
        return f"{'hằng ngày' if vi else 'daily'} {routine.at}"
    if routine.every == "weekdays":
        return f"{'thứ 2-6' if vi else 'weekdays'} {routine.at}"
    if routine.every == "weekly":
        names = ("thứ 2", "thứ 3", "thứ 4", "thứ 5", "thứ 6", "thứ 7", "chủ nhật") if vi else WEEKDAYS
        return f"{'hằng tuần' if vi else 'weekly'} {names[WEEKDAYS.index(str(routine.on or 'mon'))]} {routine.at}"
    day = routine.on or 1
    if vi:
        return f"hằng tháng {'ngày cuối' if day == 'last' else f'ngày {day}'} {routine.at}"
    return f"monthly on {'the last day' if day == 'last' else f'day {day}'} {routine.at}"


# ---- steps that write -------------------------------------------------------------------------

_OPEN_TASK = ["01_in_progress", "02_changes_requested", "03_approved", "04_waiting_normal"]


def _ensure_task(erp: Client, values: dict) -> dict:
    """An open task with this name in this project, created only when there is none (a recurring one
    stays open: Odoo opens the next occurrence when one is closed)."""
    project = values["project"]
    domain = [["name", "=", values["name"]], ["state", "in", _OPEN_TASK],
              ["project_id", "=", project] if isinstance(project, int) else ["project_id.name", "=", project]]
    existing = erp.read("work.task.list", domain, limit=1)
    if existing:
        return {"task": {"id": existing[0]["id"], "created": False}}
    created = erp.execute("work.task.create", values=values) or {}
    return {"task": {"id": created.get("id"), "created": True}}


# ---- reading the result -----------------------------------------------------------------------


def _meaning(erp: Client, operation: str) -> list[dict]:
    """What each field an operation returns means, from the catalog, for the agent's prompt."""
    try:
        described = erp.describe(operation)
    except ErpError:
        return []
    return [{"name": f.get("name"), "providerField": f.get("providerField"), "description": f.get("description")}
            for f in described.get("outputs") or []]


def _totals(groups: list[dict], aggregate: Sequence[str]) -> dict:
    """The count, and each summed aggregate; a sum of amounts in several currencies is given per
    currency, never added up into one figure that means nothing."""
    totals: dict[str, Any] = {"count": sum(g.get("count") or 0 for g in groups)}
    currencies = {_label(g.get("currency_id")) for g in groups if "currency_id" in g}
    for spec in aggregate:
        if not spec.endswith(":sum"):
            continue
        if len(currencies) > 1:
            per = {}
            for g in groups:
                if isinstance(g.get(spec), (int, float)):
                    key = _label(g.get("currency_id"))
                    per[key] = round(per.get(key, 0) + g[spec], 2)
            totals[spec] = per
        else:
            values = [g.get(spec) for g in groups if isinstance(g.get(spec), (int, float))]
            if values:
                totals[spec] = round(sum(values), 2)
    return totals


def _label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("display_name") or value.get("value") or value.get("id"))
    if isinstance(value, list) and len(value) == 2 and isinstance(value[1], str):
        return value[1]
    return "-" if value in (None, False) else str(value)


#: The fields a summary line shows after a record's name, when the record has them.
_ROW_DETAILS = ("partner", "project", "user_id", "total_amount", "amount", "amount_residual", "expected_revenue",
                "invoice_date_due", "due_on", "scheduled_date", "date", "payment_status", "state", "source_document")


def _cell(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:,.2f}".rstrip("0").rstrip(".") if isinstance(value, float) else f"{value:,}"
    return _label(value)


def summary(result: dict, language: str = "vi") -> str:
    """The run in figures: per step its count, totals and first rows. Computed, never generated."""
    vi = language == "vi"
    lines = [f"# {result['title']}", "",
             f"{'Lịch' if vi else 'Slot'}: {result['slot']} · {'chạy lúc' if vi else 'ran at'} {result['ranAt']} · "
             f"{result['source']}", ""]
    for step in result["steps"]:
        lines.append(f"## {step['name']} ({step['kind']}{' ' + step['operation'] if step.get('operation') else ''})")
        if step.get("asked"):
            lines.append(f"_{step['asked']}_")
        if step["status"] == "ERROR":
            error = step["error"]
            lines += [f"**{'Lỗi' if vi else 'Error'}** {error['code']}: {error['message']}", ""]
            continue
        if step["kind"] == "group":
            totals = step.get("totals") or {}
            lines.append(", ".join(f"{k}: " + (" + ".join(f"{_cell(n)} {c}" for c, n in v.items()) if isinstance(v, dict) else _cell(v))
                                   for k, v in totals.items()))
            first = step["groups"][0] if step["groups"] else {}
            keys = [k for k in first if k != "count" and ":" not in k or k.split(":")[-1] in ("day", "week", "month", "quarter", "year")]
            keys += [k for k in first if k != "count" and k not in keys]
            if keys:
                lines += ["", "| " + " | ".join(keys + ["count"]) + " |", "|" + "---|" * (len(keys) + 1)]
                for group in step["groups"][:20]:
                    lines.append("| " + " | ".join(_cell(group.get(k)) for k in keys) + f" | {group.get('count')} |")
        elif step["kind"] == "read":
            more = "" if step.get("complete") else (" (hoặc hơn)" if vi else " (or more)")
            lines.append(f"{step['count']} {'bản ghi' if vi else 'records'}{more}")
            for row in step["rows"][:10]:
                details = [_cell(row[k]) for k in _ROW_DETAILS if row.get(k) not in (None, False, "", [])]
                lines.append(f"- #{row.get('id')} {_label(row.get('name') or row.get('display_name'))}"
                             + (f" · {' · '.join(details[:5])}" if details else ""))
        elif step["kind"] == "review":
            report = step["report"]
            lines.append(f"{step['period']['from']} → {step['period']['to']}: {step['count']} "
                         f"{'phát hiện' if vi else 'findings'} {json.dumps(report.get('counts') or {}, ensure_ascii=False)}")
            for finding in (report.get("findings") or [])[:10]:
                lines.append(f"- [{finding.get('severity')}] {finding.get('check')} {finding.get('title')}")
        elif step["kind"] == "ensure_task":
            task = step["task"]
            lines.append(("Đã tạo" if vi else "Created") if task["created"] else ("Đã có sẵn" if vi else "Already there"))
            lines[-1] += f" #{task['id']}"
        lines.append("")
    return "\n".join(lines)


def prompt_for(routine: Routine, result: dict, meanings: dict, language: str = "vi") -> str:
    vi = language == "vi"
    head = (_PROMPT_VI if vi else _PROMPT_EN).format(
        title=routine.title, area=routine.area or "-", schedule=schedule_text(routine, vi), slot=result["slot"],
        ran=result["ranAt"], source=result["source"],
        ask=routine.prompt or ("Tóm tắt điều đáng chú ý." if vi else "Summarise what deserves attention."))
    steps = []
    for step in routine.steps:
        meaning = meanings.get(step.operation or "") or []
        fields = "; ".join(f"{m['name']}" + (f" (= {m['providerField']})" if m["providerField"] != m["name"] else "")
                           + f": {m['description']}" for m in meaning)
        steps.append(f"- {step.name}: {step.kind} {step.operation or ''}. {step.note}" + (f"\n  {fields}" if fields else ""))
    return head + "\n".join(steps) + "\n\n" + ("Dữ liệu" if vi else "Data") + " (JSON):\n"


def analyse(agent: Any, prompt: str, folder: Path, timeout: float) -> dict:
    """Ask the chosen agent to read the run; its answer is kept in analysis.md. It is given no tools."""
    if agent in (None, "", "none", False):
        return {"status": "SKIPPED"}
    data = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    command = list(AGENTS[agent]) if isinstance(agent, str) and agent in AGENTS else (
        agent if isinstance(agent, list) else [agent])
    if not shutil.which(command[0]):
        return {"status": "AGENT_NOT_FOUND", "command": command[0]}
    as_argument = any("{prompt}" in part for part in command)
    limit = ARGUMENT_PROMPT_LIMIT if as_argument else STDIN_PROMPT_LIMIT
    text = prompt + _fit(data, limit - len(prompt.encode()), language_note=("vi" if "Dữ liệu" in prompt else "en"))
    _write(folder / "prompt.md", text)
    answer_file = folder / "agent-answer.txt"
    args = [part.replace("{prompt}", text).replace("{answer_file}", str(answer_file)).replace("{folder}", str(folder))
            for part in command]
    started = time.monotonic()
    try:
        done = subprocess.run(args, input=None if as_argument else text, capture_output=True, text=True,
                              timeout=timeout, cwd=folder)
    except subprocess.TimeoutExpired:
        return {"status": "AGENT_TIMEOUT", "command": command[0], "seconds": timeout}
    answer = answer_file.read_text(encoding="utf-8") if answer_file.exists() else done.stdout
    answer_file.unlink(missing_ok=True)
    _write(folder / "agent.log", (done.stderr or "")[-20000:])
    if done.returncode != 0 or not answer.strip():
        return {"status": "AGENT_FAILED", "command": command[0], "exitCode": done.returncode,
                "seconds": round(time.monotonic() - started, 1)}
    _write(folder / "analysis.md", answer.strip() + "\n")
    return {"status": "OK", "command": command[0], "seconds": round(time.monotonic() - started, 1)}


def _fit(data: dict, budget: int, language_note: str) -> str:
    """The run as JSON within ``budget`` bytes: rows are cut from the end of the longest step first,
    and the cut is said, so the agent never mistakes a page for the whole."""
    text = json.dumps(data, ensure_ascii=False, default=str)
    while len(text.encode()) > budget:
        longest = max((s for s in data["steps"] if s.get("rows") or s.get("groups")),
                      key=lambda s: len(s.get("rows") or s.get("groups") or []), default=None)
        if longest is None:
            return text[: max(budget, 0) // 4] + "\n[...]"
        key = "rows" if longest.get("rows") else "groups"
        keep = len(longest[key]) // 2
        longest[key] = longest[key][:keep]
        longest["cutForPrompt"] = (f"chỉ giữ {keep} dòng đầu; xem result.json" if language_note == "vi"
                                   else f"only the first {keep} kept; see result.json")
        text = json.dumps(data, ensure_ascii=False, default=str)
    return text + "\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


_PROMPT_VI = """Bạn là trợ lý phân tích vận hành của một doanh nghiệp dùng Odoo. Dưới đây là kết quả của việc định kỳ \
"{title}" (lĩnh vực: {area}; lịch: {schedule}; kỳ: {slot}; chạy lúc {ran}), lấy từ Odoo qua {source}.

Chủ doanh nghiệp muốn biết: {ask}

Quy tắc:
- Chỉ dựa trên dữ liệu bên dưới. Không bịa số, không đoán phần dữ liệu không có. Nhắc tới bản ghi nào thì ghi số chứng từ hoặc id của nó.
- Bước nào lỗi hoặc dữ liệu bị cắt (cutForPrompt), hoặc "complete" là false (còn bản ghi chưa lấy), thì nói rõ.
- Không đề nghị tự sửa Odoo. Việc cần làm thì liệt kê để người duyệt.
- Trả lời bằng tiếng Việt, Markdown, ngắn gọn: "Tóm tắt" (tối đa 3 dòng), "Cần xem ngay", "Việc đề xuất".

Các bước và ý nghĩa các trường Odoo trả về:
"""

_PROMPT_EN = """You are the operations analyst of a business that runs Odoo. Below is the result of the routine \
"{title}" (area: {area}; schedule: {schedule}; slot: {slot}; ran at {ran}), read from Odoo through {source}.

The owner wants to know: {ask}

Rules:
- Use only the data below. Never invent a figure or guess at data that is not there. Name a record by its number or id.
- Say so when a step failed, when data was cut (cutForPrompt), or when "complete" is false (more records exist).
- Never propose changing Odoo yourself. List what should be done, for a person to approve.
- Answer in English, Markdown, briefly: "Summary" (3 lines at most), "Look at now", "Suggested actions".

The steps, and what the fields Odoo returns mean:
"""

_GUIDE_VI = """# Việc định kỳ của doanh nghiệp (đọc trước khi trả lời)

Thư mục này chứa kết quả các việc định kỳ chạy trên Odoo qua odoo-cli và SDK asao-erp.
Danh sách việc và lịch nằm trong `{source}`.

- `index.md`: mỗi việc và lần chạy gần nhất.
- `<việc>/<ngày>/result.json`: đúng những gì Odoo trả về; `summary.md`: số đếm và tổng (máy tính, không phải AI viết);
  `analysis.md`: phân tích của agent ở lần chạy đó.

Khi được hỏi về tình hình hôm nay, tuần này hay tháng này:
1. Đọc `index.md`, rồi `summary.md` và `result.json` của các lần chạy liên quan. Chỉ dựa trên các file đó.
2. Cần số mới hơn thì chạy lại: `python -m asao_erp routines run <việc> --file {source}`.
3. Không tự sửa dữ liệu Odoo. Một việc cần ghi vào Odoo phải được viết thành bước trong `{source}` (writes = true) và người duyệt.

Thư mục: {output}
"""

_GUIDE_EN = """# The business's routines (read before answering)

This folder holds what the business's routines found in Odoo, through odoo-cli and the asao-erp SDK.
The routines and their schedules are in `{source}`.

- `index.md`: every routine and its latest run.
- `<routine>/<day>/result.json`: exactly what Odoo answered; `summary.md`: counts and totals (computed, not written
  by a model); `analysis.md`: the agent's reading of that run.

When asked how things stand today, this week or this month:
1. Read `index.md`, then the `summary.md` and `result.json` of the runs that matter. Rely on those files only.
2. For newer figures, run again: `python -m asao_erp routines run <routine> --file {source}`.
3. Never change Odoo yourself. A change belongs in `{source}` as a step (writes = true), for a person to approve.

Folder: {output}
"""

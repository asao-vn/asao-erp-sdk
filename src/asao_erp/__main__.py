"""asao-erp routines: the business's daily, weekly and monthly checks, from a terminal or a scheduler.

    asao-erp routines templates                      what each starter routine asks Odoo and gets back
    asao-erp routines init --profile cong-ty --agent claude [--template ID ...]
    asao-erp routines list                           the routines of the file and when each runs next
    asao-erp routines run cong-no-qua-han [--agent codex|none]
    asao-erp routines due                            run what is due (what the scheduler calls)
    asao-erp routines install [--every 15]           a timer that calls `due` (systemd, cron or launchd)
    asao-erp routines uninstall
    asao-erp routines status                         each routine's latest run

The file is ./routines.toml, or --file, or $ASAO_ROUTINES.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import routines as rt
from . import templates as tp

UNIT = "asao-erp-routines"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="asao-erp", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="group", required=True)
    group = commands.add_parser("routines", help="daily, weekly and monthly checks on Odoo")
    verbs = group.add_subparsers(dest="verb", required=True)

    def with_file(p):
        p.add_argument("--file", default=os.environ.get("ASAO_ROUTINES", "routines.toml"))
        return p

    templates = verbs.add_parser("templates", help="the starter routines")
    templates.add_argument("--area")
    templates.add_argument("--every", choices=rt.CADENCES)
    templates.add_argument("--language", default="vi", choices=["vi", "en"])
    templates.add_argument("--json", action="store_true")
    init = with_file(verbs.add_parser("init", help="write a routines file from the templates"))
    target = init.add_mutually_exclusive_group(required=True)
    target.add_argument("--profile")
    target.add_argument("--organization")
    init.add_argument("--template", action="append", help="a template id (repeatable); all read-only ones by default")
    init.add_argument("--agent", default="none", help="claude, codex, gemini, agy, none, or a command line with {prompt}")
    init.add_argument("--output", default="~/asao-routines")
    init.add_argument("--language", default="vi", choices=["vi", "en"])
    init.add_argument("--force", action="store_true")
    with_file(verbs.add_parser("list", help="the routines and their next run"))
    run = with_file(verbs.add_parser("run", help="run one routine now"))
    run.add_argument("routine")
    run.add_argument("--agent", help="override the agent for this run (none to skip)")
    run.add_argument("--day", help="run for an earlier day (YYYY-MM-DD), as if its slot were now")
    due = with_file(verbs.add_parser("due", help="run every routine that is due"))
    due.add_argument("--agent")
    install = with_file(verbs.add_parser("install", help="call `due` on a timer"))
    install.add_argument("--every", type=int, default=15, help="minutes between checks (default 15)")
    install.add_argument("--print", action="store_true", help="show what would be installed, change nothing")
    verbs.add_parser("uninstall", help="remove the timer")
    with_file(verbs.add_parser("status", help="each routine's latest run"))

    options = parser.parse_args(argv)
    try:
        return VERBS[options.verb](options)
    except (rt.RoutineError, FileNotFoundError, KeyError) as problem:
        print(f"asao-erp: {problem}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as failed:
        print(f"asao-erp: {shlex.join(failed.cmd)} failed (exit {failed.returncode})", file=sys.stderr)
        return 1


def _templates(options) -> int:
    chosen = [t for t in tp.TEMPLATES if (not options.area or t["area"] == options.area)
              and (not options.every or t["every"] == options.every)]
    if options.json:
        print(json.dumps(chosen, ensure_ascii=False, indent=1))
        return 0
    lang = options.language
    for cadence in rt.CADENCES:
        group = [t for t in chosen if t["every"] == cadence]
        if not group:
            continue
        print(f"\n== {cadence}")
        for t in group:
            routine = rt._routine(tp.as_routine(t, lang))
            flag = "  [ghi vào Odoo]" if t.get("writes") and lang == "vi" else ("  [writes]" if t.get("writes") else "")
            print(f"\n{t['id']}  ({tp.AREAS[t['area']][lang]}, {rt.schedule_text(routine, lang == 'vi')}){flag}")
            print(f"  {t['title'][lang]}")
            print(f"  {'Odoo làm' if lang == 'vi' else 'Odoo does'}: {t['does'][lang]}")
            print(f"  {'Odoo trả về' if lang == 'vi' else 'Odoo returns'}: {t['returns'][lang]}")
            print(f"  {'Thao tác' if lang == 'vi' else 'Operations'}: "
                  f"{', '.join(sorted({s.operation or 'odoo-cli review run' for s in routine.steps}))}")
    return 0


def _init(options) -> int:
    path = Path(options.file)
    if path.exists() and not options.force:
        raise rt.RoutineError(f"{path} exists; --force to replace it")
    ids = options.template or [t["id"] for t in tp.TEMPLATES if not t.get("writes")]
    data = {"profile": options.profile} if options.profile else {"organization": options.organization}
    agent = options.agent
    if agent not in rt.AGENTS and agent != "none" and " " in agent:
        agent = shlex.split(agent)
    data.update(output=options.output, agent=agent, language=options.language,
                routine=[tp.as_routine(tp.get(i), options.language) for i in ids])
    plan = rt.from_dict(data)  # refuse to write a file that would not load
    text = to_toml(data) if path.suffix != ".json" else json.dumps(data, ensure_ascii=False, indent=1)
    path.write_text(text, encoding="utf-8")
    print(f"{path}: {len(plan.routines)} routines; results in {plan.output}")
    return 0


def _list(options) -> int:
    plan = rt.load(options.file)
    now = datetime.now()
    for routine in plan.routines:
        nxt = _next(routine, now)
        print(f"{routine.id:24} {routine.area:10} {rt.schedule_text(routine, plan.language == 'vi'):28} "
              f"next {nxt:%Y-%m-%d %H:%M}{'' if routine.enabled else '  (disabled)'}{'  writes' if routine.writes else ''}")
    return 0


def _next(routine: rt.Routine, now: datetime) -> datetime:
    """The first slot after ``now``: step a day at a time past it, then back to the earliest one."""
    probe, slot = now, now
    while slot <= now:
        probe += timedelta(days=1)
        slot = routine.slot(probe)
    while (earlier := routine.slot(slot - timedelta(minutes=1))) > now:
        slot = earlier
    return slot


def _agent(value):
    if value is None:
        return None
    if value not in rt.AGENTS and value != "none" and " " in value:
        return shlex.split(value)
    return value


def _run(options) -> int:
    plan = rt.load(options.file)
    slot = None
    if options.day:
        routine = plan.get(options.routine)
        hour, minute = (int(part) for part in routine.at.split(":"))
        slot = datetime.fromisoformat(options.day).replace(hour=hour, minute=minute)
    result = plan.run(options.routine, slot=slot, agent=_agent(options.agent))
    print(_line(plan, result))
    return 1 if result["errors"] else 0


def _due(options) -> int:
    plan = rt.load(options.file)
    results = plan.run_due(agent=_agent(options.agent))
    for result in results:
        print(_line(plan, result))
    return 1 if any(r.get("failed") or r.get("errors") for r in results) else 0


def _line(plan, result) -> str:
    if result.get("failed"):
        return f"{result['routine']} {result['slot']}: FAILED {result['failed']}"
    folder = plan.output / result["routine"] / result["slot"][:10]
    agent = (result.get("agent") or {}).get("status")
    return f"{result['routine']} {result['slot']}: {len(result['steps'])} steps, {result['errors']} errors, agent {agent} -> {folder}"


def _status(options) -> int:
    plan = rt.load(options.file)
    plan.write_guides()
    print((plan.output / "index.md").read_text(encoding="utf-8"))
    return 0


# ---- the timer --------------------------------------------------------------------------------


def _command(file: str) -> list[str]:
    return [sys.executable, "-m", "asao_erp", "routines", "due", "--file", str(Path(file).resolve())]


def _environment() -> dict[str, str]:
    """What the timer needs from this shell: where odoo-cli and the agents are, and the variables
    odoo-cli reads. Never a credential: those stay in the keyring or the environment of the user."""
    keep = {"PATH": os.environ.get("PATH", "")}
    for name in ("ASAO_ALLOW_PRIVATE_PROVIDER_ENDPOINTS", "XDG_CONFIG_HOME", "ASAO_ERP_CLI", "PYTHONPATH"):
        if os.environ.get(name):
            keep[name] = os.environ[name]
    return keep


def _install(options) -> int:
    plan = rt.load(options.file)
    command = _command(options.file)
    env = _environment()
    system = platform.system()
    log = plan.output / "scheduler.log"
    plan.output.mkdir(parents=True, exist_ok=True)
    if system == "Linux" and shutil.which("systemctl") and _systemd_user():
        folder = _systemd_folder()
        service = (f"[Unit]\nDescription=asao-erp routines that are due\n\n[Service]\nType=oneshot\n"
                   + "".join(f"Environment={shlex.quote(f'{k}={v}')}\n" for k, v in env.items())
                   + f"ExecStart={shlex.join(command)}\nStandardOutput=append:{log}\nStandardError=append:{log}\n")
        timer = (f"[Unit]\nDescription=Check asao-erp routines every {options.every} minutes\n\n[Timer]\n"
                 f"OnCalendar=*:0/{options.every}\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n")
        if options.print:
            print(f"# {folder / (UNIT + '.service')}\n{service}\n# {folder / (UNIT + '.timer')}\n{timer}")
            return 0
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{UNIT}.service").write_text(service, encoding="utf-8")
        (folder / f"{UNIT}.timer").write_text(timer, encoding="utf-8")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", f"{UNIT}.timer"], check=True)
        print(f"systemd user timer {UNIT}.timer: every {options.every} minutes; log {log}")
        return 0
    if system == "Darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "vn.asao.erp-routines.plist"
        body = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
                "\"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n<plist version=\"1.0\"><dict>\n"
                "<key>Label</key><string>vn.asao.erp-routines</string>\n<key>ProgramArguments</key><array>"
                + "".join(f"<string>{_xml(part)}</string>" for part in command) + "</array>\n"
                "<key>EnvironmentVariables</key><dict>"
                + "".join(f"<key>{_xml(k)}</key><string>{_xml(v)}</string>" for k, v in env.items()) + "</dict>\n"
                f"<key>StartInterval</key><integer>{options.every * 60}</integer>\n"
                f"<key>StandardOutPath</key><string>{_xml(str(log))}</string>\n"
                f"<key>StandardErrorPath</key><string>{_xml(str(log))}</string>\n</dict></plist>\n")
        if options.print:
            print(f"# {plist}\n{body}")
            return 0
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(body, encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        subprocess.run(["launchctl", "load", str(plist)], check=True)
        print(f"launchd agent vn.asao.erp-routines: every {options.every} minutes; log {log}")
        return 0
    if system == "Windows":
        task = subprocess.list2cmdline(command)
        line = ["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", str(options.every), "/TN", UNIT, "/TR", task]
        if options.print:
            print(subprocess.list2cmdline(line))
            return 0
        subprocess.run(line, check=True)
        print(f"scheduled task {UNIT}: every {options.every} minutes")
        return 0
    if shutil.which("crontab"):
        entry = (f"*/{options.every} * * * * " + " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items()) + " "
                 + shlex.join(command) + f" >> {shlex.quote(str(log))} 2>&1 # {UNIT}")
        if options.print:
            print(entry)
            return 0
        current = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        kept = [line for line in current.splitlines() if not line.endswith(f"# {UNIT}")]
        subprocess.run(["crontab", "-"], input="\n".join(kept + [entry]) + "\n", text=True, check=True)
        print(f"crontab: every {options.every} minutes; log {log}")
        return 0
    raise rt.RoutineError("no scheduler found (systemd, launchd, Task Scheduler or cron); run `asao-erp routines due` from yours")


def _uninstall(options) -> int:
    system = platform.system()
    if system == "Linux" and shutil.which("systemctl") and _systemd_user():
        subprocess.run(["systemctl", "--user", "disable", "--now", f"{UNIT}.timer"], capture_output=True)
        folder = _systemd_folder()
        for suffix in (".service", ".timer"):
            (folder / f"{UNIT}{suffix}").unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    elif system == "Darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "vn.asao.erp-routines.plist"
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        plist.unlink(missing_ok=True)
    elif system == "Windows":
        subprocess.run(["schtasks", "/Delete", "/F", "/TN", UNIT], capture_output=True)
    if shutil.which("crontab"):
        current = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        kept = [line for line in current.splitlines() if not line.endswith(f"# {UNIT}")]
        if kept != current.splitlines():
            subprocess.run(["crontab", "-"], input="\n".join(kept) + ("\n" if kept else ""), text=True, check=True)
    print("removed")
    return 0


def _systemd_folder() -> Path:
    """Where the user's systemd manager reads units: its own XDG_CONFIG_HOME, not this shell's (which
    may point odoo-cli at another profile folder)."""
    shown = subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True, text=True).stdout
    config = next((line.split("=", 1)[1] for line in shown.splitlines() if line.startswith("XDG_CONFIG_HOME=")), "")
    return Path(config or Path.home() / ".config") / "systemd" / "user"


def _systemd_user() -> bool:
    return subprocess.run(["systemctl", "--user", "is-system-running"], capture_output=True).returncode in (0, 1)


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---- writing TOML (the standard library only reads it) ----------------------------------------


def _value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_key(k)} = {_value(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"cannot write {type(value).__name__} as TOML")


def _key(key: str) -> str:
    return key if key.replace("_", "").replace("-", "").isalnum() else json.dumps(key, ensure_ascii=False)


def to_toml(data: dict) -> str:
    lines = ["# Việc định kỳ trên Odoo: asao-erp routines --help" if data.get("language", "vi") == "vi"
             else "# Routines on Odoo: asao-erp routines --help"]
    for key, value in data.items():
        if key != "routine":
            lines.append(f"{_key(key)} = {_value(value)}")
    for routine in data.get("routine", []):
        lines += ["", "[[routine]]"]
        for key, value in routine.items():
            if key != "step":
                lines.append(f"{_key(key)} = {_value(value)}")
        for step in routine.get("step", []):
            lines += ["", "  [[routine.step]]"]
            lines += [f"  {_key(k)} = {_value(v)}" for k, v in step.items()]
    return "\n".join(lines) + "\n"


VERBS = {"templates": _templates, "init": _init, "list": _list, "run": _run, "due": _due, "install": _install,
         "uninstall": _uninstall, "status": _status}

if __name__ == "__main__":
    sys.exit(main())

"""The ASAO ERP catalog from Python: reads, groups, prints, reviews and the catalog itself, for notebooks.

Every call goes through an ASAO command line, never to Odoo directly:

* the standalone ``odoo`` CLI with a local profile (``Client(profile="asao-hq")``), which acts with
  that profile's Odoo credential; or
* the governed ``asao aerp`` (``Client(organization=..., connection=...)``), which acts as the
  caller's ASAO login, within the capabilities granted to it.

The SDK holds no credential and speaks no Odoo protocol. The catalog's scopes, readiness rules and
refusals therefore apply to a call from a notebook exactly as they do on the command line, and a
refusal arrives as an :class:`ErpError` carrying the CLI's code, message and remediation.

A client reads by default. An operation that changes data runs only on a client made with
``allow_writes=True``.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

Domain = Sequence[Sequence[Any]]

#: The operation kinds that change nothing.
READ_KINDS = frozenset({"READ"})


class ErpError(Exception):
    """A refusal or failure reported by the CLI, with its machine-readable fields."""

    def __init__(self, code: str, message: str, *, category: str = "", exit_code: int | None = None,
                 remediation: str = "", context: dict | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.category = category
        self.exit_code = exit_code
        self.remediation = remediation
        self.context = context or {}


class Client:
    """One ERP, reached through one CLI.

    Pass ``profile=`` for the standalone ``odoo`` CLI, or ``organization=`` (and, with several Odoo
    connections, ``connection=``) for the governed ``asao aerp``. ``binary`` overrides the
    executable (or ``ASAO_ERP_CLI``); it may be a list, a command prefix.
    """

    def __init__(self, profile: str | None = None, *, organization: str | None = None,
                 connection: str | None = None, binary: str | Sequence[str] | None = None,
                 allow_unverified: bool = False, allow_writes: bool = False, timeout: float = 120):
        if (profile is None) == (organization is None):
            raise ValueError("pass profile= (the standalone odoo-cli) or organization= (the governed asao CLI)")
        self.profile = profile
        self.organization = organization
        self.connection = connection
        self.governed = organization is not None
        self.allow_unverified = allow_unverified
        self.allow_writes = allow_writes
        self.timeout = timeout
        chosen = binary or os.environ.get("ASAO_ERP_CLI") or ("asao" if self.governed else "odoo-cli")
        if isinstance(chosen, str):
            self._command = [shutil.which(chosen) or chosen]
        else:
            self._command = list(chosen)
        self._kinds: dict[str, str] = {}

    # ---- the catalog ------------------------------------------------------------------------

    def operations(self, *, domain: str | None = None, strategy: str | None = None,
                   readiness: str | None = None) -> list[dict]:
        """The catalog's operations: id, kind, strategy, readiness, risk, required capability."""
        args = self._catalog("list")
        for flag, value in (("--domain", domain), ("--strategy", strategy), ("--readiness", readiness)):
            if value:
                args += [flag, value]
        return (self._run(args) or {}).get("items", [])

    def describe(self, operation: str) -> dict:
        """One operation's whole contract: its inputs, outputs, scope and readiness."""
        return self._run(self._catalog("describe") + ["--operation", str(operation)]) or {}

    # ---- reads ------------------------------------------------------------------------------

    def read(self, operation: str, filter: Domain | None = None, *, limit: int = 80, offset: int = 0,
             order: str | None = None, id: int | None = None) -> list[dict]:
        """Records of a read operation: a filtered page of a list, or the one record a describe names."""
        self._require_read(operation, "read")
        args = ["--limit", str(limit)]
        if offset:
            args += ["--offset", str(offset)]
        if order:
            args += ["--order", order]
        if filter:
            args += ["--filter", json.dumps(list(filter))]
        if id is not None:
            args += ["--provider-target-id", str(id)]
        return _records(self._execute(operation, args))

    def iterate(self, operation: str, filter: Domain | None = None, *, page: int = 200,
                order: str = "id") -> Iterator[dict]:
        """Every record a read operation matches, page by page, in a stable order."""
        offset = 0
        while True:
            rows = self.read(operation, filter, limit=page, offset=offset, order=order)
            yield from rows
            if len(rows) < page:
                return
            offset += page

    def group(self, operation: str, by: Iterable[str] = (), aggregate: Iterable[str] = (),
              filter: Domain | None = None, *, limit: int | None = None, order: str | None = None) -> list[dict]:
        """Groups Odoo aggregates: ``by`` fields or date buckets (``"date_order:month"``),
        ``aggregate`` as ``"field:sum"``; every group carries ``count``. Without ``by``, one group
        totals every record the filter matches."""
        self._require_read(operation, "group")
        args: list[str] = []
        for field in by:
            args += ["--group-by", field]
        for spec in aggregate:
            args += ["--aggregate", spec]
        if filter:
            args += ["--filter", json.dumps(list(filter))]
        if limit:
            args += ["--limit", str(limit)]
        if order:
            args += ["--order", order]
        return _records(self._execute(operation, args))

    # ---- documents --------------------------------------------------------------------------

    def print(self, operation: str, id: int, to: str | os.PathLike | None = None) -> bytes | Path:
        """A record's PDF report (``finance.invoice.print``): the bytes, or the path it was saved to."""
        self._require_read(operation, "print")
        outcome = self._execute(operation, ["--provider-target-id", str(id)])
        document = (outcome or {}).get("data") or {}
        pdf = base64.b64decode(document.get("content", ""))
        if to is None:
            return pdf
        path = Path(to)
        path.write_bytes(pdf)
        return path

    # ---- review -----------------------------------------------------------------------------

    def review(self, start: str | date, end: str | date, *, as_of: str | date | None = None,
               checks: Iterable[str] = (), params: dict[str, dict[str, float]] | None = None) -> dict:
        """Review the books of a period (``odoo-cli review run``): mistakes, duplicates and signs of fraud.

        Returns the report the command line computes; the formulas live there, not here. Its
        ``findings`` each name their check, severity (XEM_NGAY, NEN_XU_LY, THEO_DOI), formula,
        thresholds and the records behind them; ``checks`` says which ran and why any did not;
        ``figures`` is the period month by month. ``params`` overrides thresholds by check:
        ``{"O01": {"window_days": 10}}``. ``to_frame(report["findings"])`` makes a DataFrame.
        """
        if self.governed:
            raise ErpError("REVIEW_NOT_GOVERNED_YET", "the governed asao CLI has no aerp review yet",
                           remediation="Review through odoo-cli: Client(profile=...).")
        command = self._command + ["review", "run", "--profile", self.profile,
                                   "--from", _day(start), "--to", _day(end)]
        if as_of is not None:
            command += ["--as-of", _day(as_of)]
        for check in checks:
            command += ["--check", str(check)]
        for check, values in (params or {}).items():
            for name, value in values.items():
                command += ["--param", f"{check}.{name}={value}"]
        if self.allow_unverified:
            command += ["--allow-unverified"]
        return self._run(command) or {}

    # ---- changes ----------------------------------------------------------------------------

    def execute(self, operation: str, *, id: int | None = None, values: dict | None = None,
                approval: str | None = None) -> Any:
        """Run any operation. One that changes data runs only on a client made with allow_writes=True.

        On the governed asao CLI, a high-risk operation (posting, payments, rates) runs only with
        ``approval=``: the id of a request a colleague approved (see ``request_approval``). The
        approved request then runs exactly as approved, so give neither ``id`` nor ``values``.
        """
        if not self.allow_writes and self._kind(operation) not in READ_KINDS:
            raise ErpError("WRITES_NOT_ALLOWED", f"{operation} changes data, and this client reads only",
                           remediation="Make the client with allow_writes=True to run it.")
        args: list[str] = []
        if approval is not None:
            if not self.governed:
                raise ErpError("APPROVAL_NOT_GOVERNED", "approvals exist only on the governed asao CLI (organization=)")
            if id is not None or values:
                raise ErpError("APPROVAL_INPUT_RESUPPLIED", "an approved request runs exactly as it was approved",
                               remediation="Pass only the operation and approval=.")
            args += ["--approval", approval]
        if id is not None:
            args += ["--provider-target-id", str(id)]
        if values:
            args += ["--values", json.dumps(values)]
        return (self._execute(operation, args) or {}).get("data")

    def request_approval(self, operation: str, reason: str, *, id: int | None = None,
                         values: dict | None = None) -> dict:
        """Ask a colleague to approve one high-risk operation, exactly as given (governed asao CLI only).

        Returns the approval request; its ``id`` goes to ``execute(..., approval=)`` once a colleague
        holding aerp.approval.decide has approved it. Asking changes nothing in the ERP.
        """
        if not self.governed:
            raise ErpError("APPROVAL_NOT_GOVERNED", "approvals exist only on the governed asao CLI (organization=)")
        command = self._command + ["aerp", "approval", "request", "--operation", str(operation),
                                   "--organization", self.organization, "--reason", reason]
        if self.connection:
            command += ["--connection", self.connection]
        if id is not None:
            command += ["--provider-target-id", str(id)]
        if values:
            command += ["--values", json.dumps(values)]
        return (self._run(command) or {}).get("approval", {})

    # ---- the command line -------------------------------------------------------------------

    def _require_read(self, operation: str, verb: str) -> None:
        """read(), iterate(), group() and print() run read operations only: a write named there by
        mistake is refused before anything runs, whatever the client may do (found 16/10/2026: a read
        of a write operation ran it, even on a client made without allow_writes)."""
        if self._kind(operation) not in READ_KINDS:
            raise ErpError("NOT_A_READ", f"{operation} changes data, and {verb}() runs read operations only",
                           remediation="Run it with execute() on a client made with allow_writes=True.")

    def _kind(self, operation: str) -> str:
        if operation not in self._kinds:
            self._kinds[operation] = self.describe(operation).get("kind", "")
        return self._kinds[operation]

    def _catalog(self, verb: str) -> list[str]:
        return self._command + (["aerp", "catalog", verb] if self.governed else ["catalog", verb])

    def _execute(self, operation: str, args: list[str]) -> Any:
        command = self._command + (["aerp", "execute"] if self.governed else ["execute"])
        command += ["--operation", str(operation)] + args
        if self.governed:
            command += ["--organization", self.organization]
            if self.connection:
                command += ["--connection", self.connection]
        else:
            command += ["--profile", self.profile]
            if self.allow_unverified:
                command += ["--allow-unverified"]
        return self._run(command)

    def _run(self, command: list[str]) -> Any:
        return _run_cli(command, self.timeout)


def _run_cli(command: list[str], timeout: float) -> Any:
    """Runs one asao / odoo-cli command and answers its envelope's data, or raises its refusal as ErpError."""
    try:
        done = subprocess.run(command + ["--output", "json"], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as missing:
        raise ErpError("CLI_NOT_FOUND", f"{command[0]} is not installed or not on PATH",
                       remediation="Install odoo-cli (profile=) or the asao CLI (organization=), or name it with binary= or ASAO_ERP_CLI.") from missing
    try:
        envelope = json.loads(done.stdout)
    except ValueError:
        raise ErpError("CLI_OUTPUT_UNREADABLE", (done.stderr or done.stdout).strip()[:500],
                       exit_code=done.returncode) from None
    if envelope.get("status") != "OK":
        error = envelope.get("error") or {}
        raise ErpError(error.get("code", "CLI_ERROR"), error.get("message", ""), category=error.get("category", ""),
                       exit_code=error.get("exitCode", done.returncode), remediation=error.get("remediation", ""),
                       context=error.get("context"))
    return envelope.get("data")


def _day(value: str | date) -> str:
    """A day as the CLI takes it, YYYY-MM-DD."""
    return value.isoformat() if isinstance(value, date) else str(value)


def _records(outcome: Any) -> list[dict]:
    data = (outcome or {}).get("data") if isinstance(outcome, dict) else outcome
    if data is None:
        return []
    return data if isinstance(data, list) else [data]


def flatten(record: dict) -> dict:
    """A record as plain columns: a relation as its name, a date bucket as its first day."""
    flat = {}
    for key, value in record.items():
        if isinstance(value, dict) and "value" in value:
            flat[key] = value["value"]
        elif isinstance(value, dict) and "display_name" in value:
            flat[key] = value["display_name"]
        elif isinstance(value, list) and len(value) == 2 and isinstance(value[0], int) and isinstance(value[1], str):
            flat[key] = value[1]
        else:
            flat[key] = value
    return flat


def to_frame(rows: Iterable[dict]):
    """Records or groups as a pandas DataFrame, relations as names (pip install pandas)."""
    try:
        import pandas
    except ImportError as missing:
        raise ErpError("PANDAS_NOT_INSTALLED", "to_frame needs pandas",
                       remediation="pip install pandas (or: pip install 'asao-erp[pandas]')") from missing
    return pandas.DataFrame([flatten(row) for row in rows])

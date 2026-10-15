# Changelog

## 0.3.0 (2026-10-16)

- Routines (`asao_erp.routines`, and the `asao-erp routines` command): daily, weekday, weekly and
  monthly checks on Odoo, written in a TOML or JSON file, run on a schedule (`install` sets up
  systemd, launchd, Task Scheduler or cron) or by hand, and read by the agent you choose (`claude`,
  `codex`, `gemini`, `agy`, or any command). Each run keeps what Odoo answered, a computed summary
  and the agent's analysis, plus an index and an AGENTS.md/CLAUDE.md/GEMINI.md for an agent opened in
  that folder. Ten starter routines by area (`asao-erp routines templates`); writes only in steps a
  routine declares (`writes = true`).
- `ensure_task` keeps a task, recurring or not, open in Odoo: created once, never twice. Recurring
  tasks need odoo-cli 0.11 (`recurring`, `repeat_every`, `repeat_unit`, `repeat_type`, `repeat_until`).
- `pip install 'asao-erp[toml]'` reads routines files on Python 3.10.
- The timer `install` sets up was run on Linux with systemd. The launchd (macOS), Task Scheduler
  (Windows) and cron versions are written the same way but have not been run yet.
- `ops` follows the catalog: 1357 operations. New: the change history,
  `structure.field_change.list|describe` and `structure.change_note.list|describe` (odoo-cli 0.11).
  Creating a loyalty card is now verified.
- `Client.review()` runs the 20 checks of odoo-cli 0.11, six more than 0.10's.

## 0.2.1 (2026-10-15)

Documentation and package metadata only; the code is 0.2.0's.

- The README names the owner, says what the library collects (nothing: it only runs the CLI) and
  links the hosted service's Terms of Service and Privacy Policy.
- How to support the project: Ko-fi (cards or PayPal), PayPal, and Vietcombank by VietQR. The
  package's Funding URL is Ko-fi.

## 0.2.0 (2026-10-15)

- `Client.review(start, end, as_of=..., checks=..., params=...)` reviews the books of a period through
  `odoo-cli review run` (odoo-cli 0.10.0 or later) and returns its report: findings with check,
  severity, formula, thresholds and the records behind them; which checks ran; the period's figures.
  It reads only, on a profile; the governed `asao` CLI has no review yet (`REVIEW_NOT_GOVERNED_YET`).
- `ops` follows the catalog: 1353 operations. Five writes that Odoo itself refuses are gone:
  `finance.payment_method.create`, `livechat.channel_member_history.create` and `.update`,
  `manufacturing.workcenter_productivity_loss_type.create` and `.update`.
- Packaging: the license is the SPDX expression `Apache-2.0` (setuptools 77 or later builds it), and
  the source distribution carries the fake CLI, so its tests run.

## 0.1.0 (2026-10-13)

The first public release.

- `Client(profile=...)` drives `odoo-cli`; `Client(organization=..., connection=...)` drives the
  governed `asao` CLI.
- `read`, `iterate`, `group` (grouping computed by Odoo), `print` (PDF), `operations`, `describe`,
  `execute`, and `to_frame` for pandas.
- `ops` lists every catalog operation by domain, for completion in the editor.
- Writes run only with `allow_writes=True`; unverified results only with `allow_unverified=True`.
- Governed `asao` CLI: a high-risk operation (posting, payments, rates) runs only after a colleague
  approves the exact request. `request_approval(operation, reason, id=..., values=...)` asks;
  `execute(operation, approval=...)` runs the approved request once.

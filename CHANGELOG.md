# Changelog

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

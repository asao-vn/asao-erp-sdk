# asao-erp

Odoo Community from Python, through a verified command line. Read, group, page, print PDFs and
browse the operation catalog, for notebooks, scripts and staff statistics; review a period's books
for mistakes, duplicates and signs of fraud; and run daily, weekly and monthly routines whose results
the agent you choose (Claude Code, Codex, agy, any command) reads for you.

```python
from asao_erp import Client, ops, to_frame

erp = Client(profile="my-odoo")          # odoo-cli and its local profile
monthly = erp.group(ops.sales.quotation_list, by=["date_order:month"],
                    aggregate=["amount_total:sum"], filter=[["state", "=", "sale"]])
to_frame(monthly)
```

> Odoo is a registered trademark of Odoo S.A. This project is not affiliated with or endorsed by
> Odoo S.A.

## Install

```sh
pip install asao-erp            # or: pip install 'asao-erp[pandas]'
```

`asao-erp` holds no credential and never calls Odoo itself: every call goes through a command line,
so the catalog's checks, readiness rules and refusals apply exactly as on the command line. Install
the command line too, either of:
- [`odoo-cli`](https://github.com/asao-vn/asao-odoo-tools), for an Odoo you configure locally:
  `Client(profile="my-odoo")`. Set the profile up once with `odoo-cli profile set`; the credential
  stays in the environment or the OS keyring, never in your notebook.
- The governed `asao` CLI, for an ASAO organization:
  `Client(organization="...", connection="...")`. Calls then act with the caller's ASAO login, within
  the permissions their role grants: reads, and, with a domain's write key, the verified writes.
  A high-risk one (posting, payments, rates) runs only after a colleague approves the exact request
  (`asao aerp approval request`, then `approve`); deletes and prints stay with `odoo-cli`.

Name a binary that is not on `PATH` with `binary=` or `ASAO_ERP_CLI`.

## Use

| Call | Does |
|---|---|
| `read(op, filter, limit, offset, order, id)` | One page of records of a read operation |
| `iterate(op, filter, page)` | Every record, page by page |
| `group(op, by, aggregate, filter)` | Groups computed by Odoo: `"date_order:month"`, `"amount_total:sum"`; each group has `count` |
| `print(op, id, to)` | A document's PDF (`ops.finance.invoice_print`) |
| `operations(domain)`, `describe(op)` | The catalog, and one operation's contract |
| `execute(op, id, values)` | Any operation. A write runs only with `Client(..., allow_writes=True)` |
| `to_frame(rows)` | A pandas DataFrame, with relations as names |

`ops` lists every operation by domain, so the editor completes them (`ops.finance.invoice_list`). A
failure raises `ErpError` with the command line's code, message and remediation.

## Review the books of a period

`review()` runs `odoo-cli review run` (odoo-cli 0.10.0 or later) and returns the report it computes:
bills or payments entered twice, duplicate partners, a supplier paid into an employee's account,
orders split under an approval threshold, sales below cost, refunds after payment, expense claims
twice or on leave, valuable scrap, overdue receivables, and the period's figures month by month.

```python
report = erp.review("2026-07-01", "2026-09-30", params={"O01": {"window_days": 10}})
to_frame(report["findings"])   # check, severity, title, why, formula, thresholds, the records behind it
report["checks"]               # which checks ran, and why any did not
report["figures"]              # revenue, margin, purchases, cash in and out, by month
```

It only reads. A finding is a sign to look at again, never a verdict. The formulas live in odoo-cli,
not in the SDK, so a script, a notebook and an agent read the same findings; `odoo-cli review checks`
lists each check's formula and thresholds. It runs on a profile (`Client(profile=...)`); the governed
`asao` CLI has no review yet.

## Routines: every day, week and month, read by your agent

A routine asks Odoo the same questions on a schedule and keeps what Odoo answered; the agent you
choose then reads it and writes what deserves attention. The agent only reads: anything that changes
Odoo is a step written in the routine, never improvised.

```sh
asao-erp routines templates                    # each starter routine: what Odoo does, what it returns
asao-erp routines init --profile my-odoo --agent claude     # writes routines.toml
asao-erp routines run cong-no-qua-han          # run one now
asao-erp routines install                      # a timer (systemd, launchd, Task Scheduler or cron) that runs what is due
```

The timer has been run on Linux with systemd; the launchd (macOS), Task Scheduler (Windows) and cron
versions have not been run yet.

| Every | Starter routines |
|---|---|
| day | sales yesterday by salesperson; overdue receivables by customer and currency; money in and out; late transfers; overdue tasks (weekdays); recurring tasks kept in Odoo (writes) |
| week (Monday) | the books review of last week; opportunities stalled for 14 days |
| month (the 1st) | the books review of last month; revenue by month and by customer |

A routine is a few lines of TOML (or JSON), so you or your agent can write more:

```toml
profile = "my-odoo"
output = "~/asao-routines"
agent = "claude"          # claude | codex | gemini | agy | none | ["any", "command", "{prompt}"]

[[routine]]
id = "overdue"
title = "Overdue receivables"
every = "daily"           # daily | weekdays | weekly (on = "mon") | monthly (on = 1 or "last")
at = "07:30"
prompt = "Who owes the most past due, and whom should we call today?"

  [[routine.step]]
  group = "finance.invoice.list"
  by = ["partner_id", "currency_id"]
  aggregate = ["amount_residual:sum"]
  filter = [["move_type", "=", "out_invoice"], ["state", "=", "posted"],
            ["payment_state", "in", ["not_paid", "partial"]], ["invoice_date_due", "<", "{today}"]]
```

Steps are `read`, `group`, `review` (the books review of yesterday, last week or last month),
`ensure_task` (an Odoo task, recurring or not, created once and never twice) and `execute`; a routine
with a writing step must say `writes = true`. Dates are `{today}`, `{yesterday}`, `{week_start+4}`,
`{month_start-3m}`... counted from the day the routine was due, so a run that is late still asks about
the right day.

Each run is kept in `~/asao-routines/<routine>/<day>/`: `result.json` (exactly what Odoo answered),
`summary.md` (counts and totals, computed, never written by a model; sums in several currencies stay
per currency), and `analysis.md` (the agent's reading). `index.md` lists the latest run of each, and
`AGENTS.md`, `CLAUDE.md` and `GEMINI.md` there tell an agent you open in that folder how to read them,
so "how are we doing this morning?" is answered from the files, not from guesses.

The agents: `claude` (`claude -p`), `codex` (`codex exec`, read-only sandbox), `agy` (`agy -p`),
`gemini` (Gemini CLI; Google moved individual accounts to Antigravity, so use `agy` there), or any
command: the prompt goes on standard input, or where the command says `{prompt}`. The agent gets the
data in its prompt and no tools. In Python, `asao_erp.routines.load("routines.toml").run("overdue")`
does the same.

**Recurring tasks in Odoo.** With odoo-cli 0.11, `work.task.create` and `work.task.update` take
`recurring`, `repeat_every`, `repeat_unit` (day, week, month, year), `repeat_type` and `repeat_until`,
with `due_on`, `priority`, `tags` and `description`. Odoo opens a task's next occurrence when the
current one is closed (done or cancelled), not on a calendar date: a routine's `ensure_task` keeps
the first one there, and closing it is the person's.

## What is verified, and what is not

The catalog's operations are verified on the stock Odoo Community image: 1290 on 19.0, and 1176 on
20.0, a candidate series that runs only with `allow_unverified=True` until it is supported. A public
[conformance run](https://github.com/asao-vn/asao-odoo-tools/blob/main/docs/conformance.md) checks them
again every week. Before each call, the
command line checks the Odoo it reaches:
- Is it Odoo, and which series?
- Are the needed modules installed?
- Is it customised where a write acts?

A write on a customised Odoo is held back (`AERP_ENVIRONMENT_UNVERIFIED`). It runs only with
`allow_unverified=True`.

**Odoo Online and Enterprise.** The SDK reaches them through odoo-cli and the JSON-2 API (an API key
of scope RPC; Odoo Online offers the external API on its Custom plan only). Reads run there, marked
unverified, and `group()` works there as on Community; see [odoo-cli's page on them](https://github.com/asao-vn/asao-odoo-tools/blob/main/docs/odoo-online-and-enterprise.md).

**Customised Odoo is not guaranteed.** On an Odoo changed beyond the stock image (Enterprise,
third-party or in-house modules, Studio, automations, fields added by hand), operations cannot be
verified, and nothing guarantees that they work as described or without error. What you accept
there runs at your own risk.

## Develop

```sh
python -m unittest discover -s tests     # a fake command line, no network
```

`examples/vscode/` is a sample VS Code workspace with a statistics notebook.

This repository is exported from the ASAO monorepo (see `SOURCE.md`). Issues and pull requests are
welcome. An accepted change is applied in the monorepo and arrives with the next export.

## Support the project

asao-erp is free and built by one person. If it saves you time and you would like to chip in, any
amount helps:

- **From anywhere, by card or PayPal:** [ko-fi.com/nguyenhuuhoang](https://ko-fi.com/nguyenhuuhoang)

| PayPal | Vietcombank (VietQR, any Vietnamese banking app) |
|:---:|:---:|
| <img src="https://raw.githubusercontent.com/asao-vn/asao-erp-sdk/main/docs/support/paypal-qr.png" alt="PayPal QR code for paypal.me/AldenNguyen2345" width="160" height="160"> | <img src="https://raw.githubusercontent.com/asao-vn/asao-erp-sdk/main/docs/support/vcb-qr.png" alt="VietQR code for Vietcombank account 1031712729" width="160" height="160"> |
| [paypal.me/AldenNguyen2345](https://paypal.me/AldenNguyen2345) | NGUYEN HUU HOANG · 1031712729 |

A star, an issue or a note about what you use it for helps just as much. Support buys no priority and
no warranty; the license and its terms stay the same.

## License, owner, privacy and terms

- **License:** Apache License 2.0, see [LICENSE](LICENSE) and [NOTICE](NOTICE). The software is
  provided "as is", without warranty (sections 7 and 8 of the license).
- **Owner:** Copyright 2026 Nguyễn Hữu Hoàng, who publishes it under the brand ASAO.
  Contact: nguyenhuuhoang711@gmail.com.
- **Privacy:** asao-erp collects nothing and opens no connection of its own. It runs `odoo-cli` (or
  `asao`) on your machine and returns what that command answers, so it holds no credential and has
  no telemetry.
- **Terms:** using this library on its own is governed by its license only. ASAO's hosted service
  (asao.vn) has its own [Terms of Service](https://asao.vn/terms) and [Privacy Policy](https://asao.vn/privacy), which apply
  when you use that service, including through `Client(organization=...)`.

## Tiếng Việt

`asao-erp` cho phép làm việc với Odoo Community bằng Python: đọc, gộp nhóm, phân trang, in PDF và tra
catalog. Thư viện hợp cho notebook và cho nhân viên làm thống kê. Mọi lệnh đi qua `odoo-cli` (profile
cục bộ) hoặc `asao` (theo tổ chức ASAO). SDK không giữ mật khẩu.

ASAO chỉ kiểm chứng trên bản Odoo chuẩn. Với Odoo đã tuỳ biến, ASAO không bảo đảm thao tác chạy đúng;
dùng `allow_unverified=True` trên Odoo đó là tự chịu rủi ro.

Từ bản 0.3.0, `asao-erp routines` chạy các việc định kỳ hằng ngày, hằng tuần, hằng tháng trên Odoo:
bán hàng hôm qua, công nợ quá hạn, tiền vào ra, phiếu kho trễ, việc trễ hạn, rà soát sổ sách tuần và
tháng, doanh thu tháng, và giữ sẵn các việc lặp lại trong Odoo (chốt quỹ, kiểm kho, khoá sổ). Mỗi lần
chạy lưu đúng những gì Odoo trả về, một bản tóm tắt số liệu do máy tính, và phần phân tích của agent bạn
chọn: Claude Code, Codex, agy hay lệnh nào cũng được. Agent chỉ đọc; việc nào ghi vào Odoo phải được viết
sẵn trong file việc định kỳ. `asao-erp routines templates` cho xem từng việc: Odoo làm gì, trả về gì.

Từ bản 0.2.0, `review()` rà soát sổ sách một kỳ qua `odoo-cli review run` (odoo-cli 0.10.0 trở lên): hoá
đơn hay khoản chi nhập hai lần, đối tác trùng, trả tiền nhà cung cấp vào tài khoản nhân viên, chia nhỏ đơn
dưới ngưỡng duyệt, bán dưới giá vốn, công nợ quá hạn, và số liệu từng tháng. Mỗi phát hiện là dấu hiệu
cần xem lại, không phải kết luận, và kèm công thức, ngưỡng cùng chứng từ. Công thức nằm trong odoo-cli,
không nằm trong SDK.

**Giấy phép, chủ sở hữu, quyền riêng tư.** asao-erp phát hành theo giấy phép Apache 2.0, thuộc sở hữu của
cá nhân Nguyễn Hữu Hoàng (thương hiệu ASAO), và được cung cấp "nguyên trạng", không kèm bảo đảm. Thư viện
không thu thập dữ liệu gì và không tự mở kết nối nào: nó chỉ chạy `odoo-cli` hoặc `asao` trên máy bạn. Dịch
vụ ASAO (asao.vn) có [Điều khoản sử dụng](https://asao.vn/terms) và [Chính sách quyền riêng tư](https://asao.vn/privacy) riêng; chúng
chỉ áp dụng khi bạn dùng dịch vụ đó.

**Ủng hộ dự án.** asao-erp miễn phí và do một người làm. Nếu nó giúp bạn tiết kiệm thời gian và bạn muốn
ủng hộ một chút: chuyển khoản Vietcombank **1031712729** (NGUYEN HUU HOANG), quét VietQR bằng app ngân hàng
nào cũng được, hoặc PayPal [paypal.me/AldenNguyen2345](https://paypal.me/AldenNguyen2345), hoặc thẻ quốc tế qua
[ko-fi.com/nguyenhuuhoang](https://ko-fi.com/nguyenhuuhoang). Mã QR ở mục
[Support the project](#support-the-project). Một sao trên GitHub, một issue hay một lời kể bạn dùng nó
vào việc gì cũng quý như vậy.

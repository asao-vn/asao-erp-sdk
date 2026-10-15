# asao-erp

Odoo Community from Python, through a verified command line. Read, group, page, print PDFs and
browse the operation catalog, for notebooks, scripts and staff statistics, and review a period's
books for mistakes, duplicates and signs of fraud.

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

## What is verified, and what is not

The catalog's operations are verified on the stock Odoo Community image: 1285 on 19.0, and 1170 on
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
  (app.asao.vn) has its own [Terms of Service](https://app.asao.vn/terms) and [Privacy Policy](https://app.asao.vn/privacy), which apply
  when you use that service, including through `Client(organization=...)`.

## Tiếng Việt

`asao-erp` cho phép làm việc với Odoo Community bằng Python: đọc, gộp nhóm, phân trang, in PDF và tra
catalog. Thư viện hợp cho notebook và cho nhân viên làm thống kê. Mọi lệnh đi qua `odoo-cli` (profile
cục bộ) hoặc `asao` (theo tổ chức ASAO). SDK không giữ mật khẩu.

ASAO chỉ kiểm chứng trên bản Odoo chuẩn. Với Odoo đã tuỳ biến, ASAO không bảo đảm thao tác chạy đúng;
dùng `allow_unverified=True` trên Odoo đó là tự chịu rủi ro.

Từ bản 0.2.0, `review()` rà soát sổ sách một kỳ qua `odoo-cli review run` (odoo-cli 0.10.0 trở lên): hoá
đơn hay khoản chi nhập hai lần, đối tác trùng, trả tiền nhà cung cấp vào tài khoản nhân viên, chia nhỏ đơn
dưới ngưỡng duyệt, bán dưới giá vốn, công nợ quá hạn, và số liệu từng tháng. Mỗi phát hiện là dấu hiệu
cần xem lại, không phải kết luận, và kèm công thức, ngưỡng cùng chứng từ. Công thức nằm trong odoo-cli,
không nằm trong SDK.

**Giấy phép, chủ sở hữu, quyền riêng tư.** asao-erp phát hành theo giấy phép Apache 2.0, thuộc sở hữu của
cá nhân Nguyễn Hữu Hoàng (thương hiệu ASAO), và được cung cấp "nguyên trạng", không kèm bảo đảm. Thư viện
không thu thập dữ liệu gì và không tự mở kết nối nào: nó chỉ chạy `odoo-cli` hoặc `asao` trên máy bạn. Dịch
vụ ASAO (app.asao.vn) có [Điều khoản sử dụng](https://app.asao.vn/terms) và [Chính sách quyền riêng tư](https://app.asao.vn/privacy) riêng; chúng
chỉ áp dụng khi bạn dùng dịch vụ đó.

**Ủng hộ dự án.** asao-erp miễn phí và do một người làm. Nếu nó giúp bạn tiết kiệm thời gian và bạn muốn
ủng hộ một chút: chuyển khoản Vietcombank **1031712729** (NGUYEN HUU HOANG), quét VietQR bằng app ngân hàng
nào cũng được, hoặc PayPal [paypal.me/AldenNguyen2345](https://paypal.me/AldenNguyen2345), hoặc thẻ quốc tế qua
[ko-fi.com/nguyenhuuhoang](https://ko-fi.com/nguyenhuuhoang). Mã QR ở mục
[Support the project](#support-the-project). Một sao trên GitHub, một issue hay một lời kể bạn dùng nó
vào việc gì cũng quý như vậy.

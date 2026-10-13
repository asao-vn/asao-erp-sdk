# asao-erp

Odoo Community from Python, through a verified command line. Read, group, page, print PDFs and
browse the operation catalog, for notebooks, scripts and staff statistics.

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
- The governed [`asao`](https://github.com/asao-vn/asao-cli) CLI, for an ASAO organization:
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

## What is verified, and what is not

The catalog's operations are verified on the stock Odoo Community image: 1267 on 19.0, and 1170 on
20.0, a candidate series that runs only with `allow_unverified=True` until it is supported. A public
[conformance run](https://github.com/asao-vn/asao-odoo-tools/blob/main/docs/conformance.md) checks them
again every week. Before each call, the
command line checks the Odoo it reaches:
- Is it Odoo, and which series?
- Are the needed modules installed?
- Is it customised where a write acts?

A write on a customised Odoo is held back (`AERP_ENVIRONMENT_UNVERIFIED`). It runs only with
`allow_unverified=True`.

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

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Tiếng Việt

`asao-erp` cho phép làm việc với Odoo Community bằng Python: đọc, gộp nhóm, phân trang, in PDF và tra
catalog. Thư viện hợp cho notebook và cho nhân viên làm thống kê. Mọi lệnh đi qua `odoo-cli` (profile
cục bộ) hoặc `asao` (theo tổ chức ASAO). SDK không giữ mật khẩu.

ASAO chỉ kiểm chứng trên bản Odoo chuẩn. Với Odoo đã tuỳ biến, ASAO không bảo đảm thao tác chạy đúng;
dùng `allow_unverified=True` trên Odoo đó là tự chịu rủi ro.

"""A stand-in for the odoo / asao CLI: answers the JSON envelopes the SDK reads, and logs each call."""
import base64
import json
import os
import sys


def value(name, default=None):
    args = sys.argv[1:]
    return args[args.index(name) + 1] if name in args else default


def values(name):
    args = sys.argv[1:]
    return [args[i + 1] for i, arg in enumerate(args) if arg == name]


def reply(data=None, error=None, code=0):
    envelope = {"status": "ERROR", "error": error} if error else {"status": "OK", "data": data}
    print(json.dumps(envelope))
    sys.exit(code)


with open(os.environ["FAKE_CLI_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")

args = sys.argv[1:]
if args[:2] == ["review", "run"]:
    reply({"from": value("--from"), "to": value("--to"), "asOf": value("--as-of", value("--to")),
           "findings": [{"check": "O01", "severity": "XEM_NGAY", "title": "Một hoá đơn mua có thể bị nhập hai lần",
                         "amountVnd": 34320000, "formula": "same vendor, same total, references alike",
                         "params": {"window_days": 14}, "evidence": [{"operation": "finance.invoice.list", "id": 1}]}],
           "counts": {"XEM_NGAY": 1}, "checks": [{"id": "O01", "ran": True}], "figures": {"revenue": 0}})
if args[:3] == ["aerp", "approval", "request"]:
    reply({"approval": {"id": "appr-1", "status": "PENDING", "operation": value("--operation")}})
if "--approval" in args:
    reply({"operation": value("--operation"), "data": {"id": 42, "state": "posted"}})
if "catalog" in args and "list" in args:
    reply({"items": [{"id": "sales.quotation.list", "kind": "READ"}], "count": 1})
if "catalog" in args and "describe" in args:
    operation = value("--operation")
    reply({"id": operation, "kind": "COMMAND" if operation.endswith(".create") else "READ"})
operation = value("--operation")
if value("--filter") == '[["name", "=", "boom"]]':
    reply(error={"code": "AERP_VALIDATION_FAILED", "message": "boom is refused", "exitCode": 2,
                 "remediation": "Do not say boom."}, code=2)
if operation.endswith(".print"):
    reply({"operation": operation, "data": {"filename": "INV_1.pdf", "content": base64.b64encode(b"%PDF-1.4 x").decode()}})
if values("--group-by") or values("--aggregate"):
    reply({"operation": operation, "data": [{"date_order:month": {"value": "2026-10-01", "display_name": "October 2026"},
                                              "amount_total:sum": 1500.0, "count": 3}]})
if operation.endswith(".create"):
    reply({"operation": operation, "data": {"id": 9, "created": True}})
offset, limit = int(value("--offset", 0)), int(value("--limit", 80))
rows = [{"id": i + 1, "name": f"S{i + 1:05d}", "partner_id": [7, "Acme"], "state": "sale"} for i in range(450)]
reply({"operation": operation, "data": rows[offset:offset + limit]})

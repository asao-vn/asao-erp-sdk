"""asao_erp: the ASAO ERP catalog from Python, through the ASAO command line.

    from asao_erp import Client, ops, to_frame
    erp = Client(profile="asao-hq")
    to_frame(erp.group(ops.sales.quotation_list, by=["date_order:month"], aggregate=["amount_total:sum"]))
    report = erp.review("2026-07-01", "2026-09-30")
    to_frame(report["findings"])

Routines (asao_erp.routines, or `asao-erp routines`) run the same questions every day, week or month
and hand what Odoo answered to the agent you choose: Claude Code, Codex, Gemini CLI, agy or none.
"""

from . import operations as ops
from . import routines
from .client import READ_KINDS, Client, ErpError, flatten, to_frame

__all__ = ["Client", "ErpError", "READ_KINDS", "flatten", "ops", "routines", "to_frame"]
__version__ = "0.3.0"

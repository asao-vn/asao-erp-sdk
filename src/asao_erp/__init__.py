"""asao_erp: the ASAO ERP catalog from Python, through the ASAO command line.

    from asao_erp import Client, ops, to_frame
    erp = Client(profile="asao-hq")
    to_frame(erp.group(ops.sales.quotation_list, by=["date_order:month"], aggregate=["amount_total:sum"]))
"""

from . import operations as ops
from .client import READ_KINDS, Client, ErpError, flatten, to_frame

__all__ = ["Client", "ErpError", "READ_KINDS", "flatten", "ops", "to_frame"]
__version__ = "0.1.0"

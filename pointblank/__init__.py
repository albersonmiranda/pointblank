try:
    from importlib.metadata import PackageNotFoundError, version
except ImportError:  # pragma: no cover
    from importlib_metadata import PackageNotFoundError, version

try:  # pragma: no cover
    __version__ = version("pointblank")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

# Import objects from the module
from pointblank.column import (
    col,
    contains,
    ends_with,
    everything,
    first_n,
    last_n,
    matches,
    starts_with,
)
from pointblank.datascan import DataScan
from pointblank.draft import DraftValidation
from pointblank.schema import Schema
from pointblank.tf import TF
from pointblank.thresholds import Actions, Thresholds
from pointblank.validate import (
    Validate,
    config,
    get_column_count,
    get_row_count,
    load_dataset,
    missing_vals_tbl,
    preview,
)

__all__ = [
    "TF",
    "Validate",
    "Thresholds",
    "Actions",
    "Schema",
    "DataScan",
    "DraftValidation",
    "col",
    "starts_with",
    "ends_with",
    "contains",
    "matches",
    "everything",
    "first_n",
    "last_n",
    "load_dataset",
    "config",
    "preview",
    "missing_vals_tbl",
    "get_column_count",
    "get_row_count",
]

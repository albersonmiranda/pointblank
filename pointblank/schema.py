from __future__ import annotations

from dataclasses import dataclass

import narwhals as nw

from pointblank._utils import _get_tbl_type
from pointblank._constants import IBIS_BACKENDS


@dataclass
class Schema:
    """Definition of a schema object.

    The schema object defines the structure of a table, including the table name and its columns.
    A schema for a table can be defined by adding column names and types for each of the columns
    as tuples in a list, as a dictionary, or as individual keyword arguments. The schema object
    can then be used to validate the structure of a table against the schema.

    We can alternatively provide a DataFrame or Ibis table object and the schema will be collected
    from either type of object. Note that if `tbl=` is provided then there shouldn't be any other
    inputs provided through either `columns=` or `**kwargs`.

    Parameters
    ----------
    columns
        A list of tuples or a dictionary containing column information. If provided, this will take
        precedence over any individual column arguments provided via `**kwargs`.
    tbl
        A DataFrame or Ibis table object from which the schema will be collected.
    **kwargs
        Individual column arguments. These will be ignored if the `columns=` parameter is provided.
    """

    columns: list[tuple[str, str]] | None = None
    tbl: any | None = None

    def __init__(
        self,
        columns: list[tuple[str, str]] | dict[str, str] | None = None,
        tbl: any | None = None,
        **kwargs,
    ):
        if tbl is None and columns is None and not kwargs:
            raise ValueError(
                "Either `columns`, `tbl`, or individual column arguments must be provided."
            )

        if tbl is not None and (columns is not None or kwargs):
            raise ValueError(
                "Only one of `columns`, `tbl`, or individual column arguments can be provided."
            )

        self.tbl = tbl
        if columns is not None or kwargs:
            self.columns = _process_columns(columns=columns, **kwargs)
        else:
            self.columns = None

        self.__post_init__()

    def __post_init__(self):
        if self.columns is not None:
            self._validate_schema_inputs()
        if self.tbl is not None:
            self._collect_schema_from_table()

    def _validate_schema_inputs(self):
        if not isinstance(self.columns, list):
            raise ValueError("`columns` must be a list.")

        if not all(isinstance(col, tuple) for col in self.columns):
            raise ValueError("All elements of `columns` must be tuples.")

        if not all(len(col) == 2 for col in self.columns):
            raise ValueError("All tuples in `columns` must have exactly two elements.")

        if not all(isinstance(col[0], str) for col in self.columns):
            raise ValueError("The first element of each tuple in `columns` must be a string.")

    def _collect_schema_from_table(self):

        # Determine if this table can be converted to a Narwhals DataFrame
        table_type = _get_tbl_type(self.tbl)

        if table_type == "pandas" or table_type == "polars":

            tbl_nw = nw.from_native(self.tbl)

            schema_dict = dict(tbl_nw.schema.items())

            schema_dict = {k: str(v) for k, v in schema_dict.items()}

            self.columns = list(schema_dict.items())

        elif table_type in IBIS_BACKENDS:

            schema_dict = dict(self.tbl.schema().items())

            schema_dict = {k: str(v) for k, v in schema_dict.items()}

            self.columns = list(schema_dict.items())

        else:
            raise ValueError(
                "The provided table object cannot be converted to a Narwhals DataFrame."
            )

    def __str__(self):
        return "Pointblank Schema\n" + "\n".join([f"  {col[0]}: {col[1]}" for col in self.columns])

    def __repr__(self):
        return f"Schema(columns={self.columns})"


def _process_columns(
    *, columns: list[tuple[str, str]] | dict[str, str] | None = None, **kwargs
) -> list[tuple[str, str]]:
    """
    Process column information provided as individual arguments or as a list of
    tuples/dictionary.

    Parameters
    ----------
    columns
        A list of tuples or a dictionary containing column information.
    **kwargs
        Individual column arguments.

    Returns
    -------
    list[tuple[str, str]]
        A list of tuples containing column information.
    """
    if columns is not None:
        if isinstance(columns, dict):
            return list(columns.items())
        return columns

    return list(kwargs.items())

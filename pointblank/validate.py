from __future__ import annotations

import base64
import commonmark
import datetime
import inspect
import json
import re

from dataclasses import dataclass
from typing import Callable

import narwhals as nw
from narwhals.typing import FrameT
from great_tables import GT, html, loc, style, google_font, from_column

from pointblank._constants import (
    TYPE_METHOD_MAP,
    COMPATIBLE_TYPES,
    COMPARE_TYPE_MAP,
    ROW_BASED_VALIDATION_TYPES,
    VALIDATION_REPORT_FIELDS,
    TABLE_TYPE_STYLES,
    SVG_ICONS_FOR_ASSERTION_TYPES,
    SVG_ICONS_FOR_TBL_STATUS,
)
from pointblank._constants_docs import ARG_DOCSTRINGS
from pointblank._comparison import (
    ColValsCompareOne,
    ColValsCompareTwo,
    ColValsCompareSet,
    NumberOfTestUnits,
)
from pointblank.thresholds import (
    Thresholds,
    _normalize_thresholds_creation,
    _convert_abs_count_to_fraction,
)
from pointblank._utils import _get_def_name, _check_invalid_fields
from pointblank._utils_check_args import (
    _check_column,
    _check_value_float_int,
    _check_set_types,
    _check_pre,
    _check_thresholds,
    _check_boolean_input,
)


def _col_vals_compare_one_title_docstring(comparison: str) -> str:
    return "Validate whether column values are ___ a single value.".replace("___", comparison)


def _col_vals_compare_two_title_docstring(comparison: str) -> str:
    return "Validate whether column values are ___ two values.".replace("___", comparison)


def _col_vals_compare_set_title_docstring(inside: bool) -> str:
    return "Validate whether column values are ___ a set of values.".replace(
        "___", "in" if inside else "not in"
    )


def _col_vals_compare_one_args_docstring() -> str:
    return f"""
Parameters
----------
{ARG_DOCSTRINGS["column"]}
{ARG_DOCSTRINGS["value"]}
{ARG_DOCSTRINGS["na_pass"]}
{ARG_DOCSTRINGS["pre"]}
{ARG_DOCSTRINGS["thresholds"]}
{ARG_DOCSTRINGS["active"]}"""


def _col_vals_compare_two_args_docstring() -> str:
    return f"""
Parameters
----------
{ARG_DOCSTRINGS["column"]}
{ARG_DOCSTRINGS["left"]}
{ARG_DOCSTRINGS["right"]}
{ARG_DOCSTRINGS["inclusive"]}
{ARG_DOCSTRINGS["na_pass"]}
{ARG_DOCSTRINGS["pre"]}
{ARG_DOCSTRINGS["thresholds"]}
{ARG_DOCSTRINGS["active"]}"""


def _col_vals_compare_set_args_docstring() -> str:
    return f"""
Parameters
----------
{ARG_DOCSTRINGS["column"]}
{ARG_DOCSTRINGS["set"]}
{ARG_DOCSTRINGS["pre"]}
{ARG_DOCSTRINGS["thresholds"]}
{ARG_DOCSTRINGS["active"]}"""


@dataclass
class _ValidationInfo:
    """
    Information about a validation to be performed on a table and the results of the interrogation.

    Attributes
    ----------
    i : int | None
        The validation step number.
    i_o : int | None
        The original validation step number (if a step creates multiple steps). Unused.
    step_id : str | None
        The ID of the step (if a step creates multiple steps). Unused.
    sha1 : str | None
        The SHA-1 hash of the step. Unused.
    assertion_type : str | None
        The type of assertion. This is the method name of the validation (e.g., `"col_vals_gt"`).
    column : str | None
        The column to validate. Currently we don't allow for column expressions (which may map to
        multiple columns).
    values : any | list[any] | tuple | None
        The value or values to compare against.
    na_pass : bool | None
        Whether to pass test units that hold missing values.
    pre : Callable | None
        A pre-processing function or lambda to apply to the data table for the validation step.
    thresholds : Thresholds | None
        The threshold values for the validation.
    label : str | None
        A label for the validation step. Unused.
    brief : str | None
        A brief description of the validation step. Unused.
    active : bool | None
        Whether the validation step is active.
    all_passed : bool | None
        Upon interrogation, this describes whether all test units passed for a validation step.
    n : int | None
        The number of test units for the validation step.
    n_passed : int | None
        The number of test units that passed (i.e., passing test units).
    n_failed : int | None
        The number of test units that failed (i.e., failing test units).
    f_passed : int | None
        The fraction of test units that passed. The calculation is `n_passed / n`.
    f_failed : int | None
        The fraction of test units that failed. The calculation is `n_failed / n`.
    warn : bool | None
        Whether the number of failing test units is beyond the warning threshold.
    stop : bool | None
        Whether the number of failing test units is beyond the stopping threshold.
    notify : bool | None
        Whether the number of failing test units is beyond the notification threshold.
    tbl_checked : bool | None
        The data table in its native format that has been checked for the validation step. It wil
        include a new column called `pb_is_good_` that is a boolean column that indicates whether
        the row passed the validation or not.
    time_processed : str | None
        The time the validation step was processed. This is in the ISO 8601 format in UTC time.
    proc_duration_s : float | None
        The duration of processing for the validation step in seconds.
    """

    # Validation plan
    i: int | None = None
    i_o: int | None = None
    step_id: str | None = None
    sha1: str | None = None
    assertion_type: str | None = None
    column: str | None = None
    values: any | list[any] | tuple | None = None
    inclusive: tuple[bool, bool] | None = None
    na_pass: bool | None = None
    pre: Callable | None = None
    thresholds: Thresholds | None = None
    label: str | None = None
    brief: str | None = None
    active: bool | None = None
    # Interrogation results
    all_passed: bool | None = None
    n: int | None = None
    n_passed: int | None = None
    n_failed: int | None = None
    f_passed: int | None = None
    f_failed: int | None = None
    warn: bool | None = None
    stop: bool | None = None
    notify: bool | None = None
    tbl_checked: FrameT | None = None
    extract: FrameT | None = None
    time_processed: str | None = None
    proc_duration_s: float | None = None


@dataclass
class Validate:
    data: FrameT
    tbl_name: str | None = None
    label: str | None = None
    thresholds: int | float | tuple | dict | Thresholds | None = None

    """
    Workflow for defining a set of validations on a table and interrogating for results.

    Parameters
    ----------
    data : FrameT
        The table to validate. Can be a Pandas or a Polars DataFrame.
    tbl_name : str | None, optional
        A optional name to assign to the input table object. If no value is provided, a name will
        be generated based on whatever information is available. This table name will be displayed
        in the header area of the HTML report generated by using the `report_as_html()` method.
    label : str | None, optional
        An optional label for the validation plan. If no value is provided, a label will be
        generated based on the current system date and time. Markdown can be used here to make the
        label more visually appealing (it will appear in the header area of the HTML report).
    thresholds : int | float | tuple | dict| Thresholds, optional
        Generate threshold failure levels so that all validation steps can report and react
        accordingly when exceeding the set levels. This is to be created in one of several input
        schemes: (1) single integer/float denoting absolute number or fraction of failing test units
        for the 'warn' level, (2) a tuple of 1-3 values, (3) a dictionary of 1-3 entries, or a
        Thresholds object.

    Returns
    -------
    Validate
        A `Validate` object with the table and validations to be performed.
    """

    def __post_init__(self):

        # Check input of the `thresholds=` argument
        _check_thresholds(thresholds=self.thresholds)

        # Normalize the thresholds value (if any) to a Thresholds object
        self.thresholds = _normalize_thresholds_creation(self.thresholds)

        # TODO: Add functionality to obtain the column names and types from the table
        self.col_names = None
        self.col_types = None

        self.time_start = None
        self.time_end = None

        self.validation_info = []

    def col_vals_gt(
        self,
        column: str,
        value: float | int,
        na_pass: bool = False,
        pre: Callable | None = None,
        thresholds: int | float | tuple | dict | Thresholds = None,
        active: bool = True,
    ):
        assertion_type = _get_def_name()

        _check_column(column=column)
        _check_value_float_int(value=value)
        _check_pre(pre=pre)
        _check_thresholds(thresholds=thresholds)
        _check_boolean_input(param=na_pass, param_name="na_pass")
        _check_boolean_input(param=active, param_name="active")

        thresholds = (
            super().__getattribute__("thresholds")
            if thresholds is None
            else _normalize_thresholds_creation(thresholds)
        )

        val_info = _ValidationInfo(
            assertion_type=assertion_type,
            column=column,
            values=value,
            na_pass=na_pass,
            pre=pre,
            thresholds=thresholds,
            active=active,
        )

        return self._add_validation(validation_info=val_info)

    col_vals_gt.__doc__ = f"""{_col_vals_compare_one_title_docstring(comparison="greater than")}
    {_col_vals_compare_one_args_docstring()}
    """

    def col_vals_lt(
        self,
        column: str,
        value: float | int,
        na_pass: bool = False,
        pre: Callable | None = None,
        thresholds: int | float | tuple | dict | Thresholds = None,
        active: bool = True,
    ):
        assertion_type = _get_def_name()

        _check_column(column=column)
        _check_value_float_int(value=value)
        _check_pre(pre=pre)
        _check_thresholds(thresholds=thresholds)
        _check_boolean_input(param=na_pass, param_name="na_pass")
        _check_boolean_input(param=active, param_name="active")

        thresholds = (
            super().__getattribute__("thresholds")
            if thresholds is None
            else _normalize_thresholds_creation(thresholds)
        )

        val_info = _ValidationInfo(
            assertion_type=assertion_type,
            column=column,
            values=value,
            na_pass=na_pass,
            pre=pre,
            thresholds=thresholds,
            active=active,
        )

        return self._add_validation(validation_info=val_info)

    col_vals_lt.__doc__ = f"""{_col_vals_compare_one_title_docstring(comparison="less than")}
    {_col_vals_compare_one_args_docstring()}
    """

    def col_vals_eq(
        self,
        column: str,
        value: float | int,
        na_pass: bool = False,
        pre: Callable | None = None,
        thresholds: int | float | tuple | dict | Thresholds = None,
        active: bool = True,
    ):
        assertion_type = _get_def_name()

        _check_column(column=column)
        _check_value_float_int(value=value)
        _check_pre(pre=pre)
        _check_thresholds(thresholds=thresholds)
        _check_boolean_input(param=na_pass, param_name="na_pass")
        _check_boolean_input(param=active, param_name="active")

        thresholds = (
            super().__getattribute__("thresholds")
            if thresholds is None
            else _normalize_thresholds_creation(thresholds)
        )

        val_info = _ValidationInfo(
            assertion_type=assertion_type,
            column=column,
            values=value,
            na_pass=na_pass,
            pre=pre,
            thresholds=thresholds,
            active=active,
        )

        return self._add_validation(validation_info=val_info)

    col_vals_eq.__doc__ = f"""{_col_vals_compare_one_title_docstring(comparison="equal to")}
    {_col_vals_compare_one_args_docstring()}
    """

    def col_vals_ne(
        self,
        column: str,
        value: float | int,
        na_pass: bool = False,
        pre: Callable | None = None,
        thresholds: int | float | tuple | dict | Thresholds = None,
        active: bool = True,
    ):
        assertion_type = _get_def_name()

        _check_column(column=column)
        _check_value_float_int(value=value)
        _check_pre(pre=pre)
        _check_thresholds(thresholds=thresholds)
        _check_boolean_input(param=na_pass, param_name="na_pass")
        _check_boolean_input(param=active, param_name="active")

        thresholds = (
            super().__getattribute__("thresholds")
            if thresholds is None
            else _normalize_thresholds_creation(thresholds)
        )

        val_info = _ValidationInfo(
            assertion_type=assertion_type,
            column=column,
            values=value,
            na_pass=na_pass,
            pre=pre,
            thresholds=thresholds,
            active=active,
        )

        return self._add_validation(validation_info=val_info)

    col_vals_ne.__doc__ = f"""{_col_vals_compare_one_title_docstring(comparison="not equal to")}
    {_col_vals_compare_one_args_docstring()}
    """

    def col_vals_ge(
        self,
        column: str,
        value: float | int,
        na_pass: bool = False,
        pre: Callable | None = None,
        thresholds: int | float | tuple | dict | Thresholds = None,
        active: bool = True,
    ):
        assertion_type = _get_def_name()

        _check_column(column=column)
        _check_value_float_int(value=value)
        _check_pre(pre=pre)
        _check_thresholds(thresholds=thresholds)
        _check_boolean_input(param=na_pass, param_name="na_pass")
        _check_boolean_input(param=active, param_name="active")

        thresholds = (
            super().__getattribute__("thresholds")
            if thresholds is None
            else _normalize_thresholds_creation(thresholds)
        )

        val_info = _ValidationInfo(
            assertion_type=assertion_type,
            column=column,
            values=value,
            na_pass=na_pass,
            pre=pre,
            thresholds=thresholds,
            active=active,
        )

        return self._add_validation(validation_info=val_info)

    col_vals_ge.__doc__ = f"""{_col_vals_compare_one_title_docstring(comparison="greater than or equal to")}
    {_col_vals_compare_one_args_docstring()}
    """

    def col_vals_le(
        self,
        column: str,
        value: float | int,
        na_pass: bool = False,
        pre: Callable | None = None,
        thresholds: int | float | tuple | dict | Thresholds = None,
        active: bool = True,
    ):
        assertion_type = _get_def_name()

        _check_column(column=column)
        _check_value_float_int(value=value)
        _check_pre(pre=pre)
        _check_thresholds(thresholds=thresholds)
        _check_boolean_input(param=na_pass, param_name="na_pass")
        _check_boolean_input(param=active, param_name="active")

        thresholds = (
            super().__getattribute__("thresholds")
            if thresholds is None
            else _normalize_thresholds_creation(thresholds)
        )

        val_info = _ValidationInfo(
            assertion_type=assertion_type,
            column=column,
            values=value,
            na_pass=na_pass,
            pre=pre,
            thresholds=thresholds,
            active=active,
        )

        return self._add_validation(validation_info=val_info)

    col_vals_le.__doc__ = f"""{_col_vals_compare_one_title_docstring(comparison="less than or equal to")}
    {_col_vals_compare_one_args_docstring()}
    """

    def col_vals_between(
        self,
        column: str,
        left: float | int,
        right: float | int,
        inclusive: tuple[bool, bool] = (True, True),
        na_pass: bool = False,
        pre: Callable | None = None,
        thresholds: int | float | tuple | dict | Thresholds = None,
        active: bool = True,
    ):
        assertion_type = _get_def_name()

        _check_column(column=column)
        _check_value_float_int(value=left)
        _check_value_float_int(value=right)
        _check_pre(pre=pre)
        _check_thresholds(thresholds=thresholds)
        _check_boolean_input(param=na_pass, param_name="na_pass")
        _check_boolean_input(param=active, param_name="active")

        thresholds = (
            super().__getattribute__("thresholds")
            if thresholds is None
            else _normalize_thresholds_creation(thresholds)
        )

        value = (left, right)

        val_info = _ValidationInfo(
            assertion_type=assertion_type,
            column=column,
            values=value,
            inclusive=inclusive,
            na_pass=na_pass,
            pre=pre,
            thresholds=thresholds,
            active=active,
        )

        return self._add_validation(validation_info=val_info)

    col_vals_between.__doc__ = f"""{_col_vals_compare_two_title_docstring(comparison="between")}
    {_col_vals_compare_two_args_docstring()}
    """

    def col_vals_outside(
        self,
        column: str,
        left: float | int,
        right: float | int,
        inclusive: tuple[bool, bool] = (True, True),
        na_pass: bool = False,
        pre: Callable | None = None,
        thresholds: int | float | tuple | dict | Thresholds = None,
        active: bool = True,
    ):
        assertion_type = _get_def_name()

        _check_column(column=column)
        _check_value_float_int(value=left)
        _check_value_float_int(value=right)
        _check_pre(pre=pre)
        _check_thresholds(thresholds=thresholds)
        _check_boolean_input(param=na_pass, param_name="na_pass")
        _check_boolean_input(param=active, param_name="active")

        value = (left, right)

        thresholds = (
            super().__getattribute__("thresholds")
            if thresholds is None
            else _normalize_thresholds_creation(thresholds)
        )

        val_info = _ValidationInfo(
            assertion_type=assertion_type,
            column=column,
            values=value,
            inclusive=inclusive,
            na_pass=na_pass,
            pre=pre,
            thresholds=thresholds,
            active=active,
        )

        return self._add_validation(validation_info=val_info)

    col_vals_outside.__doc__ = f"""{_col_vals_compare_two_title_docstring(comparison="outside of")}
    {_col_vals_compare_two_args_docstring()}
    """

    def col_vals_in_set(
        self,
        column: str,
        set: list[float | int],
        pre: Callable | None = None,
        thresholds: int | float | tuple | dict | Thresholds = None,
        active: bool = True,
    ):
        assertion_type = _get_def_name()

        _check_column(column=column)
        _check_set_types(set=set)
        _check_pre(pre=pre)
        _check_thresholds(thresholds=thresholds)
        _check_boolean_input(param=active, param_name="active")

        thresholds = (
            super().__getattribute__("thresholds")
            if thresholds is None
            else _normalize_thresholds_creation(thresholds)
        )

        val_info = _ValidationInfo(
            assertion_type=assertion_type,
            column=column,
            values=set,
            pre=pre,
            thresholds=thresholds,
            active=active,
        )

        return self._add_validation(validation_info=val_info)

    col_vals_in_set.__doc__ = f"""{_col_vals_compare_set_title_docstring(inside=True)}
    {_col_vals_compare_set_args_docstring()}
    """

    def col_vals_not_in_set(
        self,
        column: str,
        set: list[float | int],
        pre: Callable | None = None,
        thresholds: int | float | tuple | dict | Thresholds = None,
        active: bool = True,
    ):
        assertion_type = _get_def_name()

        _check_column(column=column)
        _check_set_types(set=set)
        _check_pre(pre=pre)
        _check_thresholds(thresholds=thresholds)
        _check_boolean_input(param=active, param_name="active")

        thresholds = (
            super().__getattribute__("thresholds")
            if thresholds is None
            else _normalize_thresholds_creation(thresholds)
        )

        val_info = _ValidationInfo(
            assertion_type=assertion_type,
            column=column,
            values=set,
            pre=pre,
            thresholds=thresholds,
            active=active,
        )

        return self._add_validation(validation_info=val_info)

    col_vals_not_in_set.__doc__ = f"""{_col_vals_compare_set_title_docstring(inside=False)}
    {_col_vals_compare_set_args_docstring()}
    """

    def interrogate(self):
        """
        Evaluate each validation against the table and store the results.

        Returns
        -------
        Validate
            The `Validate` object with the results of the interrogation.
        """

        df = self.data

        self.time_start = datetime.datetime.now(datetime.timezone.utc)

        for validation in self.validation_info:

            start_time = datetime.datetime.now(datetime.timezone.utc)

            # Skip the validation step if it is not active but still record the time of processing
            if not validation.active:
                end_time = datetime.datetime.now(datetime.timezone.utc)
                validation.proc_duration_s = (end_time - start_time).total_seconds()
                validation.time_processed = end_time.isoformat(timespec="milliseconds")
                continue

            # Make a copy of the table for this step
            df_step = df

            # ------------------------------------------------
            # Pre-processing stage
            # ------------------------------------------------

            # Determine whether any pre-processing functions are to be applied to the table
            if validation.pre is not None:

                # Read the text of the pre-processing function
                pre_text = _pre_processing_funcs_to_str(validation.pre)

                # Determine if the pre-processing function is a lambda function; return a boolean
                is_lambda = re.match(r"^lambda", pre_text) is not None

                # If the pre-processing function is a lambda function, then check if there is
                # a keyword argument called `dfn` in the lamda signature; if so, that's a cue
                # to use a Narwhalified version of the table
                if is_lambda:

                    # Get the signature of the lambda function
                    sig = inspect.signature(validation.pre)

                    # Check if the lambda function has a keyword argument called `dfn`
                    if "dfn" in sig.parameters:

                        # Convert the table to a Narwhals DataFrame
                        df_step = nw.from_native(df_step)

                        # Apply the pre-processing function to the table
                        df_step = validation.pre(dfn=df_step)

                        # Convert the table back to its original format
                        df_step = nw.to_native(df_step)

                # If the pre-processing function is a named function, apply it to the table
                elif isinstance(validation.pre, str):
                    df_step = globals()[validation.pre](df_step)

            type = validation.assertion_type
            column = validation.column
            value = validation.values
            inclusive = validation.inclusive
            na_pass = validation.na_pass
            threshold = validation.thresholds

            comparison = TYPE_METHOD_MAP[type]
            compare_type = COMPARE_TYPE_MAP[comparison]
            compatible_types = COMPATIBLE_TYPES.get(comparison, [])

            validation.n = NumberOfTestUnits(df=df_step, column=column).get_test_units()

            if compare_type == "COMPARE_ONE":

                results_tbl = ColValsCompareOne(
                    df=df_step,
                    column=column,
                    value=value,
                    na_pass=na_pass,
                    threshold=threshold,
                    comparison=comparison,
                    allowed_types=compatible_types,
                    compare_strategy="table",
                ).get_test_results()

            if compare_type == "COMPARE_TWO":

                results_tbl = ColValsCompareTwo(
                    df=df_step,
                    column=column,
                    value1=value[0],
                    value2=value[1],
                    inclusive=inclusive,
                    na_pass=na_pass,
                    threshold=threshold,
                    comparison=comparison,
                    allowed_types=compatible_types,
                    compare_strategy="table",
                ).get_test_results()

            if compare_type == "COMPARE_SET":

                inside = True if comparison == "in_set" else False

                results_tbl = ColValsCompareSet(
                    df=df_step,
                    column=column,
                    values=value,
                    threshold=threshold,
                    inside=inside,
                    allowed_types=compatible_types,
                    compare_strategy="table",
                ).get_test_results()

            # Extract the `pb_is_good_` column from the table as a results list
            results_list = nw.from_native(results_tbl)["pb_is_good_"].to_list()

            validation.all_passed = all(results_list)
            validation.n = len(results_list)
            validation.n_passed = results_list.count(True)
            validation.n_failed = results_list.count(False)

            # Calculate fractions of passing and failing test units
            # - `f_passed` is the fraction of test units that passed
            # - `f_failed` is the fraction of test units that failed
            for attr in ["passed", "failed"]:
                setattr(
                    validation,
                    f"f_{attr}",
                    _convert_abs_count_to_fraction(
                        value=getattr(validation, f"n_{attr}"), test_units=validation.n
                    ),
                )

            # Determine if the number of failing test units is beyond the threshold value
            # for each of the severity levels
            # - `warn` is the threshold for a warning
            # - `stop` is the threshold for stopping
            # - `notify` is the threshold for notifying
            for level in ["warn", "stop", "notify"]:
                setattr(
                    validation,
                    level,
                    threshold._threshold_result(
                        fraction_failing=validation.f_failed, test_units=validation.n, level=level
                    ),
                )

            # Include the results table that has a new column called `pb_is_good_`; that
            # is a boolean column that indicates whether the row passed the validation or not
            validation.tbl_checked = results_tbl

            # If this is a row-based validation step, then extract the rows that failed
            if type in ROW_BASED_VALIDATION_TYPES:
                validation.extract = (
                    nw.from_native(results_tbl)
                    .filter(nw.col("pb_is_good_") == False)
                    .drop("pb_is_good_")
                    .to_native()
                )

            # Get the end time for this step
            end_time = datetime.datetime.now(datetime.timezone.utc)

            # Calculate the duration of processing for this step
            validation.proc_duration_s = (end_time - start_time).total_seconds()

            # Set the time of processing for this step, this should be UTC time is ISO 8601 format
            validation.time_processed = end_time.isoformat(timespec="milliseconds")

        self.time_end = datetime.datetime.now(datetime.timezone.utc)

        return self

    def all_passed(self) -> bool:
        """
        Determine if every validation step passed perfectly, with no failing test units.

        Returns
        -------
        bool
            `True` if all validations passed, `False` otherwise.
        """
        return all(validation.all_passed for validation in self.validation_info)

    def n(self, i: int | list[int] | None = None) -> dict[int, int]:
        """
        Provides a dictionary of the number of test units for each validation step.

        Parameters
        ----------
        i : int | list[int], optional
            The validation step number(s) from which the number of test units is obtained.
            If `None`, all steps are included.

        Returns
        -------
        dict[int, int]
            A dictionary of the number of test units for each validation step.
        """

        return self._get_validation_dict(i, "n")

    def n_passed(self, i: int | list[int] | None = None) -> dict[int, int]:
        """
        Provides a dictionary of the number of test units that passed for each validation step.

        Parameters
        ----------
        i : int | list[int], optional
            The validation step number(s) from which the number of passing test units is obtained.
            If `None`, all steps are included.

        Returns
        -------
        dict[int, int]
            A dictionary of the number of failing test units for each validation step.
        """

        return self._get_validation_dict(i, "n_passed")

    def n_failed(self, i: int | list[int] | None = None) -> dict[int, int]:
        """
        Provides a dictionary of the number of test units that failed for each validation step.

        Parameters
        ----------
        i : int | list[int], optional
            The validation step number(s) from which the number of failing test units is obtained.
            If `None`, all steps are included.

        Returns
        -------
        dict[int, int]
            A dictionary of the number of failing test units for each validation step.
        """

        return self._get_validation_dict(i, "n_failed")

    def f_passed(self, i: int | list[int] | None = None) -> dict[int, float]:
        """
        Provides a dictionary of the fraction of test units that passed for each validation step.

        Parameters
        ----------
        i : int | list[int], optional
            The validation step number(s) from which the fraction of passing test units is obtained.
            If `None`, all steps are included.

        Returns
        -------
        dict[int, float]
            A dictionary of the fraction of passing test units for each validation step.
        """

        return self._get_validation_dict(i, "f_passed")

    def f_failed(self, i: int | list[int] | None = None) -> dict[int, float]:
        """
        Provides a dictionary of the fraction of test units that failed for each validation step.

        Parameters
        ----------
        i : int | list[int], optional
            The validation step number(s) from which the fraction of failing test units is obtained.
            If `None`, all steps are included.

        Returns
        -------
        dict[int, float]
            A dictionary of the fraction of failing test units for each validation step.
        """

        return self._get_validation_dict(i, "f_failed")

    def warn(self, i: int | list[int] | None = None) -> dict[int, bool]:
        """
        Provides a dictionary of the warning status for each validation step.

        Parameters
        ----------
        i : int | list[int], optional
            The validation step number(s) from which the warning status is obtained.
            If `None`, all steps are included.

        Returns
        -------
        dict[int, bool]
            A dictionary of the warning status for each validation step.
        """

        return self._get_validation_dict(i, "warn")

    def stop(self, i: int | list[int] | None = None) -> dict[int, bool]:
        """
        Provides a dictionary of the stopping status for each validation step.

        Parameters
        ----------
        i : int | list[int], optional
            The validation step number(s) from which the stopping status is obtained.
            If `None`, all steps are included.

        Returns
        -------
        dict[int, bool]
            A dictionary of the stopping status for each validation step.
        """

        return self._get_validation_dict(i, "stop")

    def notify(self, i: int | list[int] | None = None) -> dict[int, bool]:
        """
        Provides a dictionary of the notification status for each validation step.

        Parameters
        ----------
        i : int | list[int], optional
            The validation step number(s) from which the notification status is obtained.
            If `None`, all steps are included.

        Returns
        -------
        dict[int, bool]
            A dictionary of the notification status for each validation step.
        """

        return self._get_validation_dict(i, "notify")

    def get_data_extracts(self, i: int | list[int] | None = None) -> dict[int, FrameT | None]:
        """
        Get the rows that failed for each validation step.

        Parameters
        ----------
        i : int | list[int], optional
            The validation step number(s) from which the failed rows are obtained. If `None`, all
            steps are included.

        Returns
        -------
        dict[int, FrameT]
            A dictionary of tables containing the rows that failed in every row-based validation
            step.
        """
        return self._get_validation_dict(i, "extract")

    def get_json_report(
        self, use_fields: list[str] | None = None, exclude_fields: list[str] | None = None
    ) -> str:
        """
        Get a report of the validation results as a JSON-formatted string.

        Parameters
        ----------
        use_fields : list[str], optional
            A list of fields to include in the report. If `None`, all fields are included.
        exclude_fields : list[str], optional
            A list of fields to exclude from the report. If `None`, no fields are excluded.

        Returns
        -------
        str
            A JSON-formatted string representing the validation report.
        """

        if use_fields is not None and exclude_fields is not None:
            raise ValueError("Cannot specify both `use_fields=` and `exclude_fields=`.")

        if use_fields is None:
            fields = VALIDATION_REPORT_FIELDS
        else:

            # Ensure that the fields to use are valid
            _check_invalid_fields(use_fields, VALIDATION_REPORT_FIELDS)

            fields = use_fields

        if exclude_fields is not None:

            # Ensure that the fields to exclude are valid
            _check_invalid_fields(exclude_fields, VALIDATION_REPORT_FIELDS)

            fields = [field for field in fields if field not in exclude_fields]

        report = []

        for validation_info in self.validation_info:
            report_entry = {
                field: getattr(validation_info, field) for field in VALIDATION_REPORT_FIELDS
            }

            # If pre-processing functions are included in the report, convert them to strings
            if "pre" in fields:
                report_entry["pre"] = _pre_processing_funcs_to_str(report_entry["pre"])

            # Filter the report entry based on the fields to include
            report_entry = {field: report_entry[field] for field in fields}

            report.append(report_entry)

        return json.dumps(report, indent=4, default=str)

    def get_tabular_report(self, title: str | None = ":default:") -> GT:
        """
        Validation report as a GT table.

        Parameters
        ----------
        title : str | None, optional
            Options for customizing the title of the report. The default is the `":default:"` value
            which produces a generic title. Another option is `":tbl_name:"`, and that presents the
            name of the table as the title for the report. If no title is wanted, then `":none:"`
            can be used. Aside from keyword options, text can be provided for the title. This will
            be interpreted as Markdown text and transformed internally to HTML.

        Returns
        -------
        GT
            A GT table object that represents the validation report.
        """

        # Determine whether Pandas or Polars is available
        try:
            import pandas as pd
        except ImportError:
            pd = None

        try:
            import polars as pl
        except ImportError:
            pl = None

        # If neither Pandas nor Polars is available, raise an ImportError
        if pd is None and pl is None:
            raise ImportError(
                "Generating a report with the `get_tabular_report()` method requires either the "
                "Polars or the Pandas library to be installed."
            )

        # Prefer the use of the Polars library if available
        tbl_lib = pl if pl is not None else pd

        validation_info_dict = _validation_info_as_dict(validation_info=self.validation_info)

        # Has the validation been performed? We can check the first `time_processed` entry in the
        # dictionary to see if it is `None` or not; The output of many cells in the reporting table
        # will be made blank if the validation has not been performed
        interrogation_performed = validation_info_dict.get("proc_duration_s", [None])[0] is not None

        # ------------------------------------------------
        # Process the `type` entry
        # ------------------------------------------------

        # Add the `type_upd` entry to the dictionary
        validation_info_dict["type_upd"] = _transform_assertion_str(
            assertion_str=validation_info_dict["assertion_type"]
        )

        # ------------------------------------------------
        # Process the `values` entry
        # ------------------------------------------------

        # Here, `values` will be transformed in ways particular to the assertion type (e.g.,
        # single values, ranges, sets, etc.)

        # Create a list to store the transformed values
        values_upd = []

        # Iterate over the values in the `values` entry
        values = validation_info_dict["values"]
        assertion_type = validation_info_dict["assertion_type"]
        inclusive = validation_info_dict["inclusive"]
        active = validation_info_dict["active"]

        for i, value in enumerate(values):

            # If the assertion type is a comparison of one value then add the value as a string
            if assertion_type[i] in [
                "col_vals_gt",
                "col_vals_lt",
                "col_vals_eq",
                "col_vals_ne",
                "col_vals_ge",
                "col_vals_le",
            ]:
                values_upd.append(str(value))

            # If the assertion type is a comparison of values within or outside of a range, add
            # the appropriate brackets (inclusive or exclusive) to the values
            elif assertion_type[i] in ["col_vals_between", "col_vals_outside"]:
                left_bracket = "[" if inclusive[i][0] else "("
                right_bracket = "]" if inclusive[i][1] else ")"
                values_upd.append(f"{left_bracket}{value[0]}, {value[1]}{right_bracket}")

            # If the assertion type is a comparison of a set of values; strip the leading and
            # trailing square brackets and single quotes
            elif assertion_type[i] in ["col_vals_in_set", "col_vals_not_in_set"]:
                values_upd.append(str(value)[1:-1].replace("'", ""))

            # If the assertion type is not recognized, add the value as a string
            else:
                values_upd.append(str(value))

        # Remove the `inclusive` entry from the dictionary
        validation_info_dict.pop("inclusive")

        # Add the `values_upd` entry to the dictionary
        validation_info_dict["values_upd"] = values_upd

        ## ------------------------------------------------
        ## The folloiwng entries rely on an interrogation
        ## to have been performed
        ## ------------------------------------------------

        # ------------------------------------------------
        # Add the `tbl` entry
        # ------------------------------------------------

        # Depending on if there was some pre-processing done, get the appropriate icon
        # for the table processing status to be displayed in the report under the `tbl` column

        validation_info_dict["tbl"] = _transform_tbl_preprocessed(
            pre=validation_info_dict["pre"], interrogation_performed=interrogation_performed
        )

        # ------------------------------------------------
        # Add the `eval` entry
        # ------------------------------------------------

        # Add the `eval` entry to the dictionary

        validation_info_dict["eval"] = _transform_eval(
            n=validation_info_dict["n"],
            interrogation_performed=interrogation_performed,
            active=active,
        )

        # ------------------------------------------------
        # Process the `test_units` entry
        # ------------------------------------------------

        # Add the `test_units` entry to the dictionary
        validation_info_dict["test_units"] = _transform_test_units(
            test_units=validation_info_dict["n"],
            interrogation_performed=interrogation_performed,
            active=active,
        )

        # ------------------------------------------------
        # Process `pass` and `fail` entries
        # ------------------------------------------------

        # Create a `pass` entry that concatenates the `n_passed` and `n_failed` entries (the length
        # of the `pass` entry should be equal to the length of the `n_passed` and `n_failed` entries)

        validation_info_dict["pass"] = _transform_passed_failed(
            n_passed_failed=validation_info_dict["n_passed"],
            f_passed_failed=validation_info_dict["f_passed"],
            interrogation_performed=interrogation_performed,
            active=active,
        )

        validation_info_dict["fail"] = _transform_passed_failed(
            n_passed_failed=validation_info_dict["n_failed"],
            f_passed_failed=validation_info_dict["f_failed"],
            interrogation_performed=interrogation_performed,
            active=active,
        )

        # ------------------------------------------------
        # Process `w_upd`, `s_upd`, `n_upd` entries
        # ------------------------------------------------

        # Transform `warn`, `stop`, and `notify` to `w_upd`, `s_upd`, and `n_upd` entries
        validation_info_dict["w_upd"] = _transform_w_s_n(
            values=validation_info_dict["warn"],
            color="#E5AB00",
            interrogation_performed=interrogation_performed,
        )
        validation_info_dict["s_upd"] = _transform_w_s_n(
            values=validation_info_dict["stop"],
            color="#CF142B",
            interrogation_performed=interrogation_performed,
        )
        validation_info_dict["n_upd"] = _transform_w_s_n(
            values=validation_info_dict["notify"],
            color="#439CFE",
            interrogation_performed=interrogation_performed,
        )

        # Remove the `assertion_type` entry from the dictionary
        validation_info_dict.pop("assertion_type")

        # Remove the `values` entry from the dictionary
        validation_info_dict.pop("values")

        # Remove the `n` entry from the dictionary
        validation_info_dict.pop("n")

        # Remove the `pre` entry from the dictionary
        validation_info_dict.pop("pre")

        # Remove the `proc_duration_s` entry from the dictionary
        validation_info_dict.pop("proc_duration_s")

        # Remove `n_passed`, `n_failed`, `f_passed`, and `f_failed` entries from the dictionary
        validation_info_dict.pop("n_passed")
        validation_info_dict.pop("n_failed")
        validation_info_dict.pop("f_passed")
        validation_info_dict.pop("f_failed")

        # Remove the `warn`, `stop`, and `notify` entries from the dictionary
        validation_info_dict.pop("warn")
        validation_info_dict.pop("stop")
        validation_info_dict.pop("notify")

        # Drop several unused keys from the dictionary
        validation_info_dict.pop("na_pass")
        validation_info_dict.pop("label")
        validation_info_dict.pop("brief")
        validation_info_dict.pop("active")
        validation_info_dict.pop("all_passed")

        # Create a table time string
        table_time = _create_table_time_html(time_start=self.time_start, time_end=self.time_end)

        # Create the title text
        title_text = _get_title_text(
            title=title, tbl_name=self.tbl_name, interrogation_performed=interrogation_performed
        )

        # Create a DataFrame from the validation information using the `tbl_lib` library; which is
        # either Polars or Pandas
        df = tbl_lib.DataFrame(validation_info_dict)

        # Return the DataFrame as a Great Tables table
        gt_tbl = (
            GT(df, id="pb_tbl")
            .tab_header(title=html(title_text))
            .tab_source_note(source_note=html(table_time))
            .fmt_markdown(columns=["pass", "fail"])
            .opt_table_font(font=google_font(name="IBM Plex Sans"))
            .opt_align_table_header(align="left")
            .tab_style(style=style.css("height: 40px;"), locations=loc.body())
            .tab_style(
                style=style.text(weight="bold", color="#666666", size="13px"),
                locations=loc.body(columns="i"),
            )
            .tab_style(
                style=style.text(weight="bold", color="#666666"), locations=loc.column_labels()
            )
            .tab_style(
                style=style.text(size="28px", weight="bold", align="left", color="#444444"),
                locations=loc.title(),
            )
            .tab_style(
                style=style.text(
                    color="black", font=google_font(name="IBM Plex Mono"), size="11px"
                ),
                locations=loc.body(
                    columns=["type_upd", "column", "values_upd", "test_units", "pass", "fail"]
                ),
            )
            .tab_style(
                style=style.borders(sides="left", color="#E5E5E5", style="dashed"),
                locations=loc.body(columns=["column", "values_upd"]),
            )
            .tab_style(
                style=style.borders(
                    sides="left",
                    color="#E5E5E5",
                    style="dashed" if interrogation_performed else "none",
                ),
                locations=loc.body(columns=["pass", "fail"]),
            )
            .tab_style(
                style=style.fill(color="#FCFCFC" if interrogation_performed else "white"),
                locations=loc.body(columns=["w_upd", "s_upd", "n_upd"]),
            )
            .tab_style(
                style=style.borders(
                    sides="right",
                    color="#D3D3D3",
                    style="solid" if interrogation_performed else "none",
                ),
                locations=loc.body(columns="n_upd"),
            )
            .tab_style(
                style=style.borders(
                    sides="left",
                    color="#D3D3D3",
                    style="solid" if interrogation_performed else "none",
                ),
                locations=loc.body(columns="w_upd"),
            )
            .tab_style(
                style=style.fill(color="#FCFCFC" if interrogation_performed else "white"),
                locations=loc.body(columns=["tbl", "eval"]),
            )
            .tab_style(
                style=style.borders(
                    sides="right",
                    color="#D3D3D3",
                    style="solid" if interrogation_performed else "none",
                ),
                locations=loc.body(columns="eval"),
            )
            .tab_style(
                style=style.borders(sides="left", color="#D3D3D3", style="solid"),
                locations=loc.body(columns="tbl"),
            )
            .cols_label(
                cases={
                    "i": "",
                    "type_upd": "STEP",
                    "column": "COLUMNS",
                    "tbl": "TBL",
                    "eval": "EVAL",
                    "values_upd": "VALUES",
                    "test_units": "UNITS",
                    "pass": "PASS",
                    "fail": "FAIL",
                    "w_upd": "W",
                    "s_upd": "S",
                    "n_upd": "N",
                }
            )
            .cols_width(
                cases={
                    "i": "35px",
                    "type_upd": "190px",
                    "column": "120px",
                    "values_upd": "120px",
                    "tbl": "50px",
                    "eval": "50px",
                    "test_units": "60px",
                    "pass": "60px",
                    "fail": "60px",
                    "w_upd": "30px",
                    "s_upd": "30px",
                    "n_upd": "30px",
                }
            )
            .cols_align(align="center", columns=["tbl", "eval", "w_upd", "s_upd", "n_upd"])
            .cols_align(align="right", columns=["test_units", "pass", "fail"])
            .cols_move_to_start(
                [
                    "i",
                    "type_upd",
                    "column",
                    "values_upd",
                    "tbl",
                    "eval",
                    "test_units",
                    "pass",
                    "fail",
                ]
            )
            .tab_options(table_font_size="90%")
        )

        # If the interrogation has not been performed, then style the table columns dealing with
        # interrogation data as grayed out
        if not interrogation_performed:
            gt_tbl = gt_tbl.tab_style(
                style=style.fill(color="#F2F2F2"),
                locations=loc.body(
                    columns=["tbl", "eval", "test_units", "pass", "fail", "w_upd", "s_upd", "n_upd"]
                ),
            )

        # Transform `active` to a list of indices of inactive validations
        inactive_steps = [i for i, active in enumerate(active) if not active]

        # If there are inactive steps, then style those rows to be grayed out
        if inactive_steps:
            gt_tbl = gt_tbl.tab_style(
                style=style.fill(color="#F2F2F2"),
                locations=loc.body(rows=inactive_steps),
            )

        return gt_tbl

    def _add_validation(self, validation_info):
        """
        Add a validation to the list of validations.

        Parameters
        ----------
        validation_info : _ValidationInfo
            Information about the validation to add.
        """

        validation_info.i = len(self.validation_info) + 1

        self.validation_info.append(validation_info)

        return self

    def _get_validations(self):
        """
        Get the list of validations.

        Returns
        -------
        list[_ValidationInfo]
            The list of validations.
        """
        return self.validation_info

    def _clear_validations(self):
        """
        Clear the list of validations.
        """
        self.validation_info.clear()

        return self.validation_info

    def _get_validation_dict(self, i: int | list[int] | None, attr: str) -> dict[int, int]:
        """
        Utility function to get a dictionary of validation attributes for each validation step.

        Parameters
        ----------
        i : int | list[int] | None
            The validation step number(s) from which the attribute values are obtained.
            If `None`, all steps are included.
        attr : str
            The attribute name to retrieve from each validation step.

        Returns
        -------
        dict[int, int]
            A dictionary of the attribute values for each validation step.
        """
        if isinstance(i, int):
            i = [i]

        if i is None:
            return {validation.i: getattr(validation, attr) for validation in self.validation_info}

        return {
            validation.i: getattr(validation, attr)
            for validation in self.validation_info
            if validation.i in i
        }


def _validation_info_as_dict(validation_info: _ValidationInfo) -> dict:
    """
    Convert a `_ValidationInfo` object to a dictionary.

    Parameters
    ----------
    validation_info : _ValidationInfo
        The `_ValidationInfo` object to convert to a dictionary.

    Returns
    -------
    dict
        A dictionary representing the `_ValidationInfo` object.
    """

    # Define the fields to include in the validation information
    validation_info_fields = [
        "i",
        "assertion_type",
        "column",
        "values",
        "inclusive",
        "na_pass",
        "pre",
        "label",
        "brief",
        "active",
        "all_passed",
        "n",
        "n_passed",
        "n_failed",
        "f_passed",
        "f_failed",
        "warn",
        "stop",
        "notify",
        "proc_duration_s",
    ]

    # Filter the validation information to include only the selected fields
    validation_info_filtered = [
        {field: getattr(validation, field) for field in validation_info_fields}
        for validation in validation_info
    ]

    # Transform the validation information into a dictionary of lists so that it
    # can be used to create a DataFrame
    validation_info_dict = {field: [] for field in validation_info_fields}

    for validation in validation_info_filtered:
        for field in validation_info_fields:
            validation_info_dict[field].append(validation[field])

    return validation_info_dict


def _transform_w_s_n(values, color, interrogation_performed):

    # If no interrogation was performed, return a list of empty strings
    if not interrogation_performed:
        return ["" for _ in range(len(values))]

    return [
        (
            "&mdash;"
            if value is None
            else (
                f'<span style="color: {color};">&#9679;</span>'
                if value is True
                else f'<span style="color: {color};">&cir;</span>' if value is False else value
            )
        )
        for value in values
    ]


def _get_assertion_icon(icon: list[str] | None, length_val: int = 30) -> list[str]:

    # If icon is None, return an empty list
    if icon is None:
        return []

    # For each icon, get the assertion icon SVG test from SVG_ICONS_FOR_ASSERTION_TYPES dictionary
    icon_svg = [SVG_ICONS_FOR_ASSERTION_TYPES.get(icon) for icon in icon]

    # Replace the width and height in the SVG string
    for i in range(len(icon_svg)):
        icon_svg[i] = _replace_svg_dimensions(icon_svg[i], height_width=length_val)

    return icon_svg


def _get_title_text(title: str | None, tbl_name: str | None, interrogation_performed: bool) -> str:

    title = _process_title_text(title=title, tbl_name=tbl_name)

    if interrogation_performed:
        return title

    html_str = (
        "<div>"
        '<span style="float: left;">'
        f"{title}"
        "</span>"
        '<span style="float: right; text-decoration-line: underline; '
        "text-underline-position: under;"
        "font-size: 16px; text-decoration-color: #9C2E83;"
        'padding-top: 0.1em; padding-right: 0.4em;">'
        "No Interrogation Peformed"
        "</span>"
        "</div>"
    )

    return html_str


def _process_title_text(title: str | None, tbl_name: str | None) -> str:

    if title is None:
        title_text = ""
    elif title == ":default:":
        title_text = _get_default_title_text()
    elif title == ":none:":
        title_text = ""
    elif title == ":tbl_name:":
        if tbl_name is not None:
            title_text = f"<code>{tbl_name}</code>"
        else:
            title_text = ""
    else:
        title_text = commonmark.commonmark(title)

    return title_text


def _get_default_title_text() -> str:
    return "Pointblank Validation"


def _replace_svg_dimensions(svg: list[str], height_width: int | float) -> list[str]:

    svg = re.sub(r'width="[0-9]*?px', f'width="{height_width}px', svg)
    svg = re.sub(r'height="[0-9]*?px', f'height="{height_width}px', svg)

    return svg


def _transform_tbl_preprocessed(pre: str, interrogation_performed: bool) -> list[str]:

    # If no interrogation was performed, return a list of empty strings
    if not interrogation_performed:
        return ["" for _ in range(len(pre))]

    # Iterate over the pre-processed table status and return the appropriate SVG icon name
    # (either 'unchanged' (None) or 'modified' (not None))
    status_list = []

    for status in pre:
        if status is None:
            status_list.append("unchanged")
        else:
            status_list.append("modified")

    return _get_preprocessed_table_icon(icon=status_list)


def _get_preprocessed_table_icon(icon: list[str]) -> list[str]:

    # If the pre-processed table is None, return an empty list
    if icon is None:
        return []

    # For each icon, get the SVG icon from the SVG_ICONS_FOR_TBL_STATUS dictionary
    icon_svg = [SVG_ICONS_FOR_TBL_STATUS.get(icon) for icon in icon]

    return icon_svg


def _transform_eval(n: list[int], interrogation_performed: bool, active: list[bool]) -> list[str]:

    # If no interrogation was performed, return a list of empty strings
    if not interrogation_performed:
        return ["" for _ in range(len(n))]

    return [
        '<span style="color:#4CA64C;">&check;</span>' if active[i] else "&mdash;"
        for i in range(len(n))
    ]


def _transform_test_units(
    test_units: list[int], interrogation_performed: bool, active: list[bool]
) -> list[str]:

    # If no interrogation was performed, return a list of empty strings
    if not interrogation_performed:
        return ["" for _ in range(len(test_units))]

    return [str(test_units[i]) if active[i] else "&mdash;" for i in range(len(test_units))]


def _transform_passed_failed(
    n_passed_failed: list[int],
    f_passed_failed: list[float],
    interrogation_performed: bool,
    active: list[bool],
) -> list[str]:

    if not interrogation_performed:
        return ["" for _ in range(len(n_passed_failed))]

    passed_failed = [
        f"{n_passed_failed[i]}<br />{f_passed_failed[i]}" if active[i] else "&mdash;"
        for i in range(len(n_passed_failed))
    ]

    return passed_failed


def _transform_assertion_str(assertion_str: list[str]) -> list[str]:

    # Get the SVG icons for the assertion types
    svg_icon = _get_assertion_icon(icon=assertion_str)

    # Append `()` to the `assertion_str`
    assertion_str = [x + "()" for x in assertion_str]

    # Obtain the number of characters contained in the assertion
    # string; this is important for sizing components appropriately
    assertion_type_nchar = [len(x) for x in assertion_str]

    # Declare the text size based on the length of `assertion_str`
    text_size = [10 if nchar + 2 >= 20 else 11 for nchar in assertion_type_nchar]

    # Create the assertion type update using a list comprehension
    type_upd = [
        f"""
        <div style="margin:0;padding:0;display:inline-block;height:30px;vertical-align:middle;">
        <!--?xml version="1.0" encoding="UTF-8"?-->{svg}
        </div>
        <span style="font-family: 'IBM Plex Mono', monospace, courier; color: black; font-size:{size}px;"> {assertion}</span>
        """
        for assertion, svg, size in zip(assertion_str, svg_icon, text_size)
    ]

    return type_upd


def _pre_processing_funcs_to_str(pre: Callable) -> str | list[str]:

    if isinstance(pre, Callable):
        return _get_callable_source(fn=pre)


def _get_callable_source(fn: Callable) -> str:
    if isinstance(fn, Callable):
        try:
            source_lines, _ = inspect.getsourcelines(fn)
            source = "".join(source_lines).strip()
            # Extract the `pre` argument from the source code
            pre_arg = _extract_pre_argument(source)
            return pre_arg
        except (OSError, TypeError):
            return fn.__name__
    return fn


def _extract_pre_argument(source: str) -> str:

    # Find the start of the `pre` argument
    pre_start = source.find("pre=")
    if pre_start == -1:
        return source

    # Find the end of the `pre` argument
    pre_end = source.find(",", pre_start)
    if pre_end == -1:
        pre_end = len(source)

    # Extract the `pre` argument and remove the leading `pre=`
    pre_arg = source[pre_start + len("pre=") : pre_end].strip()

    return pre_arg


def _create_table_time_html(
    time_start: datetime.datetime | None, time_end: datetime.datetime | None
) -> str:

    if time_start is None:
        return ""

    # Get the time duration (difference between `time_end` and `time_start`) in seconds
    time_duration = (time_end - time_start).total_seconds()

    # If the time duration is less than 1 second, use a simplified string, otherwise
    # format the time duration to four decimal places
    if time_duration < 1:
        time_duration_fmt = "< 1 s"
    else:
        time_duration_fmt = f"{time_duration:.4f} s"

    # Format the start time and end time in the format: "%Y-%m-%d %H:%M:%S %Z"
    time_start_fmt = time_start.strftime("%Y-%m-%d %H:%M:%S %Z")
    time_end_fmt = time_end.strftime("%Y-%m-%d %H:%M:%S %Z")

    # Generate an HTML string that displays the start time, duration, and end time
    return (
        f"<div style='margin-top: 5px; margin-bottom: 5px;'>"
        f"<span style='background-color: #FFF; color: #444; padding: 0.5em 0.5em; position: "
        f"inherit; text-transform: uppercase; margin-left: 10px; margin-right: 5px; border: "
        f"solid 1px #999999; font-variant-numeric: tabular-nums; border-radius: 0; padding: "
        f"2px 10px 2px 10px;'>{time_start_fmt}</span>"
        f"<span style='background-color: #FFF; color: #444; padding: 0.5em 0.5em; position: "
        f"inherit; margin-right: 5px; border: solid 1px #999999; font-variant-numeric: "
        f"tabular-nums; border-radius: 0; padding: 2px 10px 2px 10px;'>{time_duration_fmt}</span>"
        f"<span style='background-color: #FFF; color: #444; padding: 0.5em 0.5em; position: "
        f"inherit; text-transform: uppercase; margin: 5px 1px 5px -1px; border: solid 1px #999999; "
        f"font-variant-numeric: tabular-nums; border-radius: 0; padding: 2px 10px 2px 10px;'>"
        f"{time_end_fmt}</span>"
        f"</div>"
    )
def _create_thresholds_html(thresholds: Thresholds) -> str:

    if thresholds == Thresholds():
        return ""

    warn = (
        thresholds.warn_fraction
        if thresholds.warn_fraction is not None
        else (thresholds.warn_count if thresholds.warn_count is not None else "&mdash;")
    )

    stop = (
        thresholds.stop_fraction
        if thresholds.stop_fraction is not None
        else (thresholds.stop_count if thresholds.stop_count is not None else "&mdash;")
    )

    notify = (
        thresholds.notify_fraction
        if thresholds.notify_fraction is not None
        else (thresholds.notify_count if thresholds.notify_count is not None else "&mdash;")
    )

    return (
        "<span>"
        '<span style="background-color: #E5AB00; color: white; padding: 0.5em 0.5em; position: inherit; '
        "text-transform: uppercase; margin: 5px 0px 5px 5px; border: solid 1px #E5AB00; font-weight: bold; "
        'padding: 2px 15px 2px 15px; font-size: smaller;">WARN</span>'
        '<span style="background-color: none; color: #333333; padding: 0.5em 0.5em; position: inherit; '
        "margin: 5px 0px 5px -4px; font-weight: bold; border: solid 1px #E5AB00; padding: 2px 15px 2px 15px; "
        'font-size: smaller; margin-right: 5px;">'
        f"{warn}"
        "</span>"
        '<span style="background-color: #D0182F; color: white; padding: 0.5em 0.5em; position: inherit; '
        "text-transform: uppercase; margin: 5px 0px 5px 1px; border: solid 1px #D0182F; font-weight: bold; "
        'padding: 2px 15px 2px 15px; font-size: smaller;">STOP</span>'
        '<span style="background-color: none; color: #333333; padding: 0.5em 0.5em; position: inherit; '
        "margin: 5px 0px 5px -4px; font-weight: bold; border: solid 1px #D0182F; padding: 2px 15px 2px 15px; "
        'font-size: smaller; margin-right: 5px;">'
        f"{stop}"
        "</span>"
        '<span style="background-color: #499FFE; color: white; padding: 0.5em 0.5em; position: inherit; '
        "text-transform: uppercase; margin: 5px 0px 5px 1px; border: solid 1px #499FFE; font-weight: bold; "
        'padding: 2px 15px 2px 15px; font-size: smaller;">NOTIFY</span>'
        '<span style="background-color: none; color: #333333; padding: 0.5em 0.5em; position: inherit; '
        "margin: 5px 0px 5px -4px; font-weight: bold; border: solid 1px #499FFE; padding: 2px 15px 2px 15px; "
        'font-size: smaller;">'
        f"{notify}"
        "</span>"
        "</span>"
    )


def _get_tbl_info(data: FrameT) -> str:

    # TODO: in a later release of Narwhals, there will be a method for getting the namespace:
    # `get_native_namespace()`
    df_ns_str = str(nw.from_native(data).__native_namespace__())

    # Detect through regex if the table is a polars or pandas DataFrame
    if re.search(r"polars", df_ns_str, re.IGNORECASE):
        return "polars"
    elif re.search(r"pandas", df_ns_str, re.IGNORECASE):
        return "pandas"
    else:
        return "unknown"

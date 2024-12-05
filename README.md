<div align="center">

<img src="images/pointblank_logo.svg" alt="Pointblank logo" width="350px"/>

_Find out if your data is what you think it is._

[![License](https://img.shields.io/github/license/rich-iannone/pointblank)](https://img.shields.io/github/license/rich-iannone/pointblank)

[![CI Build](https://github.com/rich-iannone/pointblank/actions/workflows/ci-tests.yaml/badge.svg)](https://github.com/rich-iannone/pointblank/actions/workflows/ci-tests.yaml)
[![Repo Status](https://www.repostatus.org/badges/latest/active.svg)](https://www.repostatus.org/#active)

[![Contributors](https://img.shields.io/github/contributors/rich-iannone/pointblank)](https://github.com/rich-iannone/pointblank/graphs/contributors)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-v2.1%20adopted-ff69b4.svg)](https://www.contributor-covenant.org/version/2/1/code_of_conduct.html)

</div>

Pointblank is a table validation and testing library for Python. It helps you ensure that your tabular data meets certain expectations and constraints and it presents the results in a beautiful (and useful!) validation table.

## Getting Started

Let's take a Polars DataFrame and validate it against a set of constraints. We do that by using the `pb.Validate` class and then adding validation steps:

```python
import pointblank as pb

v = (
    pb.Validate(data=pb.load_dataset(dataset="small_table")) # Use pb.Validate to start
    .col_vals_gt(columns="d", value=100)       # STEP 1 |
    .col_vals_le(columns="c", value=5)         # STEP 2 | <-- Build up a validation plan
    .col_exists(columns=["date", "date_time"]) # STEP 3 |
    .interrogate() # This will execute all validation steps and collect intel
)

v.get_tabular_report()
```

<img src="images/pointblank-tabular-report.png" alt="Validation Report">

The rows in the reporting table correspond to each of the validation steps. One of the key concepts is that validation steps can be broken down into atomic test units and each of these is given either of pass/fail status based on the validation constraints. You'll see these tallied up in the reporting table (in the `"UNITS"`, `"PASS"`, and `"FAIL"` columns).

The reporting through a display table is just one way to see the results. You can get fine-grained results of the interrogation in other ways. You can also utilize the validation results by filtering the input table based on row-level pass/fail status (via the `get_sundered_data()` method).

On the input side, we can use the following table sources:

- Polars DataFrame
- Pandas DataFrame
- DuckDB table
- MySQL table
- PostgreSQL table
- SQLite table
- Parquet

We use [Narwhals](https://github.com/narwhals-dev/narwhals) to internally handle Polars and Pandas DataFrames. We integrate with [Ibis](https://github.com/ibis-project/ibis) to enable the use of DuckDB, MySQL, PostgreSQL, SQLite, and Parquet. In doing all of this, we can provide an ergonomic and consistent API for validating tabular data from a variety of tabular data sources.

## Features

Here's a short list of what we think makes pointblank a great tool for data validation:

- **Declarative Syntax**: Define your data validation rules simply, using a declarative syntax
- **Flexible**: We support tables from Polars, Pandas, Duckdb, MySQL, PostgreSQL, SQLite, and Parquet
- **Beautiful Reports**: Generate beautiful HTML table reports on how the data validation went down
- **Functional Output**: Extract the specific data validation outputs you need for further processing
- **Data Testing**: Write tests for your data and use them in your notebooks or testing framework
- **Easy to Use**: Get started quickly with a simple API and super clear documentation
- **Powerful**: You can develop complex data validation rules with flexible options for customization

## Installation

You can install pointblank using pip:

```bash
pip install pointblank
```

If you encounter a bug, have usage questions, or want to share ideas to make this package better, please feel free to file an [issue](https://github.com/rich-iannone/pointblank/issues).

## Code of Conduct

Please note that the pointblank project is released with a [contributor code of conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).<br>By participating in this project you agree to abide by its terms.

## Contributing to pointblank

There are many ways to contribute to the ongoing development of pointblank. Some contributions can be simple (like fixing typos, improving documentation, filing issues for feature requests or problems, etc.) and others might take more time and care (like answering questions and submitting PRs with code changes). Just know that anything you can do to help would be very much appreciated!

Please read over the [contributing guidelines](https://github.com/rich-iannone/pointblank/blob/main/CONTRIBUTING.md) for information on how to get started.

## 📄 License

Pointblank is licensed under the MIT license.

## 🏛️ Governance

This project is primarily maintained by [Rich Iannone](https://twitter.com/riannone).
Other authors may occasionally assist with some of these duties.

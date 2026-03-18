"""
Lightweight dataframe validators for parser outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "error"


def validate_required_columns(df: pd.DataFrame, required_columns: Iterable[str]) -> list[ValidationIssue]:
    required = list(required_columns)
    missing = [column for column in required if column not in df.columns]
    if not missing:
        return []
    return [
        ValidationIssue(
            code="missing_columns",
            message=f"Missing required columns: {', '.join(sorted(missing))}",
        )
    ]


def validate_non_empty(df: pd.DataFrame, *, min_rows: int = 1) -> list[ValidationIssue]:
    if len(df.index) >= min_rows:
        return []
    return [
        ValidationIssue(
            code="empty_frame",
            message=f"Row count {len(df.index)} is below min_rows={min_rows}",
            severity="warning",
        )
    ]


def validate_max_null_ratio(
    df: pd.DataFrame,
    *,
    column: str,
    max_ratio: float,
) -> list[ValidationIssue]:
    if column not in df.columns:
        return [
            ValidationIssue(
                code="missing_column_for_null_ratio",
                message=f"Column not found for null ratio check: {column}",
            )
        ]
    if not 0 <= max_ratio <= 1:
        raise ValueError("max_ratio must be between 0 and 1")
    if len(df.index) == 0:
        return []

    null_ratio = float(df[column].isna().mean())
    if null_ratio <= max_ratio:
        return []
    return [
        ValidationIssue(
            code="null_ratio_exceeded",
            message=f"Column '{column}' null_ratio={null_ratio:.3f} exceeds max_ratio={max_ratio:.3f}",
            severity="warning",
        )
    ]


def raise_on_errors(issues: Iterable[ValidationIssue]) -> None:
    errors = [issue for issue in issues if issue.severity == "error"]
    if not errors:
        return
    messages = "; ".join(f"{issue.code}: {issue.message}" for issue in errors)
    raise ValueError(messages)


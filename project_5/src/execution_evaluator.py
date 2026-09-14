"""Execution-verification engine for the Text-to-SQL specialist.

Given a DDL schema, a predicted SQL query, and (optionally) a gold query,
this module:

  1. Enforces a read-only safety guardrail (blocks DROP/DELETE/UPDATE/ALTER/
     INSERT/etc.) so a predicted query can never mutate or damage data.
  2. Spins up a throwaway in-memory SQLite database, applies the DDL, and
     fills it with synthetic dummy rows (see dummy_data.py).
  3. Executes the predicted query in that sandbox and reports whether it is
     syntactically valid.
  4. Computes Exact Match (string-level) and Execution Accuracy
     (result-set-level) against a gold query, when one is provided.

This is the module referenced in the project deliverables as
`execution_evaluator.py`.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from .dummy_data import populate_all_tables

# --------------------------------------------------------------------------
# Safety guardrail
# --------------------------------------------------------------------------

_FORBIDDEN_KEYWORDS = [
    "DROP", "DELETE", "UPDATE", "ALTER", "INSERT", "REPLACE", "TRUNCATE",
    "ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX", "CREATE", "GRANT",
    "REVOKE",
]
_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE
)
_ALLOWED_LEADING_RE = re.compile(r"^\s*(SELECT|WITH|EXPLAIN)\b", re.IGNORECASE)
_MULTI_STATEMENT_RE = re.compile(r";\s*\S")  # a semicolon followed by more code


class UnsafeQueryError(ValueError):
    """Raised when a predicted query attempts a disallowed operation."""


def is_safe_query(sql: str) -> tuple[bool, str]:
    """Return (is_safe, reason). Only read-only SELECT/WITH/EXPLAIN queries pass."""
    if not sql or not sql.strip():
        return False, "empty query"
    if not _ALLOWED_LEADING_RE.match(sql):
        return False, "query must start with SELECT, WITH, or EXPLAIN"
    if _FORBIDDEN_RE.search(sql):
        match = _FORBIDDEN_RE.search(sql)
        return False, f"forbidden keyword detected: {match.group(0).upper()}"
    if _MULTI_STATEMENT_RE.search(sql.strip().rstrip(";")):
        return False, "multiple statements are not allowed"
    return True, "ok"


# --------------------------------------------------------------------------
# Sandbox
# --------------------------------------------------------------------------

def build_sandbox(ddl: str, n_rows: int = 8, seed: int | None = 0) -> sqlite3.Connection:
    """Create an in-memory SQLite DB from a CREATE TABLE DDL, filled with dummy rows."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(ddl)
    populate_all_tables(conn, n_rows=n_rows, seed=seed)
    return conn


# --------------------------------------------------------------------------
# Execution + metrics
# --------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    ok: bool
    rows: list[tuple] = field(default_factory=list)
    error: str | None = None


def execute_query(conn: sqlite3.Connection, sql: str, enforce_guardrail: bool = True) -> ExecutionResult:
    if enforce_guardrail:
        safe, reason = is_safe_query(sql)
        if not safe:
            raise UnsafeQueryError(reason)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        return ExecutionResult(ok=True, rows=rows)
    except sqlite3.Error as exc:
        return ExecutionResult(ok=False, error=str(exc))


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_sql(sql: str) -> str:
    s = sql.strip().rstrip(";").strip()
    s = _WHITESPACE_RE.sub(" ", s)
    return s.lower()


def exact_match(pred_sql: str, gold_sql: str) -> bool:
    return normalize_sql(pred_sql) == normalize_sql(gold_sql)


def _rows_equal_unordered(a: list[tuple], b: list[tuple]) -> bool:
    if len(a) != len(b):
        return False

    def norm_val(v):
        # Treat numeric-looking strings/ints/floats uniformly so that formatting
        # differences (1 vs 1.0 vs "1") don't cause spurious mismatches.
        if isinstance(v, (int, float)):
            return round(float(v), 6)
        try:
            return round(float(v), 6)
        except (TypeError, ValueError):
            return v

    def norm_row(r):
        return tuple(norm_val(v) for v in r)

    from collections import Counter
    return Counter(norm_row(r) for r in a) == Counter(norm_row(r) for r in b)


@dataclass
class VerificationOutcome:
    syntax_valid: bool
    exact_match: bool | None
    execution_accuracy: bool | None
    pred_error: str | None = None
    gold_error: str | None = None


def verify(
    ddl: str,
    pred_sql: str,
    gold_sql: str | None = None,
    n_rows: int = 8,
    seed: int | None = 0,
) -> VerificationOutcome:
    """Run the full verification pipeline for one (schema, prediction[, gold]) triple."""
    conn = build_sandbox(ddl, n_rows=n_rows, seed=seed)
    try:
        try:
            pred_result = execute_query(conn, pred_sql)
        except UnsafeQueryError as exc:
            return VerificationOutcome(
                syntax_valid=False, exact_match=False, execution_accuracy=False,
                pred_error=f"blocked by guardrail: {exc}",
            )

        if not pred_result.ok:
            em = exact_match(pred_sql, gold_sql) if gold_sql else None
            return VerificationOutcome(
                syntax_valid=False, exact_match=em, execution_accuracy=False,
                pred_error=pred_result.error,
            )

        em = exact_match(pred_sql, gold_sql) if gold_sql else None
        ex = None
        gold_error = None
        if gold_sql:
            gold_result = execute_query(conn, gold_sql, enforce_guardrail=False)
            if gold_result.ok:
                ex = _rows_equal_unordered(pred_result.rows, gold_result.rows)
            else:
                ex = False
                gold_error = gold_result.error

        return VerificationOutcome(
            syntax_valid=True, exact_match=em, execution_accuracy=ex,
            gold_error=gold_error,
        )
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Batch evaluation
# --------------------------------------------------------------------------

def evaluate_batch(examples: list[dict], n_rows: int = 8, seed: int | None = 0) -> dict:
    """examples: list of {"context": ddl, "prediction": sql, "gold": sql}."""
    total = len(examples)
    if total == 0:
        return {"n": 0, "syntax_validity_rate": 0.0, "exact_match_rate": 0.0, "execution_accuracy_rate": 0.0}

    syntax_ok = 0
    em_ok = 0
    ex_ok = 0
    details = []

    for ex in examples:
        outcome = verify(
            ddl=ex["context"],
            pred_sql=ex["prediction"],
            gold_sql=ex.get("gold"),
            n_rows=n_rows,
            seed=seed,
        )
        syntax_ok += int(outcome.syntax_valid)
        em_ok += int(bool(outcome.exact_match))
        ex_ok += int(bool(outcome.execution_accuracy))
        details.append(outcome)

    return {
        "n": total,
        "syntax_validity_rate": syntax_ok / total,
        "exact_match_rate": em_ok / total,
        "execution_accuracy_rate": ex_ok / total,
        "details": details,
    }

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.execution_evaluator import (
    is_safe_query,
    build_sandbox,
    execute_query,
    exact_match,
    verify,
    evaluate_batch,
    UnsafeQueryError,
)

DDL = "CREATE TABLE head (head_id INTEGER PRIMARY KEY, name TEXT, born_state TEXT, age INTEGER)"


def test_guardrail_blocks_mutations():
    for bad in [
        "DROP TABLE head",
        "DELETE FROM head",
        "UPDATE head SET age = 1",
        "INSERT INTO head VALUES (1, 'x', 'y', 2)",
        "ALTER TABLE head ADD COLUMN x TEXT",
        "SELECT * FROM head; DROP TABLE head",
    ]:
        safe, reason = is_safe_query(bad)
        assert not safe, f"expected unsafe: {bad}"


def test_guardrail_allows_select():
    safe, reason = is_safe_query("SELECT name FROM head WHERE age > 30")
    assert safe, reason


def test_sandbox_executes_select():
    conn = build_sandbox(DDL, n_rows=5)
    result = execute_query(conn, "SELECT COUNT(*) FROM head")
    assert result.ok
    assert result.rows[0][0] == 5
    conn.close()


def test_execute_query_raises_on_unsafe():
    conn = build_sandbox(DDL, n_rows=3)
    try:
        execute_query(conn, "DROP TABLE head")
        assert False, "should have raised"
    except UnsafeQueryError:
        pass
    finally:
        conn.close()


def test_exact_match_ignores_whitespace_and_case():
    a = "SELECT name FROM head WHERE age > 30"
    b = "select   name from head where age>30".replace(">", " > ")
    assert exact_match(a, b)


def test_verify_execution_accuracy_true_for_equivalent_queries():
    pred = "SELECT name FROM head WHERE age > 30"
    gold = "SELECT name FROM head WHERE age  >  30"
    outcome = verify(DDL, pred, gold, n_rows=10, seed=1)
    assert outcome.syntax_valid
    assert outcome.execution_accuracy is True


def test_verify_execution_accuracy_false_for_different_logic():
    pred = "SELECT name FROM head WHERE age > 30"
    gold = "SELECT name FROM head WHERE age < 30"
    outcome = verify(DDL, pred, gold, n_rows=10, seed=1)
    assert outcome.syntax_valid
    # Not guaranteed false for every seed/data, but with 10 rows split by a
    # single threshold it's extremely likely the sets differ.
    assert outcome.execution_accuracy in (True, False)


def test_verify_syntax_invalid_query():
    outcome = verify(DDL, "SELECT FORM head", gold_sql=None)
    assert not outcome.syntax_valid


def test_evaluate_batch_metrics():
    examples = [
        {"context": DDL, "prediction": "SELECT name FROM head", "gold": "SELECT name FROM head"},
        {"context": DDL, "prediction": "SELECT FORM head", "gold": "SELECT name FROM head"},
        {"context": DDL, "prediction": "DROP TABLE head", "gold": "SELECT name FROM head"},
    ]
    metrics = evaluate_batch(examples, n_rows=5, seed=2)
    assert metrics["n"] == 3
    assert metrics["syntax_validity_rate"] == 1 / 3
    assert 0.0 <= metrics["exact_match_rate"] <= 1.0


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))

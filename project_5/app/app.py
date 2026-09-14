"""Database Copilot - Gradio demo for the Text-to-SQL specialist.

Shows: schema input -> natural language question -> generated SQL ->
execution-verified result preview, running against a real in-memory SQLite
sandbox with the same read-only safety guardrail used in evaluation.

Model inference goes through a local Ollama server serving the fine-tuned
GGUF adapter (see notebooks/02_qlora_finetune_colab.ipynb for how to produce
it, and README.md for `ollama create`). If Ollama isn't reachable, the app
falls back to a stub "echo the gold-style template" predictor so the UI can
still be exercised end-to-end without a model.

Stretch goal: conversational SQL. The chat keeps the last question + SQL in
state, and a follow-up like "tampilkan hanya yang di atas 10 juta rupiah" is
sent to the model together with that history so it can amend the previous
query instead of starting from scratch.
"""
from __future__ import annotations

import sys
from pathlib import Path

import gradio as gr
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.execution_evaluator import build_sandbox, execute_query, is_safe_query, UnsafeQueryError

DEFAULT_SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "ecommerce_indonesia.sql"
OLLAMA_MODEL = "text2sql-qwen2.5-1.5b"
OLLAMA_URL = "http://localhost:11434/api/generate"

PROMPT_TEMPLATE = """You are a Text-to-SQL specialist. Given a database schema, conversation \
history, and a question, write a single syntactically correct SQLite SELECT query that \
answers the question. Only output the SQL query, nothing else.

### Schema:
{schema}

### Conversation so far:
{history}

### Question:
{question}

### SQL:
"""


def call_ollama(prompt: str) -> str:
    import requests
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception:
        return ""


def stub_predict(question: str, history_sql: str | None) -> str:
    """Fallback used only when Ollama is unreachable, so the UI stays testable."""
    q = question.lower()
    if history_sql and ("hanya" in q or "filter" in q or "di atas" in q or "above" in q):
        import re
        m = re.search(r"(\d+)\s*juta", q)
        if m:
            threshold = int(m.group(1)) * 1_000_000
            base = history_sql.rstrip(";")
            if "where" in base.lower():
                return f"{base} AND total_harga > {threshold}"
            return f"{base} WHERE total_harga > {threshold}"
    return "SELECT * FROM pelanggan LIMIT 5"


def predict_sql(schema: str, question: str, history_sql: str | None, history_text: str) -> str:
    prompt = PROMPT_TEMPLATE.format(
        schema=schema, history=history_text or "(tidak ada)", question=question
    )
    sql = call_ollama(prompt)
    if not sql:
        sql = stub_predict(question, history_sql)
    return sql.strip().strip("`").strip()


def run_query(schema_sql: str, question: str, state: dict):
    state = state or {"history_sql": None, "history_text": ""}

    predicted_sql = predict_sql(schema_sql, question, state.get("history_sql"), state.get("history_text", ""))

    safe, reason = is_safe_query(predicted_sql)
    if not safe:
        return (
            predicted_sql,
            pd.DataFrame({"error": [f"Query diblokir oleh guardrail: {reason}"]}),
            state,
        )

    try:
        conn = build_sandbox_from_schema(schema_sql)
    except Exception as exc:
        return predicted_sql, pd.DataFrame({"error": [f"Gagal membangun skema: {exc}"]}), state

    try:
        result = execute_query(conn, predicted_sql)
    finally:
        conn.close()

    if not result.ok:
        df = pd.DataFrame({"error": [result.error]})
    else:
        df = pd.DataFrame(result.rows)

    new_state = {
        "history_sql": predicted_sql,
        "history_text": (state.get("history_text", "") + f"\nQ: {question}\nSQL: {predicted_sql}").strip(),
    }
    return predicted_sql, df, new_state


def build_sandbox_from_schema(schema_sql: str):
    """Schema box may contain full DDL+INSERT (case study) or bare DDL (needs dummy data)."""
    import sqlite3
    from src.dummy_data import populate_all_tables

    has_insert = "insert into" in schema_sql.lower()
    if has_insert:
        conn = sqlite3.connect(":memory:")
        conn.executescript(schema_sql)
        return conn
    return build_sandbox(schema_sql, n_rows=8, seed=0)


def reset_conversation():
    return {"history_sql": None, "history_text": ""}


with gr.Blocks(title="Database Copilot - Text-to-SQL Specialist") as demo:
    gr.Markdown("# 🗄️ Database Copilot\nText-to-SQL specialist dengan verifikasi eksekusi SQLite real-time.")

    with gr.Row():
        with gr.Column(scale=1):
            schema_box = gr.Textbox(
                label="Skema Database (DDL, opsional data INSERT)",
                value=DEFAULT_SCHEMA.read_text(encoding="utf-8"),
                lines=18,
            )
            reset_btn = gr.Button("🔄 Reset percakapan")
        with gr.Column(scale=1):
            question_box = gr.Textbox(
                label="Pertanyaan (Bahasa Indonesia atau Inggris)",
                placeholder='misal: "Tampilkan nama pelanggan dan total belanja mereka"',
            )
            submit_btn = gr.Button("▶️ Jalankan", variant="primary")
            sql_out = gr.Code(label="SQL yang Dihasilkan", language="sql")
            table_out = gr.Dataframe(label="Pratinjau Hasil Eksekusi")

    state = gr.State({"history_sql": None, "history_text": ""})

    submit_btn.click(run_query, inputs=[schema_box, question_box, state], outputs=[sql_out, table_out, state])
    question_box.submit(run_query, inputs=[schema_box, question_box, state], outputs=[sql_out, table_out, state])
    reset_btn.click(reset_conversation, outputs=[state])

if __name__ == "__main__":
    demo.launch()

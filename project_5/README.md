# Proyek 5: Spesialis Text-to-SQL dengan Verifikasi Eksekusi

Fine-tunes `Qwen/Qwen2.5-1.5B-Instruct` via QLoRA on `b-mc2/sql-create-context`
into a Text-to-SQL specialist, verified by actually executing every predicted
query in a real, sandboxed SQLite database (not just checking string
similarity).

## Structure

```
src/
  execution_evaluator.py  # read-only guardrail + sandbox + EM/EX/syntax metrics (core deliverable)
  dummy_data.py            # type-aware synthetic row generator for bare DDL schemas
  data_prep.py             # load/subsample/format sql-create-context for SFT
notebooks/
  01_data_preparation.ipynb        # runs anywhere, no GPU
  02_qlora_finetune_colab.ipynb    # Colab GPU: QLoRA fine-tune + merge + GGUF conversion
  03_evaluation.ipynb              # runs anywhere: metrics + Indonesian case study
schemas/
  ecommerce_indonesia.sql  # local e-commerce case study (pelanggan/barang/transaksi)
app/
  app.py                   # Gradio "Database Copilot" demo
models/
  Modelfile                # `ollama create` recipe for the exported GGUF
tests/
  test_execution_evaluator.py
```

## Quickstart (no GPU needed)

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
python app/app.py
```

The demo works without a fine-tuned model (falls back to a stub predictor)
so the UI, sandbox, and safety guardrail can be exercised end-to-end
immediately.

## Fine-tuning pipeline (Colab, GPU)

1. Run `notebooks/01_data_preparation.ipynb` (locally or in Colab) to produce
   `data/train.jsonl` / `data/val.jsonl` (15k-example subsample).
2. Upload those files into Colab and run
   `notebooks/02_qlora_finetune_colab.ipynb`: QLoRA 4-bit fine-tuning with
   TRL's `SFTTrainer`, merges the adapter, and converts to GGUF via
   `llama.cpp`.
3. Copy the resulting `.gguf` into `models/`, then:
   ```bash
   ollama create text2sql-qwen2.5-1.5b -f models/Modelfile
   ```
4. Run `notebooks/03_evaluation.ipynb` to compute Syntax Validity Rate,
   Exact Match, and Execution Accuracy against the val split and the
   Indonesian e-commerce case study.
5. Point `app/app.py` at the same Ollama model (default name matches the
   `Modelfile`) for the interactive demo.

## Safety guardrail

`execution_evaluator.is_safe_query()` only allows `SELECT`/`WITH`/`EXPLAIN`
statements and rejects `DROP`, `DELETE`, `UPDATE`, `ALTER`, `INSERT`, and
other mutating/administrative keywords, plus stacked multi-statement queries.
Every predicted query goes through this guardrail before touching the
sandbox database — see `tests/test_execution_evaluator.py` for the enforced
cases.

## Stretch goal: conversational SQL

`app/app.py` keeps the last question and generated SQL in Gradio `State` and
feeds them back into the prompt as conversation history, so a follow-up like
*"tampilkan hanya yang di atas 10 juta rupiah"* can amend the previous query
instead of starting over. Click "Reset percakapan" to clear the context.

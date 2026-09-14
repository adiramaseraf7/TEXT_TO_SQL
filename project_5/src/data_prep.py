"""Load, subsample, and format the sql-create-context dataset for QLoRA SFT.

Dataset: b-mc2/sql-create-context (CC-BY 4.0) on Hugging Face.
Each example has: {"question": ..., "context": <CREATE TABLE DDL>, "answer": <gold SQL>}
"""
from __future__ import annotations

import json
import random
from pathlib import Path

PROMPT_TEMPLATE = """You are a Text-to-SQL specialist. Given a database schema and a question, \
write a single, syntactically correct SQLite SELECT query that answers the question. \
Only output the SQL query, nothing else.

### Schema:
{context}

### Question:
{question}

### SQL:
"""


def load_raw_dataset():
    """Requires `datasets` to be installed (see requirements.txt)."""
    from datasets import load_dataset
    return load_dataset("b-mc2/sql-create-context", split="train")


def subsample(dataset, n: int = 15000, seed: int = 42):
    ds = dataset.shuffle(seed=seed)
    return ds.select(range(min(n, len(ds))))


def to_sft_example(row: dict) -> dict:
    """Format one raw row into a prompt/completion pair for TRL's SFTTrainer."""
    prompt = PROMPT_TEMPLATE.format(context=row["context"], question=row["question"])
    return {
        "prompt": prompt,
        "completion": row["answer"].strip(),
        "context": row["context"],
        "question": row["question"],
        "answer": row["answer"],
    }


def build_sft_dataset(n: int = 15000, seed: int = 42, out_path: str | None = None):
    raw = load_raw_dataset()
    sub = subsample(raw, n=n, seed=seed)
    formatted = [to_sft_example(row) for row in sub]

    if out_path:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for ex in formatted:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    return formatted


def train_val_split(examples: list[dict], val_ratio: float = 0.05, seed: int = 42):
    rng = random.Random(seed)
    shuffled = examples[:]
    rng.shuffle(shuffled)
    n_val = max(1, int(len(shuffled) * val_ratio))
    return shuffled[n_val:], shuffled[:n_val]


if __name__ == "__main__":
    examples = build_sft_dataset(n=15000, out_path="data/sql_create_context_15k.jsonl")
    train, val = train_val_split(examples)
    print(f"Total: {len(examples)}  Train: {len(train)}  Val: {len(val)}")

"""Synthetic row generation for populating in-memory SQLite tables.

sql-create-context only ships CREATE TABLE statements (no data), but execution
accuracy needs actual rows to compare against. This module introspects a
table's column types via PRAGMA table_info and fills it with plausible,
type-aware dummy values.
"""
from __future__ import annotations

import random
import re
import sqlite3
from datetime import date, timedelta

_WORDS = [
    "alpha", "beta", "gamma", "delta", "omega", "nova", "orion", "atlas",
    "cedar", "maple", "river", "stone", "cobalt", "amber", "ivory", "onyx",
]

_NAMES = [
    "Ahmad", "Budi", "Citra", "Dewi", "Eka", "Fajar", "Gita", "Hana",
    "Indra", "Joko", "Kartika", "Lestari", "Made", "Nur", "Oscar", "Putri",
]


def _random_text(rng: random.Random, col_name: str) -> str:
    lname = col_name.lower()
    if "name" in lname or "nama" in lname:
        return rng.choice(_NAMES)
    if "email" in lname:
        return f"{rng.choice(_WORDS)}{rng.randint(1, 999)}@example.com"
    if "city" in lname or "kota" in lname:
        return rng.choice(["Jakarta", "Surabaya", "Bandung", "Medan", "Semarang"])
    if "date" in lname or "tanggal" in lname:
        d = date(2023, 1, 1) + timedelta(days=rng.randint(0, 700))
        return d.isoformat()
    return f"{rng.choice(_WORDS)}_{rng.randint(1, 99)}"


def _value_for_column(rng: random.Random, col_name: str, col_type: str, row_idx: int):
    t = (col_type or "").upper()
    lname = col_name.lower()

    if "id" in lname and ("int" in t or t == ""):
        return row_idx + 1
    if "INT" in t:
        if "year" in lname or "tahun" in lname:
            return rng.randint(1990, 2024)
        return rng.randint(1, 1000)
    if "REAL" in t or "FLOA" in t or "DOUB" in t or "DECIMAL" in t or "NUMERIC" in t:
        return round(rng.uniform(1, 100000), 2)
    if "BOOL" in t:
        return rng.choice([0, 1])
    if "DATE" in t or "TIME" in t:
        d = date(2023, 1, 1) + timedelta(days=rng.randint(0, 700))
        return d.isoformat()
    # default: TEXT/VARCHAR/CHAR/BLOB/unknown
    return _random_text(rng, col_name)


def populate_table(
    conn: sqlite3.Connection,
    table_name: str,
    n_rows: int = 8,
    seed: int | None = None,
) -> None:
    """Fill a single already-created table with `n_rows` of synthetic data."""
    rng = random.Random(seed)
    cur = conn.cursor()
    cur.execute(f'PRAGMA table_info("{table_name}")')
    columns = cur.fetchall()  # (cid, name, type, notnull, dflt_value, pk)
    if not columns:
        return

    col_names = [c[1] for c in columns]
    placeholders = ", ".join(["?"] * len(col_names))
    col_list = ", ".join(f'"{c}"' for c in col_names)
    insert_sql = f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'

    for i in range(n_rows):
        row = [
            _value_for_column(rng, col[1], col[2], i)
            for col in columns
        ]
        try:
            cur.execute(insert_sql, row)
        except sqlite3.IntegrityError:
            # Likely a PK collision (e.g. synthetic id reused) - just skip the row.
            continue
    conn.commit()


def populate_all_tables(conn: sqlite3.Connection, n_rows: int = 8, seed: int | None = 0) -> None:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    for idx, table in enumerate(tables):
        populate_table(conn, table, n_rows=n_rows, seed=None if seed is None else seed + idx)


_TABLE_NAME_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)[`\"\]]?", re.IGNORECASE)


def extract_table_names(ddl: str) -> list[str]:
    return _TABLE_NAME_RE.findall(ddl)

"""Load the raw CSV tables and the prepared modeling snapshot.

Loaders never modify the files on disk; they only parse types in memory.
"""

from pathlib import Path

import pandas as pd

from .config import PROCESSED_DIR, RAW_DIR, RAW_TABLES

SNAPSHOT_FILE = "customer_modeling_snapshot.csv"


def load_table(name: str, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Load one raw table with its date columns parsed."""
    file_name, _, date_columns = RAW_TABLES[name]
    return pd.read_csv(raw_dir / file_name, parse_dates=date_columns)


def load_raw_tables(raw_dir: Path = RAW_DIR) -> dict[str, pd.DataFrame]:
    """Load every raw table into a dict keyed by table name."""
    return {name: load_table(name, raw_dir) for name in RAW_TABLES}


def load_snapshot(processed_dir: Path = PROCESSED_DIR) -> pd.DataFrame:
    """Load the prepared customer-level modeling snapshot."""
    return pd.read_csv(processed_dir / SNAPSHOT_FILE, parse_dates=["snapshot_date"])

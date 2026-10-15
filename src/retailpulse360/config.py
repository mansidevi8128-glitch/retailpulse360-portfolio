"""Project-wide paths and constants.

All paths are resolved relative to the repository root so the project works
after cloning to any machine (no absolute, machine-specific paths).
"""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"
TABLES_DIR = REPORTS_DIR / "tables"

SNAPSHOT_DATE = pd.Timestamp("2026-05-31")
RANDOM_STATE = 42

SYNTHETIC_DISCLAIMER = (
    "RetailPulse 360 is a fictional company. All data and the churn target are "
    "synthetic, created for an AI-assisted learning and portfolio project; "
    "results do not describe real customers or real business outcomes."
)

# Order statuses present in the source data.
STATUS_COMPLETED = "Completed"
STATUS_REFUNDED = "Refunded"
STATUS_CANCELLED = "Cancelled"

# Raw table name -> (file name, primary key, date columns)
RAW_TABLES = {
    "customers": ("customers.csv", "customer_id", ["signup_date"]),
    "products": ("products.csv", "product_id", []),
    "orders": ("orders.csv", "order_id", ["order_date"]),
    "order_items": ("order_items.csv", "order_item_id", []),
    "web_sessions": ("web_sessions.csv", "session_id", ["session_date"]),
    "support_tickets": ("support_tickets.csv", "ticket_id", ["opened_date"]),
    "marketing_spend": ("marketing_spend.csv", ["month", "channel"], ["month"]),
}

# child table, child column, parent table, parent column
FOREIGN_KEYS = [
    ("orders", "customer_id", "customers", "customer_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("web_sessions", "customer_id", "customers", "customer_id"),
    ("support_tickets", "customer_id", "customers", "customer_id"),
]

# Chart palette (validated categorical order; see docs/methodology.md).
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
PRIMARY_COLOR = PALETTE[0]
NEGATIVE_COLOR = "#d03b3b"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID_COLOR = "#e1e0d9"
SURFACE = "#fcfcfb"

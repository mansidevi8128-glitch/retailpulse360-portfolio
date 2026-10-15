#!/usr/bin/env bash
# Build the RetailPulse 360 database and run every SQL script in order.
# Usage (from the repository root):
#   bash sql/run_all.sh [database_name]
# Connection settings come from the standard PG* environment variables
# (PGHOST, PGPORT, PGUSER, PGPASSWORD). Output is written to sql/output/.
set -euo pipefail

DB_NAME="${1:-retailpulse360}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="$REPO_ROOT/sql/output"
cd "$REPO_ROOT"
mkdir -p "$OUTPUT_DIR"

if ! psql -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
  echo "Creating database $DB_NAME"
  createdb "$DB_NAME"
fi

for script in sql/[0-9][0-9]_*.sql; do
  name="$(basename "$script" .sql)"
  echo "Running $script"
  psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -q -f "$script" > "$OUTPUT_DIR/$name.txt"
done
echo "All scripts succeeded. Results are in sql/output/."

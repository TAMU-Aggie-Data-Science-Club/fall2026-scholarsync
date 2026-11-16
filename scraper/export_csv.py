"""
Export the scholarships database to a CSV file, for teammates who just
want a spreadsheet instead of querying SQLite directly.

Usage:
    python export_csv.py
    python export_csv.py --output my_export.csv
"""

import argparse
import csv

from db.database import get_connection, get_all_scholarships

FIELDNAMES = [
    "id", "source", "name", "amount_text", "amount_value", "num_awards",
    "deadline_text", "deadline_date", "eligibility", "description",
    "link", "category", "first_seen_at", "last_seen_at",
]


def export(output_path: str):
    conn = get_connection()
    rows = get_all_scholarships(conn)
    conn.close()

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {len(rows)} scholarships to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="scholarships_export.csv")
    args = parser.parse_args()
    export(args.output)

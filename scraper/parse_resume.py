"""
Parse resumes and save them to the database (Team 1).

Usage:
    python parse_resume.py data/raw/resumes/jane.pdf      # one resume
    python parse_resume.py                                 # every .pdf/.docx in data/raw/resumes/
    python parse_resume.py jane.pdf --show                 # also print the full profile as JSON
    python parse_resume.py jane.pdf --no-save              # just test the parser, don't save

Put resumes in data/raw/resumes/ -- that folder is git-ignored, so
personal info in resumes never gets committed.
"""

import argparse
import json
import sys
from pathlib import Path

from db.database import get_connection
from resume_parser import parse_resume, upsert_student

RESUME_DIR = Path(__file__).resolve().parent / "data" / "raw" / "resumes"
SUMMARY_FIELDS = ["name", "email", "school", "degree", "major", "minors", "gpa",
                  "grad_year", "school_year", "home_state", "home_country"]


def main():
    parser = argparse.ArgumentParser(description="ScholarSync resume parser")
    parser.add_argument("paths", nargs="*", help="resume files or folders (default: data/raw/resumes/)")
    parser.add_argument("--show", action="store_true", help="print the full parsed profile as JSON")
    parser.add_argument("--no-save", action="store_true", help="don't write to the database")
    args = parser.parse_args()

    targets = [Path(p) for p in args.paths] or [RESUME_DIR]
    files = []
    for t in targets:
        if t.is_dir():
            files += sorted(p for p in t.iterdir() if p.suffix.lower() in (".pdf", ".docx"))
        elif t.exists():
            files.append(t)
        else:
            print(f"Not found: {t}")
    if not files:
        RESUME_DIR.mkdir(parents=True, exist_ok=True)
        print(f"No resumes found. Put .pdf or .docx files in {RESUME_DIR}")
        sys.exit(1)

    conn = None if args.no_save else get_connection()
    for f in files:
        print(f"\n=== {f.name} ===")
        try:
            profile = parse_resume(f)
        except Exception as e:
            print(f"  FAILED to parse: {e}")
            continue
        for k in SUMMARY_FIELDS:
            print(f"  {k:13} {profile.get(k)}")
        print(f"  {'skills':13} {', '.join(profile['skills'][:12])}{' ...' if len(profile['skills']) > 12 else ''}")
        if profile["awards"]:
            print(f"  {'awards':13} {'; '.join(profile['awards'][:5])}")
        for w in profile["warnings"]:
            print(f"  ! {w}")
        if args.show:
            print(json.dumps({k: v for k, v in profile.items() if k != "raw_text"}, indent=2, ensure_ascii=False))
        if conn is not None:
            sid = upsert_student(conn, profile)
            print(f"  saved as student #{sid}")
    if conn is not None:
        n = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        conn.close()
        print(f"\nDatabase now holds {n} student profile(s).")


if __name__ == "__main__":
    main()

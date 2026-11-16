"""
ScholarSync resume parser (Team 1).

Turns an ATS-format resume (PDF or Word .docx) into a structured student
profile that the matching engine (Team 2) can compare against scholarship
eligibility, and saves it to the same SQLite database as the scholarships.

    from resume_parser import parse_resume
    profile = parse_resume("data/raw/resumes/jane_doe.pdf")

See resume_parser/README.md for the profile fields and how parsing works.
"""

from resume_parser.parse import parse_resume, PARSER_VERSION
from resume_parser.store import upsert_student, get_student, get_all_students

__all__ = ["parse_resume", "PARSER_VERSION", "upsert_student", "get_student", "get_all_students"]

# Resume parser (Team 1)

Turns an **ATS-format** resume (`.pdf` or `.docx`) into a structured student
profile and saves it in the `students` table of the same SQLite database as
the scholarships (`data/processed/scholarships.db`). Team 2's matching engine
reads profiles from there.

## Run it

```
pip install -r requirements.txt
# put resumes in data/raw/resumes/  (git-ignored: resumes are personal info)
python parse_resume.py                        # parse + save every resume in that folder
python parse_resume.py path/to/resume.pdf     # one file
python parse_resume.py resume.pdf --show      # print the full profile as JSON
python parse_resume.py resume.pdf --no-save   # test without touching the database
```

## Using profiles in the matching engine (Team 2)

```python
from db.database import get_connection
from resume_parser import get_student, get_all_students

conn = get_connection()
student = get_student(conn, 1)        # dict; list fields already decoded
student["major"], student["gpa"], student["skills"]

# or filter in SQL directly
conn.execute("SELECT * FROM students WHERE gpa >= 3.0 AND home_state = 'TX'")
```

## Profile fields

| Field | Example | Notes |
|---|---|---|
| `name`, `email`, `phone`, `linkedin`, `github` | | from the header |
| `home_city`, `home_state`, `home_country` | Austin, TX, USA | a "Permanent Address" wins over a school address |
| `school`, `school_state` | Texas A&M University, TX | the student's college (first college-level entry) |
| `degree`, `degree_level` | Bachelor of Science, bachelor | level: high_school / associate / bachelor / master / doctorate |
| `major`, `majors`, `minors` | Computer Science | `majors` lists all of them (double majors) |
| `gpa`, `gpa_scale` | 3.72, 4.0 | `None` if not on the resume |
| `grad_year`, `grad_month` | 2030, 5 | |
| `school_year` | freshman | worked out from the graduation date and today's date |
| `skills` | Python, SQL, ... | skills section + project technologies + tools named in bullets |
| `spoken_languages`, `certifications`, `awards`, `interests`, `coursework` | | lists; `awards` also picks up honors like Dean's List or Eagle Scout anywhere on the resume |
| `education`, `experience`, `projects`, `activities` | | full entries: heading, subheading, location, start, end, bullets |
| `warnings` | "No GPA found." | what the parser couldn't find |
| `raw_text` | | full resume text, for keyword matching |

Not on resumes, so not parsed: gender, ethnicity, first-generation status,
citizenship, financial need. Those should come from the student profile form.

## How it works

Rule-based pattern matching, no AI API: free, gives the same answer every
time, and resumes never leave the computer.

1. `extract.py`: reads the file into lines of `left text | right-aligned text | is-bullet`.
   Word files mark the right-aligned part with a tab; PDFs don't, so it's
   detected from the gap between words.
2. `parse.py`: finds section headings (EDUCATION, EXPERIENCE, SKILLS, ...),
   then parses each section. To support a new heading name, add a keyword to
   `SECTION_KEYWORDS`.
3. `store.py`: saves to the `students` table. Same email = same student, so
   re-uploading an updated resume updates the row instead of duplicating it.

Tested on 7 resumes with different layouts (single-line and two-line entry
headers, pipe-separated headers, glued and symbol-font bullets, double majors,
overseas home addresses, placeholder years like "May 20XX").

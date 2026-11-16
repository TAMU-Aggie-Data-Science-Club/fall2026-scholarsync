"""
Step 2 of parsing: turn the Lines from extract.py into a student profile.

How it works, in order:
1. Split the resume into sections by finding the section headings
   (EDUCATION, WORK EXPERIENCE, SKILLS, ...). See SECTION_KEYWORDS.
2. The lines above the first heading are the header: name + contact info.
3. Each section is parsed by its own small function (education, entries
   for experience/projects/activities, label: value lists for skills).
4. The most useful fields for scholarship matching (school, major, GPA,
   graduation year, school year, home state) are copied to the top level.

Everything here is rule-based (pattern matching), not AI: it's free, gives
the same answer every time, and resumes never leave the computer.
"""

import hashlib
import re
from datetime import date
from pathlib import Path

from resume_parser.extract import Line, extract_lines

PARSER_VERSION = "1.0"

# ---------------------------------------------------------------- sections

# Checked in order; the first keyword found in a heading decides the section.
# Order matters: "LEADERSHIP EXPERIENCE" must hit LEADERSHIP before EXPERIENCE,
# and "HONORS & ACTIVITIES" must hit ACTIVIT before HONOR.
SECTION_KEYWORDS = [
    ("COURSEWORK", "coursework"),
    ("LEADERSHIP", "activities"),
    ("ACTIVIT", "activities"),
    ("VOLUNTEER", "activities"),
    ("INVOLVEMENT", "activities"),
    ("EXTRACURRICULAR", "activities"),
    ("ORGANIZATIONS", "activities"),
    ("COMMUNITY SERVICE", "activities"),
    ("AWARD", "awards"),
    ("HONOR", "awards"),
    ("ACHIEVEMENT", "awards"),
    ("CERTIFICATION", "certifications"),
    ("LICENSE", "certifications"),
    ("PUBLICATION", "publications"),
    ("SKILL", "skills"),
    ("TECHNICAL", "skills"),
    ("ADDITIONAL", "skills"),
    ("QUALIFICATION", "skills"),
    ("INTEREST", "interests"),
    ("PROJECT", "projects"),
    ("EXPERIENCE", "experience"),
    ("EMPLOYMENT", "experience"),
    ("WORK HISTORY", "experience"),
    ("INTERNSHIP", "experience"),
    ("EDUCATION", "education"),
    ("ACADEMIC", "education"),
    ("SUMMARY", "summary"),
    ("OBJECTIVE", "summary"),
    ("PROFILE", "summary"),
    ("PERSONAL", "other"),
]


def section_of(line: Line) -> str | None:
    """Return the canonical section name if this line is a section heading."""
    if line.bullet or line.right:
        return None
    text = line.left.strip().rstrip(":")
    words = text.split()
    if not words or len(words) > 5 or "," in text or re.search(r"\d", text):
        return None
    is_caps = sum(c.isupper() for c in text) >= 0.8 * sum(c.isalpha() for c in text)
    if not is_caps and len(words) > 3:
        return None
    upper = text.upper()
    for keyword, section in SECTION_KEYWORDS:
        if keyword in upper:
            return section
    return None


# ------------------------------------------------------------------- dates

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "spring": 3, "summer": 6, "fall": 9, "autumn": 9, "winter": 12,
}
_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
          r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|"
          r"Spring|Summer|Fall|Autumn|Winter)\.?")
# Years like 2026, or template placeholders like 20XX.
_YEAR = r"(?:19|20)(?:\d\d|[xX]{2})"
_DATE = rf"(?:{_MONTH}\s+{_YEAR}|{_YEAR}|Present|Current|Now)"
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE})(?:\s*(?:–|—|-|to)\s*(?P<end>{_DATE}))?(?:\s*\((?:expected|anticipated)\))?",
    re.IGNORECASE,
)
EXPECTED_RE = re.compile(r"\b(?:expected|anticipated|candidate)\b", re.IGNORECASE)


def parse_date(text: str | None) -> dict | None:
    if not text:
        return None
    t = text.strip()
    if re.fullmatch(r"(?i)present|current|now", t):
        return {"text": t, "year": None, "month": None, "present": True}
    year_m = re.search(_YEAR, t)
    year = int(year_m.group(0)) if year_m and year_m.group(0)[2:].isdigit() else None
    month = None
    m = re.match(r"([A-Za-z]+)", t)
    if m:
        month = _MONTHS.get(m.group(1)[:3].lower()) or _MONTHS.get(m.group(1).lower())
    return {"text": t, "year": year, "month": month, "present": False}


def find_date_range(text: str) -> tuple[dict | None, dict | None, str | None]:
    """Return (start, end, matched_text) for the LAST date range in text.
    A single date ("May 2030") comes back as (None, end, ...) because on a
    resume a lone date is almost always an end/graduation date."""
    matches = list(DATE_RANGE_RE.finditer(text))
    if not matches:
        return None, None, None
    m = matches[-1]
    start, end = m.group("start"), m.group("end")
    if end is None:
        return None, parse_date(start), m.group(0)
    return parse_date(start), parse_date(end), m.group(0)


# --------------------------------------------------------------- locations

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico",
}
_STATE_BY_NAME = {v.lower(): k for k, v in US_STATES.items()}
COUNTRIES = {
    "usa", "u.s.a.", "united states", "canada", "mexico", "india", "china", "japan", "korea",
    "south korea", "england", "uk", "u.k.", "united kingdom", "scotland", "ireland", "france",
    "germany", "spain", "italy", "brazil", "nigeria", "kenya", "pakistan", "bangladesh",
    "philippines", "vietnam", "uae", "u.a.e.", "united arab emirates", "saudi arabia", "qatar",
    "egypt", "australia", "singapore", "taiwan", "hong kong", "netherlands",
}


def parse_region(text: str) -> tuple[str | None, str | None]:
    """'TX' / 'TX 78664' / 'Texas' -> ('TX', 'USA'); 'U.A.E.' -> (None, 'U.A.E.')."""
    t = re.sub(r"\s+\d{5}(?:-\d{4})?$", "", text.strip()).strip(" .")
    if t.upper() in US_STATES and len(t) == 2:
        return t.upper(), "USA"
    if t.lower() in _STATE_BY_NAME:
        return _STATE_BY_NAME[t.lower()], "USA"
    raw = text.strip()
    if raw.lower() in COUNTRIES or t.lower() in COUNTRIES:
        return None, raw
    return None, None


def split_trailing_location(text: str) -> tuple[str, dict | None]:
    """'Penn Cricket Club, Vice-President, Philadelphia, PA'
         -> ('Penn Cricket Club, Vice-President', {city: Philadelphia, state: PA})
       'UNIVERSITY OF PENNSYLVANIA – Philadelphia, PA'
         -> ('UNIVERSITY OF PENNSYLVANIA', {...})"""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 2:
        return text, None
    state, country = parse_region(parts[-1])
    if not (state or country):
        return text, None
    city_part = parts[-2]
    # "ORG – City" or "ORG | City": the city is after the last dash/pipe.
    pieces = re.split(r"\s+[–—|-]\s+", city_part)
    city = pieces[-1].strip()
    rest_of_city_part = " – ".join(pieces[:-1]).strip()
    if not city or (len(city.split()) > 2 and not rest_of_city_part and len(parts) == 2):
        return text, None  # too ambiguous to tell where the org ends and the city starts
    head = ", ".join([p for p in parts[:-2]] + ([rest_of_city_part] if rest_of_city_part else []))
    return head.strip(" ,–-|"), {"city": city, "state": state, "country": country,
                                  "raw": f"{city}, {parts[-1]}"}


def parse_location(text: str) -> dict | None:
    if not text:
        return None
    _, loc = split_trailing_location("x, " + text) if "," in text else (None, None)
    return loc


# ------------------------------------------------------------------ header

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/[\w/-]+", re.I)
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w-]+", re.I)


def parse_header(lines: list[Line]) -> dict:
    out = {"name": None, "email": None, "phone": None, "linkedin": None, "github": None,
           "location": None}
    if not lines:
        return out
    name = lines[0].left.strip()
    if name.isupper():
        name = name.title()
    out["name"] = name
    text_lines = [l.text for l in lines[1:]]
    blob = " | ".join(text_lines)
    if m := EMAIL_RE.search(blob):
        out["email"] = m.group(0).lower()
    if m := PHONE_RE.search(blob):
        out["phone"] = m.group(0)
    if m := LINKEDIN_RE.search(blob):
        out["linkedin"] = m.group(0)
    if m := GITHUB_RE.search(blob):
        out["github"] = m.group(0)

    # Home location: a "Permanent/Home Address" line wins over a school address,
    # since scholarship residency rules care about where the student is FROM.
    def location_from(line_text: str) -> dict | None:
        line_text = re.sub(r"^[A-Za-z ]*Address:\s*", "", line_text)
        for seg in reversed(re.split(r"\s*[|•·]\s*", line_text)):
            seg = EMAIL_RE.sub("", PHONE_RE.sub("", seg)).strip(" ,")
            if "," in seg:
                _, loc = split_trailing_location(seg)
                if loc:
                    return loc
        return None

    ordered = sorted(text_lines, key=lambda t: 0 if re.match(r"(?i)\s*(permanent|home)\s+address", t)
                     else (2 if re.match(r"(?i)\s*(school|campus|current)\s+address", t) else 1))
    for t in ordered:
        if loc := location_from(t):
            out["location"] = loc
            break
    return out


# ---------------------------------------------------------- generic entries

def _right_kind(text: str) -> str:
    if not text:
        return ""
    if DATE_RANGE_RE.search(text):
        return "date"
    if parse_location(text):
        return "location"
    return "other"


def parse_entries(lines: list[Line]) -> list[dict]:
    """Group lines into entries (one job / project / activity each).

    An entry is one or two heading lines (organization, role, title...)
    followed by bullet points. A new entry starts when a non-bullet line
    appears after bullets, after two heading lines, or when its right-aligned
    text is the same kind (date/location) as one the entry already has.
    """
    entries: list[dict] = []
    cur: dict | None = None

    def new_entry():
        return {"_headings": [], "_kinds": set(), "bullets": [], "location": None,
                "start": None, "end": None}

    for line in lines:
        if line.bullet:
            if cur is None:
                cur = new_entry()
                entries.append(cur)
            cur["bullets"].append(line.text)
            continue
        kind = _right_kind(line.right)
        if (cur is None or cur["bullets"] or len(cur["_headings"]) >= 2
                or (kind and kind in cur["_kinds"])):
            cur = new_entry()
            entries.append(cur)
        cur["_headings"].append(line)
        if kind:
            cur["_kinds"].add(kind)

    for e in entries:
        headings: list[Line] = e.pop("_headings")
        e.pop("_kinds")
        texts = []
        for h in headings:
            left = h.left
            if h.right:
                if _right_kind(h.right) == "date":
                    e["start"], e["end"], _ = find_date_range(h.right)
                elif loc := parse_location(h.right):
                    e["location"] = e["location"] or loc
            else:
                s, en, matched = find_date_range(left)
                if matched and left.strip().endswith(matched.strip().rstrip(")")):
                    e["start"], e["end"] = s, en
                    left = left[: left.rfind(matched)].strip(" ,–-|")
            # "GOOGLE | Software Engineering Intern | Mountain View, CA"
            pipe_parts = [p.strip() for p in re.split(r"\s*\|\s*", left) if p.strip()]
            if len(pipe_parts) > 1:
                if (loc := parse_location(pipe_parts[-1])):
                    e["location"] = e["location"] or loc
                    pipe_parts = pipe_parts[:-1]
                texts.extend(pipe_parts)
                continue
            head, loc = split_trailing_location(left)
            if loc:
                e["location"] = e["location"] or loc
            texts.append(head)
        texts = [t for t in texts if t]
        e["heading"] = texts[0] if texts else None
        e["subheading"] = " | ".join(texts[1:]) or None
    return [{k: e[k] for k in ("heading", "subheading", "location", "start", "end", "bullets")}
            for e in entries]


# ------------------------------------------------------------ skills & lists

TECH_VOCAB = [
    "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "SQL", "MySQL", "PostgreSQL",
    "SQLite", "MongoDB", "HTML", "CSS", "PHP", "Ruby", "Ruby on Rails", "Rust", "Swift", "SwiftUI",
    "Kotlin", "MATLAB", "OCaml", "Haskell", "Scala", "Perl", "Bash", "Shell Scripting", "Linux",
    "Unix", "Git", "GitHub", "GitLab", "Docker", "Kubernetes", "AWS", "Azure", "GCP",
    "Google Cloud", "Hadoop", "Spark", "OpenStack", "TensorFlow", "PyTorch", "Keras",
    "scikit-learn", "Pandas", "NumPy", "Tableau", "Power BI", "Excel", "Microsoft Office",
    "Jupyter", "Colab", "React", "Node.js", "Django", "Flask", "jQuery", "Flash", "Arduino",
    "Raspberry Pi", "Verilog", "VHDL", "LabVIEW", "AutoCAD", "SolidWorks", "Figma", "Miro",
    "Unity", "LaTeX", "Android", "iOS", "Firebase", "XGBoost", "Spring", "Graphic design",
    "pgAdmin", "Access",
]
_VOCAB_RES = [(t, re.compile(rf"(?<![A-Za-z0-9+#]){re.escape(t)}(?![A-Za-z0-9+#])")) for t in TECH_VOCAB]


def vocab_scan(text: str) -> list[str]:
    return [t for t, rx in _VOCAB_RES if rx.search(text)]


_PROFICIENCY_PREFIX = re.compile(
    r"^(?:(?:highly|very)\s+)?(?:advanced|proficient|fluent|familiar|experienced|skilled|basic|"
    r"intermediate|expert|strong|knowledge|working knowledge|exposure|some|beginner|native|"
    r"conversational|elementary|limited|professional|bilingual)"
    r"(?:\s+proficiency)?(?:\s+(?:in|with|at|of))?\s*[:-]?\s*",
    re.IGNORECASE,
)


def split_items(text: str, separators: str = ",;|") -> list[str]:
    """Split a list on separators, but never inside (parentheses) or [brackets]."""
    items, depth, buf = [], 0, ""
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch in separators and depth == 0:
            items.append(buf)
            buf = ""
        else:
            buf += ch
    items.append(buf)
    items = [re.sub(r"^(?:and|or)\s+", "", i.strip(" .")) for i in items]
    return [i for i in items if i]


def clean_skill_items(text: str) -> list[str]:
    out = []
    text = re.sub(r"\[[^\]]*\]", "", text)  # template junk like "[enter keywords ...]"
    for chunk in split_items(text, ";|"):
        chunk = _PROFICIENCY_PREFIX.sub("", chunk)
        for item in split_items(chunk, ","):
            for sub in re.split(r"\s+and\s+(?![^(]*\))", item):
                sub = _PROFICIENCY_PREFIX.sub("", sub.strip())
                sub = re.split(r"\s+(?:for|to)\s+", sub)[0].strip(" .")
                if not sub or not sub[0].isupper() and not sub[0].isdigit() and not re.match(r"[a-z]+[A-Z]", sub):
                    continue  # prose fragments ("talent for organizing ...")
                if len(sub.split()) <= 5:
                    out.append(sub)
    return out


def split_award_items(text: str) -> list[str]:
    # "A (IBM), B (Coursera); C" -> split on ";" and on commas right after ")".
    return [p.strip(" .") for p in re.split(r";|(?<=\)),", text) if p.strip(" .")]


def split_language_items(text: str) -> list[str]:
    out = []
    for item in split_items(text, ",;|"):
        item = _PROFICIENCY_PREFIX.sub("", item).strip()
        item = re.sub(r"\s*\(.*?\)\s*$", "", item)
        for sub in re.split(r"\s+and\s+", item):
            sub = _PROFICIENCY_PREFIX.sub("", sub).strip(" .")
            if sub and sub[0].isupper():
                out.append(sub)
    return out


def dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for i in items:
        k = i.lower()
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out


LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z &/+,'’-]{1,40}?)\s*:\s*(.+)$")


def labeled_lines(lines: list[Line]) -> list[tuple[str | None, str]]:
    """Turn 'Label: a, b, c' lines into (label, values). A line with no label
    right after a labeled one is that line wrapping (PDFs), so it's joined on."""
    out: list[list] = []
    prev_bullet = True
    for line in lines:
        text = line.text
        m = LABEL_RE.match(text)
        if m:
            out.append([m.group(1).strip(), m.group(2).strip()])
        elif out and not line.bullet and (out[-1][0] is not None or not prev_bullet) \
                and not out[-1][1].endswith("."):
            out[-1][1] += " " + text   # wrapped continuation of the line above
        else:
            out.append([None, text])
        prev_bullet = line.bullet
    return [(a, b) for a, b in out]


# --------------------------------------------------------------- education

DEGREE_RE = re.compile(
    r"(?P<deg>"
    r"(?:Bachelor|Master|Associate|Doctor)(?:'s|’s)?(?:\s+of\s+(?:Science|Arts|Business Administration|"
    r"Engineering|Fine Arts|Applied Science|Music|Education|Public Health|Philosophy|Architecture)"
    r"(?:\s+in\s+Engineering)?)?"
    r"|\b(?:B\.?S\.?E\.?|B\.?S\.?|B\.?A\.?|B\.?B\.?A\.?|M\.?S\.?|M\.?B\.?A\.?|M\.?A\.?|M\.?Eng\.?|Ph\.?\s?D\.?|A\.?A\.?|A\.?S\.?)"
    r"(?=\s+in\s|,)"
    r"|High School Diploma)"
    r"(?:\s+in\s+|,\s*|:\s*|\s+-\s+|\s+–\s+)?"
    r"(?P<major>[^,;|(]*?)"
    r"(?=\s*(?:,|;|\||\(|\s-\s|\s–\s|\bMinor|\bConcentration|\bCumulative|\bOverall|\bGPA|$))"
)
GPA_RE = re.compile(r"GPA[^0-9]{0,15}([0-4]\.\d{1,3})(?:\s*/\s*([0-9]+(?:\.\d+)?))?|"
                    r"([0-4]\.\d{1,3})\s*/\s*(4\.0+|5\.0+)\s*GPA", re.IGNORECASE)
MINOR_RE = re.compile(r"\bMinors?\s*(?:in\b|:)\s*(.+?)(?=\s*(?:[;|(]|,|\bCumulative|\bOverall|\bMajor|\bGPA|\bConcentration|$))")
CONCENTRATION_RE = re.compile(r"\bConcentrations?\s*(?:in\b|:)\s*(.+?)(?=\s*(?:[;|(]|\bMinor|\bGPA|$))")
HONORS_RE = re.compile(r"Dean[’']?s List|Cum Laude|Magna Cum Laude|Summa Cum Laude|Honors? (?:College|Program|Student)|"
                       r"President[’']?s List|National Merit\w*|Valedictorian|Salutatorian", re.IGNORECASE)
# Recognitions that specific scholarships target, wherever they appear on the
# resume (e.g. "Eagle Scout" as a role under ACTIVITIES).
NOTABLE_AWARDS_RE = re.compile(
    r"Eagle Scout|Girl Scout Gold Award|Gold Award|National Merit (?:Scholar|Finalist|Semifinalist|Commended Student)\w*|"
    r"AP Scholar(?: with (?:Honor|Distinction))?|National AP Scholar|Valedictorian|Salutatorian|"
    r"QuestBridge \w+|Coca-Cola Scholar|Gates Scholar|Presidential Scholar|Boys State|Girls State",
    re.IGNORECASE,
)
SCHOOL_WORDS = re.compile(r"\b(University|College|Institute|Academy|School|Polytechnic|Conservatory)\b", re.I)


def degree_level(deg: str) -> str | None:
    d = deg.replace(".", "").lower()
    if d.startswith(("bachelor", "bs", "ba", "bba")):
        return "bachelor"
    if d.startswith(("master", "ms", "mba", "ma", "meng")):
        return "master"
    if d.startswith(("doctor", "phd")):
        return "doctorate"
    if d.startswith(("associate", "aa", "as")):
        return "associate"
    if d.startswith("high school"):
        return "high_school"
    return None


def parse_education(lines: list[Line]) -> list[dict]:
    # Group into one entry per school. A new school starts on a non-bullet line
    # that names a school, once the current entry already has degree/GPA info.
    groups: list[list[Line]] = []
    has_detail = False
    for line in lines:
        text = line.text
        detail = bool(DEGREE_RE.search(text) or GPA_RE.search(text) or line.bullet)
        starts_school = (not line.bullet and SCHOOL_WORDS.search(line.left)
                         and not (DEGREE_RE.search(text) or GPA_RE.search(text)
                                  or MINOR_RE.search(text) or re.search(r"(?i)coursework", text)))
        if not groups or (starts_school and has_detail):
            groups.append([line])
            has_detail = detail and len(groups[-1]) > 1
            continue
        groups[-1].append(line)
        has_detail = has_detail or detail

    entries = []
    for group in groups:
        first = group[0]
        school_text, loc = split_trailing_location(first.left)
        if not loc and first.right:
            loc = parse_location(first.right)
        unit = None
        # "University of Pennsylvania, School of Engineering ..." -> school + unit
        if "," in school_text:
            school, unit = [s.strip() for s in school_text.split(",", 1)]
        else:
            school = school_text
        all_text = " | ".join(l.text for l in group)

        degrees = []
        for m in DEGREE_RE.finditer(all_text):
            major = m.group("major").strip(" :–-")
            major = re.sub(r"^Engineering\s+in\s+", "", major)
            deg = m.group("deg").strip()
            if deg and not any(d["degree"] == deg and d["major"] == (major or None) for d in degrees):
                degrees.append({"degree": deg, "level": degree_level(deg), "major": major or None})
        conc = [c.strip() for c in CONCENTRATION_RE.findall(all_text)]
        for d in degrees:
            d["concentration"] = conc[0] if conc and len(degrees) == 1 else None

        minors = [DATE_RANGE_RE.sub("", re.sub(r"\s*\(.*$", "", m)).strip(" ,") for m in MINOR_RE.findall(all_text)]
        gpa = gpa_scale = None
        if m := GPA_RE.search(all_text):
            gpa = float(m.group(1) or m.group(3))
            scale = m.group(2) or m.group(4)
            gpa_scale = float(scale) if scale else 4.0
        # Graduation date: the end of the latest date range in this entry.
        grad = None
        for l in group:
            for part in (l.right, l.left):
                s, e, matched = find_date_range(part or "")
                if e and not e["present"]:
                    grad = e
        coursework = []
        for l in group:
            if m := re.match(r"(?i)(?:relevant\s+)?coursework\s*:\s*(.+)", l.text):
                coursework += split_items(m.group(1))
        honors = dedupe([h.group(0) for h in HONORS_RE.finditer(all_text)])

        is_high_school = bool(re.search(r"High School|\bSAT\b|\bACT\b|A Levels|\bAP\b", all_text)) and not any(
            d["level"] in ("bachelor", "master", "doctorate", "associate") for d in degrees)
        if not degrees and re.search(r"\bAcademy\b|\bPrep\b", school):
            is_high_school = True
        school = re.sub(r"\s*\(High School\)\s*", "", school).strip()
        if school.isupper():
            school = school.title()  # "TEXAS A&M UNIVERSITY" -> "Texas A&M University"
        entries.append({
            "school": school, "unit": unit, "location": loc, "degrees": degrees,
            "minors": minors, "gpa": gpa, "gpa_scale": gpa_scale,
            "graduation": grad, "expected": bool(EXPECTED_RE.search(all_text)),
            "honors": honors, "coursework": coursework,
            "level": "high_school" if is_high_school else (degrees[0]["level"] if degrees else None),
        })
    return entries


def school_year(level: str | None, grad: dict | None, today: date) -> str | None:
    """Where the student is right now, from their expected graduation date.
    A school year runs fall to spring, so it 'ends' in the spring/summer."""
    if not grad or not grad.get("year"):
        return None
    current_end = today.year + (1 if today.month >= 7 else 0)
    grad_end = grad["year"] + (1 if (grad.get("month") or 5) >= 7 else 0)
    years_left = grad_end - current_end
    if years_left < 0:
        return "graduated"
    if level == "high_school":
        return {0: "high school senior", 1: "high school junior",
                2: "high school sophomore", 3: "high school freshman"}.get(years_left, "high school student")
    if level in ("master", "doctorate"):
        return "graduate student"
    return {0: "senior", 1: "junior", 2: "sophomore", 3: "freshman"}.get(years_left, "incoming freshman")


# ------------------------------------------------------------------- main

def parse_resume(path: str | Path, today: date | None = None) -> dict:
    """Parse one resume file (.pdf or .docx) into a profile dict."""
    path = Path(path)
    today = today or date.today()
    lines = extract_lines(path)
    warnings: list[str] = []
    if any(l.unreadable for l in lines):
        warnings.append("Some text in this PDF uses a font that couldn't be decoded; "
                        "a few words or dates may be missing. A .docx or re-exported PDF fixes this.")

    # 1. Split into header + sections.
    header: list[Line] = []
    sections: dict[str, list[Line]] = {}
    order: list[str] = []
    current = None
    for line in lines:
        sec = section_of(line)
        if sec:
            current = sec
            if sec not in sections:
                sections[sec] = []
                order.append(sec)
            continue
        (sections[current] if current else header).append(line)

    profile: dict = {"parser_version": PARSER_VERSION, "source_file": path.name}
    profile.update(parse_header(header))

    # 2. Education.
    education = parse_education(sections.get("education", []))
    college = [e for e in education if e["level"] in ("bachelor", "master", "doctorate", "associate")]
    primary = college[0] if college else (education[0] if education else None)
    profile["education"] = education

    # 3. Experience-like sections.
    for sec in ("experience", "projects", "activities", "awards", "publications", "other", "summary"):
        profile[sec if sec != "awards" else "_award_entries"] = parse_entries(sections.get(sec, []))
    for p in profile["projects"]:
        techs = []
        if p["heading"] and (m := re.search(r"\(([^()]*)\)\s*$", p["heading"])):
            groups = [g.strip() for g in m.group(1).split(";")]
            tech_part = groups[-1]
            items = [t.strip() for t in tech_part.split(",") if t.strip()]
            if len(groups) > 1 or len(items) > 1 or vocab_scan(tech_part):
                techs = items
                p["affiliation"] = "; ".join(groups[:-1]) or None
                p["heading"] = p["heading"][: m.start()].strip()
        p.setdefault("affiliation", None)
        p["technologies"] = dedupe(techs + vocab_scan(" ".join(p["bullets"])))

    # 4. Skills / languages / certifications / awards / interests.
    skills, by_cat = [], {}
    languages, certs, awards, interests, coursework = [], [], [], [], []
    for label, values in labeled_lines(sections.get("skills", [])):
        lab = (label or "").lower()
        if label is None:
            items = [re.sub(r"^(?:and|or|some)\s+", "", i) for i in split_items(values, ",;|")]
            if items and all(len(i.split()) <= 4 for i in items):
                # A plain comma list: "Java, Python, MySQL, Swift – iOS, ..."
                found = [re.split(r"\s+[–-]\s+", i)[0] for i in items]
            else:
                found = vocab_scan(values)
            skills += found
            by_cat.setdefault("Other", []).extend(found)
        elif "language" in lab and "program" not in lab and "computer" not in lab:
            languages += split_language_items(values)
        elif re.search(r"certif|training|course|license", lab):
            certs += split_award_items(values)
        elif re.search(r"award|honou?r|achievement", lab):
            awards += split_award_items(values)
        elif re.search(r"interest|hobb", lab):
            interests += split_items(values, ",;|")
        else:
            items = clean_skill_items(values)
            skills += items
            by_cat.setdefault(label, []).extend(items)
    for label, values in labeled_lines(sections.get("coursework", [])):
        coursework += split_items(values, ",;|")
    for label, values in labeled_lines(sections.get("interests", [])):
        interests += split_items(values, ",;|")
    for label, values in labeled_lines(sections.get("certifications", [])):
        certs += split_award_items(values)
    for e in profile.pop("_award_entries"):
        if e["heading"]:
            awards.append(e["heading"])
        awards += [b for b in e["bullets"] if len(b.split()) <= 12]
    for e in education:
        awards += e["honors"]
        coursework += e["coursework"]
    awards += [m.group(0) for m in NOTABLE_AWARDS_RE.finditer("\n".join(l.text for l in lines))]

    mentioned = vocab_scan(" ".join(b for sec in ("experience", "activities")
                                    for e in profile[sec] for b in e["bullets"]))
    skills += [t for p in profile["projects"] for t in p["technologies"]] + mentioned

    profile["skills"] = dedupe(skills)
    profile["skills_by_category"] = {k: dedupe(v) for k, v in by_cat.items()}
    profile["spoken_languages"] = dedupe(languages)
    profile["certifications"] = dedupe(certs)
    profile["awards"] = dedupe(awards)
    profile["interests"] = dedupe(interests)
    profile["coursework"] = dedupe(coursework)

    # 5. Flatten the fields the matching engine filters on most.
    loc = profile.get("location") or {}
    profile["home_city"] = loc.get("city")
    profile["home_state"] = loc.get("state")
    profile["home_country"] = loc.get("country")
    if primary:
        deg = primary["degrees"][0] if primary["degrees"] else {}
        profile.update({
            "school": primary["school"],
            "school_state": (primary["location"] or {}).get("state"),
            "degree": deg.get("degree"),
            "degree_level": primary["level"],
            "major": deg.get("major"),
            "majors": [d["major"] for d in primary["degrees"] if d.get("major")],
            "minors": primary["minors"],
            "gpa": primary["gpa"],
            "gpa_scale": primary["gpa_scale"],
            "grad_year": (primary["graduation"] or {}).get("year"),
            "grad_month": (primary["graduation"] or {}).get("month"),
            "school_year": school_year(primary["level"], primary["graduation"], today),
        })
    else:
        for k in ("school", "school_state", "degree", "degree_level", "major", "gpa", "gpa_scale",
                  "grad_year", "grad_month", "school_year"):
            profile[k] = None
        profile["majors"], profile["minors"] = [], []

    # 6. Warnings for anything the matching engine will be missing.
    if not sections.get("education"):
        warnings.append("No EDUCATION section found.")
    for field, label in (("major", "major"), ("gpa", "GPA"), ("grad_year", "graduation year"),
                         ("home_state", "home state"), ("email", "email")):
        if profile.get(field) is None:
            warnings.append(f"No {label} found.")
    if primary and primary["graduation"] and primary["graduation"]["year"] is None:
        warnings.append(f"Graduation date '{primary['graduation']['text']}' has no real year.")
    profile["sections_found"] = order
    profile["warnings"] = warnings
    profile["raw_text"] = "\n".join(l.text for l in lines)
    profile["resume_hash"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return profile

"""
Step 1 of parsing: read a resume file into a list of Lines.

ATS resumes put a heading/organization on the left and a location or date
range right-aligned on the same line, e.g.

    TEXAS A&M UNIVERSITY                         College Station, TX
    Bachelor of Science, Computer Science        Aug 2026 – May 2030

Word (.docx) stores that right-aligned part after a tab character. PDFs have
no tabs -- just a big horizontal gap between words -- so for PDFs we rebuild
each line from word positions and split it wherever that gap is. Either way,
every format comes out as the same Line(left, right, bullet), so parse.py only
has to understand one shape.
"""

import re
from dataclasses import dataclass
from pathlib import Path

# A horizontal gap (in PDF points, 72 per inch) wider than this between two
# words on the same line means "this is the right-aligned column".
# Normal spaces between words are ~2-4 pt.
RIGHT_COLUMN_GAP = 20

# Words on the same visual line can differ slightly in vertical position.
SAME_LINE_TOLERANCE = 3

BULLET_GLYPHS = {"●", "•", "▪", "◦", "‣", "·", "∙", "■", "□", "○", "➢", "►", "✓", "-", "–", "*"}
# Glyphs that may be glued to the first word ("•Launched ..."). Dashes and
# asterisks are left out: "-" glued to a word is usually not a bullet.
GLUED_BULLET_GLYPHS = BULLET_GLYPHS - {"-", "–", "*"}

# Some PDFs use fonts that don't say which real character each glyph is, so
# pdfplumber prints codes like "(cid:3)". In practice (cid:3) is a space; the
# rest can't be recovered, so they're dropped and the profile gets a warning.
CID_RE = re.compile(r"\(cid:(\d+)\)")


def is_bullet_char(ch: str) -> bool:
    """Bullet glyphs, including Wingdings/Symbol bullets, which show up as
    characters in Unicode's "private use" range (e.g. U+F0B7, U+F0A7)."""
    return ch in BULLET_GLYPHS or 0xE000 <= ord(ch) <= 0xF8FF


def clean_text(text: str) -> str:
    text = CID_RE.sub(lambda m: " " if m.group(1) == "3" else "", text)
    text = text.replace("\xa0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", text).strip()

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass
class Line:
    left: str            # main text of the line
    right: str = ""      # right-aligned text (location or dates), if any
    bullet: bool = False # True for bullet-point lines
    x0: float = 0.0      # PDF only: where the text starts horizontally
    unreadable: bool = False  # PDF only: contained font codes we couldn't decode

    @property
    def text(self) -> str:
        return f"{self.left} {self.right}".strip()


def extract_lines(path: str | Path) -> list[Line]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    raise ValueError(f"Unsupported resume format '{suffix}' -- use .pdf or .docx")


def _extract_pdf(path: Path) -> list[Line]:
    import pdfplumber

    lines: list[Line] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = sorted(page.extract_words(), key=lambda w: (round(w["top"]), w["x0"]))
            # Group words into visual lines by vertical position.
            rows: list[list[dict]] = []
            for w in words:
                if rows and abs(w["top"] - rows[-1][0]["top"]) <= SAME_LINE_TOLERANCE:
                    rows[-1].append(w)
                else:
                    rows.append([w])
            for row in rows:
                row.sort(key=lambda w: w["x0"])
                bullet = False
                first = row[0]["text"]
                text_x0 = row[0]["x0"]
                if len(first) == 1 and is_bullet_char(first) and len(row) > 1:
                    bullet = True                     # "●  Developed ..."
                    row = row[1:]
                    text_x0 = row[0]["x0"]
                elif len(first) > 1 and (first[0] in GLUED_BULLET_GLYPHS or 0xE000 <= ord(first[0]) <= 0xF8FF):
                    bullet = True                     # "•Developed ..."
                    w0 = dict(row[0])
                    char_w = (w0["x1"] - w0["x0"]) / len(first)
                    w0["text"] = first[1:]
                    w0["x0"] += char_w
                    row = [w0] + row[1:]
                    text_x0 = w0["x0"]
                # Split into segments at large gaps.
                segments: list[list[dict]] = [[row[0]]]
                for prev, cur in zip(row, row[1:]):
                    if cur["x0"] - prev["x1"] > RIGHT_COLUMN_GAP:
                        segments.append([cur])
                    else:
                        segments[-1].append(cur)
                raw_texts = [" ".join(w["text"] for w in seg) for seg in segments]
                unreadable = any(CID_RE.search(t.replace("(cid:3)", "")) for t in raw_texts)
                texts = [clean_text(t) for t in raw_texts]
                texts = [t for t in texts if t]
                if not texts:
                    continue
                lines.append(Line(
                    left=texts[0],
                    right=" ".join(texts[1:]),
                    bullet=bullet,
                    x0=text_x0,
                    unreadable=unreadable,
                ))
    return _join_pdf_wraps(lines)


def _join_pdf_wraps(lines: list[Line]) -> list[Line]:
    """A long bullet wraps onto the next line in a PDF. That wrapped line
    starts at the bullet's text indent (not the left margin) and has no
    bullet glyph of its own, so glue it back onto the bullet above."""
    out: list[Line] = []
    for line in lines:
        prev = out[-1] if out else None
        is_wrap = (
            prev is not None
            and prev.bullet
            and not line.bullet
            and not line.right
            # A wrapped line starts where the bullet's TEXT starts. Centered
            # section headings (far to the right) and new entries at the left
            # margin (left of the bullet text) don't match, so they stay separate.
            and prev.x0 - 2 <= line.x0 <= prev.x0 + 12
        )
        if is_wrap:
            prev.left = f"{prev.left} {line.left}"
        else:
            out.append(line)
    return out


def _extract_docx(path: Path) -> list[Line]:
    import docx

    document = docx.Document(str(path))
    paragraphs = list(document.paragraphs)
    # Some resume templates lay content out in tables.
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                paragraphs.extend(cell.paragraphs)

    lines: list[Line] = []
    for p in paragraphs:
        raw = p.text
        if not raw.strip():
            continue
        left, _, right = raw.partition("\t")
        left, right = clean_text(left), clean_text(right)
        # Word list paragraphs (bulleted lists) carry a numPr element.
        bullet = p._p.find(f".//{_W}numPr") is not None
        if left[:1] and is_bullet_char(left[0]) and (left[1:2] == " " or left[0] in GLUED_BULLET_GLYPHS):
            bullet, left = True, left[1:].strip()
        if not left and right:
            left, right = right, ""
        lines.append(Line(left=left, right=right, bullet=bullet))
    return lines

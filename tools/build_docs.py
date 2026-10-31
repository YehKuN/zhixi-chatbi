from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ACCENT = "123B5D"
LIGHT = "EAF2F8"
BORDER = "D9E1E8"


def shade(cell, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    element = properties.find(qn("w:shd"))
    if element is None:
        element = OxmlElement("w:shd")
        properties.append(element)
    element.set(qn("w:fill"), fill)


def set_cell_border(cell, color: str = BORDER, size: str = "6") -> None:
    properties = cell._tc.get_or_add_tcPr()
    borders = properties.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        properties.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        node = borders.find(qn(tag))
        if node is None:
            node = OxmlElement(tag)
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), size)
        node.set(qn("w:space"), "0")
        node.set(qn("w:color"), color)


def set_cell_text(cell, text: str, *, bold: bool = False, color: str = "000000") -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.space_before = Pt(3)
    plain_text = text.strip().replace("`", "")
    plain_text = re.sub(r"\*\*([^*]+)\*\*", r"\1", plain_text)
    run = paragraph.add_run(plain_text)
    run.bold = bold
    run.font.name = "Microsoft YaHei"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(9.5)
    run.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    set_cell_border(cell)


def add_table(doc: Document, rows: list[list[str]]) -> None:
    if not rows:
        return
    columns = max(len(row) for row in rows)
    table = doc.add_table(rows=len(rows), cols=columns)
    table.style = "Table Grid"
    header_properties = table.rows[0]._tr.get_or_add_trPr()
    repeat_header = OxmlElement("w:tblHeader")
    repeat_header.set(qn("w:val"), "true")
    header_properties.append(repeat_header)
    for row_index, row in enumerate(rows):
        row_properties = table.rows[row_index]._tr.get_or_add_trPr()
        keep_row = OxmlElement("w:cantSplit")
        row_properties.append(keep_row)
        for column_index in range(columns):
            value = row[column_index] if column_index < len(row) else ""
            cell = table.cell(row_index, column_index)
            if row_index == 0:
                shade(cell, ACCENT)
                set_cell_text(cell, value, bold=True, color="FFFFFF")
            else:
                shade(cell, "FFFFFF" if row_index % 2 else LIGHT)
                set_cell_text(cell, value)
    doc.add_paragraph()


def add_inline(paragraph, text: str) -> None:
    tick = chr(96)
    cursor = 0
    while cursor < len(text):
        code_start = text.find(tick, cursor)
        bold_start = text.find("**", cursor)
        candidates = [index for index in (code_start, bold_start) if index >= 0]
        if not candidates:
            paragraph.add_run(text[cursor:])
            break
        start = min(candidates)
        if start > cursor:
            paragraph.add_run(text[cursor:start])
        if start == code_start:
            end = text.find(tick, start + 1)
            if end < 0:
                paragraph.add_run(text[start:])
                break
            run = paragraph.add_run(text[start + 1:end])
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor.from_string("294A62")
            cursor = end + 1
        else:
            end = text.find("**", start + 2)
            if end < 0:
                paragraph.add_run(text[start:])
                break
            run = paragraph.add_run(text[start + 2:end])
            run.bold = True
            cursor = end + 2


def add_markdown(doc: Document, markdown: str, *, document_title: str) -> None:
    lines = markdown.replace("\r\n", "\n").split("\n")
    index = 0
    in_code = False
    code_lines: list[str] = []
    table_rows: list[list[str]] = []

    def flush_table() -> None:
        nonlocal table_rows
        if table_rows:
            add_table(doc, table_rows)
            table_rows = []

    while index < len(lines):
        raw = lines[index]
        line = raw.strip()
        if line.startswith(chr(96) * 3):
            flush_table()
            if not in_code:
                in_code = True
                code_lines = []
            else:
                paragraph = doc.add_paragraph(style="No Spacing")
                paragraph.paragraph_format.left_indent = Cm(0.5)
                paragraph.paragraph_format.space_after = Pt(7)
                paragraph.paragraph_format.keep_together = True
                for code_line in code_lines:
                    run = paragraph.add_run(code_line + "\n")
                    run.font.name = "Consolas"
                    run.font.size = Pt(8.5)
                    run.font.color.rgb = RGBColor.from_string("2D3748")
                in_code = False
            index += 1
            continue
        if in_code:
            code_lines.append(raw)
            index += 1
            continue
        if not line:
            flush_table()
            index += 1
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [part.strip() for part in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                index += 1
                continue
            table_rows.append(cells)
            index += 1
            continue
        flush_table()
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            heading_text = heading.group(2).strip()
            if len(heading.group(1)) == 1 and heading_text == document_title:
                index += 1
                continue
            level = min(max(len(heading.group(1)) - 1, 1), 3)
            paragraph = doc.add_paragraph(style="Heading " + str(level))
            add_inline(paragraph, heading_text)
            paragraph.paragraph_format.keep_with_next = True
            index += 1
            continue
        if line.startswith(("- ", "* ", "+ ")):
            paragraph = doc.add_paragraph(style="List Bullet")
            add_inline(paragraph, line[2:].strip())
            index += 1
            continue
        ordered = re.match(r"^(\d+)[.)]\s+(.*)$", line)
        if ordered:
            paragraph = doc.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(0.45)
            paragraph.paragraph_format.first_line_indent = Cm(-0.45)
            paragraph.add_run(ordered.group(1) + ". ")
            add_inline(paragraph, ordered.group(2).strip())
            index += 1
            continue
        paragraph = doc.add_paragraph()
        add_inline(paragraph, line)
        index += 1
    flush_table()


def configure_document(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.7)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string("202A35")
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.18
    for name, size in (("Heading 1", 15), ("Heading 2", 12.5), ("Heading 3", 11)):
        style = styles[name]
        style.font.name = "Microsoft YaHei"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string("000000")
        style.paragraph_format.space_before = Pt(10 if name == "Heading 1" else 7)
        style.paragraph_format.space_after = Pt(4)
    title_style = styles["Title"]
    title_style.font.name = "Microsoft YaHei"
    title_style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    title_style.font.size = Pt(23)
    title_style.font.bold = True
    title_style.font.color.rgb = RGBColor.from_string("000000")
    title_properties = title_style._element.pPr
    if title_properties is not None:
        title_borders = title_properties.find(qn("w:pBdr"))
        if title_borders is not None:
            title_properties.remove(title_borders)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer_run = footer.add_run("智析 ChatBI · V1.0")
    footer_run.font.name = "Microsoft YaHei"
    footer_run.font.size = Pt(8)
    footer_run.font.color.rgb = RGBColor.from_string("718096")


def create_docx(source: Path, output: Path) -> None:
    doc = Document()
    configure_document(doc)
    title = source.stem
    first_heading = next(
        (
            line.strip().lstrip("#").strip()
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("#")
        ),
        title,
    )
    title_paragraph = doc.add_paragraph(style="Title")
    title_paragraph.paragraph_format.space_after = Pt(6)
    title_paragraph.paragraph_format.keep_with_next = True
    title_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph_properties = title_paragraph._p.get_or_add_pPr()
    paragraph_borders = paragraph_properties.find(qn("w:pBdr"))
    if paragraph_borders is not None:
        paragraph_properties.remove(paragraph_borders)
    title_run = title_paragraph.add_run(first_heading)
    title_run.font.name = "Microsoft YaHei"
    title_run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    title_run.font.size = Pt(23)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor.from_string("000000")
    subtitle = doc.add_paragraph("智析 ChatBI · V1.0 评审文档")
    subtitle.paragraph_format.space_after = Pt(16)
    subtitle.runs[0].font.size = Pt(10)
    subtitle.runs[0].font.color.rgb = RGBColor.from_string(ACCENT)
    add_markdown(doc, source.read_text(encoding="utf-8"), document_title=first_heading)
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)


def main() -> None:
    for source in sorted(DOCS.glob("[0-9][0-9]-*.md")):
        create_docx(source, source.with_suffix(".docx"))


if __name__ == "__main__":
    main()

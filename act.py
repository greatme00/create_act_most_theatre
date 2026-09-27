"""Генерация Word-акта."""

import calendar
from datetime import date
from pathlib import Path

from config import ACTS_DIR
from utils import friendly_day


# ---------- Числа прописью ----------

def _plural_ru(n: int, one: str, few: str, many: str) -> str:
    n = abs(n) % 100
    if 11 <= n <= 19:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


_ONES = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
         "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
         "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят",
         "семьдесят", "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот",
             "шестьсот", "семьсот", "восемьсот", "девятьсот"]
_MONTHS_GEN = {1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
               7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"}


def _female(word: str) -> str:
    if not word:
        return word
    if word.endswith(("н", "р", "л", "м", "д", "т", "к", "в", "з", "с", "б", "п", "г", "ф")):
        return word[:-1] + "а"
    return word


def _triple(n: int, female: bool = False) -> str:
    words = []
    h, rem = divmod(n, 100)
    if h:
        words.append(_HUNDREDS[h])
    if rem >= 20:
        t, o = divmod(rem, 10)
        words.append(_TENS[t])
        if o:
            words.append(_female(_ONES[o]) if female else _ONES[o])
    elif rem:
        words.append(_female(_ONES[rem]) if female else _ONES[rem])
    return " ".join(words)


def _num_to_words(n: int) -> str:
    if n == 0:
        return "ноль"
    parts = []
    for unit, female, one, few, many in (
        (1_000_000, False, "миллион", "миллиона", "миллионов"),
        (1_000, True, "тысяча", "тысячи", "тысяч"),
        (1, False, "", "", ""),
    ):
        if n >= unit:
            chunk, n = divmod(n, unit)
            if not chunk:
                continue
            text = _triple(chunk, female)
            if unit > 1:
                text = f"{text} {_plural_ru(chunk, one, few, many)}"
            parts.append(text)
    return " ".join(p for p in parts if p).strip()


def rubles_in_words(amount: float) -> str:
    rub = int(amount)
    kop = int(round((amount - rub) * 100))
    return (f"{_num_to_words(rub).capitalize()} "
            f"{_plural_ru(rub, 'рубль', 'рубля', 'рублей')} "
            f"{kop:02d} {_plural_ru(kop, 'копейка', 'копейки', 'копеек')}")


# ---------- Генерация акта ----------

def make_act(user_id: int, month: str, database) -> Path:
    """Word-акт по образцу act_template.docx. Все тексты берутся из БД."""
    from docx import Document
    from docx.shared import Pt, Cm, Mm
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    from docx.enum.table import WD_ALIGN_VERTICAL
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    shows = database.month_rows("shows", user_id, month)
    rehearsals = database.month_rows("rehearsals", user_id, month)
    user_prices = database.prices(user_id)
    profile = database.profile(user_id)
    texts = database.get_all_act_texts()

    full_name = (profile["full_name"] if profile and profile["full_name"] else "ВВЕДИТЕ ИМЯ")
    contract_number = (profile["contract_number"] if profile else None) or ""

    parts = full_name.split()
    if len(parts) >= 2:
        surname = parts[0]
        initials = "".join(f"{p[0]}." for p in parts[1:] if p)
        sign_name = f"{initials} {surname}"
    else:
        sign_name = full_name

    year, mon = int(month[:4]), int(month[5:7])
    last_day_num = calendar.monthrange(year, mon)[1]
    end_day = date(year, mon, last_day_num)

    period_text = f"с 1 {_MONTHS_GEN[mon]} {year} г. по {last_day_num} {_MONTHS_GEN[mon]} {year} г."

    # Плейсхолдеры для подстановки в тексты
    fmt = {
        "full_name": full_name,
        "sign_name": sign_name,
        "contract_number": contract_number,
        "period": period_text,
        "month": month,
        "year": year,
    }

    def t(key: str) -> str:
        """Возвращает текст по ключу с подставленными плейсхолдерами."""
        raw = texts.get(key, "")
        try:
            return raw.format(**fmt)
        except (KeyError, IndexError):
            return raw

    # ---------- группировка показов ----------
    grouped: dict[tuple, dict] = {}
    for row in shows:
        category = row["category"] or ""
        key = (row["title"], category)
        grouped.setdefault(key, {
            "title": row["title"],
            "role": category,
            "price": float(user_prices.get(category, row["price"] or 0)),
            "days": [],
            "times": [],
        })
        grouped[key]["days"].append(row["day"])
        grouped[key]["times"].append(row["show_time"] or "")

    grouped = dict(sorted(grouped.items(), key=lambda kv: min(kv[1]["days"])))

    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(11)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts")) or OxmlElement("w:rFonts")
    if rfonts.getparent() is None:
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), "Times New Roman")
    pf = style.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.space_after = Pt(0)
    pf.space_before = Pt(0)
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for section in doc.sections:
        section.page_width = Mm(210)
        section.page_height = Mm(297)
        section.left_margin = Cm(3)
        section.right_margin = Cm(1.5)
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)

    def _p(text="", *, align=WD_ALIGN_PARAGRAPH.JUSTIFY, bold=False,
           indent=Cm(1.25), size=None, space_after=0, space_before=0):
        p = doc.add_paragraph()
        p.alignment = align
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.space_before = Pt(space_before)
        p.paragraph_format.first_line_indent = indent
        if text:
            r = p.add_run(text)
            r.bold = bold
            if size:
                r.font.size = Pt(size)
        return p

    # ---------- Заголовок ----------
    _p("АКТ", align=WD_ALIGN_PARAGRAPH.CENTER, bold=True,
       indent=Cm(0), size=14, space_after=2)
    _p("сдачи-приемки оказанных услуг", align=WD_ALIGN_PARAGRAPH.CENTER,
       bold=True, indent=Cm(0), size=12, space_after=0)

    # ---------- Дата (таблица 2 колонки) ----------
    date_table = doc.add_table(rows=1, cols=2)
    date_table.autofit = False
    date_table.allow_autofit = False
    left_cell, right_cell = date_table.rows[0].cells
    left_cell.width = Cm(8.25)
    right_cell.width = Cm(8.25)

    left_cell.text = ""
    p_left = left_cell.paragraphs[0]
    p_left.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_left.paragraph_format.space_before = Pt(14)
    p_left.paragraph_format.space_after = Pt(14)
    p_left.paragraph_format.first_line_indent = Cm(0)
    p_left.add_run(t("header_city"))

    right_cell.text = ""
    p_right = right_cell.paragraphs[0]
    p_right.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_right.paragraph_format.space_before = Pt(14)
    p_right.paragraph_format.space_after = Pt(14)
    p_right.paragraph_format.first_line_indent = Cm(0)
    p_right.add_run(f"«{end_day.day:02d}» {_MONTHS_GEN[end_day.month]} {end_day.year} г.")

    date_tbl_pr = date_table._tbl.tblPr
    date_borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "none")
        el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        date_borders.append(el)
    date_tbl_pr.append(date_borders)

    # ---------- Преамбула ----------
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Cm(1.25)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.space_before = Pt(6)

    r = p.add_run(t("preamble_theater"))
    r.bold = True
    p.add_run(t("preamble_position"))
    r = p.add_run(t("preamble_performer_label"))
    r.bold = True
    p.add_run(t("preamble_footer"))

    # ---------- Договор ----------
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Cm(1.25)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.space_before = Pt(6)

    if contract_number:
        p.add_run(t("contract_text"))
    else:
        p.add_run(t("contract_text_empty"))

    _p(t("period_text"), space_after=6)

    # ---------- Таблица ----------
    headers = ("№ п/п", "Наименование услуг", "Наименование спектакля",
               "Артистическая роль/ Вокал", "Цена за единицу, руб.",
               "Кол-во услуг", "Стоимость, руб.")

    table = doc.add_table(rows=1, cols=7)
    table.style = "Table Grid"
    table.autofit = False
    table.allow_autofit = False

    tblPr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)

    widths = [Cm(1.0), Cm(2.8), Cm(2.9), Cm(2.7), Cm(2.3), Cm(1.6), Cm(2.7)]

    def _set_cell(cell, text, *, align=WD_ALIGN_PARAGRAPH.LEFT, bold=False):
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = align
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        for line in str(text).split("\n"):
            if p.runs:
                p.add_run().add_break()
            r = p.add_run(line)
            r.font.name = "Times New Roman"
            r.font.size = Pt(8)
            r.bold = bold
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    def _apply_widths(row):
        for cell, w in zip(row.cells, widths):
            cell.width = w

    for cell, text in zip(table.rows[0].cells, headers):
        _set_cell(cell, text, align=WD_ALIGN_PARAGRAPH.CENTER, bold=True)
    _apply_widths(table.rows[0])

    def money(v: float) -> str:
        return f"{v:,.2f}".replace(",", "\u00A0").replace(".", ",")

    row_number = 0
    total = 0.0

    from collections import Counter

    for group in grouped.values():
        row_number += 1
        count = len(group["days"])
        price = float(group["price"])
        summa = price * count
        total += summa

        day_counts = Counter(group["days"])
        day_time_pairs = list(zip(group["days"], group["times"]))
        day_time_pairs.sort(key=lambda dt: (dt[0], dt[1] or "00:00"))

        dates_parts = []
        for d, tm in day_time_pairs:
            if tm and day_counts[d] > 1:
                dates_parts.append(f"{friendly_day(d)} ({tm})")
            else:
                dates_parts.append(friendly_day(d))
        dates_text = ", ".join(dates_parts)

        values = (
            row_number,
            t("service_show"),
            f"«{group['title']}»\n{dates_text}",
            group["role"],
            money(price),
            count,
            money(summa),
        )
        row = table.add_row()
        _apply_widths(row)
        for i, (cell, value) in enumerate(zip(row.cells, values)):
            align = WD_ALIGN_PARAGRAPH.CENTER if i in (0, 4, 5, 6) else WD_ALIGN_PARAGRAPH.LEFT
            _set_cell(cell, value, align=align)

    if rehearsals:
        row_number += 1
        units = sum(r["units"] for r in rehearsals)
        rehearsal_price = float(user_prices.get("Репетиция", 750))
        summa = rehearsal_price * units
        total += summa
        days_sorted = sorted(r["day"] for r in rehearsals)
        dates_text = ", ".join(friendly_day(d) for d in days_sorted)
        values = (
            row_number,
            t("service_rehearsal"),
            f"{t('rehearsal_theater')}\n{dates_text}",
            "",
            money(rehearsal_price),
            units,
            money(summa),
        )
        row = table.add_row()
        _apply_widths(row)
        for i, (cell, value) in enumerate(zip(row.cells, values)):
            align = WD_ALIGN_PARAGRAPH.CENTER if i in (0, 4, 5, 6) else WD_ALIGN_PARAGRAPH.LEFT
            _set_cell(cell, value, align=align)

    total_row = table.add_row()
    _apply_widths(total_row)
    merged = total_row.cells[0].merge(total_row.cells[5])
    _set_cell(merged, "ВСЕГО", align=WD_ALIGN_PARAGRAPH.CENTER, bold=True)
    _set_cell(total_row.cells[6], money(total), align=WD_ALIGN_PARAGRAPH.CENTER, bold=True)

    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)

    # ---------- После таблицы ----------
    _p("", indent=Cm(0), space_after=6)
    _p(t("obligations"), space_after=6)
    _p("", indent=Cm(0), space_after=6)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Cm(1.25)
    p.paragraph_format.space_after = Pt(6)
    p.add_run(t("total_label"))
    r = p.add_run(rubles_in_words(total))
    r.bold = True
    p.add_run(".")

    _p(t("payment_terms"), space_after=6)
    _p(t("copies_text"), space_after=6)
    _p("", indent=Cm(0), space_after=12)

    # ---------- Подписи ----------
    sign = doc.add_table(rows=1, cols=2)
    sign.autofit = False
    sign.allow_autofit = False
    for cell, w in zip(sign.rows[0].cells, [Cm(8.25), Cm(8.25)]):
        cell.width = w

    left, right = sign.rows[0].cells

    def _fill_sign(cell, lines):
        cell.text = ""
        first = True
        for text, bold in lines:
            if first:
                p = cell.paragraphs[0]
                first = False
            else:
                p = cell.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.space_before = Pt(0)
            if text:
                r = p.add_run(text)
                r.font.name = "Times New Roman"
                r.font.size = Pt(11)
                r.bold = bold

    _fill_sign(left, [
        (t("signature_customer_title"), True),
        ("", False),
        (t("signature_customer_position"), False),
        ("", False),
        (t("signature_customer_name"), False),
        (t("signature_date"), False),
        (t("signature_mp"), False),
    ])

    _fill_sign(right, [
        (t("signature_performer_title"), True),
        ("", False),
        (t("signature_performer_label"), False),
        ("", False),
        (t("signature_performer_name"), False),
        (t("signature_date"), False),
    ])

    tbl_pr = sign._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "none")
        el.set(qn("w:sz"), "0")
        el.set(qn("w:space"), "0")
        borders.append(el)
    tbl_pr.append(borders)

    ACTS_DIR.mkdir(exist_ok=True)
    path = ACTS_DIR / f"акт_{month}_{sign_name}.docx"
    doc.save(path)
    return path
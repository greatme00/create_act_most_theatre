"""Генерация Word-акта."""

import calendar
from collections import Counter
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


# ---------- Вспомогательные ----------

def _performer_label_key(status: str, gender: str) -> str:
    status = status or "self_employed"
    gender = gender or "m"
    return f"preamble_performer_label_{status}_{gender}"


def _gender_ending(gender: str) -> str:
    return "ая" if gender == "f" else "ый"


def _sign_name(full_name: str, gender: str) -> str:
    parts = full_name.split()
    if len(parts) < 2:
        return full_name
    surname = parts[0]
    initials = "".join(f"{p[0]}." for p in parts[1:] if p)
    if gender == "f":
        if surname.endswith(("ий", "ый", "ой")):
            surname = surname[:-2] + "ая"
        elif surname.endswith(("ов", "ев", "ин", "ын")):
            surname = surname + "а"
    return f"{initials} {surname}"


def _format_money(v: float) -> str:
    return f"{v:,.2f}".replace(",", "\u00A0").replace(".", ",")


# ---------- Генерация акта ----------

def make_act(user_id: int, month: str, database) -> Path:
    from docx import Document
    from docx.shared import Pt, Cm, Mm, Twips
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT
    from docx.enum.table import WD_ALIGN_VERTICAL
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    BODY_PT = 8

    shows = database.month_rows("shows", user_id, month)
    rehearsals = database.month_rows("rehearsals", user_id, month)
    user_prices = database.prices(user_id)
    profile = database.profile(user_id)
    texts = database.get_all_act_texts()

    full_name = (profile["full_name"] if profile and profile["full_name"] else "ВВЕДИТЕ ИМЯ")
    contract_number = (profile["contract_number"] if profile else None) or ""

    status = (profile["status"] if profile else None) or "self_employed"
    gender = (profile["gender"] if profile else None) or "m"
    sign_name = _sign_name(full_name, gender)

    year, mon = int(month[:4]), int(month[5:7])
    last_day_num = calendar.monthrange(year, mon)[1]
    end_day = date(year, mon, last_day_num)

    period_text = f"с 1 {_MONTHS_GEN[mon]} {year} г. по {last_day_num} {_MONTHS_GEN[mon]} {year} г."

    fmt = {
        "full_name": full_name,
        "sign_name": sign_name,
        "contract_number": contract_number,
        "period": period_text,
        "month": month,
        "year": year,
        "gender_ending": _gender_ending(gender),
    }

    def t(key: str) -> str:
        raw = texts.get(key, "")
        try:
            return raw.format(**fmt)
        except (KeyError, IndexError):
            return raw

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
    style.font.size = Pt(BODY_PT)
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
           indent=Cm(1.0), size=None, space_after=0, space_before=0):
        p = doc.add_paragraph()
        p.alignment = align
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.space_before = Pt(space_before)
        p.paragraph_format.first_line_indent = indent
        if text:
            r = p.add_run(text)
            r.bold = bold
            r.font.name = "Times New Roman"
            r.font.size = Pt(size if size is not None else BODY_PT)
        return p

    _p("АКТ", align=WD_ALIGN_PARAGRAPH.CENTER, bold=True,
       indent=Cm(0), size=BODY_PT, space_after=0)
    _p("сдачи-приемки оказанных услуг", align=WD_ALIGN_PARAGRAPH.CENTER,
       bold=True, indent=Cm(0), size=BODY_PT, space_after=0)

    content_width = Cm(16.5)
    p_date = doc.add_paragraph()
    p_date.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_date.paragraph_format.first_line_indent = Cm(0)
    p_date.paragraph_format.space_before = Pt(6)
    p_date.paragraph_format.space_after = Pt(6)
    p_date.paragraph_format.tab_stops.add_tab_stop(content_width, WD_TAB_ALIGNMENT.RIGHT)
    r_city = p_date.add_run(t("header_city"))
    r_city.font.name = "Times New Roman"
    r_city.font.size = Pt(BODY_PT)
    p_date.add_run("\t")
    r_date = p_date.add_run(f"«{end_day.day:02d}» {_MONTHS_GEN[end_day.month]} {end_day.year} г.")
    r_date.font.name = "Times New Roman"
    r_date.font.size = Pt(BODY_PT)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Cm(1.0)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.space_before = Pt(4)

    r = p.add_run(t("preamble_theater"))
    r.bold = True
    r.font.name = "Times New Roman"
    r.font.size = Pt(BODY_PT)
    r2 = p.add_run(t("preamble_position"))
    r2.font.name = "Times New Roman"
    r2.font.size = Pt(BODY_PT)
    r = p.add_run(t(_performer_label_key(status, gender)))
    r.bold = True
    r.font.name = "Times New Roman"
    r.font.size = Pt(BODY_PT)
    r3 = p.add_run(t("preamble_footer"))
    r3.font.name = "Times New Roman"
    r3.font.size = Pt(BODY_PT)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Cm(1.0)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.space_before = Pt(0)

    if contract_number:
        r = p.add_run(t("contract_text"))
    else:
        r = p.add_run(t("contract_text_empty"))
    r.font.name = "Times New Roman"
    r.font.size = Pt(BODY_PT)

    _p(t("period_text"), space_after=8, space_before=2)

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

    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:w"), "9605")
    tblW.set(qn("w:type"), "dxa")
    tblPr.append(tblW)

    tblCellMar = OxmlElement("w:tblCellMar")
    tblCellMar = OxmlElement("w:tblCellMar")
    for m_name, m_val in (("top", "40"), ("left", "103"), ("bottom", "40"), ("right", "103")):
        node = OxmlElement(f"w:{m_name}")
        node.set(qn("w:w"), m_val)
        node.set(qn("w:type"), "dxa")
        tblCellMar.append(node)
    tblPr.append(tblCellMar)
    tblPr.append(tblCellMar)

    col_widths_dxa = [492, 2093, 2812, 1540, 980, 796, 892]
    widths = [Twips(w) for w in col_widths_dxa]

    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for w in col_widths_dxa:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(w))
        grid.append(gc)

    def _set_cell(cell, text, *, align=WD_ALIGN_PARAGRAPH.LEFT, bold=False):
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = align
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        # убираем пустые строки сверху/снизу из текста БД
        lines = [ln for ln in str(text).strip().split("\n")]
        for i, line in enumerate(lines):
            if i > 0:
                p.add_run().add_break()
            r = p.add_run(line)
            r.font.name = "Times New Roman"
            r.font.size = Pt(BODY_PT)
            r.bold = bold
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    def _apply_widths(row):
        for cell, w in zip(row.cells, widths):
            cell.width = w

    for cell, text in zip(table.rows[0].cells, headers):
        _set_cell(cell, text, align=WD_ALIGN_PARAGRAPH.CENTER, bold=True)
    _apply_widths(table.rows[0])

    row_number = 0
    total = 0.0
    total_units = 0

    for group in grouped.values():
        row_number += 1
        count = len(group["days"])
        price = float(group["price"])
        summa = price * count
        total += summa
        total_units += count

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
            _format_money(price),
            count,
            _format_money(summa),
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
        total_units += units
        days_sorted = sorted(r["day"] for r in rehearsals)
        dates_text = ", ".join(friendly_day(d) for d in days_sorted)
        values = (
            row_number,
            t("service_rehearsal"),
            f"{t('rehearsal_theater')}\n{dates_text}",
            "",
            _format_money(rehearsal_price),
            units,
            _format_money(summa),
        )
        row = table.add_row()
        _apply_widths(row)
        for i, (cell, value) in enumerate(zip(row.cells, values)):
            align = WD_ALIGN_PARAGRAPH.CENTER if i in (0, 4, 5, 6) else WD_ALIGN_PARAGRAPH.LEFT
            _set_cell(cell, value, align=align)

    total_row = table.add_row()
    _apply_widths(total_row)
    merged = total_row.cells[0].merge(total_row.cells[4])
    _set_cell(merged, "ВСЕГО", align=WD_ALIGN_PARAGRAPH.RIGHT, bold=True)
    _set_cell(total_row.cells[5], str(total_units), align=WD_ALIGN_PARAGRAPH.CENTER, bold=True)
    _set_cell(total_row.cells[6], _format_money(total), align=WD_ALIGN_PARAGRAPH.RIGHT, bold=True)

    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)

    _p("", indent=Cm(0), space_after=6)

    _p(t("obligations"), space_after=4)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Cm(1.0)
    p.paragraph_format.space_after = Pt(4)
    r0 = p.add_run(t("total_label"))
    r0.font.name = "Times New Roman"
    r0.font.size = Pt(BODY_PT)
    r = p.add_run(rubles_in_words(total))
    r.bold = True
    r.font.name = "Times New Roman"
    r.font.size = Pt(BODY_PT)
    r1 = p.add_run(".")
    r1.font.name = "Times New Roman"
    r1.font.size = Pt(BODY_PT)

    if status == "gph":
        ndfl_amount = round(total * 0.13, 2)
        insurance_amount = round(total * 0.30, 2)
        ndfl_text = t("tax_ndfl").format(ndfl_amount=_format_money(ndfl_amount))
        insurance_text = t("insurance_fees").format(insurance_amount=_format_money(insurance_amount))
        _p(ndfl_text, space_after=4)
        _p(insurance_text, space_after=4)
        _p(t("insurance_responsibility"), space_after=4)

    _p(t("payment_terms"), space_after=4)
    _p(t("copies_text"), space_after=8)

    # ---------- Подписи 

        # ---------- Подписи: левый у левого края, правый у правого ----------
    full = Cm(16.5)  # ширина рабочей области

    def _sign_line(left_text: str, right_text: str = ""):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.left_indent = Cm(0)
        p.paragraph_format.right_indent = Cm(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        # RIGHT-tab на правом краю — правый текст прижмётся вправо
        p.paragraph_format.tab_stops.add_tab_stop(full, WD_TAB_ALIGNMENT.RIGHT)
        pPr = p._p.get_or_add_pPr()
        for old in pPr.findall(qn("w:ind")):
            pPr.remove(old)
        r1 = p.add_run(left_text)
        r1.font.name = "Times New Roman"
        r1.font.size = Pt(BODY_PT)
        if right_text:
            p.add_run("\t")
            r2 = p.add_run(right_text)
            r2.font.name = "Times New Roman"
            r2.font.size = Pt(BODY_PT)
        return p

    def _extract_fio(raw: str) -> str:
        s = (raw or "").strip()
        if "/" in s:
            for part in s.split("/"):
                part = part.strip()
                if part and not set(part) <= set("_—–- "):
                    return part
        return s

    cust_fio = _extract_fio(t("signature_customer_name")) or "А.А. Черепнев"
    perf_fio = _extract_fio(t("signature_performer_name")) or sign_name

    cust_title = (t("signature_customer_title") or "Заказчик:").strip()
    perf_title = (t("signature_performer_title") or "Исполнитель:").strip()
    cust_pos = (t("signature_customer_position") or "Директор").strip()
    mp = (t("signature_mp") or "М.П.").strip()

    line_cust = f"___________________ /{cust_fio}/"
    line_perf = f"___________________ /{perf_fio}/"
    line_date = f"«____» ___________________ {year} г."

    _sign_line(cust_title, perf_title)
    _sign_line(cust_pos, "")
    _sign_line(line_cust, line_perf)
    _sign_line("", "")
    _sign_line(line_date, line_date)
    _sign_line("", "")
    _sign_line(mp, "")

    ACTS_DIR.mkdir(exist_ok=True)
    path = ACTS_DIR / f"акт_{month}_{sign_name}.docx"
    doc.save(path)
    return path
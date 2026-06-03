"""
Парсер импорта сметы из Excel.
Колонки: 1 — № п/п, 3 — наименование, 4 — ед. изм., 5 — количество.
Логика разделов/позиций — по правилам локальной сметы АВС; PDF не затрагивается.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, BinaryIO, Iterator

from openpyxl import load_workbook

# --- текст и фильтры ---

_INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_MULTI_SPACE = re.compile(r"\s+")
_CYRILLIC = re.compile(r"[\u0400-\u04FF\u0500-\u052F]")
_LATIN = re.compile(r"[A-Za-z]")
_DIGITS_ONLY = re.compile(r"^[\d\s.,]+$")
_SPECIALS_ONLY = re.compile(r"^[\s\W_]+$", re.UNICODE)

_ENGLISH_SKIP = frozenset(
    s.upper()
    for s in (
        "SECTION",
        "EARTH WORKS",
        "DESCRIPTION",
        "QUANTITY",
        "UNIT",
        "TOTAL",
        "SUMMARY",
        "SUBTOTAL",
        "AMOUNT",
        "BILL OF QUANTITIES",
        "NO",
        "ITEM",
        "CODE",
        "RATE",
        "PRICE",
        "COST",
        "REMARKS",
        "NOTES",
    )
)

_TOTALS_SKIP = frozenset(
    s.upper()
    for s in (
        "ИТОГО",
        "ВСЕГО",
        "ВСЕГО ПО РАЗДЕЛУ",
        "ВСЕГО ПО СМЕТЕ",
        "НАКЛАДНЫЕ РАСХОДЫ",
        "СМЕТНАЯ ПРИБЫЛЬ",
        "НДС",
        "ИТОГО С НДС",
    )
)

_PLACEHOLDER_UNITS = frozenset({"", "/", "*", "—", "-", "–", "/ "})

# ARGB из Excel → стиль заголовка раздела в UI
_FILL_TO_ACCENT: dict[str, str] = {}
for _rgb, _accent in (
    ("FFCC0000", "red"),
    ("FFC00000", "red"),
    ("FFFF0000", "red"),
    ("FF800000", "bordeaux"),
    ("FF7030A0", "bordeaux"),
    ("FF993366", "bordeaux"),
    ("FFFFC000", "gold"),
    ("FFFF9900", "gold"),
    ("FFD99694", "gold"),
    ("FFE26B0A", "gold"),
):
    _FILL_TO_ACCENT[_rgb.upper()] = _accent


@dataclass
class ParsedExcelRow:
    kind: str  # "section" | "position"
    name: str
    list_no: str = ""  # № из 1-го столбца Excel
    unit: str = ""
    quantity: Decimal | None = None
    header_accent: str = ""
    source_row: int = 0


@dataclass
class ExcelParseResult:
    rows: list[ParsedExcelRow] = field(default_factory=list)
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def clean_cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value == int(value):
        s = str(int(value))
    else:
        s = str(value)
    s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    s = s.replace("\t", " ")
    s = _INVISIBLE.sub("", s)
    s = _MULTI_SPACE.sub(" ", s).strip()
    return s


# Разделители двуязычных ячеек BOQ: «русский / English», «м3 грунта / m3 of soil»
_BILINGUAL_SPLIT = re.compile(r"\s*/\s*|\s*\\\s*")
# Хвост «/ MONOLITHIC …» или «/ Repair of …» без кириллицы в той же части
_TRAILING_LATIN_TAIL = re.compile(
    r"\s*/\s*(?![\u0400-\u04FF\u0500-\u052F])[\s\S]*$",
    re.IGNORECASE,
)
# Английские слова в хвосте (Canal, DISMANTLING, Dismantling works …)
_LATIN_WORD = re.compile(r"[A-Za-z]{3,}")
# Типичные английские дубли в BOQ/сметах (в т.ч. «Сanal» с кириллической С)
_TRAILING_EN_WORDS = frozenset(
    w.lower()
    for w in (
        "Canal",
        "Channel",
        "Dismantling",
        "EARTHWORKS",
        "WORKS",
        "Repair",
        "OTHER",
        "LINING",
        "TRAYS",
        "CONCRETE",
        "STRUCTURE",
    )
)
# Визуально похожие кириллица ↔ латиница (С↔C, а↔a …)
_HOMOGLYPH_MAP = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "С": "C",
        "Е": "E",
        "Н": "H",
        "К": "K",
        "М": "M",
        "О": "O",
        "Р": "P",
        "Т": "T",
        "Х": "X",
        "а": "a",
        "в": "b",
        "с": "c",
        "е": "e",
        "н": "h",
        "к": "k",
        "м": "m",
        "о": "o",
        "р": "p",
        "т": "t",
        "х": "x",
    }
)


def _latin_fold(word: str) -> str:
    """Омографы кириллицы в латиницу для сравнения (Сanal → Canal)."""
    return word.translate(_HOMOGLYPH_MAP)


def _should_strip_trailing_word(word: str) -> bool:
    w = word.strip(".,;:!?")
    if not w:
        return False
    if re.fullmatch(r"[\(\)\d.\-+/№]+", w):
        return False
    folded = _latin_fold(w).lower()
    if folded in _TRAILING_EN_WORDS:
        return True
    if has_cyrillic(w):
        return False
    if re.fullmatch(r"[A-Za-z][A-Za-z.\-]*", w) and len(w) >= 3:
        return True
    return False


def _strip_trailing_english_words(text: str) -> str:
    """Убирает последние слова-англицизмы: Canal, Сanal, Works …"""
    words = text.split()
    while words and _should_strip_trailing_word(words[-1]):
        words.pop()
    return " ".join(words).strip()


def _is_english_tail(fragment: str) -> bool:
    """Фрагмент без кириллицы, похожий на английский дубляж наименования."""
    if not fragment or has_cyrillic(fragment):
        return False
    return bool(_LATIN_WORD.search(fragment))


def _strip_latin_suffix_after_cyrillic(text: str) -> str:
    """
    Убирает хвост без кириллицы после русского текста:
    «… (ГР-29) Canal 4-K-1-1. DISMANTLING WORKS» → «… (ГР-29)».
    """
    words = text.split()
    if len(words) < 2:
        return text
    for i in range(1, len(words)):
        head = " ".join(words[:i]).strip()
        tail = " ".join(words[i:]).strip()
        if has_cyrillic(head) and _is_english_tail(tail):
            return head
    return text


def keep_cyrillic_text(text: str) -> str:
    """
    Оставляет только русский/казахский фрагмент ячейки.
    Английский дубляж после «/», через «/» или отдельным хвостом отбрасывается.
    """
    s = clean_cell_text(text)
    if not s:
        return ""
    if not has_cyrillic(s):
        return ""

    parts = [p.strip() for p in _BILINGUAL_SPLIT.split(s) if p.strip()]
    if len(parts) > 1:
        cyr_parts = [p for p in parts if has_cyrillic(p)]
        if not cyr_parts:
            return ""
        if len(cyr_parts) == 1:
            s = cyr_parts[0]
        else:
            keys = [_unit_token_key(p) for p in cyr_parts]
            if len(set(keys)) == 1 and keys[0] and all(len(p) <= 8 for p in cyr_parts):
                s = next(p for p in cyr_parts if has_cyrillic(p))
            else:
                s = " ".join(cyr_parts)

    s = _TRAILING_LATIN_TAIL.sub("", s).strip()
    for _ in range(6):
        prev = s
        s = _strip_latin_suffix_after_cyrillic(s)
        s = re.sub(
            r"\s*\(\s*[A-Za-z][^)]*\)\s*$",
            "",
            s,
        ).strip()
        if s == prev:
            break
    s = _strip_trailing_english_words(s)
    # Хвост из латинских слов без кириллицы (Dismantling works …)
    s = re.sub(
        r"\s+(?:(?:[A-Za-z]{2,}[A-Za-z0-9.\-/]*)\s*)+$",
        "",
        s,
    ).strip()
    s = _strip_trailing_english_words(s)
    s = re.sub(
        r"\s+(?:[СCсc][AaАа][NnНн][AaАа][LlЛл]\.?)\s*$",
        "",
        s,
    ).strip()
    s = _MULTI_SPACE.sub(" ", s).strip()
    return s if has_cyrillic(s) else ""


def normalize_estimate_name(text: str) -> str:
    """Наименование раздела/позиции без английского дубляжа (импорт и отображение)."""
    cleaned = keep_cyrillic_text(text)
    return cleaned if cleaned else (text or "").strip()


# Соответствие латиница ↔ кириллица для коротких единиц (t/т, m3/м3 …)
_UNIT_TOKEN_MAP = {
    "t": "т",
    "m3": "м3",
    "m2": "м2",
    "kg": "кг",
    "km": "км",
    "m": "м",
    "l": "л",
    "pcs": "шт",
    "pc": "шт",
    "шт": "шт",
    "компл": "компл",
    "комплект": "комплект",
}


def _unit_token_key(token: str) -> str:
    """Ключ для сравнения дублей «т/т», «m3/м3»."""
    t = _latin_fold(token.strip().lower().rstrip(".,;:"))
    t = t.replace("³", "3").replace(" ", "")
    if t in _UNIT_TOKEN_MAP:
        return _UNIT_TOKEN_MAP[t]
    if t == "т":
        return "т"
    return t


def _collapse_duplicate_unit_tokens(text: str) -> str:
    """«т т», «т/т», «m3 м3» → одна единица."""
    s = _MULTI_SPACE.sub(" ", (text or "").strip())
    if not s:
        return s
    if re.fullmatch(r"(?i)(т|t)\s*/\s*(т|t)\.?", s):
        return "т"
    words = s.split()
    if len(words) == 2:
        k0, k1 = _unit_token_key(words[0]), _unit_token_key(words[1])
        if k0 and k0 == k1 and len(k0) <= 6:
            return words[0] if has_cyrillic(words[0]) else words[1]
    return s


def normalize_excel_unit(text: str) -> str:
    """Ед. изм. без английского дубляжа; т/т → т."""
    cleaned = keep_cyrillic_text(text)
    if not cleaned:
        return (text or "").strip()
    return _collapse_duplicate_unit_tokens(cleaned)


def _normalize_rgb(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip().upper()
        if len(s) == 8 and s.startswith("FF"):
            return s
        if len(s) == 6:
            return "FF" + s
        return None
    try:
        s = str(raw).strip().upper()
        if hasattr(raw, "rgb"):
            s = str(raw.rgb).strip().upper()
    except Exception:
        return None
    if s in ("00000000", "FFFFFFFF", "FF000000", "NONE", "AUTO"):
        return None
    if len(s) == 8:
        return s
    if len(s) == 6:
        return "FF" + s
    return None


def cell_fill_accent(cell: Any) -> str:
    """Цвет заливки ячейки (кол. 3) → accent для заголовка раздела."""
    if cell is None:
        return ""
    fill = getattr(cell, "fill", None)
    if not fill or getattr(fill, "fill_type", None) in (None, "none"):
        return ""
    candidates: list[str] = []
    for attr in ("fgColor", "start_color", "bgColor"):
        part = getattr(fill, attr, None)
        if part is None:
            continue
        rgb = _normalize_rgb(getattr(part, "rgb", None) or part)
        if rgb:
            candidates.append(rgb)
    for rgb in candidates:
        accent = _FILL_TO_ACCENT.get(rgb.upper())
        if accent:
            return accent
    for rgb in candidates:
        r = int(rgb[2:4], 16)
        g = int(rgb[4:6], 16)
        b = int(rgb[6:8], 16)
        if r >= 160 and g < 100 and b < 100:
            return "red" if r >= 200 else "bordeaux"
        if r >= 200 and g >= 140 and b < 80:
            return "gold"
    return ""


def _is_placeholder_unit(unit: str) -> bool:
    u = unit.strip()
    if u in _PLACEHOLDER_UNITS:
        return True
    if u.replace(" ", "") in ("/", "*"):
        return True
    return False


def has_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC.search(text))


def is_english_only_line(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if not _LATIN.search(t):
        return False
    if has_cyrillic(t):
        return False
    upper = re.sub(r"[^A-Za-z\s]", "", t).strip().upper()
    if upper in _ENGLISH_SKIP:
        return True
    words = [w for w in upper.split() if w]
    if words and all(w in _ENGLISH_SKIP for w in words):
        return True
    return not has_cyrillic(t) and bool(_LATIN.search(t))


def is_totals_line(name: str) -> bool:
    key = re.sub(r"\s+", " ", name.strip().upper())
    if key in _TOTALS_SKIP:
        return True
    for prefix in _TOTALS_SKIP:
        if key.startswith(prefix + " ") or key.startswith(prefix + ":"):
            return True
    return False


def is_junk_name(name: str) -> bool:
    if not name:
        return True
    if _DIGITS_ONLY.match(name):
        return True
    if _SPECIALS_ONLY.match(name):
        return True
    if is_english_only_line(name):
        return True
    if is_totals_line(name):
        return True
    return False


def parse_excel_list_no(value: Any) -> str:
    """№ п/п из 1-го столбца (целое или короткая метка)."""
    if value is None or value is False:
        return ""
    if isinstance(value, (int, float)):
        try:
            if value == int(value):
                return str(int(value))
        except (ValueError, OverflowError):
            return ""
        return clean_cell_text(value)[:16]
    s = clean_cell_text(value)
    if not s:
        return ""
    upper = s.upper().replace("№", "").strip()
    if upper in ("NO", "N", "П/П", "ПП"):
        return ""
    if re.fullmatch(r"\d+", s):
        return s
    return s[:16]


def parse_quantity(value: Any) -> Decimal | None:
    if value is None or value is False:
        return None
    if isinstance(value, (int, float)):
        try:
            d = Decimal(str(value))
            return d if d > 0 else None
        except (InvalidOperation, ValueError):
            return None
    s = clean_cell_text(value)
    if not s:
        return None
    s = re.sub(r"^[−–—-]+\s*", "", s)
    s = s.replace(" ", "").replace(",", ".")
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    return d if d > 0 else None


def classify_row(
    name: str,
    unit: str,
    qty: Decimal | None,
    *,
    fill_accent: str = "",
) -> str | None:
    """section | position | None (пропуск)."""
    if is_junk_name(name):
        return None
    if not has_cyrillic(name):
        return None
    unit_ok = _is_placeholder_unit(unit)
    if unit_ok and qty is None:
        return "section"
    if not unit_ok and qty is not None:
        return "position"
    if fill_accent and unit_ok and qty is None:
        return "section"
    return None


def _seekable_copy(file: BinaryIO) -> BinaryIO:
    if hasattr(file, "seek"):
        try:
            file.seek(0)
            return file
        except (OSError, AttributeError, TypeError):
            pass
    data = file.read()
    return BytesIO(data)


def _iter_xlsx_rows(
    file: BinaryIO,
) -> Iterator[tuple[int, str, str, str, str, Decimal | None, str]]:
    wb = load_workbook(_seekable_copy(file), data_only=True, read_only=False)
    try:
        ws = wb.active
        if not ws:
            return
        for row_idx in range(1, (ws.max_row or 0) + 1):
            c1 = parse_excel_list_no(ws.cell(row_idx, 1).value)
            c3 = keep_cyrillic_text(ws.cell(row_idx, 3).value)
            c4 = normalize_excel_unit(ws.cell(row_idx, 4).value)
            c5_raw = ws.cell(row_idx, 5).value
            qty = parse_quantity(c5_raw)
            accent = cell_fill_accent(ws.cell(row_idx, 3))
            yield row_idx, c1, c3, c4, c5_raw if c5_raw is not None else "", qty, accent
    finally:
        wb.close()


def _iter_xls_rows(
    file: BinaryIO,
) -> Iterator[tuple[int, str, str, str, str, Decimal | None, str]]:
    import xlrd

    book = xlrd.open_workbook(file_contents=_seekable_copy(file).read())
    sheet = book.sheet_by_index(0)
    for row_idx in range(sheet.nrows):
        r = row_idx + 1
        c1 = parse_excel_list_no(
            sheet.cell_value(row_idx, 0) if sheet.ncols > 0 else ""
        )
        c3 = keep_cyrillic_text(sheet.cell_value(row_idx, 2) if sheet.ncols > 2 else "")
        c4 = normalize_excel_unit(
            sheet.cell_value(row_idx, 3) if sheet.ncols > 3 else ""
        )
        c5_raw = sheet.cell_value(row_idx, 4) if sheet.ncols > 4 else ""
        qty = parse_quantity(c5_raw)
        accent = ""
        try:
            xf = sheet.cell_xf_index(row_idx, 2) if sheet.ncols > 2 else 0
            bk = book.xf_list[xf]
            bg = getattr(getattr(bk, "background", None), "background_colour_index", None)
            if bg is not None and bg != 9:
                # xlrd palette — грубая эвристика для красных/жёлтых
                if bg in (10, 11, 12):
                    accent = "red"
                elif bg in (13, 14, 51, 52):
                    accent = "gold"
        except Exception:
            pass
        yield r, c1, c3, c4, c5_raw, qty, accent


def parse_excel_estimate(file) -> ExcelParseResult:
    """
    Читает .xlsx / .xls и возвращает упорядоченные строки разделов и позиций.
    """
    result = ExcelParseResult()
    name = (getattr(file, "name", "") or "").lower()
    if name.endswith(".xls") and not name.endswith(".xlsx"):
        row_iter = _iter_xls_rows(file)
    elif name.endswith(".xlsx"):
        row_iter = _iter_xlsx_rows(file)
    else:
        result.errors.append("Поддерживаются только файлы .xlsx и .xls")
        return result

    header_like = 0
    for row_idx, list_no, c3, c4, _c5_raw, qty, accent in row_iter:
        if not c3 and not c4 and qty is None:
            continue
        if not c3:
            result.skipped += 1
            continue
        # пропуск шапки таблицы (первые ~6 строк с «описание/unit/quantity» на латинице)
        if row_idx <= 6 and is_english_only_line(c3):
            header_like += 1
            result.skipped += 1
            continue

        kind = classify_row(c3, c4, qty, fill_accent=accent)
        if kind is None:
            result.skipped += 1
            continue

        if kind == "section":
            result.rows.append(
                ParsedExcelRow(
                    kind="section",
                    name=c3,
                    list_no=list_no,
                    header_accent=accent or "",
                    source_row=row_idx,
                )
            )
        else:
            unit = c4
            result.rows.append(
                ParsedExcelRow(
                    kind="position",
                    name=c3,
                    list_no=list_no,
                    unit=unit,
                    quantity=qty,
                    source_row=row_idx,
                )
            )

    if not result.rows and header_like:
        result.errors.append("Не найдено строк для импорта — проверьте формат файла.")
    return result

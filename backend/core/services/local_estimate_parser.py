from __future__ import annotations

import io
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, BinaryIO, Union

import pdfplumber

logger = logging.getLogger(__name__)

from core.models import ESTIMATE_ITEM_NAME_MAX_LENGTH

START_KEYWORDS = (
    "локальная смета",
    "локальный сметный расчет",
    "локальный сметный расчёт",
)

END_KEYWORDS = (
    "трудовые ресурсы",
    "строительные машины",
    "материалы",
    "ресурсная ведомость",
    "ведомость ресурсов",
    "ресурсная смета",
)

END_EXACT = frozenset(
    {
        "трудовые ресурсы",
        "материалы",
        "ресурсная ведомость",
        "ведомость ресурсов",
        "ресурсная смета",
    }
)
END_PREFIX = ("строительные машины",)

STOP_SUBSTR = (
    "итого",
    "всего",
    "ндс",
    "сумма",
    "стоимость",
    "в том числе",
    "сметная стоимость",
    "сметная заработная",
    "итого по смете",
    "итого по раздел",
)

RE_POS = re.compile(
    r"^(\d{1,4})\.?\s+"
    r"((?:\d+-\d+-\d+)(?:'[0-9+,\s.]+'[0-9'+\s.]*)?)\s*"
    r"(.*)$"
)
# Второй столбец — «Прайслист» / «Прайс-лист» вместо шифра нормы
RE_POS_PRICELIST = re.compile(
    r"^(\d{1,4})\.?\s+(Прайслист|Прайс[\s-]*лист)\b\s*(.*)$",
    re.IGNORECASE,
)
RE_NAIM_OBJ = re.compile(
    r"^Наименование\s+объекта\s*[-–—:]\s*(.+?)\s*$",
    re.IGNORECASE,
)
RE_TABLE_COLS = re.compile(
    r"^\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+"
    r"[\d-]"
)
# Подзаголовок между позициями («литальный» или частая опечатка «лекальный»)
_RE_MONOLITH_CAST_BLOCK_LINE = re.compile(
    r"^Монолитный\s+(?:литальный|л[ие]кальный)\s+блок\s*\.?\s*$",
    re.IGNORECASE,
)
# Тип изделия — две буквы (кириллица или латиница в экспорте PDF).
_RE_ZATVOR_DIM_BANNER_CORE = (
    r"Затвор\s+(?:[А-Яа-яЁё]{2}|[A-Za-z]{2})\s+\d+\s*[ХХххxX×]\s*\d+(?:\s*\.)?\s*"
)
# Под «БЕТОННЫЕ РАБОТЫ»: серый баннер «Монолитный ж/б колодец»
_RE_MONOLITH_WELL_BANNER_CORE = (
    r"(?:Монолитный\s+ж\s*/\s*б\s+колодец|Монолитный\s+железобетонный\s+колодец)"
    r"(?:\s*\.)?\s*"
)
RE_SECTION = re.compile(
    r"^(?:КАНАЛ|П\s+КАНАЛ|ДЮКЕР|"
    r"ДЕМОНТАЖНЫЕ\s+РАБОТЫ|СТРОИТЕЛЬНЫЕ\s+РАБОТЫ|МОНТАЖНЫЕ\s+РАБОТЫ|"
    r"БЕТОННЫЕ\s+РАБОТЫ|"
    r"ПРОЧИЕ\s+РАБОТЫ|"
    r"(?:МОНОЛИТНЫЙ\s+ЛИТАЛЬНЫЙ|МОНОЛИТНЫЙ\s+Л[ИЕ]КАЛЬНЫЙ)\s+БЛОК|"
    r"МОНОЛИТНЫЙ\s+ОГОЛОВОК|"
    r"МОНОЛИТНАЯ\s+ДИАФРАГМА|ЗУБ\s+МОНОЛИТНЫЙ|"
    + _RE_MONOLITH_WELL_BANNER_CORE
    + r"|"
    r"ПРОЕЗЖАЯ\s+ЧАСТЬ|ПРОЕЗДНАЯ\s+ЧАСТЬ|"
    + _RE_ZATVOR_DIM_BANNER_CORE
    + r"|"
    r"ЗЕМЛЯНЫЕ\s+РАБОТЫ|КОНЦЕВОЙ\s+КОЛОДЕЦ|ПОВОРОТНЫЙ\s+КОЛОДЕЦ|"
    r"ЛОТКОВЫЙ\s+КАНАЛ)",
    re.IGNORECASE,
)
RE_RAZDEL = re.compile(
    r"^РАЗДЕЛ\s*(\d+)\s*[\.\:]\s*(.+?)\s*$",
    re.IGNORECASE,
)
RE_RAZDEL_INNER = re.compile(
    r"^РАЗДЕЛ\s*\d+\s*[\.\:]",
    re.IGNORECASE,
)
RE_LSR_NO = re.compile(
    r"№\s*([\d\.\-]+)\s*",
    re.IGNORECASE,
)
# «1-1 ЛОКАЛЬНАЯ СМЕТА №» — номер в начале строки, после № может не быть цифр на той же строке
RE_LSR_LEADING_NO = re.compile(
    r"^([\d\.\-]+)\s+ЛОКАЛЬНАЯ",
    re.IGNORECASE,
)
RE_REG_FALLBACK = re.compile(
    r"([^\n]{12,1000}?\S)\s+"
    r"(м2|м3|м²|м³|шт|кг|т|т·км|т\.км)\s+"
    r"(-?[0-9][0-9\s,]*[,.]?\d*)\b",
    re.IGNORECASE,
)

MAX_QTY = 1_000_000.0
_LOOSE_PROJECT_QTY_INT_CAP = 25_000
_EQ_COEFF_MAX = 2.5
Y_CLUSTER_TOL = 2.5
# Col.3: слова на краях часто попадают в соседние колонки по центроиду.
C3_LEFT_PAD = 28.0
C3_RIGHT_PAD = 32.0


def _norm(s: str) -> str:
    s = s.replace("\u00a0", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s.strip())
    return s


def _soft_norm(s: str) -> str:
    """Нормализация наименований: сохраняет логические переносы строк из PDF."""
    if not s:
        return ""
    s = s.replace("\u00a0", " ").replace("\r", "")
    lines: list[str] = []
    for line in s.split("\n"):
        line = re.sub(r"[ \t]+", " ", line.strip())
        if line:
            lines.append(line)
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _collapse_m_units_multiline(s: str) -> str:
    if not s or "\n" not in s:
        return _collapse_m_units(s)
    return "\n".join(_collapse_m_units(line) for line in s.split("\n"))


def _flatten_name_display(name: str) -> str:
    """Одна строка для БД/UI: без переносов PDF, только пробелы между фрагментами."""
    if not name:
        return ""
    s = name.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def _join_name_lines(acc: str, frag: str) -> str:
    a = (acc or "").strip()
    f = (frag or "").strip()
    if not a:
        return _flatten_name_display(f)
    if not f:
        return _flatten_name_display(a)
    return _flatten_name_display(f"{a} {f}")


def _log_name_debug(stage: str, **fields: Any) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return
    parts = " ".join(f"{key}={value!r}" for key, value in fields.items())
    logger.debug("local_estimate_parser name %s: %s", stage, parts)


def _collapse_m_units(s: str) -> str:
    if not s:
        return s
    s = re.sub(
        r"(?i)м\s*(?:3|\u00b3)(?![0-9])",
        "м3",
        s,
    )
    s = re.sub(
        r"(?i)м\s*(?:2|\u00b2)(?![0-9])",
        "м2",
        s,
    )
    return s


def _normalize_re_pos_line(s: str) -> str:
    s = s.strip()
    s = re.sub(
        r"^(\d{1,4}\.?\s+)[\u0415Ee](?=\d)",
        r"\1",
        s,
    )
    s = re.sub(
        r"^(\d{1,4}\.?\s+)[\u0421C](?=\d{3,4}-\d+-\d+)",
        r"\1",
        s,
    )
    return s


def _match_position_head(ph: str) -> re.Match[str] | None:
    ph = _normalize_re_pos_line(ph)
    m = RE_POS.match(ph)
    if m:
        return m
    return RE_POS_PRICELIST.match(ph)


def _fnum(s: str) -> float | None:
    t = re.sub(r"\s+", "", s or "").replace(",", ".")
    if not t or t in ("--", "—", "–", "-."):
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    if v == 0 or abs(v) > MAX_QTY:
        return None
    return v


def _is_year_like(n: int) -> bool:
    return 1900 <= n <= 2100


def _is_equals_coefficient_decimal(sl: str, dec_start: int, q: float) -> bool:
    if dec_start < 1 or sl[dec_start - 1] != "=":
        return False
    return 0.0001 < abs(q) < _EQ_COEFF_MAX


_FALSE_MATERIALS_END_PREV = (
    "стоимость",
    "заработная",
    "оборудован",
    "транспорт",
    "металломонтаж",
    "общестроительн",
    "конструкций",
)


def _materials_line_likely_inside_lsr_table(prev_low: str | None) -> bool:
    if not prev_low:
        return False
    pl = prev_low.strip()
    return any(k in pl for k in _FALSE_MATERIALS_END_PREV)


def _is_end(ln: str, low: str, prev_low: str | None = None) -> bool:
    t = low.strip()
    if not t:
        return False
    # Длинная строка таблицы с шифром не должна закрывать ЛСР по startswith("ресурсная …")
    if len(t) > 160 and re.search(r"\d+-\d+-\d+", t):
        return False
    # Только короткие «шапки» документа; длинный хвост титула не считаем концом сметы
    def _title_like_end() -> bool:
        return len(t) <= 140

    if t == "материалы" and _materials_line_likely_inside_lsr_table(prev_low):
        return False
    for ex in END_EXACT:
        if t == ex:
            return True
        if (
            ex != "материалы"
            and t.startswith(ex + " ")
            and _title_like_end()
        ):
            return True
    for px in END_PREFIX:
        if t.startswith(px) and _title_like_end():
            return True
    if t.startswith("материал") and len(t) < 35 and "тенге" not in t and "тыс" not in t:
        if _materials_line_likely_inside_lsr_table(prev_low):
            return False
        return True
    return False


def _is_lsr_start(low: str) -> bool:
    return any(k in low for k in START_KEYWORDS)


def _format_section(lsr: str | None, body: str) -> str:
    t = _norm(body)
    if lsr:
        return f"ЛС № {lsr} | {t}"
    return t


_ZEMLYANYE_SECTION_SUFFIX = " ЗЕМЛЯНЫЕ РАБОТЫ"


def _normalize_zemlyanye_section_groups(items: list[dict[str, Any]]) -> None:
    """
    Подряд идущие позиции с секцией X и X + « ЗЕМЛЯНЫЕ РАБОТЫ» объединяют одну
    длинную секцию — иначе при импорте получаются два EstimateSection, и демонтаж
    «теряется» из карточки земляных работ.
    """
    if not items:
        return
    i = 0
    n = len(items)
    while i < n:
        sec0 = _norm(items[i].get("section") or "")
        if not sec0:
            i += 1
            continue
        if sec0.endswith(_ZEMLYANYE_SECTION_SUFFIX):
            base = _norm(sec0[: -len(_ZEMLYANYE_SECTION_SUFFIX)]).rstrip()
        else:
            base = sec0
        long_sec = base + _ZEMLYANYE_SECTION_SUFFIX
        j = i + 1
        saw_long = sec0 == long_sec
        while j < n:
            s = _norm(items[j].get("section") or "")
            if s == base:
                j += 1
                continue
            if s == long_sec:
                saw_long = True
                j += 1
                continue
            break
        if saw_long and base:
            for k in range(i, j):
                if _norm(items[k].get("section") or "") == base:
                    items[k]["section"] = long_sec
        i = j if j > i else i + 1


_WORK_NAME_SAVE_SUBSTR = frozenset(
    {
        "разработк",
        "экскаватор",
        "грунт",
        "насып",
        "укладк",
        "устройств",
        "демонтаж",
        "монтаж",
        "погрузк",
        "самосвал",
        "полив",
        "насос",
        "уплотн",
        "карьер",
        "бульдозер",
        "перемещен",
        "водохозяйствен",
    }
)


def _is_noise_line(low: str) -> bool:
    if not _norm(low):
        return True
    for w in STOP_SUBSTR:
        if w not in low:
            continue
        if w == "стоимость":
            if len(low) > 45 and any(k in low for k in _WORK_NAME_SAVE_SUBSTR):
                continue
        if w in (
            "в том числе",
            "сумма",
            "всего",
        ) and len(low) > 40 and any(k in low for k in _WORK_NAME_SAVE_SUBSTR):
            continue
        return True
    return False


def _word_xc(w: dict) -> float:
    return (float(w["x0"]) + float(w["x1"])) / 2.0


def _word_column_overlap_ratio(ww: dict, lo: float, hi: float) -> float:
    x0, x1 = float(ww["x0"]), float(ww["x1"])
    overlap = min(x1, hi) - max(x0, lo)
    if overlap <= 0:
        return 0.0
    return overlap / max(x1 - x0, 0.001)


def _is_col2_metadata_token(text: str) -> bool:
    """Отдельное слово/токен метаданных col.2 (не текст наименования)."""
    t = (text or "").strip()
    if not t:
        return False
    if re.match(r"(?i)^ТЧ$", t):
        return True
    if re.match(r"(?i)^табл\.$", t):
        return True
    if re.match(r"(?i)^РСНБ$", t):
        return True
    if re.match(r"(?i)^Кзтр$", t):
        return True
    if re.match(r"(?i)^Кэм$", t):
        return True
    if re.match(r"(?i)^п\.", t):
        return True
    compact = re.sub(r"\s+", "", t)
    if re.fullmatch(r"\d+-\d+-\d+(?:'[^']*')*", compact):
        return True
    return False


def _name_column_zone(bounds: list[float]) -> tuple[float, float]:
    return bounds[2] - C3_LEFT_PAD, bounds[3] + C3_RIGHT_PAD


def _extract_name_column_words(
    ws: list[dict],
    bounds: list[float],
) -> list[dict]:
    """
    Col.3: слова зоны наименования с расширенными bounds.
    Не забираем метаданные col.2; не теряем крайние слова («96 кВт», «На», «мощностью»).
    """
    c3_lo, c3_hi = _name_column_zone(bounds)
    col2_hi = bounds[2]
    picked: list[dict] = []
    for ww in ws:
        text = (ww.get("text") or "").strip()
        if not text:
            continue
        x0, x1 = float(ww["x0"]), float(ww["x1"])
        xc = _word_xc(ww)
        overlap_c3 = min(x1, c3_hi) - max(x0, c3_lo)
        if overlap_c3 <= 0:
            continue
        ratio_c3 = overlap_c3 / max(x1 - x0, 0.001)
        if ratio_c3 < 0.15:
            continue
        if _is_col2_metadata_token(text) and xc < col2_hi:
            continue
        overlap_c2 = min(x1, col2_hi) - max(x0, bounds[1])
        if overlap_c2 > 0 and x1 <= col2_hi + 0.5:
            if _is_col2_metadata_token(text):
                continue
        # Чисто числовые токены col.4–5 (кол-во, цены) — не в наименование
        if xc >= bounds[3] + 2.0 and re.fullmatch(
            r"[\d\s.,]+",
            text.replace("\u00a0", " "),
        ):
            continue
        picked.append(ww)
    return picked


def _split_row_words_by_columns(
    ws: list[dict],
    bounds: list[float],
) -> list[list[dict]]:
    """Распределить слова строки по колонкам 1…5; col.3 с расширенными bounds."""
    cols: list[list[dict]] = [[] for _ in range(5)]
    name_words = _extract_name_column_words(ws, bounds)
    cols[2] = list(name_words)
    assigned = {id(w) for w in name_words}
    for ww in ws:
        if id(ww) in assigned:
            continue
        scores: list[float] = []
        for j in range(5):
            if j == 2:
                scores.append(0.0)
                continue
            lo, hi = bounds[j], bounds[j + 1]
            scores.append(_word_column_overlap_ratio(ww, lo, hi))
        best = max(range(5), key=lambda j: scores[j])
        if best == 2:
            continue
        if scores[best] < 0.28:
            continue
        cols[best].append(ww)
    return cols


def _multiline_text_from_words(words: list[dict]) -> str:
    if not words:
        return ""
    by_y: dict[float, list[dict]] = {}
    for ww in words:
        by_y.setdefault(_word_line_key(ww), []).append(ww)
    lines: list[str] = []
    for yk in sorted(by_y.keys()):
        parts: list[str] = []
        for ww in sorted(by_y[yk], key=lambda x: float(x["x0"])):
            t = ww.get("text") or ""
            if t:
                parts.append(t)
        if parts:
            lines.append(" ".join(parts))
    if not lines:
        return ""
    return _soft_norm("\n".join(lines))


def _word_in_column(
    ww: dict,
    lo: float,
    hi: float,
    *,
    right_pad: float = 0.0,
) -> bool:
    """Слово принадлежит ячейке: x0 внутри колонки или заметное перекрытие."""
    x0 = float(ww["x0"])
    x1 = float(ww["x1"])
    hi_eff = hi + right_pad
    if x0 >= lo and x0 < hi_eff:
        return True
    xc = _word_xc(ww)
    if lo <= xc < hi:
        return True
    overlap = min(x1, hi_eff) - max(x0, lo)
    if overlap <= 0:
        return False
    width = max(x1 - x0, 0.001)
    return overlap / width >= 0.45


def _word_line_key(w: dict, tol: float = Y_CLUSTER_TOL) -> float:
    return (
        round((float(w["top"]) + float(w["bottom"])) / 2.0 / tol) * tol
    )


def _cell_text_from_words(
    ws: list[dict],
    lo: float,
    hi: float,
    *,
    right_pad: float = 0.0,
) -> str:
    """
    Текст ячейки АВС: слова группируются по Y (визуальные строки),
    внутри строки сортируются по X, строки склеиваются через \\n.
    """
    cell_words = [
        ww for ww in ws if _word_in_column(ww, lo, hi, right_pad=right_pad)
    ]
    if not cell_words:
        return ""
    by_y: dict[float, list[dict]] = {}
    for ww in cell_words:
        yk = _word_line_key(ww)
        by_y.setdefault(yk, []).append(ww)
    lines: list[str] = []
    for yk in sorted(by_y.keys()):
        parts: list[str] = []
        for ww in sorted(by_y[yk], key=lambda x: float(x["x0"])):
            t = ww.get("text") or ""
            if t:
                parts.append(t)
        if parts:
            lines.append(" ".join(parts))
    if not lines:
        return ""
    text = _soft_norm("\n".join(lines))
    if len(lines) > 1:
        _log_name_debug(
            "cell_lines",
            bounds=(lo, hi),
            right_pad=right_pad,
            line_count=len(lines),
            reconstructed=text,
        )
    return text


def _parse_qty_cell(s: str) -> float | None:
    if not s:
        return None
    compact = _norm(s.replace("\u00a0", " "))
    if not compact or compact in ("-", "—", "--"):
        return None
    found: list[float] = []
    for m in re.finditer(r"-?[0-9]+(?:[.,][0-9]+)?", compact):
        q = _fnum(m.group(0))
        if q is not None and 0.0001 < abs(q) < MAX_QTY:
            found.append(q)
    if not found:
        return None
    if len(found) >= 2:
        return found[-1]
    return found[0]


def _header_column_bounds(ws: list[dict]) -> list[float] | None:
    nums: list[tuple[dict, int]] = []
    for w in sorted(ws, key=lambda wx: float(wx["x0"])):
        t = (w.get("text") or "").strip()
        if t.isdigit():
            nums.append((w, int(t)))
    best: list[tuple[dict, int]] | None = None
    for start_i, (_sw, v0) in enumerate(nums):
        if v0 != 1:
            continue
        chain: list[tuple[dict, int]] = [nums[start_i]]
        expect = 2
        idx = start_i + 1
        while idx < len(nums):
            wn, vn = nums[idx]
            if vn == expect:
                chain.append((wn, vn))
                expect += 1
                idx += 1
                if expect > 13:
                    break
                continue
            if vn == expect - 1:
                idx += 1
                continue
            break
        if len(chain) < 5:
            continue
        if best is None or len(chain) > len(best):
            best = chain
    if not best or len(best) < 5:
        return None
    bounds: list[float] = [max(0.0, float(best[0][0]["x0"]) - 5.0)]
    for i in range(len(best) - 1):
        a, b = best[i][0], best[i + 1][0]
        bounds.append((float(a["x1"]) + float(b["x0"])) / 2.0)
    bounds.append(float(best[-1][0]["x1"]) + 600.0)
    return bounds


@dataclass
class AbcGridRow:
    """Одна геометрическая строка таблицы АВС: только ячейки 1…5."""

    page: int
    c1: str
    c2: str
    c3: str
    c4: str
    c5_raw: str
    c5_qty: float | None
    raw_joined: str

    def pos_head(self) -> str:
        return _normalize_re_pos_line(_norm(f"{self.c1} {self.c2}"))


def _row_desc_probe(row: AbcGridRow) -> str:
    """
    Текст строки для эвристик подзаголовков: склейка кол.1–3.
    Баннер «Прочие работы» часто режется между кол.2 и 3 — брать только c3 ломало
    распознавание («работы» < 8 символов и не совпадает с RE_SECTION).
    Если в ячейках короткий обломок при длинном raw_joined — берём raw (типично цены в склейке).
    """
    merged = _norm(f"{row.c1} {row.c2} {row.c3}".strip())
    raw = _norm(row.raw_joined or "")
    if not merged:
        return raw
    if not raw:
        return merged
    if len(merged) < 12 and len(raw) > len(merged) + 10:
        return raw
    return merged


def _squeeze_embedded_section_title(title: str) -> str:
    """Из длинной склеённой строки таблицы вытащить «ПРОЧИЕ РАБОТЫ», если фраза есть внутри."""
    t = _norm(title)
    m = re.search(r"(?i)\b(ПРОЧИЕ\s+РАБОТЫ)\b", t)
    if m:
        frag = _norm(m.group(1))
        if len(t) > len(frag) + 8:
            return frag
    return t


def _iter_grid_rows_pdfplumber(pdf: Any) -> list[AbcGridRow]:
    out: list[AbcGridRow] = []
    bounds: list[float] | None = None
    for pno, page in enumerate(pdf.pages, start=1):
        words = page.extract_words() or []
        by_y: dict[float, list[dict]] = {}
        for w in words:
            k = _word_line_key(w)
            by_y.setdefault(k, []).append(w)
        for yk in sorted(by_y.keys()):
            ws = by_y[yk]
            hb = _header_column_bounds(ws)
            if hb and len(hb) >= 6:
                bounds = hb
            parts: list[str] = []
            for ww in sorted(ws, key=lambda x: (float(x["top"]), float(x["x0"]))):
                t = ww.get("text") or ""
                if t:
                    parts.append(t)
            raw = _norm(" ".join(parts))
            if not raw:
                continue
            if not bounds or len(bounds) < 6:
                out.append(
                    AbcGridRow(
                        page=pno,
                        c1="",
                        c2="",
                        c3=raw,
                        c4="",
                        c5_raw="",
                        c5_qty=None,
                        raw_joined=raw,
                    )
                )
                continue
            c1 = _cell_text_from_words(ws, bounds[0], bounds[1])
            c2 = _cell_text_from_words(ws, bounds[1], bounds[2])
            col_words = _split_row_words_by_columns(ws, bounds)
            c3 = _multiline_text_from_words(col_words[2])
            if len(col_words[2]) > 3:
                _log_name_debug(
                    "c3_words",
                    word_count=len(col_words[2]),
                    c3=c3,
                )
            c4 = _cell_text_from_words(ws, bounds[3], bounds[4])
            c5t = _cell_text_from_words(ws, bounds[4], bounds[5])
            q5 = _parse_qty_cell(c5t)
            out.append(
                AbcGridRow(
                    page=pno,
                    c1=c1,
                    c2=c2,
                    c3=c3,
                    c4=c4,
                    c5_raw=c5t,
                    c5_qty=q5,
                    raw_joined=raw,
                )
            )
    return out


def _strip_price_tail_line(n: str) -> str:
    n = _norm(n)
    if not n:
        return n
    dec_token = r"(?:\d{1,3}(?:\s\d{3})*[.,]\d{1,3}|\d+[.,]\d{1,3})"
    m = re.search(
        rf"(?i)^(?P<head>.+?)\s+{dec_token}\s+{dec_token}\s+",
        n,
    )
    if m:
        return _norm(m.group("head"))
    return n


def _strip_price_tail(name: str) -> str:
    if not name:
        return name
    if "\n" not in name:
        return _strip_price_tail_line(name)
    lines = name.split("\n")
    lines[-1] = _strip_price_tail_line(lines[-1])
    return _soft_norm("\n".join(lines))


def _name_from_pos_raw_joined(raw: str) -> str:
    """
    Полное наименование из склеенной строки позиции: после п/п и шифра всё,
    что до НР/СП или типичной строки сумм (в той же ячейке).
    """
    if not (raw or "").strip():
        return ""
    s = _norm(raw)
    nps = _normalize_re_pos_line(s)
    m = _match_position_head(nps)
    if not m:
        return ""
    tail = (m.group(3) or "").strip()
    if not tail:
        return ""
    tail = re.split(
        r"(?i)(?=\s*НР\s*[-–—]\s*\d+\s*%)",
        tail,
        maxsplit=1,
    )[0]
    tail = _strip_price_tail(
        _soft_norm(tail),
    )
    return _soft_norm(tail)


def _is_abc_price_row(raw: str) -> bool:
    """Строка вида «14485,17 4655,52 …» — начало блока стоимостей."""
    s = _norm(raw)
    if not s:
        return False
    return bool(
        re.match(
            r"^(?:\d{1,3}(?:\s\d{3})*[.,]\d{1,3}|\d+[.,]\d{1,3})\s+"
            r"(?:\d{1,3}(?:\s\d{3})*[.,]\d{1,3}|\d+[.,]\d{1,3})\b",
            s,
        )
    )


def _is_abc_nr_percent_row(raw: str) -> bool:
    """
    Строка накладных в смете АВС: «НР - 72%» или лат. «HP» в PDF, часто с «СП - 8%».
    Пока строка не распознана, merge продолжений позиции затягивает хвост в наименование.
    """
    s = _norm(raw or "")
    if not s:
        return False
    if len(s) > 160:
        return False
    # Кириллица НР или латиница HP (подмена шрифта)
    nr_or_hp = r"(?:НР|HP)"
    if re.match(rf"^(?:{nr_or_hp})\s*[-–—]\s*\d+\s*%", s):
        return True
    if re.search(
        rf"(?:{nr_or_hp})\s*[-–—]\s*\d+\s*%\s*[;,]?\s*(?:СП|CP)\s*[-–—]\s*\d+\s*%",
        s,
    ):
        return True
    return False


_SERVICE_METADATA_LEADING = (
    r"(?i)^РСНБ\s+РК\s*\d{4}(?:\s*г\.?)?\s*",
    r"(?i)^Кзтр\s+и\s*Кэм\s*=\s*[\d.,]+\s*",
    r"(?i)^Кзтр\s*=\s*[\d.,]+(?:\s*[;,]\s*)?",
    r"(?i)^Кэм\s*=\s*[\d.,]+\s*",
    r"(?i)^ТЧ\s+\d+\s+табл\.\s*\d+\s*",
    r"(?i)^п\.\d+\.\d+(?:\s+Кэм\s*=\s*[\d.,]+)?\s*",
    r"(?i)^Изм\.\s*и\s*доп\.\s*вып\.?\s*\d*\s*",
)


def _is_pure_service_metadata_line(line: str) -> bool:
    """Строка целиком — служебная метадата col.2 (ТЧ, п.3.31, РСНБ…)."""
    t = _norm(line)
    if not t:
        return True
    if re.fullmatch(r"\d+-\d+-\d+(?:'[^']*')*", re.sub(r"\s+", "", t)):
        return True
    if re.fullmatch(
        r"(?i)(?:РСНБ\s+РК\s*\d{4}(?:\s*г\.?)?|"
        r"Кзтр\s+и\s*Кэм\s*=\s*[\d.,]+|"
        r"Кзтр\s*=\s*[\d.,]+|"
        r"Кэм\s*=\s*[\d.,]+|"
        r"ТЧ\s+\d+\s+табл\.\s*\d+|"
        r"п\.\d+\.\d+(?:\s+Кэм\s*=\s*[\d.,]+)?)",
        t,
    ):
        return True
    return False


def _strip_service_metadata_from_line(line: str) -> str:
    """Убрать служебные префиксы, случайно попавшие в col.3."""
    s = line.strip()
    if not s:
        return ""
    changed = True
    while changed and s:
        changed = False
        for pat in _SERVICE_METADATA_LEADING:
            s2 = re.sub(pat, "", s).strip()
            if s2 != s:
                s = s2
                changed = True
    return s


def _is_name_unit_suffix_line(line: str) -> bool:
    """Короткие хвосты единиц: «м/.», «/20 м/.» — не трогать cleaner'ом."""
    s = line.strip()
    if not s:
        return False
    if re.fullmatch(r"(?i)/?\d*\s*м/\.?", s):
        return True
    if re.fullmatch(r"(?i)м/\.", s):
        return True
    if len(s) <= 12 and re.search(r"(?i)/\d+\s*м/\.?$", s):
        return True
    return False


def _merge_split_unit_suffix_lines(lines: list[str]) -> list[str]:
    """«… /20» + «м/.» → «/20 м/.» как в оригинальной смете."""
    if len(lines) < 2:
        return lines
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if (
            i + 1 < len(lines)
            and re.search(r"/\d+\s*$", line)
            and re.fullmatch(r"(?i)м/\.", lines[i + 1].strip())
        ):
            out.append(f"{line.rstrip()} {lines[i + 1].strip()}")
            i += 2
            continue
        out.append(line)
        i += 1
    return out


def _continuation_name_fragment(nxt: AbcGridRow) -> str:
    """Текст продолжения наименования — только col.3, без метаданных col.2."""
    raw_t3 = _soft_norm(nxt.c3)
    if not raw_t3:
        _log_name_debug(
            "cont_skip_empty",
            c2=nxt.c2,
            c3=nxt.c3,
        )
        return ""
    lines_out: list[str] = []
    removed: list[str] = []
    for line in raw_t3.split("\n"):
        cleaned = _strip_service_metadata_from_line(line)
        if not cleaned:
            if line.strip():
                removed.append(line.strip())
            continue
        if _is_pure_service_metadata_line(cleaned):
            removed.append(cleaned)
            continue
        lines_out.append(cleaned)
    if removed:
        _log_name_debug(
            "cont_service_removed",
            removed=removed,
            c2=nxt.c2,
        )
    if not lines_out:
        return ""
    return _soft_norm("\n".join(lines_out))


def _abc_merge_name_from_cells(r: AbcGridRow) -> str:
    ph = r.pos_head()
    m = _match_position_head(ph)
    prefix = _soft_norm(
        m.group(3) or "",
    ) if m else ""
    c3 = _soft_norm(
        r.c3,
    )
    if c3:
        c3_lines = []
        for line in c3.split("\n"):
            cl = _strip_service_metadata_from_line(line)
            if cl and not _is_pure_service_metadata_line(cl):
                c3_lines.append(cl)
        c3 = _soft_norm("\n".join(c3_lines))
    if prefix and c3:
        c3_first = c3.split("\n", 1)[0]
        if c3.startswith(prefix) or c3_first.startswith(prefix):
            return c3
        pref = prefix.rstrip(".")
        if pref and c3_first.startswith(pref):
            return c3
        return _soft_norm(
            f"{prefix} {c3}",
        )
    return prefix or c3


def _strip_abc_branding_and_column_tail_line(name: str) -> str:
    """
    Мусор из шапки/колонтитула АВС: «(Программный) комплекс АВС (редакция…)»,
    цепочки «1 2 3 …» и короткие хвосты «2 3» после точки/скобки.
    """
    if _is_name_unit_suffix_line(name):
        return name.strip()
    n = _norm(name)
    if not n:
        return n
    n = re.sub(
        r"(?i)\s*(?:программный\s+)?комплекс\s+АВС\s*(?:\([^)]{0,160}\))?",
        " ",
        n,
    )
    n = re.sub(
        r"(?i)\s*редакция\s+[\d.]+\s*",
        " ",
        n,
    )
    n = re.sub(r"\b(?:\d{1,2}\s+){4,}\d{1,2}\b", " ", n)
    for _ in range(6):
        n2 = re.sub(
            r"(?<=[\.\)а-яё»\"·])\s+(?:\d{1,2}(?:\s+\d{1,2}){1,11})\s*$",
            "",
            n,
            flags=re.I,
        )
        n2 = re.sub(
            r"(?<=[а-яёa-z])\.?\s+(?:\d{1,2}(?:\s+\d{1,2}){1,11})\s*$",
            "",
            n2,
            flags=re.I,
        )
        n2 = _norm(n2)
        if n2 == n:
            break
        n = n2
    return n


def _strip_abc_branding_and_column_tail(name: str) -> str:
    if not name:
        return name
    if "\n" not in name:
        return _strip_abc_branding_and_column_tail_line(name)
    lines = [
        _strip_abc_branding_and_column_tail_line(line)
        for line in name.split("\n")
    ]
    return _soft_norm("\n".join(line for line in lines if line))


def _finalize_name_col3_last_line(n: str, unit: str, qty: float | None) -> str:
    if _is_name_unit_suffix_line(n):
        return re.sub(r"[ \t]+", " ", n).strip()
    n = _strip_price_tail(n)
    n = re.sub(r"(?i)\s+ПРОЧИЕ\s+РАБОТЫ\s*$", "", n)
    n = re.sub(
        r"(?i)\s+Монолитный\s+(?:литальный|л[ие]кальный)\s+блок\s*\.?\s*$",
        "",
        n,
    )
    n = re.sub(r"(?i)(?<=[а-яё.)])\s+т\s+[\d\s,./-]+$", "", n)
    n = re.sub(
        r"(?i)\s+т[\s·]*км\s+[\d\s,./-]+(?:\s+--[\d\s,./-]*)*\s*$",
        "",
        n,
    )
    n = re.sub(r"(?<=\.)\s+\d{1,3}\s*$", "", n)
    u = _norm(_collapse_m_units(unit))
    if u and qty is not None and qty > 0:
        ql = str(qty).rstrip("0").rstrip(".") if isinstance(qty, float) else str(qty)
        variants = {
            ql,
            str(qty),
            str(qty).replace(".", ","),
            f"{qty:.1f}".replace(".", ","),
            f"{qty:.2f}".replace(".", ","),
        }
        nl = n.lower()
        ul = u.lower()
        for qv in variants:
            if not qv:
                continue
            suf = f"{ul} {qv.lower()}"
            if nl.endswith(suf):
                n = n[: -len(suf)].rstrip(" ,.;")
                nl = n.lower()
                break
        for qv in variants:
            suf = f"{u} {qv}".lower()
            if nl.endswith(suf):
                n = n[: -len(suf)].rstrip(" ,.;")
                break
    if u:
        nl = n.lower()
        ul = u.lower()
        if nl.endswith(ul):
            n = n[: -len(u)].rstrip(" ,.;")
    return re.sub(r"[ \t]+", " ", n).strip()


def _finalize_name_col3(name: str, unit: str, qty: float | None) -> str:
    """
    Наименование — только кол.3. Убираем типичные хвосты и дубли ед./кол-ва.
    Сохраняет переносы строк из PDF.
    """
    n = _soft_norm(_collapse_m_units_multiline(name))
    if not n:
        return n
    while True:
        n2 = re.sub(
            r"^--\s*[\d\s.,]+(?:\s*[–-]\s*[\d\s.,]+)?\s*--\s*",
            "",
            n,
        )
        if n2 == n:
            break
        n = _soft_norm(n2)
    lines = n.split("\n")
    cleaned: list[str] = []
    for line in lines:
        line = _strip_service_metadata_from_line(line)
        if not line or _is_pure_service_metadata_line(line):
            continue
        line = re.sub(r"(?:^|\s)СП\s*-\s*\d+\s*%\s*", " ", line, flags=re.I)
        line = re.sub(r"Страниц\s*-\s*\d+", "", line, flags=re.I)
        if not _is_name_unit_suffix_line(line):
            line = _strip_abc_branding_and_column_tail_line(line)
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            cleaned.append(line)
    cleaned = _merge_split_unit_suffix_lines(cleaned)
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        n = _finalize_name_col3_last_line(cleaned[0], unit, qty)
    else:
        head = "\n".join(cleaned[:-1])
        tail = _finalize_name_col3_last_line(cleaned[-1], unit, qty)
        n = f"{head}\n{tail}" if tail else head
    if re.search(r"(?i)диаметром\s+от\s+\d+\s+до\s+\d+", n) and not re.search(
        r"(?i)диаметром\s+от\s+\d+\s+до\s+\d+.*\bмм\b",
        _norm(n),
    ):
        n = re.sub(
            r"(?i)(диаметром\s+от\s+\d+\s+до\s+)(\d+)\s*\.?\s*$",
            r"\1\2 мм.",
            n,
            flags=re.M,
        )
    return _flatten_name_display(n)


_SECTION_MARKERS_IN_MIXED_LSR_LINE = (
    r"\bКАНАЛ\b",
    r"\bП\s+КАНАЛ\b",
    r"\bДЮКЕР\b",
    r"\bДЕМОНТАЖНЫЕ\s+РАБОТЫ\b",
    r"\bСТРОИТЕЛЬНЫЕ\s+РАБОТЫ\b",
    r"\bМОНТАЖНЫЕ\s+РАБОТЫ\b",
    r"\bБЕТОННЫЕ\s+РАБОТЫ\b",
    r"\bПРОЧИЕ\s+РАБОТЫ\b",
    r"\bМонолитный\s+(?:литальный|л[ие]кальный)\s+блок\b",
    r"\bМонолитный\s+оголовок\b",
    r"\bМонолитный\s+ж\s*/\s*б\s+колодец\b",
    r"\bМонолитный\s+железобетонный\s+колодец\b",
    r"\bМонолитная\s+диафрагма\b",
    r"\bЗуб\s+монолитный\b",
    r"\bПРОЕЗЖАЯ\s+ЧАСТЬ\b",
    r"\bПРОЕЗДНАЯ\s+ЧАСТЬ\b",
    r"\bЗатвор\s+(?:[А-Яа-яЁё]{2}|[A-Za-z]{2})\b",
    r"\bЗЕМЛЯНЫЕ\s+РАБОТЫ\b",
    r"\bЛОТКОВЫЙ\s+КАНАЛ\b",
    r"\bВОДОВЫПУСК\b",
    r"\bКОНЦЕВОЙ\s+КОЛОДЕЦ\b",
    r"\bПОВОРОТНЫЙ\s+КОЛОДЕЦ\b",
)


def _section_title_from_lsr_header(ln: str) -> str | None:
    """
    «ЛОКАЛЬНАЯ СМЕТА № 1-1 КАНАЛ 4-К-1-1. ДЕМОНТАЖНЫЕ РАБОТЫ (ГР-29)»
    → «КАНАЛ 4-К-1-1. ДЕМОНТАЖНЫЕ РАБОТЫ (ГР-29)».
    """
    if not re.search(
        r"локальн",
        ln,
        re.I,
    ):
        return None
    best: tuple[int, str] | None = None
    for pat in _SECTION_MARKERS_IN_MIXED_LSR_LINE:
        m = re.search(
            pat,
            ln,
            re.I,
        )
        if not m:
            continue
        frag = _norm(
            ln[
                m.start() :
            ],
        )
        if (
            best is None
            or m.start() < best[0]
        ):
            best = (
                m.start(),
                frag,
            )
    return best[1] if best else None


def _sec_tail_meaningful_for_merge(sec_tail: str) -> bool:
    """
    Не дописывать к подзаголовку только «ЛОКАЛЬНАЯ СМЕТА № …» без вида работ —
    иначе получается «ЛОКАЛЬНАЯ СМЕТА № 2-1-2 ЗЕМЛЯНЫЕ РАБОТЫ» вместо «ЗЕМЛЯНЫЕ РАБОТЫ».
    """
    t = (sec_tail or "").strip()
    if len(t) < 10:
        return False
    if re.match(
        r"(?i)^локальн\w*\s+смет\w*\s+№\s*[\d.\-\s]+\s*$",
        t,
    ):
        return False
    return True


def _is_section_line(ln: str) -> bool:
    if _section_title_from_lsr_header(
        ln,
    ):
        return True
    l = ln.lower()
    if "локальн" in l:
        return False
    if re.match(r"^1\s+2\s+3", ln) or len(ln) < 8:
        return False
    st = ln.strip()
    if _match_position_head(st):
        return False
    if RE_SECTION.match(st):
        return True
    if re.search(r"\(ГР-\d+\)", ln):
        if len(ln) > 220:
            return False
        if re.match(r"^\d{1,4}\.?\s+\d+-\d+-\d+", _normalize_re_pos_line(ln)):
            return False
        return True
    # Баннер «ВОДОВЫПУСК ИЗ ЛОТКА (30 ШТ), ГР-33» — часто без скобок вокруг ГР-NN
    if re.search(r"\bГР-\d+\s*$", st.rstrip(". "), re.I):
        if len(ln) > 220:
            return False
        if _match_position_head(_normalize_re_pos_line(st)):
            return False
        return True
    stn = _norm(ln)
    if len(stn) > 100:
        head_snip = _normalize_re_pos_line(stn[:180])
        if not _match_position_head(head_snip):
            tl = re.sub(r"^[\d\s·.\-]{0,100}", "", stn).strip()
            if re.match(r"(?i)^ПРОЧИЕ\s+РАБОТЫ\b", tl):
                return True
            if re.match(r"(?i)^Монолитная\s+диафрагма\b", tl):
                return True
            if re.match(r"(?i)^Зуб\s+монолитный\b", tl):
                return True
            if re.match(
                r"(?i)^Монолитный\s+ж\s*/\s*б\s+колодец\b",
                tl,
            ):
                return True
            if re.match(
                r"(?i)^Монолитный\s+железобетонный\s+колодец\b",
                tl,
            ):
                return True
            if re.match(r"(?i)^ПРОЕЗЖАЯ\s+ЧАСТЬ\b", tl):
                return True
            if re.match(r"(?i)^ПРОЕЗДНАЯ\s+ЧАСТЬ\b", tl):
                return True
            if re.match(
                r"(?i)^Затвор\s+(?:[А-Яа-яЁё]{2}|[A-Za-z]{2})\s+\d+\s*[ХХххxX×]\s*\d+",
                tl,
            ):
                return True
        return False
    tail = re.sub(r"^[\d\s·.]{0,24}", "", stn, flags=re.I).strip()
    if not _match_position_head(st):
        if re.match(r"(?i)^КОНЦЕВОЙ\s+КОЛОДЕЦ\b", tail):
            return True
        if re.match(r"(?i)^ПОВОРОТНЫЙ\s+КОЛОДЕЦ\b", tail):
            return True
        if re.match(r"(?i)^ЗЕМЛЯНЫЕ\s+РАБОТЫ\b", tail):
            return True
        if re.match(r"(?i)^ПРОЧИЕ\s+РАБОТЫ\b", tail):
            return True
        if re.match(r"(?i)^БЕТОННЫЕ\s+РАБОТЫ\s*$", tail):
            return True
        if re.match(r"(?i)^Монолитный\s+оголовок\s*\.?\s*$", tail):
            return True
        if _RE_MONOLITH_CAST_BLOCK_LINE.match(tail):
            return True
        if re.match(r"(?i)^Монолитная\s+диафрагма\b", tail):
            return True
        if re.match(r"(?i)^Зуб\s+монолитный\b", tail):
            return True
        if re.match(
            r"(?i)^Монолитный\s+ж\s*/\s*б\s+колодец(?:\s*\.)?\s*$",
            tail,
        ):
            return True
        if re.match(
            r"(?i)^Монолитный\s+железобетонный\s+колодец(?:\s*\.)?\s*$",
            tail,
        ):
            return True
        if re.match(r"(?i)^ПРОЕЗЖАЯ\s+ЧАСТЬ\b", tail):
            return True
        if re.match(r"(?i)^ПРОЕЗДНАЯ\s+ЧАСТЬ\b", tail):
            return True
        if re.match(
            r"(?i)^Затвор\s+(?:[А-Яа-яЁё]{2}|[A-Za-z]{2})\s+\d+\s*[ХХххxX×]\s*\d+(?:\s*\.)?\s*$",
            tail,
        ):
            return True
    return False


def _is_position_start(row: AbcGridRow) -> bool:
    h = row.pos_head()
    return bool(_match_position_head(h))


def _pos_cipher_cell(row: AbcGridRow) -> str:
    """Шифр из кол.1–2 (вторая группа RE_POS / Прайслист), для уникальности дедупа."""
    ph = _normalize_re_pos_line(row.pos_head())
    m = _match_position_head(ph)
    if not m:
        return ""
    g2 = _norm(m.group(2) or "")
    g2_compact = g2.replace(" ", "")
    if re.match(r"^\d+-\d+-\d+", g2_compact):
        return g2_compact
    if re.search(r"(?i)прайс", g2):
        return "Прайслист"
    return g2_compact


def _pos_line_no(row: AbcGridRow) -> str:
    """№ п/п позиции (первая группа RE_POS / Прайслист)."""
    ph = _normalize_re_pos_line(row.pos_head())
    m = _match_position_head(ph)
    if not m:
        return ""
    return _norm(m.group(1) or "").rstrip(".")


def _pos_line_no_int(row: AbcGridRow) -> int | None:
    s = _pos_line_no(row)
    if not s:
        return None
    try:
        return int(str(s).split(".", 1)[0])
    except (TypeError, ValueError):
        return None


def _peek_next_position_line_no(rows: list[AbcGridRow], start_i: int) -> int | None:
    """Следующий № п/п после текущей строки (для отличия колонтитула от новой сметы)."""
    n = len(rows)
    j = start_i + 1
    while j < n:
        row = rows[j]
        if _is_position_start(row):
            return _pos_line_no_int(row)
        raw_j = row.raw_joined or ""
        if _is_end(raw_j, raw_j.lower(), None):
            break
        j += 1
    return None


def _is_razdel_line(s: str) -> bool:
    return bool(RE_RAZDEL.match(_norm(s)))


def _lookahead_qty_unit(
    rows: list[AbcGridRow], start_i: int
) -> tuple[float | None, str]:
    n = len(rows)
    for j in range(start_i + 1, min(start_i + 6, n)):
        if _is_position_start(rows[j]):
            break
        q = rows[j].c5_qty
        if q is not None and q > 0:
            u = _norm(_collapse_m_units(rows[j].c4))
            return q, u
    return None, ""


def _infer_unit_from_cell_text(*parts: str) -> str:
    """
    Кол.4 иногда пустая при съезженной геометрии (номер/шифр попали не в те
    колонки). Ищем м²/м³/т и т.д. в склейке строки или в наименовании.
    """
    blob = _norm(_collapse_m_units(" ".join(p for p in parts if p)))
    if not blob:
        return ""
    checks = (
        (r"(?i)т[\s·]*км", "т·км"),
        (r"(?i)\bм3\b|м³", "м3"),
        (r"(?i)\bм2\b|м²", "м2"),
        (r"(?i)\bшт\b", "шт"),
        (r"(?i)\bкм\b", "км"),
        (r"(?i)(?<![а-яёa-z])т(?=\s|$|и|,|\.)", "т"),
    )
    for pat, u in checks:
        if re.search(pat, blob):
            return u
    return ""


def _merge_continuation_rows(rows: list[AbcGridRow]) -> list[AbcGridRow]:
    """
    Многострочное наименование АВС: до строки с двумя суммами или «НР - …%».
    Учитывается текст в кол.2 (продолжение у шифра) и строки РСНБ/Кзтр перед ценой.
    """
    if not rows:
        return rows
    out: list[AbcGridRow] = []
    i = 0
    n = len(rows)
    while i < n:
        r = rows[i]
        if not _is_position_start(r):
            out.append(r)
            i += 1
            continue
        j = i + 1
        name_acc = _abc_merge_name_from_cells(
            r,
        ) or _name_from_pos_raw_joined(
            r.raw_joined or "",
        )
        _log_name_debug(
            "merge_start",
            pos=_pos_line_no(r),
            raw_c3=r.c3,
            name_acc=name_acc,
        )
        acc_c4 = _norm(r.c4)
        acc_q = r.c5_qty
        acc_c5t = r.c5_raw
        merged_raw = r.raw_joined or ""
        while j < n:
            nxt = rows[j]
            if _is_position_start(nxt):
                break
            rjn = nxt.raw_joined or ""
            if _is_section_line(rjn) or _is_section_line(_row_desc_probe(nxt)):
                break
            if _is_abc_price_row(rjn):
                break
            if _is_abc_nr_percent_row(rjn) or _is_abc_nr_percent_row(
                _norm(nxt.c3 or ""),
            ):
                break
            frag = _continuation_name_fragment(nxt)
            if frag:
                name_acc = _join_name_lines(name_acc, frag) if name_acc else frag
                _log_name_debug(
                    "merge_cont",
                    pos=_pos_line_no(r),
                    frag=frag,
                    merged=name_acc,
                )
            if acc_q is None or acc_q <= 0:
                if nxt.c5_qty is not None and nxt.c5_qty > 0:
                    acc_q = nxt.c5_qty
                    acc_c4 = _norm(nxt.c4) or acc_c4
                    acc_c5t = nxt.c5_raw or acc_c5t
            merged_raw = _norm(f"{merged_raw} {rjn}")
            j += 1
        _log_name_debug(
            "merge_done",
            pos=_pos_line_no(r),
            final=name_acc,
        )
        out.append(
            AbcGridRow(
                page=r.page,
                c1=r.c1,
                c2=r.c2,
                c3=name_acc,
                c4=acc_c4 or r.c4,
                c5_raw=acc_c5t,
                c5_qty=acc_q,
                raw_joined=merged_raw,
            )
        )
        i = j if j > i else i + 1
    return out


def parse_pdf_grid_to_items(data: bytes, dedupe: set) -> list[dict[str, Any]]:
    """Разбор PDF АВС: кол.3 — наименование, 4 — ед. изм., 5 — количество."""
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        grid = _iter_grid_rows_pdfplumber(pdf)
    grid = _merge_continuation_rows(grid)
    out: list[dict[str, Any]] = []
    after_lsr_footer = False
    last_pos_no: int | None = None
    in_lsr = False
    section: str | None = None
    lsr_id: str | None = None
    object_name: str | None = None
    auto_razdel = 1
    pending_razdel: str | None = None
    last_zemlyanye_section: str | None = None
    last_heading_line: str | None = None
    prev_raw_low: str | None = None

    def _detect_lsr_footer_in_row(raw_ln: str, probe_ln: str, low_probe: str) -> bool:
        """Окончание таблицы ЛСР перед следующим файлом («РЕСУРСНАЯ СМЕТА» и т.д.)."""
        blob_l = _norm(f"{raw_ln or ''} {probe_ln or ''}").lower()
        lr = (raw_ln or "").lower()
        if "итого по смете" in lr or "итого по смете" in blob_l:
            return True
        if low_probe and "итого по смете" in low_probe:
            return True
        if re.search(r"(?is)итого\s+по\s+смете", blob_l):
            return True
        return False

    def _remember_carriageway_ctx(sec: str | None) -> None:
        """
        Сохраняем секцию колодца/земляных работ для строки «Проезжая часть»:
        в PDF между позициями часто вставляют заголовок следующего объекта (Дюкер),
        из‑за чего позиции проезжей оказываются под чужим ГР до нормального подвала сметы.
        """
        nonlocal last_zemlyanye_section
        if not sec:
            return
        tail = sec.split("|", 1)[-1].strip() if "|" in sec else sec.strip()
        if re.match(r"(?i)^ДЮКЕР\b", tail):
            return
        if _ZEMLYANYE_SECTION_SUFFIX in sec:
            last_zemlyanye_section = sec
            return
        if re.search(r"(?i)ПОВОРОТНЫЙ\s+КОЛОДЕЦ", tail) or re.search(
            r"(?i)КОНЦЕВОЙ\s+КОЛОДЕЦ",
            tail,
        ):
            last_zemlyanye_section = sec

    def _emit_subsection_row(body: str, pending: str | None) -> None:
        """Подзаголовок группы работ — отдельная строка в таблице сметы."""
        nonlocal pending_razdel, last_heading_line
        if after_lsr_footer:
            return
        if not section or not body or not str(body).strip():
            return
        merged = _norm(f"{pending}  {body}" if pending else body)
        if not merged:
            return
        name_u = merged.upper()[:ESTIMATE_ITEM_NAME_MAX_LENGTH]
        # В одном файле локальная смета часто продублирована (тираж/выборка страниц).
        # Ключ только по тексту секции склеивает все повторы и выкидывает баннеры
        # («ПРОЧИЕ РАБОТЫ», «ЗЕМЛЯНЫЕ РАБОТЫ») во втором и следующих блоках той же формы.
        key = ("hdr", section[:255], name_u[:2000], i)
        if key in dedupe:
            return
        dedupe.add(key)
        out.append(
            {
                "section": section[:255],
                "name": name_u,
                "unit": "—",
                "quantity": 0.0,
                "is_subsection_header": True,
            }
        )
        if lsr_id and (
            "ЗЕМЛЯНЫЕ" in name_u
            or "КОЛОДЕЦ" in name_u
            or "ДЮКЕР" in name_u
        ):
            _remember_carriageway_ctx(_format_section(lsr_id, merged)[:255])
        pending_razdel = None
        last_heading_line = name_u

    n = len(grid)
    i = 0
    while i < n:
        row = grid[i]
        raw = row.raw_joined or ""
        probe = _row_desc_probe(row)
        low = probe.lower()
        low_raw = raw.lower()
        if _detect_lsr_footer_in_row(raw, probe, low):
            after_lsr_footer = True
        if _is_lsr_start(low_raw) or _is_lsr_start(low):
            in_lsr = True
        if not in_lsr:
            prev_raw_low = low_raw
            i += 1
            continue
        if _is_end(raw, low_raw, prev_raw_low):
            in_lsr = False
            section = None
            pending_razdel = None
            object_name = None
            auto_razdel = 1
            last_zemlyanye_section = None
            after_lsr_footer = False
            last_pos_no = None
            prev_raw_low = low_raw
            i += 1
            continue
        if _is_noise_line(low) and len(probe) < 80:
            if "итого по смете" in low_raw or (
                probe and "итого по смете" in low
            ):
                after_lsr_footer = True
            prev_raw_low = low_raw
            i += 1
            continue
        if re.match(r"^всего\s*$|^итого\s*$", low.strip()):
            prev_raw_low = low_raw
            i += 1
            continue
        if (
            RE_TABLE_COLS.match(raw.strip() if raw else "")
            and "шифр" not in low_raw
        ):
            prev_raw_low = low_raw
            i += 1
            continue
        skip_hdr = (
            bool(
                re.match(
                    r"^1\s+2\s+3|^№\s*п/п|^№\s*шифр|^наименование работ|^шифр норм",
                    low,
                )
            )
            or bool(re.search(r"шифр норм,", low))
        )
        if not skip_hdr:
            skip_hdr = (
                bool(
                    re.match(
                        r"^1\s+2\s+3|^№\s*п/п|^№\s*шифр|^наименование работ|^шифр норм",
                        low_raw,
                    )
                )
                or bool(re.search(r"шифр норм,", low_raw))
            )
        if skip_hdr:
            prev_raw_low = low_raw
            i += 1
            continue
        comb_hdr = _norm(f"{raw} {probe}")
        if re.search(r"(?i)\bПРОЕЗЖАЯ\s+ЧАСТЬ\b", comb_hdr) or re.search(
            r"(?i)\bПРОЕЗДНАЯ\s+ЧАСТЬ\b",
            comb_hdr,
        ):
            # Раньше подменяли section на последнюю «земляную» — позиции уезжали в другой раздел UI.
            # Нужна строка-подзаголовок и те же позиции остаются в текущей ЛСР.
            if section:
                _emit_subsection_row("ПРОЕЗЖАЯ ЧАСТЬ", None)
            prev_raw_low = low_raw
            i += 1
            continue
        m_obj = RE_NAIM_OBJ.match(_norm(probe))
        if not m_obj and raw:
            m_obj = RE_NAIM_OBJ.match(_norm(raw))
        if m_obj:
            object_name = m_obj.group(1).strip()[:200] or object_name
            prev_raw_low = low_raw
            i += 1
            continue
        if "локальн" in low_raw and "смет" in low_raw:
            m_no = RE_LSR_NO.search(raw)
            nid: str | None = None
            if m_no:
                nid = (m_no.group(1) or "").strip()[:32]
            if not nid:
                ml = RE_LSR_LEADING_NO.match(_norm(raw))
                if ml:
                    nid = (ml.group(1) or "").strip()[:32]
            if nid:
                if lsr_id and nid != lsr_id:
                    next_no = _peek_next_position_line_no(grid, i)
                    if (
                        last_pos_no is not None
                        and next_no is not None
                        and next_no > last_pos_no
                    ):
                        # Колонтитул «Локальная смета № …» на следующей странице:
                        # нумерация позиций продолжается (37 после 36) — это та же смета.
                        prev_raw_low = low_raw
                        i += 1
                        continue
                if lsr_id != nid:
                    auto_razdel = 1
                    last_zemlyanye_section = None
                    last_heading_line = None
                    after_lsr_footer = False
                    last_pos_no = None
                lsr_id = nid
                section = f"ЛОКАЛЬНАЯ СМЕТА № {nid}"[:255]
            sub_frag = _section_title_from_lsr_header(raw) or _section_title_from_lsr_header(
                probe,
            )
            if sub_frag:
                _emit_subsection_row(sub_frag.strip(), pending_razdel)
            prev_raw_low = low_raw
            i += 1
            continue
        nline = _norm(probe)
        m_raz = RE_RAZDEL.match(nline)
        if not m_raz and raw:
            m_raz = RE_RAZDEL.match(_norm(raw))
        if m_raz and in_lsr:
            rnum = m_raz.group(1)
            rtitle = m_raz.group(2).strip()
            pending_razdel = f"РАЗДЕЛ {rnum}. {rtitle}"[:200]
            try:
                auto_razdel = int(rnum) + 1
            except ValueError:
                pass
            prev_raw_low = low_raw
            i += 1
            continue
        sec_src = raw if _is_section_line(raw) else probe
        if _is_section_line(sec_src) and not _is_position_start(row):
            title = (
                _section_title_from_lsr_header(sec_src)
                or _section_title_from_lsr_header(probe)
                or sec_src.strip()
            )
            t_strip = title.strip()
            peek_advance = 0

            blobs_m = [_norm(sec_src), _norm(raw), _norm(probe), comb_hdr]
            for blob_in in blobs_m:
                if not blob_in:
                    continue
                m_nl = re.search(
                    r"(?is)^\s*БЕТОННЫЕ\s+РАБОТЫ\s*(?:\.?\s*\r?\n)+\s*(Монолитный\s+оголовок)\s*\.?",
                    blob_in,
                )
                if not m_nl:
                    m_nl = re.search(
                        r"(?i)БЕТОННЫЕ\s+РАБОТЫ[^\n\d]{0,120}?(Монолитный\s+оголовок)\s*\.?",
                        blob_in,
                    )
                if m_nl:
                    title = _norm(f"БЕТОННЫЕ РАБОТЫ {_norm(m_nl.group(1))}")
                    t_strip = title.strip()
                    break

            if (
                peek_advance == 0
                and re.match(r"(?i)^БЕТОННЫЕ\s+РАБОТЫ\s*$", t_strip)
                and i + 1 < n
            ):
                nrow = grid[i + 1]
                n_raw = nrow.raw_joined or ""
                n_probe = _row_desc_probe(nrow)
                ns_src = n_raw if _is_section_line(n_raw) else n_probe
                if _is_section_line(ns_src) and not _is_position_start(nrow):
                    nt = (
                        _section_title_from_lsr_header(ns_src)
                        or _section_title_from_lsr_header(n_probe)
                        or ns_src.strip()
                    ).strip()
                    if re.match(r"(?i)^Монолитный\s+оголовок\s*\.?\s*$", nt):
                        title = _norm(f"{t_strip} {nt}")
                        peek_advance = 1
            title = _squeeze_embedded_section_title(title.strip())
            t_strip = title
            pend = pending_razdel
            if pend:
                _emit_subsection_row(title.strip(), pend)
            elif (
                lsr_id
                and object_name
                and re.search(r"ЗЕМЛЯНЫЕ|ГР-", title, re.I)
                # Banner-like subsection titles ending with ", ГР-NN" must stay intact (not merged into РАЗДЕЛ …).
                and not re.search(r"\bГР-\d+\s*$", title.strip(), re.I)
            ):
                sec_tail_gr = (
                    section.split("|", 1)[-1].strip()
                    if section and "|" in section
                    else ""
                )
                if sec_tail_gr and re.search(r"\(ГР-\d+\)", title):
                    body = _norm(f"{sec_tail_gr} {title.strip()}")[:220]
                else:
                    body = f"РАЗДЕЛ {auto_razdel}. {object_name}  {title}"
                    auto_razdel += 1
                _emit_subsection_row(body, None)
            else:
                sec_tail = (
                    section.split("|", 1)[-1].strip()
                    if section and "|" in section
                    else (section or "")
                )
                if (
                    last_heading_line
                    and "ДЮКЕР" in last_heading_line.upper()
                    and re.search(
                        r"^ЗЕМЛЯНЫЕ\s+РАБОТЫ",
                        title.strip(),
                        re.I,
                    )
                    and not re.search(
                        r"ЗЕМЛЯНЫЕ\s+РАБОТЫ",
                        last_heading_line,
                        re.I,
                    )
                ):
                    merged = _norm(f"{last_heading_line} {title.strip()}")[:220]
                    _emit_subsection_row(merged, None)
                else:
                    body = title.strip()
                    if (
                        sec_tail
                        and len(sec_tail) > 12
                        and _sec_tail_meaningful_for_merge(sec_tail)
                        and re.match(
                            r"(?i)^ЗЕМЛЯНЫЕ\s+РАБОТЫ\s*$",
                            body,
                        )
                        and not re.search(
                            r"ЗЕМЛЯНЫЕ\s+РАБОТЫ",
                            sec_tail,
                            re.I,
                        )
                    ):
                        body = _norm(f"{sec_tail} {body}")[:220]
                    if (
                        sec_tail
                        and len(sec_tail) > 12
                        and _sec_tail_meaningful_for_merge(sec_tail)
                        and re.match(
                            r"(?i)^ПРОЧИЕ\s+РАБОТЫ\s*$",
                            body,
                        )
                        and not re.search(
                            r"(?i)\bПРОЧИЕ\s+РАБОТЫ\b",
                            sec_tail,
                        )
                    ):
                        body = _norm(f"{sec_tail} {body}")[:220]
                    if (
                        sec_tail
                        and len(sec_tail) > 12
                        and _sec_tail_meaningful_for_merge(sec_tail)
                        and _RE_MONOLITH_CAST_BLOCK_LINE.match(body)
                        and not re.search(
                            r"(?i)\bМонолитный\s+(?:литальный|л[ие]кальный)\s+блок\b",
                            sec_tail,
                        )
                    ):
                        body = _norm(f"{sec_tail} {body}")[:220]
                    _emit_subsection_row(body, None)
            if peek_advance >= 1:
                prev_raw_low = (
                    grid[i + peek_advance].raw_joined or ""
                ).lower()
            else:
                prev_raw_low = low_raw
            i += 1 + peek_advance
            continue
        if _is_position_start(row):
            if after_lsr_footer:
                prev_raw_low = low_raw
                i += 1
                continue
            unit = _norm(_collapse_m_units(row.c4))
            qty = row.c5_qty
            if qty is None or qty <= 0:
                q2, u2 = _lookahead_qty_unit(grid, i)
                if q2 and q2 > 0:
                    qty = q2
                    if u2:
                        unit = u2
            name_src = _soft_norm(row.c3)
            if not name_src:
                name_src = _abc_merge_name_from_cells(
                    row,
                ) or _name_from_pos_raw_joined(
                    raw,
                )
            if not name_src:
                m = _match_position_head(row.pos_head())
                if m:
                    g3 = m.group(3) or ""
                    name_src = _strip_price_tail(_soft_norm(g3))
            if (not unit) and qty is not None and qty > 0:
                gu = _infer_unit_from_cell_text(
                    raw,
                    row.raw_joined or "",
                    name_src,
                )
                if gu:
                    unit = gu
            name_f = _finalize_name_col3(name_src, unit, qty)
            _log_name_debug(
                "final",
                pos=_pos_line_no(row),
                raw_c3=row.c3,
                name_src=name_src,
                name_f=name_f,
                unit=unit,
                qty=qty,
            )
            if name_f and unit and qty is not None and qty > 0:
                cipher_k = _pos_cipher_cell(
                    row,
                ).replace(
                    " ",
                    "",
                )
                line_no = _pos_line_no(row)
                dedup = (
                    section,
                    line_no,
                    cipher_k,
                    name_f[:ESTIMATE_ITEM_NAME_MAX_LENGTH].lower(),
                    unit.lower(),
                    round(float(qty), 4),
                )
                if dedup not in dedupe:
                    dedupe.add(dedup)
                    out.append(
                        {
                            "section": section,
                            "name": name_f[:ESTIMATE_ITEM_NAME_MAX_LENGTH],
                            "unit": unit[:80],
                            "quantity": float(qty),
                            "pdf_pos_no": line_no,
                            "pdf_norm_code": cipher_k,
                        }
                    )
                    pno = _pos_line_no_int(row)
                    if pno is not None:
                        last_pos_no = pno
                    if re.search(
                        r"(?is)итого\s+по\s+смете",
                        (name_f or "").lower(),
                    ):
                        after_lsr_footer = True
        prev_raw_low = low_raw
        i += 1
    return out


def _regex_fallback(text: str, section: str | None, dedupe: set) -> list[dict[str, Any]]:
    out: list[dict] = []
    t = re.sub(r"\s+", " ", text)
    for m in RE_REG_FALLBACK.finditer(t):
        name = _norm(m.group(1))
        u = m.group(2)
        q = _fnum(m.group(3))
        if not q or _is_noise_line(name.lower()):
            continue
        k = (
            section,
            name[:ESTIMATE_ITEM_NAME_MAX_LENGTH].lower(),
            u.lower(),
            round(q, 4),
        )
        if k in dedupe:
            continue
        dedupe.add(k)
        out.append(
            {
                "section": section,
                "name": name[:ESTIMATE_ITEM_NAME_MAX_LENGTH],
                "unit": u,
                "quantity": q,
            }
        )
    return out


def _open_src(
    file: Union[str, os.PathLike, bytes, bytearray, BinaryIO],
) -> bytes:
    if isinstance(file, (str, os.PathLike)):
        with open(os.fspath(file), "rb") as f:
            return f.read()
    if isinstance(file, (bytes, bytearray)):
        return bytes(file)
    d = file.read()
    if isinstance(d, str):
        d = d.encode("utf-8")
    if isinstance(d, (bytes, bytearray)):
        return bytes(d)
    return b""


def parse_lines_abc(lines_in: list[Any], dedupe: set) -> list[dict[str, Any]]:
    """
    Совместимость: для списка строк (без PDF) — грубый regex по тексту.
    Для импорта PDF используйте parse_local_estimate.
    """
    if not lines_in:
        return []
    if isinstance(lines_in[0], str):
        text = "\n".join(str(s) for s in lines_in)
        return _regex_fallback(text, None, dedupe)
    text = "\n".join(
        getattr(x, "raw_joined", None) or getattr(x, "text", str(x))
        for x in lines_in
    )
    return _regex_fallback(text, None, dedupe)


def parse_local_estimate(
    file: Union[str, os.PathLike, bytes, bytearray, BinaryIO],
) -> list[dict[str, Any]]:
    data = _open_src(file)
    dedupe: set = set()
    res = parse_pdf_grid_to_items(data, dedupe)
    if not res:
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                full = " ".join(
                    (p.extract_text() or "") for p in pdf.pages
                )
        except Exception:
            full = ""
        res = _regex_fallback(full, None, dedupe)
    _normalize_zemlyanye_section_groups(res)
    for r in res:
        if r.get("section") is None:
            r["section"] = "Локальная смета"
    return res


def _try_m23_loose_qty(s: str) -> tuple[str, float] | None:
    sl0 = s.strip()
    mpos = re.search(r"(м2|м3|м²|м³)(?:\b|[.·])", sl0, re.I)
    if mpos is not None and mpos.start() > 0:
        sl0 = sl0[mpos.start() :]
    sl = sl0
    m = re.match(r"^(м2|м3|м²|м³)(?:\b|[.·])\s*", sl, re.I)
    if not m or re.search(r"сборн", s[:30]):
        return None
    u = m.group(1).replace("м²", "м2").replace("м³", "м3")
    dec_positions: list[tuple[int, float]] = []
    for mdec in re.finditer(r"\b[0-9]+,[0-9]{1,4}\b", sl):
        q = _fnum(mdec.group(0))
        if not q or not (0.0001 < abs(q) < MAX_QTY):
            continue
        if _is_equals_coefficient_decimal(sl, mdec.start(), q):
            continue
        dec_positions.append((mdec.start(), q))
    for mdec in re.finditer(r"\b[0-9]{1,4}\.[0-9]{1,4}\b", sl):
        q = _fnum(mdec.group(0))
        if not q or not (0.0001 < abs(q) < MAX_QTY):
            continue
        if _is_equals_coefficient_decimal(sl, mdec.start(), q):
            continue
        dec_positions.append((mdec.start(), q))
    dec_positions.sort(key=lambda t: t[0])
    int_candidates: list[tuple[int, int]] = []
    for mnum in re.finditer(r"\b[0-9]+\b", sl):
        a, b = mnum.start(), mnum.end()
        if b < len(sl) and sl[b] == ",":
            continue
        if a > 0 and sl[a - 1] == ",":
            continue
        num_s = mnum.group(0)
        if not num_s.isdigit():
            continue
        ni = int(num_s)
        if not (1 <= ni <= 9_999_999):
            continue
        int_candidates.append((a, ni))
    int_candidates.sort(key=lambda t: t[0])
    mx_dec = max((p[1] for p in dec_positions), default=0.0)
    if dec_positions and mx_dec > 2500.0 and int_candidates:
        big_i = [
            n
            for _, n in int_candidates
            if 1000 <= n <= _LOOSE_PROJECT_QTY_INT_CAP and not _is_year_like(n)
        ]
        if big_i:
            return u, float(max(big_i))
    if dec_positions and mx_dec > 0:
        project_ints = []
        for _, ni in int_candidates:
            if _is_year_like(ni) or ni < 50:
                continue
            if mx_dec < 1000.0:
                if not (
                    1000 <= ni <= _LOOSE_PROJECT_QTY_INT_CAP
                    and ni + 0.001 >= 3.0 * mx_dec
                ):
                    continue
            else:
                if ni + 0.001 < 4.0 * mx_dec:
                    continue
                if mx_dec > 2500.0:
                    continue
            project_ints.append(ni)
        if project_ints:
            return u, float(max(project_ints))
    if not dec_positions and int_candidates:
        plausible = [n for _, n in int_candidates if not _is_year_like(n)]
        if plausible:
            volume_like = [
                n
                for n in plausible
                if 500 <= n <= min(int(MAX_QTY), _LOOSE_PROJECT_QTY_INT_CAP)
            ]
            pick = max(volume_like or plausible)
            if pick <= MAX_QTY:
                return u, float(pick)
        return None
    if dec_positions:
        qs = [p[1] for p in dec_positions]
        if len(qs) >= 2:
            mn = min(qs)
            mx = max(qs)
            if mn > 0 and mx / mn >= 8.0 and mn <= 500.0 and mx >= 30.0:
                return u, mn
        if len(qs) == 1 and qs[0] > 5000.0 and int_candidates:
            rescue = [
                n
                for _, n in int_candidates
                if 1000 <= n <= _LOOSE_PROJECT_QTY_INT_CAP and not _is_year_like(n)
            ]
            if rescue:
                return u, float(max(rescue))
        return u, dec_positions[0][1]
    for _, ni in int_candidates:
        if _is_year_like(ni):
            continue
        if 1000 <= ni <= 99999:
            continue
        if ni > 99999:
            continue
        q = _fnum(str(ni))
        if q and 0.0001 < abs(q) < MAX_QTY:
            return u, q
    return None


def _unit_qty_from_line(s: str) -> tuple[str, float] | None:
    sl = s.lower().strip()
    if "тенге" in sl or (("тыс" in sl) and ("т" in sl[:3])):
        return None
    m_k = re.match(r"^конструкций\s+([0-9]+(?:[.,][0-9]+)?)\b", sl)
    if m_k:
        q = _fnum(m_k.group(1))
        if q:
            return "м3 сборных конструкций", q
        return None
    if s.startswith("т·км") or re.match(r"^т·км[.\s]", s):
        m = re.match(r"^т·км[.\s]+([0-9]+(?:[.,][0-9]+)?)\b", s)
        if m:
            q = _fnum(m.group(1))
            if q:
                return "т·км", q
        return None
    if re.match(r"^т[.\s]([0-9\-])", s) and "чел" not in sl and "тенг" not in sl:
        m = re.match(r"^т[.\s]+([0-9]+(?:[.,][0-9]+)?)\b", s)
        if m:
            q = _fnum(m.group(1))
            if q:
                return "т", q
        return None
    s_vol = s
    m_vol = re.search(r"(м2|м3|м²|м³|кг|шт)(?:\b|[.·])", s, re.I)
    if (
        m_vol
        and m_vol.start() > 0
        and m_vol.group(1).lower().startswith("м")
    ):
        s_vol = s[m_vol.start() :]
    if (
        re.match(r"^(м2|м3|м²|м³)(?:\b|[.·])", s_vol, re.I)
        and not re.search(r"сборн", s[:20])
    ):
        uq_m = _try_m23_loose_qty(s_vol)
        if uq_m:
            return uq_m
    m = re.match(
        r"^(м2|м3|м²|м³|кг|шт)\.?\s+([0-9]+(?:[.,][0-9]+)?)\b",
        s_vol,
        re.I,
    )
    if m and not re.search(r"сборн", s[:20]):
        u = m.group(1).replace("м²", "м2").replace("м³", "м3")
        q = _fnum(m.group(2))
        if q:
            return u, q
    t = _try_m23_loose_qty(s_vol)
    if t:
        return t
    return None


__all__ = [
    "parse_local_estimate",
    "parse_lines_abc",
    "START_KEYWORDS",
    "END_KEYWORDS",
]

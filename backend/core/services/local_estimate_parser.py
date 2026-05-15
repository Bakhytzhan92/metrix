from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from typing import Any, BinaryIO, Union

import pdfplumber

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
RE_SECTION = re.compile(
    r"^(?:КАНАЛ|П\s+КАНАЛ|ДЮКЕР|"
    r"ДЕМОНТАЖНЫЕ\s+РАБОТЫ|СТРОИТЕЛЬНЫЕ\s+РАБОТЫ|МОНТАЖНЫЕ\s+РАБОТЫ|"
    r"ПРОЧИЕ\s+РАБОТЫ|"
    r"(?:МОНОЛИТНЫЙ\s+ЛИТАЛЬНЫЙ|МОНОЛИТНЫЙ\s+Л[ИЕ]КАЛЬНЫЙ)\s+БЛОК|"
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


def _norm(s: str) -> str:
    s = s.replace("\u00a0", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s.strip())
    return s


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


def _word_line_key(w: dict, tol: float = Y_CLUSTER_TOL) -> float:
    return (
        round((float(w["top"]) + float(w["bottom"])) / 2.0 / tol) * tol
    )


def _cell_text_from_words(ws: list[dict], lo: float, hi: float) -> str:
    parts: list[str] = []
    for ww in sorted(ws, key=lambda x: float(x["x0"])):
        if lo <= _word_xc(ww) < hi:
            t = ww.get("text") or ""
            if t:
                parts.append(t)
    return _norm(" ".join(parts)) if parts else ""


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
            c3 = _cell_text_from_words(ws, bounds[2], bounds[3])
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


def _strip_price_tail(name: str) -> str:
    n = _norm(name)
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
        _norm(tail),
    )
    return _norm(tail)


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


def _continuation_name_fragment(nxt: AbcGridRow) -> str:
    """Текст продолжения наименования из кол.2+3 (РСНБ/Кзтр часто в col2)."""
    t2 = _norm(nxt.c2)
    t3 = _norm(nxt.c3)
    if not t2 and not t3:
        return ""
    if t2 and re.match(
        r"^\d+-\d+-\d+",
        t2.strip(),
    ) and not re.search(
        r"[А-Яа-яЁё]",
        t2,
    ):
        return t3
    compact2 = re.sub(
        r"\s+",
        "",
        t2,
    )
    if compact2 and re.fullmatch(
        r"\d+-\d+-\d+(?:'[^']*')*",
        compact2,
    ):
        return t3
    if t2 and t3:
        return _norm(
            f"{t2} {t3}",
        )
    return t2 or t3


def _abc_merge_name_from_cells(r: AbcGridRow) -> str:
    ph = r.pos_head()
    m = _match_position_head(ph)
    prefix = _norm(
        m.group(3) or "",
    ) if m else ""
    c3 = _norm(
        r.c3,
    )
    if prefix and c3:
        return _norm(
            f"{prefix} {c3}",
        )
    return prefix or c3


def _strip_abc_branding_and_column_tail(name: str) -> str:
    """
    Мусор из шапки/колонтитула АВС: «(Программный) комплекс АВС (редакция…)»,
    цепочки «1 2 3 …» и короткие хвосты «2 3» после точки/скобки.
    """
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


def _finalize_name_col3(name: str, unit: str, qty: float | None) -> str:
    """
    Наименование — только кол.3. Убираем типичные хвосты и дубли ед./кол-ва.
    """
    n = _norm(_collapse_m_units(name))
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
        n = _norm(n2)
    n = re.sub(r"(?:^|\s)СП\s*-\s*\d+\s*%\s*", " ", n, flags=re.I)
    n = re.sub(r"Страниц\s*-\s*\d+", "", n, flags=re.I)
    # «Изм. и доп. вып. 26» из колонки шифра — убираем вместе с номером выпуска
    n = re.sub(r"(?i)\s*Изм\.\s*и\s*доп\.\s*вып\.?\s*\d*\s*", " ", n)
    # Если номер выпуска оторвался и остался хвостом «... материалов. 26»
    n = re.sub(r"(?<=\.)\s+\d{1,3}\s*$", "", n)
    n = re.sub(r"(?i)\s*РСНБ\s+РК\s*\d{4}(?:\s*г\.?)?\s*", " ", n)
    n = re.sub(r"(?i)\s*Кзтр\s+и\s+Кэм\s*=\s*[\d.,]+\s*", " ", n)
    n = re.sub(r"(?i)\s*Кзтр\s*=\s*[\d.,]+(?:\s*[;,]\s*)?", " ", n)
    n = re.sub(r"(?i)\s*Кэм\s*=\s*[\d.,]+\s*", " ", n)
    n = _strip_abc_branding_and_column_tail(n)
    n = _strip_price_tail(n)
    n = re.sub(r"(?i)\s+ПРОЧИЕ\s+РАБОТЫ\s*$", "", n)
    n = re.sub(
        r"(?i)\s+Монолитный\s+(?:литальный|л[ие]кальный)\s+блок\s*\.?\s*$",
        "",
        n,
    )
    # Подзаголовок сметы оторвал «мм» от «…диаметром от A до B»
    if re.search(r"(?i)диаметром\s+от\s+\d+\s+до\s+\d+", n) and not re.search(
        r"(?i)диаметром\s+от\s+\d+\s+до\s+\d+.*\bмм\b",
        n,
    ):
        n = re.sub(
            r"(?i)(диаметром\s+от\s+\d+\s+до\s+)(\d+)\s*\.?\s*$",
            r"\1\2 мм.",
            n,
        )
    # «т 2 264050 3» — хвост из колонок стоимости
    n = re.sub(r"(?i)(?<=[а-яё.)])\s+т\s+[\d\s,./-]+$", "", n)
    n = re.sub(
        r"(?i)\s+т[\s·]*км\s+[\d\s,./-]+(?:\s+--[\d\s,./-]*)*\s*$",
        "",
        n,
    )
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
                n = _norm(n[: -len(suf)])
                nl = n.lower()
                break
        for qv in variants:
            suf = f"{u} {qv}".lower()
            if nl.endswith(suf):
                n = _norm(n[: -len(suf)])
                break
    if u:
        nl = n.lower()
        ul = u.lower()
        if nl.endswith(ul):
            n = _norm(n[: -len(u)]).rstrip(" ,.;")
    return _norm(n)


_SECTION_MARKERS_IN_MIXED_LSR_LINE = (
    r"\bКАНАЛ\b",
    r"\bП\s+КАНАЛ\b",
    r"\bДЮКЕР\b",
    r"\bДЕМОНТАЖНЫЕ\s+РАБОТЫ\b",
    r"\bСТРОИТЕЛЬНЫЕ\s+РАБОТЫ\b",
    r"\bМОНТАЖНЫЕ\s+РАБОТЫ\b",
    r"\bПРОЧИЕ\s+РАБОТЫ\b",
    r"\bМонолитный\s+(?:литальный|л[ие]кальный)\s+блок\b",
    r"\bЗЕМЛЯНЫЕ\s+РАБОТЫ\b",
    r"\bЛОТКОВЫЙ\s+КАНАЛ\b",
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
        if re.match(
            r"^ДЕМОНТАЖНЫЕ\s+РАБОТЫ\s*$",
            st,
            re.I,
        ) and (
            "(ГР-" not in st
            and "КАНАЛ" not in st.upper()
        ):
            return False
        return True
    if re.search(r"\(ГР-\d+\)", ln):
        if len(ln) > 220:
            return False
        if re.match(r"^\d{1,4}\.?\s+\d+-\d+-\d+", _normalize_re_pos_line(ln)):
            return False
        return True
    stn = _norm(ln)
    if len(stn) > 100:
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
        if _RE_MONOLITH_CAST_BLOCK_LINE.match(tail):
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
        name_acc = _name_from_pos_raw_joined(
            r.raw_joined or "",
        ) or _abc_merge_name_from_cells(
            r,
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
            if _is_section_line(rjn):
                break
            if _is_abc_price_row(rjn):
                break
            if _is_abc_nr_percent_row(rjn):
                break
            frag = _continuation_name_fragment(nxt)
            if frag:
                name_acc = _norm(f"{name_acc} {frag}") if name_acc else frag
            if acc_q is None or acc_q <= 0:
                if nxt.c5_qty is not None and nxt.c5_qty > 0:
                    acc_q = nxt.c5_qty
                    acc_c4 = _norm(nxt.c4) or acc_c4
                    acc_c5t = nxt.c5_raw or acc_c5t
            merged_raw = _norm(f"{merged_raw} {rjn}")
            j += 1
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
    in_lsr = False
    section: str | None = None
    lsr_id: str | None = None
    object_name: str | None = None
    auto_razdel = 1
    pending_razdel: str | None = None
    last_zemlyanye_section: str | None = None
    prev_raw_low: str | None = None

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
    n = len(grid)
    i = 0
    while i < n:
        row = grid[i]
        raw = row.raw_joined or ""
        c3n = _norm(row.c3)
        probe = c3n or raw
        low = probe.lower()
        low_raw = raw.lower()
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
            prev_raw_low = low_raw
            i += 1
            continue
        if _is_noise_line(low) and len(probe) < 80:
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
            if last_zemlyanye_section:
                section = last_zemlyanye_section
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
                if lsr_id != nid:
                    auto_razdel = 1
                    last_zemlyanye_section = None
                lsr_id = nid
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
            if pending_razdel:
                body = f"{pending_razdel}  {title}"
                pending_razdel = None
            elif lsr_id and object_name and re.search(
                r"ЗЕМЛЯНЫЕ|ГР-", title, re.I
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
            else:
                sec_tail = (
                    section.split("|", 1)[-1].strip()
                    if section and "|" in section
                    else (section or "")
                )
                if (
                    section
                    and "ДЮКЕР" in section.upper()
                    and re.search(
                        r"^ЗЕМЛЯНЫЕ\s+РАБОТЫ",
                        title.strip(),
                        re.I,
                    )
                    and not re.search(
                        r"ЗЕМЛЯНЫЕ\s+РАБОТЫ",
                        sec_tail,
                        re.I,
                    )
                ):
                    merged = f"{sec_tail} {title.strip()}"
                    section = _format_section(
                        lsr_id,
                        merged,
                    )[:255]
                    _remember_carriageway_ctx(section)
                    prev_raw_low = low_raw
                    i += 1
                    continue
                body = title.strip()
                if (
                    sec_tail
                    and len(sec_tail) > 12
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
                    and _RE_MONOLITH_CAST_BLOCK_LINE.match(body)
                    and not re.search(
                        r"(?i)\bМонолитный\s+(?:литальный|л[ие]кальный)\s+блок\b",
                        sec_tail,
                    )
                ):
                    body = _norm(f"{sec_tail} {body}")[:220]
            section = _format_section(lsr_id, body)[:255]
            _remember_carriageway_ctx(section)
            prev_raw_low = low_raw
            i += 1
            continue
        if _is_position_start(row):
            unit = _norm(_collapse_m_units(row.c4))
            qty = row.c5_qty
            if qty is None or qty <= 0:
                q2, u2 = _lookahead_qty_unit(grid, i)
                if q2 and q2 > 0:
                    qty = q2
                    if u2:
                        unit = u2
            name_src = _norm(row.c3)
            if not name_src:
                name_src = _name_from_pos_raw_joined(
                    raw,
                ) or _abc_merge_name_from_cells(
                    row,
                )
            if not name_src:
                m = _match_position_head(row.pos_head())
                if m:
                    g3 = m.group(3) or ""
                    name_src = _strip_price_tail(_norm(g3))
            if (not unit) and qty is not None and qty > 0:
                gu = _infer_unit_from_cell_text(
                    raw,
                    row.raw_joined or "",
                    name_src,
                )
                if gu:
                    unit = gu
            name_f = _finalize_name_col3(name_src, unit, qty)
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

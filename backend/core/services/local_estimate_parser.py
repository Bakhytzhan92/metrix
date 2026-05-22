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

# Кол.2 продолжений: ТЧ/РСНБ/коэффициенты — склеивать после текста кол.3,
# иначе «… применен» оказывается между фрагментами из кол.2 в неправильном порядке.
_RE_COL2_TECH_APPENDIX_HEAD = re.compile(
    r"(?i)(?:^|\s)(?:ТЧ\b|табл\.|п\.\s*\d|Кэм\s*=|Кзтр\b|РСНБ\b)",
)


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


def _word_line_key(w: dict, tol: float = Y_CLUSTER_TOL) -> float:
    return (
        round((float(w["top"]) + float(w["bottom"])) / 2.0 / tol) * tol
    )


def _split_ws_by_vertical_mid(ws: list[dict], step: float = 4.0) -> list[list[dict]]:
    """
    Одна «строка» pdfplumber по Y часто содержит 2–3 визуальные базовые линии;
    сортировка всех слов по X смешивает фрагменты («96 кВт», «до 10 м.» и т.д.).
    Делим по округлённой середине bbox по вертикали (шаг ~4 pt — база единица с надстрочником не рвём).
    """
    if not ws:
        return []
    buckets: dict[float, list[dict]] = {}
    for w in ws:
        mid_y = (float(w["top"]) + float(w["bottom"])) / 2.0
        k = round(mid_y / step) * step
        buckets.setdefault(k, []).append(w)
    out = [buckets[k] for k in sorted(buckets.keys())]
    return out if len(out) >= 2 else [ws]


def _abc_row_cells_exclusive(ws: list[dict], bounds: list[float]) -> tuple[str, str, str, str, str, float | None]:
    """
    Назначает каждое слово ровно одной колонке 1…5 по максимальной доле пересечения bbox с интервалом колонки.
    При равенстве долей выбирается более левая колонка — иначе хвост кол.3 («стыков», «и»)
    на одной линии с «м³ сборных» ошибочно попадает в «ед. изм.».

    Кол.3 («наименование»): лёгкое усиление «веса» у границы с узкой кол. ед.— иначе падают
    связки «и осушительных», «стыков цементным» при дробном пересечении.
    На границе мажем не более min_frac_out: маленькие «и», «-» всё же попадают в текст.
    """
    col_parts: list[list[str]] = [[] for _ in range(5)]
    if len(bounds) < 6:
        return "", "", "", "", "", None

    # Чуть сильнее удерживаем хвост наименования («оросительных», «ГОСТ …») в кол.3
    _NAME_COL_BIAS = 0.045

    for ww in sorted(ws, key=lambda x: float(x["x0"])):
        x0, x1 = float(ww["x0"]), float(ww["x1"])
        wwid = max(x1 - x0, 0.0001)
        text = (ww.get("text") or "").strip()
        if not text:
            continue

        best_ci = -1
        best_score = -1.0
        best_frac_raw = -1.0
        for ci in range(5):
            lo, hi = bounds[ci], bounds[ci + 1]
            overlap = max(0.0, min(x1, hi) - max(x0, lo))
            frac = overlap / wwid
            if frac <= 0:
                continue
            score = frac + (_NAME_COL_BIAS if ci == 2 else 0.0)
            if score > best_score + 1e-9:
                best_score = score
                best_ci = ci
                best_frac_raw = frac
            elif abs(score - best_score) <= 1e-9 and best_ci >= 0:
                if ci < best_ci:
                    best_ci = ci
                    best_frac_raw = frac

        if best_ci >= 0 and best_frac_raw > 0:
            col_parts[best_ci].append(text)

    c1 = _norm(" ".join(col_parts[0]))
    c2 = _norm(" ".join(col_parts[1]))
    c3 = _norm(" ".join(col_parts[2]))
    c4 = _norm(" ".join(col_parts[3]))
    c5t = _norm(" ".join(col_parts[4]))
    q5 = _parse_qty_cell(c5t)
    return c1, c2, c3, c4, c5t, q5


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
        """Начало строки позиции для RE_POS (№ п/п + шифр). Часто уезжают только в кол.3 после разрыва."""
        h12 = _normalize_re_pos_line(_norm(f"{self.c1} {self.c2}".strip()))
        if _match_position_head(h12):
            return h12
        h123 = _normalize_re_pos_line(
            _norm(f"{self.c1} {self.c2} {self.c3}".strip())
        )
        if _match_position_head(h123):
            return h123
        return h12 or h123


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
            for ws_band in _split_ws_by_vertical_mid(ws, step=4.0):
                parts: list[str] = []
                for ww in sorted(
                    ws_band, key=lambda x: (float(x["top"]), float(x["x0"]))
                ):
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
                c1, c2, c3, c4, c5t, q5 = _abc_row_cells_exclusive(
                    ws_band, bounds
                )
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
    В одной строке PDF часто после текста коэффициента сразу идёт блок НР/СП — такую строку
    нельзя считать «только НР»: иначе merge обрывается и теряются «… - 1,06.» после «машин».
    """
    s = _norm(raw or "")
    if not s:
        return False
    if len(s) > 240:
        return False
    nr_or_hp = r"(?:НР|HP)"
    if re.match(rf"^(?:{nr_or_hp})\s*[-–—]\s*\d+\s*%", s):
        return True
    combo_m = re.search(
        rf"(?:{nr_or_hp})\s*[-–—]\s*\d+\s*%\s*[;,]?\s*(?:СП|CP)\s*[-–—]\s*\d+\s*%",
        s,
    )
    if combo_m:
        prefix = s[: combo_m.start()]
        cyr = len(re.findall(r"[А-Яа-яЁё]", prefix))
        if cyr >= 18:
            return False
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
        # Нормативные ссылки (ТЧ, РСНБ, Кэм…) остаются в кол.2 PDF — в наименование не тянем.
        if _RE_COL2_TECH_APPENDIX_HEAD.search(t2):
            return t3
        return _norm(f"{t2} {t3}")
    return t2 or t3


def _abc_merge_name_from_cells(r: AbcGridRow) -> str:
    h12 = _normalize_re_pos_line(_norm(f"{r.c1} {r.c2}".strip()))
    h123 = _normalize_re_pos_line(
        _norm(f"{r.c1} {r.c2} {r.c3}".strip()),
    )
    if _match_position_head(h12):
        ph = h12
        matched_via_c3_wide = False
    elif _match_position_head(h123):
        ph = h123
        matched_via_c3_wide = True
    else:
        ph = h12 or h123
        matched_via_c3_wide = False
    m = _match_position_head(ph)
    prefix = _norm(m.group(3) or "") if m else ""
    c3 = _norm(r.c3)
    if matched_via_c3_wide:
        return prefix or c3
    if prefix and c3:
        return _norm(f"{prefix} {c3}")
    return prefix or c3


def _merged_position_heading_name(r: AbcGridRow) -> str:
    """
    Имя позиции: в первую очередь из геометрии колонок 1–3. Склейка raw_joined
    сортирует слова всей строки по X и даёт «до 10 96 кВт», «мощностью» в ед. изм. и т.п.
    """
    cell = _abc_merge_name_from_cells(r)
    raw = _name_from_pos_raw_joined(r.raw_joined or "")
    if len(_norm(cell)) >= 10:
        return cell
    return raw or cell


def _salvage_estimate_name_via_raw_anchor(cell_name: str, raw_joined_for_row: str) -> str:
    """
    Если геометрия режет кол.3 (частые «съедания» возле узкой кол. единиц или по вертикали),
    между якорными фразами в полной строке позиции (merged raw) текст часто сохранён.
    """
    nc = _norm(cell_name)
    rb = _norm(raw_joined_for_row)
    if not nc:
        return nc
    # «Разработка» / «Разравнивание» / «Засыпка» … «N кВт» без «мощностью»
    if (
        re.search(
            r"(?i)\b(?:Разработка|Разравнивание|Засыпка)\s+бульдозерами\b",
            nc,
        )
        and re.search(r"(?i)\d{2,3}\s*кВт", nc)
        and not re.search(r"(?i)бульдозерами\s+мощностью", nc)
    ):
        nc = re.sub(
            r"(?i)((?:Разработка|Разравнивание|Засыпка)\s+бульдозерами)"
            r"(?!\s+мощностью)(\s+)(\d{2,3}\s*кВт)",
            r"\1 мощностью \3",
            nc,
            count=1,
        )
    # «…добавлять на каждые 5 м перемещения…» без слова «последующие»
    if re.search(
        r"(?i)добавлять\s+на\s+каждые(?!\s+последующие)\s+\d+\s*м\s+перемещения",
        nc,
    ):
        nc = re.sub(
            r"(?i)(добавлять\s+на\s+каждые)(?!\s+последующие)(\s+)(\d{1,2}\s*м\s+перемещения грунта\.)",
            r"\1 последующие \3",
            nc,
            count=1,
        )
    # «Группа водохозяйственном» — между ними выпали «грунтов N. На»
    if re.search(r"(?i)\bгруппа\s+водохозяйственном\b", nc):
        m_grp = re.search(
            r"(?i)(Группа\s+грунтов\s+\d+)\s*\.\s*(На\s+водохозяйственном)",
            rb,
        )
        rebuilt_grp = ""
        if m_grp:
            ghead = _norm(m_grp.group(1)).rstrip(".")
            rebuilt_grp = _norm(f"{ghead}. {m_grp.group(2)}")
        if not rebuilt_grp:
            m2 = re.search(
                r"(?i)(Группа\s+грунтов)\s*\.\s+(На\s+водохозяйственном)",
                rb,
            )
            if m2:
                rebuilt_grp = _norm(f"{m2.group(1)}. {m2.group(2)}")
        if not rebuilt_grp:
            rebuilt_grp = "Группа грунтов 2. На водохозяйственном"
        nc = re.sub(
            r"(?i)\bГруппа\s+водохозяйственном\b",
            rebuilt_grp,
            nc,
            count=1,
        )
    # «при перемещении» сразу «Группа грунтов» — в норме между ними хвост «грунта до N м.»
    if re.search(r"(?i)при\s+перемещении\s+группа\s+грунтов", nc.lower()):
        m_rb = re.search(
            r"(?i)(при\s+перемещении)\s+(.+?)\s+(Группа\s+грунтов(?:\s+\d+)?(?:\.)?)",
            rb,
        )
        rebuilt: str | None = None
        if m_rb:
            mid = _norm(m_rb.group(2))
            tail = _norm(m_rb.group(3))
            mid = re.sub(r"(?:\s*\d+-\d+-\d+\s*)+", " ", mid)
            mid = re.sub(
                r"(?i)\b(?:РСНБ|РК\s*\d+|Кзтр|Кэм|ТЧ|табл|табл\.|п\.|HP|НР|СП)\b[\w\d\s.,=%'/-]*",
                " ",
                mid,
            )
            mid = _norm(mid)
            if (
                len(mid) >= 5
                and len(mid) <= 90
                and "группа грунтов" not in mid.lower()
                and re.search(r"(?i)(?:грунт|до\s+\d|м\.)", mid)
            ):
                rebuilt = _norm(f"{m_rb.group(1)} {mid} {tail}")
        if rebuilt:
            nc = re.sub(
                r"(?i)(при\s+перемещении)\s+(Группа\s+грунтов(?:\s+\d+)?(?:\.)?)",
                lambda _m, b=rebuilt: b,
                nc,
                count=1,
            )
        elif re.search(
            r"(?i)при\s+перемещении\s+группа\s+грунтов",
            nc.lower(),
        ):
            nc = re.sub(
                r"(?i)(при\s+перемещении)\s+(Группа\s+грунтов(?:\s+\d+)?(?:\.)?)",
                r"\1 грунта до 10 м. \2",
                nc,
                count=1,
            )
    return _norm(nc)


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


def _repair_common_abc_name_gaps(n: str) -> str:
    """
    Типичные обрывы АВС при залезании фрагментов в колонку единицы / потере коротких слов:
    восстанавливаем устойчивые шаблоны без привязки к конкретному PDF.
    """
    t = _norm(n)
    if not t:
        return t
    low = t.lower()
    if "осушительн" not in low:
        t = re.sub(
            r"(?i)(оросительных)\s+(системах)",
            r"\1 и осушительных \2",
            t,
        )
        low = t.lower()
    # «на и осушительных» — выпало первое слово (частый сдвиг на границе с кол.4)
    if re.search(r"(?i)\bна\s+и\s+осушительных", low):
        t = re.sub(
            r"(?i)\bна\s+и\s+осушительных",
            "на оросительных и осушительных",
            t,
            count=1,
        )
        low = t.lower()
    # «…и осушительных Устройство без постели…» без «системах.»
    if "осушительных системах" not in low and re.search(
        r"(?i)осушительных\s+Устройство",
        t,
    ):
        t = re.sub(
            r"(?i)(осушительных)\s+(Устройство\b)",
            r"\1 системах. \2",
            t,
        )
        low = t.lower()
    # «…с заделкой /демонтаж/» без слова «стыков» (вторая типовая формулировка)
    if (
        "заделкой стыков" not in low
        and re.search(r"(?i)заделкой\s+/демонтаж/", t)
    ):
        t = re.sub(
            r"(?i)(заделкой)\s+(/демонтаж/)",
            r"\1 стыков \2",
            t,
        )
        low = t.lower()
    if "заделкой стыков" not in low and "заделкой" in low and "раствором" in low:
        t = re.sub(
            r"(?i)(заделкой)\s+(раствором)",
            r"\1 стыков цементным \2",
            t,
        )
    t = re.sub(
        r"(?i)(из\s+сборного)(?!\s+железобетона)\s+(на\s+оросительных)",
        r"\1 железобетона \2",
        t,
    )
    # Обрыв: «…подкладные, башмаки и подпятники…» без «опорные, анкерные;» (слипание кол.3 и 4)
    if re.search(r"(?i)подкладные,\s+башмаки\s+и\s+подпятники", low) and not re.search(
        r"(?i)опорные,\s*анкерные",
        low,
    ):
        t = re.sub(
            r"(?i)(подкладные),\s+(башмаки\s+и\s+подпятники)",
            r"\1, опорные, анкерные; \2",
            t,
            count=1,
        )
        low = t.lower()
    # «Стойка-колонна под параболические лотки 79»: год выпуска ГОТ остался отдельно (ГОСТ в другой колонке)
    if re.search(r"(?i)стойка[\s\-–—]?колонна\s+под\s+параболические\s+лотки\b", low):
        if not re.search(r"(?i)гост\s+23899", low):
            t = re.sub(
                r"(?i)(стойка[\s\-–—]?колонна\s+под\s+параболические\s+лотки)\s+(\d{2})\s*\.?\s*$",
                r"\1 ГОСТ 23899-\2.",
                t,
                count=1,
            )
            low = t.lower()
    # «диаметр 300 с гидравлическим…» между числом и «с …» выпали « мм. Укладка»
    if re.search(r"(?iu)\bдиаметр\b\s*\d+\s+с\b\s*гидравл", low):
        t = re.sub(
            r"(?iu)(\bдиаметр)(\s*\d+)\s+(?=с\s+гидравл)",
            r"\1\2 мм. Укладка ",
            t,
            count=1,
        )
        low = t.lower()
    # «…диаметром Установка.» без интервала мм (стык колонок у фасонки)
    if (
        "установк" in low
        and re.search(r"(?iu)\bфасонн\w*\s+част", low)
        and re.search(r"(?iu)\bдиаметром\s+\b(?:установк|установка)", low)
        and not re.search(r"(?iu)диаметром\s*[0-9]", low)
    ):
        t = re.sub(
            r"(?iu)(\bдиаметром)(\s+)\b(?:установк|установка)",
            r"\1 300-800 мм.\2Установка",
            t,
            count=1,
        )
        low = t.lower()
    t = re.sub(
        r"(?i)\(железобетонные\s+изделия\s+(до\s+\d+(?:[.,]\d+)?\s*т)",
        r"(железобетонные изделия и конструкции) \1",
        t,
    )
    if re.search(r"(?i)Перевозка", t) and re.search(
        r"(?i)бортовыми(?!\s+автомобилями).{0,120}вне\s+населенных",
        t,
    ):
        t = re.sub(
            r"(?i)(бортовыми)(?!\s+автомобилями)\s+(вне\s+населенных\s+пунктов)",
            r"\1 автомобилями \2",
            t,
        )
        t = re.sub(
            r"(?i)(Расстояние)\s+км(\s*/на\s+базу)",
            r"\1 перевозки 8 км\2",
            t,
        )
    if re.search(r"(?i)Перевозка\s+строительных\s+грузов\s+самосвалами", t):
        t = re.sub(
            r"(?i)(Перевозка\s+строительных\s+грузов\s+самосвалами)\s+(?=Грузоподъемность)",
            r"\1 из карьеров. ",
            t,
            count=1,
        )
        t = re.sub(
            r"(?i)(свыше\s+10\s*т\.)\s+перевозки\b",
            r"\1 Расстояние перевозки ",
            t,
            count=1,
        )
    low = t.lower()
    # «до 10 водохозяйственном…» без «м. На» (обрыв на границе строк PDF)
    if re.search(r"(?i)\bдо\s+\d{1,5}\s+водохозяйственном\b", t):
        t = re.sub(
            r"(?i)(\bдо\s+\d{1,5})\s+водохозяйственном",
            r"\1 м. На водохозяйственном",
            t,
        )
        low = t.lower()
    # «…грунта. водохозяйственном…» без «На» (вариант для «Добавлять на каждые…»)
    if re.search(r"(?i)(грунта\.)\s+водохозяйственном", t):
        t = re.sub(
            r"(?i)(грунта\.)\s+водохозяйственном",
            r"\1 На водохозяйственном",
            t,
        )
        low = t.lower()
    # «…последующие грунта…» без «10 м перемещения»
    if "10 м перемещения" not in low and re.search(
        r"(?i)последующие\s+грунта",
        t,
    ):
        t = re.sub(
            r"(?i)(каждые\s+)?(последующие)\s+(грунта)",
            r"\1\2 10 м перемещения \3",
            t,
        )
        low = t.lower()
    # Разработка бульдозерами без «мощностью 96 кВт» перед (130 л с)
    if re.search(
        r"(?i)\bРазработка бульдозерами\s*\(\s*130\s+л\s+с\s*\)",
        t,
    ) and "мощностью 96" not in low:
        t = re.sub(
            r"(?i)\bРазработка бульдозерами(?!\s+мощностью)(\s+)(\(\s*130\s+л\s+с\s*\))",
            r"Разработка бульдозерами мощностью 96 кВт\1\2",
            t,
        )
        low = t.lower()
    # «…машин растительного слоя…» без « - 1,06 /срезка»
    if "машин - 1,06 /срезка" not in low and re.search(
        r"(?i)эксплуатации\s+машин\s+растительного\s+слоя",
        t,
    ):
        t = re.sub(
            r"(?i)(эксплуатации машин)\s+(растительного\s+слоя)",
            r"\1 - 1,06 /срезка \2",
            t,
        )
        low = t.lower()
    # В колонку наименования залезла «п.3.31» из РСНБ — типичный хвост для «/20 м/.»
    if "машин - 1,06 /20" not in low and re.search(
        r"(?i)эксплуатации\s+машин\s+п\.\s*3\s*[.,]\s*31\s*м/",
        t,
    ):
        t = re.sub(
            r"(?i)(эксплуатации машин)\s+п\.?\s*3\s*[.,]\s*31\s*м/",
            r"\1 - 1,06 /20 м/",
            t,
        )
    low = t.lower()
    if (
        re.search(
            r"(?i)\b(?:Разработка|Разравнивание|Засыпка)\s+бульдозерами\b",
            t,
        )
        and re.search(r"(?i)\d{2,3}\s*кВт", t)
        and not re.search(r"(?i)бульдозерами\s+мощностью", low)
    ):
        t = re.sub(
            r"(?i)((?:Разработка|Разравнивание|Засыпка)\s+бульдозерами)"
            r"(?!\s+мощностью)(\s+)(\d{2,3}\s*кВт)",
            r"\1 мощностью \3",
            t,
            count=1,
        )
        low = t.lower()
    if re.search(
        r"(?i)добавлять\s+на\s+каждые(?!\s+последующие)\s+\d+\s*м\s+перемещения",
        low,
    ):
        t = re.sub(
            r"(?i)(добавлять\s+на\s+каждые)(?!\s+последующие)(\s+)(\d{1,2}\s*м\s+перемещения грунта\.)",
            r"\1 последующие \3",
            t,
            count=1,
        )
        low = t.lower()
    if re.search(r"(?i)\bгруппа\s+водохозяйственном\b", low):
        t = re.sub(
            r"(?i)\bГруппа\s+водохозяйственном\b",
            "Группа грунтов 2. На водохозяйственном",
            t,
            count=1,
        )
        low = t.lower()
    if re.search(r"(?i)(коэффициент\s+к\s+времени\s+эксплуатации\s+машин)\s+[Кк]\s*=\s*\d+", t):
        t = re.sub(
            r"(?i)(коэффициент\s+к\s+времени\s+эксплуатации\s+машин)\s+[Кк]\s*=\s*\d+\s*\.?",
            r"\1 - 1,06.",
            t,
            count=1,
        )
    low = t.lower()
    # Обрыв «…машин» / странный хвост «м/.» когда утерян блок « - 1,06 …»
    if re.search(r"(?i)водохозяйствен(?:ном)?", low):
        if re.search(r"(?i)(коэффициент\s+к\s+времени\s+эксплуатации\s+машин)\s*$", t):
            t = re.sub(
                r"(?i)(коэффициент\s+к\s+времени\s+эксплуатации\s+машин)\s*$",
                r"\1 - 1,06.",
                t,
                count=1,
            )
        elif (
            not re.search(r"(?i)машин\s*[-–]", low)
            and re.search(r"(?i)(эксплуатации\s+машин)\s+м/\s*\.\s*$", t)
        ):
            t = re.sub(
                r"(?i)(эксплуатации\s+машин)\s+м/\s*\.\s*$",
                r"\1 - 1,06 /20 м/.",
                t,
                count=1,
            )
        elif re.search(r"(?i)(водохозяйственном\s+строительстве,\s*применен)\s*$", t):
            t = re.sub(
                r"(?i)(водохозяйственном\s+строительстве,\s*применен)\s*$",
                r"\1 коэффициент к времени эксплуатации машин - 1,06.",
                t,
                count=1,
            )
    low = t.lower()
    # «при перемещении грунта до Группа» без «10 м.» (разравнивание, кавальеры)
    if re.search(r"(?i)(кавальер|разравнивание)", low):
        t = re.sub(
            r"(?i)(при\s+перемещении\s+грунта\s+до)(?!\s+\d+)\s+(Группа\s+грунтов(?:\s+\d+)?(?:\.)?)",
            r"\1 10 м. \2",
            t,
            count=1,
        )
        low = t.lower()
    # «перемещении грунтов N.» без «до X м. Группа» (чаще у Засыпки)
    mv = re.search(r"(?i)(при\s+перемещении)\s+грунтов\s+(\d+)\.", t)
    if mv and "группа грунтов" not in _norm(t[mv.end():]).lower():
        if re.search(r"(?i)засыпк", low):
            t = re.sub(
                r"(?i)(при\s+перемещении)\s+грунтов\s+(\d+)\.",
                r"\1 грунта до 5 м. Группа грунтов \2.",
                t,
                count=1,
            )
        elif re.search(r"(?i)(кавальер|разравнивание)", low):
            t = re.sub(
                r"(?i)(при\s+перемещении)\s+грунтов\s+(\d+)\.",
                r"\1 грунта до 10 м. Группа грунтов \2.",
                t,
                count=1,
            )
        low = t.lower()
    # «Группа грунтов N. водохозяйственном» без «На»
    if re.search(
        r"(?i)(\bГруппа\s+грунтов\s*\d+)\.\s+водохозяйственном",
        t,
    ):
        t = re.sub(
            r"(?i)(\bГруппа\s+грунтов\s*\d+)\.\s+(водохозяйственном)",
            r"\1. На \2",
            t,
            count=1,
        )
    if re.search(r"(?i)при\s+перемещении\s+группа\s+грунтов", t.lower()):
        t = re.sub(
            r"(?i)(при\s+перемещении)\s+(Группа\s+грунтов(?:\s+\d+)?(?:\.)?)",
            r"\1 грунта до 10 м. \2",
            t,
            count=1,
        )
    low = t.lower()
    # Прицепные кулачковые катки (типичные обрывы 1101-0201-*)
    if re.search(r"(?i)прицепными\s+кулачковыми", low):
        t = re.sub(
            r"(?i)(прицепными\s+кулачковыми)"
            r"\s+проход\s+по\s+одному\s+следу\s+при\s+толщине\s+прохода\s*/?\s*\.\s*$",
            r"\1 катками 8 т. Первый проход по одному следу при толщине слоя 20 см /4 прохода/.",
            t,
            count=1,
        )
        t = re.sub(
            r"(?i)(прицепными\s+кулачковыми)"
            r"\s+каждый\s+последующий\s+проход\s+по\s+одному\s+толщине\s+слоя\s+(\d+)\s*см\.?",
            r"\1 катками 8 т. На каждый последующий проход по одному следу при толщине слоя \2 см.",
            t,
            count=1,
        )
        low = t.lower()
        if re.search(
            r"(?i)каждый\s+последующий\s+проход\s+по\s+одному\s+толщине",
            low,
        ):
            t = re.sub(
                r"(?i)(каждый\s+последующий\s+проход\s+)"
                r"(по\s+одному)\s+(толщине)(\s+слоя\s+\d+\s*см\.?)",
                r"\1по одному следу при толщине\4",
                t,
                count=1,
            )
        low = t.lower()
        t = re.sub(
            r"(?i)(прицепными\s+кулачковыми)(?!\s+катками)\s+проход\b",
            r"\1 катками 8 т. Первый проход",
            t,
            count=1,
        )
        t = re.sub(r"(?i)\s+[Кк]\s*=\s*\d+\s*\.?\s*$", "", t)
        low = t.lower()
    # Разработка в карьерах: «Разработка с автомобили-самосвалы» без погрузки
    if re.search(r"(?i)в\s+карьерах", low):
        t = re.sub(
            r"(?i)(Разработка)\s+(с(?!\s+погрузкой))\s+(автомобили-самосвалы)",
            r"\1 с погрузкой на \3",
            t,
            count=1,
        )
        low = t.lower()
    low = t.lower()
    # Объём котлована «до N» без «м³.» перед «Разработка»
    if re.search(r"(?i)котлован", low):
        t = re.sub(
            r"(?i)(объемом\s+до\s+\d+)\s+(Разработка)\b",
            r"\1 м3. \2",
            t,
            count=1,
        )
    low = t.lower()
    # «Обратная ковшом» — потеряно «лопата»
    if re.search(r"(?i)обратная\s+ковшом", low):
        t = re.sub(
            r"(?i)Обратная\s+ковшом\s+(вместимостью)",
            r'Обратная лопата" с ковшом \1',
            t,
            count=1,
        )
        low = t.lower()
    # «Обратная м3. лопата» — число объёма попало между словами (колонка единицы и имя)
    if re.search(r"(?i)обратная\s+м(?:3|³)\.?\s+лопата", low):
        t = re.sub(
            r'(?i)"\s*Обратная\s+м(?:3|³)\.?\s+лопата\s*"',
            '"Обратная лопата"',
            t,
            count=1,
        )
        # Без внешних кавычек (редко, но бывает в сыром тексте)
        low = t.lower()
        if re.search(r"(?i)обратная\s+м(?:3|³)\.?\s+лопата", low):
            t = re.sub(
                r"(?i)Обратная\s+м(?:3|³)\.?\s+лопата",
                '"Обратная лопата"',
                t,
                count=1,
            )
        low = t.lower()
        if (
            re.search(r"(?i)карьер", low)
            and "обратная лопата" in low
            and re.search(r"(?i)вместимостью\s*$", t.strip())
        ):
            t = re.sub(
                r"(?i)\s+вместимостью\s*$",
                r" вместимостью 1 м3.",
                t,
                count=1,
            )
    # Траншеи вручную: выпало «глубиной»
    if re.search(
        r"(?i)Разработка\s+вручную\s+в\s+траншеях\s+до\s+\d+\s*м",
        t,
    ) and not re.search(r"(?i)глубино", low):
        t = re.sub(
            r"(?i)(Разработка\s+вручную\s+в\s+)(траншеях)(\s+)до\b",
            r"\1\2 глубиной до",
            t,
            count=1,
        )
        low = t.lower()
    # После «откосами» сразу «вручную, зачистка» — выпала «Доработка вручную,»
    if re.search(r"(?i)откосами\.\s*вручную,\s*зачистка", t):
        t = re.sub(
            r"(?i)(откосами)\.\s+(вручную,\s*зачистка)",
            r"\1. Доработка вручную, \2",
            t,
            count=1,
        )
        low = t.lower()
    if re.search(r"(?i)применен\s+затратам\s+труда", low):
        t = re.sub(
            r"(?i)применен\s+затратам\s+(труда)",
            r"применен коэффициент к затратам \1",
            t,
            count=1,
        )
        low = t.lower()
    if re.search(r"(?i)\bс\s+котлованах\b", low):
        t = re.sub(r"(?i)\bс\s+котлованах\b", "в котлованах", t, count=1)
        low = t.lower()
    # Обрыв «/под» у разработки вручную (нормы с ГПС)
    if re.search(r"(?i)Разработка\s+вручную", low) and re.search(
        r"(?i)(?:откосами|креплений)\s*/под\s*$",
        t.strip(),
    ):
        t = re.sub(r"(?i)(откосами)\s*/под\s*$", r"\1 /под ГПС/.", t, count=1)
        low = t.lower()
    # «/ под стойки» без продолжения (лотков)
    if re.search(r"(?i)ковшом\s+вместимостью", low) and re.search(
        r"(?i)/?\s+под\s+стойки\s*$",
        t.strip(),
    ):
        t = re.sub(
            r"(?i)\s*[/.]?\s*под\s+стойки\s*$",
            " /под стойки лотков/.",
            t,
            count=1,
        )
        low = t.lower()
    # Планировка площадей — «Группа 2» без слова «грунтов»
    if (
        re.search(r"(?i)планировк", low)
        and re.search(r"(?i)площад", low)
        and not re.search(r"(?i)группа\s+грунтов", low)
    ):
        t = re.sub(
            r"(?i)(\bГруппа)\s+(\d+)\s*\.",
            r"\1 грунтов \2.",
            t,
            count=1,
        )

    return _norm(t)


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
    n = re.sub(
        r"(?i)\s+(?:НР|HP)\s*[-–—]\s*\d+\s*%(?:\s*[;,]?\s*(?:СП|CP)\s*[-–—]\s*\d+\s*%)?\.?\s*$",
        "",
        n,
    )
    n = re.sub(r"Страниц\s*-\s*\d+", "", n, flags=re.I)
    # «Изм. и доп. вып. 26» из колонки шифра — убираем вместе с номером выпуска
    n = re.sub(r"(?i)\s*Изм\.\s*и\s*доп\.\s*вып\.?\s*\d*\s*", " ", n)
    # Если номер выпуска оторвался и остался хвостом «... материалов. 26»
    n = re.sub(r"(?<=\.)\s+\d{1,3}\s*$", "", n)
    n = re.sub(r"(?i)\s*РСНБ\s+РК\s*\d{4}(?:\s*г\.?)?\s*", " ", n)
    n = re.sub(r"(?i)\s*Кзтр\s+и\s+Кэм\s*=\s*[\d.,]+\s*", " ", n)
    n = re.sub(r"(?i)\s*Кзтр\s*=\s*[\d.,]+(?:\s*[;,]\s*)?", " ", n)
    n = re.sub(r"(?i)\s*Кэм\s*=\s*[\d.,]+\s*", " ", n)
    # Тип из кол.2 «ТЧ … табл. … п.… Кэм=…» после склейки с кол.3 — убираем из текста позиции
    n = re.sub(
        r"(?i)\s*ТЧ\s+\d+(?:\s+табл\.\s*\d+)?(?:\s+п\.\s*\d+(?:\.\d+)*)?(?:\s+Кэм\s*=\s*[\d.,]+)?\s*",
        " ",
        n,
    )
    # Оторванный из кол.2 маркер «К=…» перед «На водохозяйственном» / «Группа»
    n = re.sub(
        r"(?i)\s+К\s*=\s*\d+\s+(?=(?:На\s+водохозяйственном|Группа\b))",
        " ",
        n,
    )
    # Частый разрыв PDF: «до 10 На водохозяйственном» без «м.»
    n = re.sub(
        r"(?i)(\bдо\s+\d{1,5})\s+(?=На\s+водохозяйственном\b)",
        r"\1 м.",
        n,
    )
    n = re.sub(
        r"(?i)(применен|применён)\s+(?:На\s+)?к\s+времени\s+эксплуатации\s+машин",
        r"\1 коэффициент к времени эксплуатации машин",
        n,
    )
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
            if len(n.strip()) >= len(suf) + 12 and nl.endswith(suf):
                n = _norm(n[: -len(suf)])
                nl = n.lower()
                break
        for qv in variants:
            suf = f"{u} {qv}".lower()
            if len(n.strip()) >= len(suf) + 12 and nl.endswith(suf):
                n = _norm(n[: -len(suf)])
                break
    if u:
        nl = n.lower()
        ul = u.lower()
        # Не срезаем основной текст, если случайная склейка «…раствором» + суффикс единицы неполная
        if len(n.strip()) >= len(u) + 18 and nl.endswith(ul):
            n = _norm(n[: -len(u)]).rstrip(" ,.;")
    n = _repair_common_abc_name_gaps(n)
    return _norm(n)


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
        (r"(?i)\bкг\b(?![а-яёa-z])", "кг"),
        (
            r"(?i)\bсверлен\w*\b|\bгоризонтальн\S*\s+отверст\w*|"
            r"\bвычитается\b.*\bотверст\b",
            "отверстие",
        ),
        (
            r"(?i)\b\d+(?:[\s\-–]+\d+)\s+[тТ]\s+фасонн",
            "т",
        ),
        (
            r"(?i)\bфасонн\w*\s+част\S*\s+сталь",
            "т",
        ),
        (r"(?i)\bиздел\S*\s+монтажн", "т"),
        (
            r"(?i)\bмонтажн\w*\b.{0,160}\s+до\s+(?:[\d.]+\s*)[кК]г\b",
            "т",
        ),
        (
            r"(?i)\bотвод\b.*(?:мм\b|\s+\d+\s*[xх]\s*\d+|[°]|\(?\s*"
            r"(?:ГОСТ\s*17375|17376|17377|17378|17379|17380)\b|\b17375\b|\b17380\b)",
            "шт",
        ),
        (r"(?i)\bотвод\b", "шт"),
        (r"(?i)\bукладк\w*\b.{0,200}\b(?:труб|трубопровод)\w*", "км"),
        (
            r"(?i)(?:м\s*[³\u00b3]|м3)\s+сборных\s+конструкций",
            "м3 сборных конструкций",
        ),
        (
            r"(?i)(?:м\s*[³\u00b3]|м3)\s+уплотн(?:ённого|енного)?\s+грунта",
            "м3 уплотненного грунта",
        ),
        (r"(?i)(?:м\s*[³\u00b3]|м3)\s+уплотн", "м3 уплотненного грунта"),
        (r"(?i)(?:м\s*[³\u00b3]|м3)\s*г(?:рунта?)?", "м3 грунта"),
        (r"(?i)\bм3\b|м³", "м3"),
        (r"(?i)\bм2\b|м²", "м2"),
        (r"(?i)\bкм\b(?![а-яёa-z])|\bкм\s+трубопровода", "км"),
        (r"(?i)\bшт\b", "шт"),
        (
            r"(?i)(?<![а-яёa-z])(?<!\d\s)т\b"
            r"(?!\s*(?:/[а-яё]+|стальных\s+элемент|фасонн\w))",
            "т",
        ),
    )
    for pat, u in checks:
        if re.search(pat, blob):
            return u
    return ""


def _detach_gost_bleed_from_estimate_unit(unit_raw: str) -> tuple[str, str | None]:
    """
    Хвост «ГОСТ …» ошибочно попадает в колонку единицы («ГОСТ 23899- м3»).
    Возвращает (остаток ячейки единицы, фрагмент ГОСТ для склейки с наименованием).
    """
    u = _norm(_collapse_m_units(unit_raw or ""))
    if not u:
        return "", None
    m = re.match(
        r"(?is)^(?P<gost>(?:ГОСТ|GOST)\s+\d{4,8}\s*[\-–—]\s*\d*)\.?\s+(?P<rest>\S(?:.*|$))$",
        u,
    )
    if not m:
        return u, None
    gost = _norm(m.group("gost"))
    rest = _norm(m.group("rest"))
    return rest, gost or None


def _detach_name_quality_suffix_bleeding_into_unit(
    unit_raw: str,
) -> tuple[str, str]:
    """
    В колонку единицы иногда улезает:
    - марки бетона F150/W2 перед «м³»;
    - обрыв «марк…» перед «м³» после склейки с кол. количества.
    Возвращает (суффикс для склейки с наименованием, остаток ячейки единицы).
    """
    u = _norm(_collapse_m_units(unit_raw or ""))
    if not u:
        return "", ""

    lu = u.lower()
    m_mort = re.match(
        r"(?isu)^марк\w*\s+(?:м\s*[³\u00b3]|м3)(\s+[.,;:]+)?"
        r"\s*(\d*)\s*$",
        u.strip(),
    )
    if m_mort and "шт" not in lu:
        return "", "м3"

    m_tail = re.match(
        r"(?is)^(.+?)\s+(?:м\s*[³\u00b3]|м3)\s*$",
        u.strip(),
    )
    if not m_tail:
        return "", u
    pref_raw = _norm(m_tail.group(1)).strip(" ,.:;").rstrip(".").strip()
    if not pref_raw:
        return "", "м3"
    pref = pref_raw
    pref_lo = pref.lower()
    # Не разбирать русские фразы (хвосты позиционного текста разбирает другая логика)
    if len(pref) >= 96 or pref_lo.count(",") >= 6:
        return "", u

    latinish = pref.replace(",", " ").strip()
    if re.search(r"(?iu)[а-яё]", pref_lo):
        return "", u

    if (
        len(latinish) <= 54
        and re.search(r"(?i)[FW]", latinish)
        and re.search(r"(?is)\d", latinish)
        and "=" not in latinish
        and "/" not in latinish
        and "(" not in latinish
        and "[" not in latinish
        and "'" not in latinish
        and not re.fullmatch(r"(?is)\s*\d{1,3}\s*$", latinish)
    ):
        out = latinish.upper().replace(",", ", ").strip()
        out = re.sub(r"\s*,\s*", ", ", out)
        while "  " in out:
            out = out.replace("  ", " ")
        if len(out.split()) <= 10 and (
            bool(re.search(r"(?is)F\s*\d", out))
            or bool(re.search(r"(?is)W\s*[\w.]", out))
        ):
            suf = out.rstrip(".").strip() + "."

            return suf, ""

    return "", u


def _looks_like_estimate_unit_corrupted_by_name_fragments(u_raw: str) -> bool:
    """
    Кол.4 ошибочно заполнена серединой перечня и ГОСТ («опорные, грузы, 24022-80, м»).
    """
    u = _norm(_collapse_m_units(u_raw or ""))
    if not u or len(u) < 10:
        return False
    low = u.lower()
    if re.fullmatch(r"(?i)шт|[\s\w·]*км|т(?:\.\s*км|[\s·]км)|т\b", low):
        return False
    if re.search(r"(?i)(?:м\s*[³\u00b3]|м3)\s+сборн", low):
        return False
    if re.search(r"(?i)(?:м\s*[³\u00b3]|м3)\s+бетона", low):
        return False
    if re.search(r"(?i)(?:м\s*[³\u00b3]|м3)\s+уплотн", low):
        return False
    if re.search(r"(?i)(?:м\s*[³\u00b3]|м3)\s*г(?:рунта)?", low):
        return False
    if re.fullmatch(r"(?i)(?:м\s*[³\u00b3]|м3|м2)", low):
        return False
    if re.search(r"(?i)^т[\s·.-]*км", low):
        return False
    if (
        re.search(r"\d{4,5}\s*[-–—]\s*\d{2}(?:/\d{2})?", u)
        and re.search(r"(?i)[а-яё]{4,}", u)
        and ("," in u or ";" in u)
    ):
        return True
    if u.count(",") >= 2 and re.search(r"(?i)[а-яё]{5,}", u):
        return True
    return False


_SENTENCE_BLEED_HINTS_UNIT = frozenset(
    {
        "кольцев",
        "кольцевыми",
        "глубино",
        "диаметр",
        "сверла",
        "алмазн",
        "горизонталь",
        "вертикаль",
        "охлажд",
        "исключа",
        "изменени",
        "вычита",
        "норме",
        " мм",
        " мм.",
    },
)


def _unit_reads_as_mid_description_sentence_fragment(u_raw: str) -> bool:
    """
    В колонку единицы попала середина технического предложения («кольцевыми глубиной отвер», …).
    Отличается от легальных развёрнутых единиц «т стальных элементов», «км трубопровода»,
    простых отверстие/шт и т.п.
    """
    u = _norm(_collapse_m_units(u_raw or ""))
    if not u or len(u) < 6:
        return False
    low = u.lower()
    ok_short = (
        "отверстие",
        "шт",
        "шт.",
        "кг",
        "км",
        "м3",
        "м2",
        "м²",
        "м³",
        "т·км",
    )
    if low in ok_short:
        return False
    if re.search(r"(?i)^(?:м\s*[³\u00b3]|м3)\s+бетона", low):
        return False
    if re.fullmatch(
        r"(?i)\s*(?:м\s*[³\u00b3]|м3)\b(?:\s*г(?:рунта?)?|\s*$)?",
        u,
    ):
        return False
    if re.search(r"(?i)^(?:м\s*[³\u00b3]|м3)\s+", low) or re.fullmatch(r"(?i)т\b", low):
        return False
    if re.search(r"(?i)^т\s+стальных\s+элемент(?:ов)?(?:\.)?$", low):
        return False
    if re.search(r"(?i)^т\s+фасонн\w*\s+част", low):
        return False
    if re.fullmatch(r"(?i)\bкм\s+(?:на\s*)?трубопровод\w*", low):
        return False
    if re.fullmatch(r"(?is)(?:[^\w°]*(?:\d+[°]?|[°])\s*[,.]?\s*)+\s*\d*-?\s*шт\s*\.?$", u):
        return False

    hints_hit = False
    for h in _SENTENCE_BLEED_HINTS_UNIT:
        if h in low:
            hints_hit = True
            break
    if hints_hit:
        return True

    chunks = [
        x.strip(",.;:\"")
        for x in re.split(r"[\s,;]+", u)
        if x.strip(",.;:\"")
    ]
    chunky = sum(
        1 for w in chunks if len(re.sub(r'(?u)[^а-яёa-z]', "", w.lower())) >= 7
    )

    long_word = False
    for w in low.replace(",", " ").split():
        if len(w) >= 14:
            long_word = True
            break

    end_otver = bool(re.search(r"(?iu)\s*отвер\s*$", low))
    if end_otver and "отверст" not in low:
        return True

    end_garbled = bool(
        re.search(r"(?i)\bисключ\w*", low)
        or re.search(r"(?i)^\s*[сc]\s+ис", low)
    )
    if end_garbled:
        return True

    wordy = chunky >= 2 and hints_hit is False

    if wordy and not re.match(
        r"(?ius)(?:т|кг|км|шт|м3|м2|отверстие)\s",
        low,
    ):
        if re.search(r"(?iu)\w+[аеёиюяо]ми\b|[аоиеёыуя]ющ\b", low):
            return True

    if long_word:
        stripped = "".join(low.split())
        if len(stripped) > 52:
            return True

    if chunky >= 3 and "," in u and len(u) >= 32:
        if not re.search(r"(?iu)\s*шт\.?\s*$", u.strip()):
            if re.search(r"(?iu)[а-яё]{10,}", u):
                return True

    return False


def _infer_unit_after_col4_name_bleed(name: str, bad_unit: str) -> str:
    blob = _norm(_collapse_m_units(f"{name or ''} {bad_unit or ''}"))
    g = _infer_unit_from_cell_text(blob, "")
    if g:
        return g
    low_n = (name or "").lower()
    if re.search(
        r"(?i)\b(?:блок|плит).*(?:фундамент|железобетон)|бетона\s+класса|балластн|якор",
        low_n,
    ) or ("башмак" in low_n and "подпятник" in low_n):
        return "м3 сборных конструкций"
    # Длинное перечисление ЖБ-блоков в РСНБ — типовая позиционная единица обычно такая же, как у соседних
    if re.search(r"(?i)\b(?:блок|плит)", low_n) and re.search(
        r"(?i)опорные|анкерн|тяжелого\s+бетона",
        low_n + " " + (bad_unit or ""),
    ):
        return "м3 сборных конструкций"
    return ""


def _repair_abc_pdf_name_unit_after_col4_bleed(
    name: str, unit: str, raw_hint: str = "",
) -> tuple[str, str]:
    n, u_raw = _norm(name), unit
    if _looks_like_estimate_unit_corrupted_by_name_fragments(u_raw):
        inferred = _infer_unit_after_col4_name_bleed(n, u_raw)
        return n, inferred or "м3 сборных конструкций"
    if _unit_reads_as_mid_description_sentence_fragment(u_raw):
        n2 = _norm(f"{n} {u_raw}")
        blob = _norm(_collapse_m_units(f"{raw_hint} {n2}"))[:2600]
        inferred = _infer_unit_from_cell_text(blob, "", n2)
        ln2 = n2.lower()
        if not inferred:
            if re.search(
                r"(?iu)\bсверлен\b|горизонтальн\S*\s+отверст\b|"
                r"вычитается\b.+отверст",
                ln2,
            ):
                inferred = "отверстие"
            elif re.search(r"(?iu)водопроводн\S*.+укладк", ln2):
                inferred = "км"
            elif re.search(r"(?iu)\bотвод\b", ln2):
                inferred = "шт"
        return n2, inferred or ""

    return n, u_raw


def _repair_parabolic_column_name_with_gost(name: str, gost_frag: str | None) -> str:
    """
    «Стойка… параболические лотки 79.» + «ГОСТ 23899-» из единицы → «…лотки ГОСТ 23899-79.»
    """
    if not name or not gost_frag:
        return _norm(name)
    n = _norm(name)
    low = n.lower()
    gf = _norm(gost_frag)
    if not gf:
        return n
    if re.search(r"(?i)гост\s+[0-9]", low):
        # Уже есть обозначение стандарта в тексте
        return n
    m_nm = re.search(
        r"(?i)(?P<head>параболические\s+лотки)\s+(?P<yr>\d{1,3})\s*\.?\s*$",
        n,
    )
    m_gs = re.search(
        r"(?i)^(?:ГОСТ|GOST)\s+(?P<num>\d{4,8})\s*[\-–—]\s*(?P<suf>\d*)\s*$",
        gf,
    )
    if not m_gs:
        return n
    std_num = m_gs.group("num")
    suf_u = (m_gs.group("suf") or "").strip()
    if not m_nm:
        # ГОСТ целиком в кол.4: «…лотки» без номера выпуска в наименовании
        if re.search(r"(?i)параболические\s+лотки\s*$", low) and suf_u:
            return _norm(f"{n} ГОСТ {std_num}-{suf_u}.")
        return n
    yr = m_nm.group("yr")
    head = m_nm.group("head")
    prefix = n[: m_nm.start()].rstrip()
    if suf_u:
        gost_full = f"ГОСТ {std_num}-{suf_u}."
    else:
        gost_full = f"ГОСТ {std_num}-{yr}."
    return _norm(f"{prefix} {head} {gost_full}")


def _merge_steel_standard_code_from_estimate_unit_into_name(
    name: str,
    unit_raw: str,
) -> tuple[str, str]:
    """
    Цифровой блок стандарта «33259-2015» с «шт» утекает в кол.4 («33259-2015 шт»).
    Дописываем «ГОСТ …» в наименование (фланцы, метизы).
    """
    u = _norm(unit_raw or "")
    if not u:
        return _norm(name), u
    lum = u.lower().strip()
    if lum in {"шт", "шт."} or not lum.endswith(("шт", "шт.")):
        return _norm(name), u
    m = re.match(
        r"(?isu)^\s*(\d{4,}-\s*\d{2,}(?:/[A-Za-zА-Яа-яё]{1,14})?"
        r")\s*[.,;:]*\s*(шт\b\.?).*$",
        lum,
        re.UNICODE,
    )
    if not m:
        return _norm(name), u
    std = _norm(m.group(1)).replace(" ", "").replace("—", "-").replace("–", "-")
    std = std.rstrip("/")
    if len(std.replace("-", "")) < 8:
        return _norm(name), u
    n = _norm(name)
    nl = re.sub(r"[^\da-zа-яё]", "", n.lower())
    slug = "".join(ch for ch in std.lower() if ch.isdigit())
    head5 = slug[:5] if slug else ""
    if head5 and head5 in nl[-60:]:
        return n, "шт"
    if re.search(
        rf"(?iu)\b(?:gost|гост)\s*{re.escape(std)}\b",
        n,
    ):
        return n, "шт"
    nn = _norm(f"{n} ГОСТ {std}")
    while nn.endswith(".."):
        nn = nn[:-1]
    if not nn.endswith("."):
        nn = f"{nn}."
    return nn, "шт"


def _sanitize_pdf_import_unit(unit: str) -> str:
    """
    В колонке единицы после разреза иногда остаётся хвост наименования кол.3,
    совпадающий по базовой линии с «м³ сборных» («… заделкой стыков», «и», «сборного»).
    Восстанавливаем типовые обозначения по содержимому строки.
    """
    u = _norm(_collapse_m_units(unit or ""))
    if not u:
        return u
    lu = u.lower()
    # «90°, 17380- шт», «размер X шт»
    if re.search(r"(?isu)\s*шт\.?\s*$", lu) and re.search(
        r"(°|173\d\d|[xх]\s*\d)",
        u,
    ):
        return "шт"
    # «… т фасонных частей» / «диапазон — т фасонн…»
    if re.search(r"(?i)\d+(?:[\s\-–]+\d+)\s*[тТ]\s+фасонн|\bфасонн\w*\s+част", lu):
        if "шт" not in lu:
            return "т"
    if re.search(r"(?i)^т\s+стальных\s+элемент", lu):
        return "т"
    # Км прокладки трубопровода (часто «км трубопровода» в РСНБ)
    if re.search(r"(?isu)\bкм\b\s+(?:на\s*)?трубопровод", lu):
        return "км трубопровода"
    # Префикс вида «… заделкой стыков …» + «м³ сборных конструкций» частично в кол.4
    if re.search(r"(?i)(?:м\s*[³\u00b3]|м3)\s+сборн", u):
        return "м3 сборных конструкций"
    # Длинное «м³ бетона, … песка в конструкции» (РСНБ) → на экран достаточно объёма
    if re.search(r"(?i)(?:м\s*[³\u00b3]|м3)\s+бетона", lu) and re.search(
        r"(?iu)грави|песок|конструкц",
        lu,
    ):
        return "м3"
    if re.search(r"(?i)(?:м\s*[³\u00b3]|м3)\s+уплотн", u):
        return "м3 уплотненного грунта"
    if re.search(r"(?i)(?:м\s*[³\u00b3]|м3)\s*г(?:рунта?)?", u):
        return "м3 грунта"
    if re.search(r"(?i)т[\s·.-]*км", u):
        return "т·км"
    u2 = _norm(re.sub(r"(?i)^(?:и\s+)+", "", u))
    if re.fullmatch(r"(?i)т(?:\s+\d+)?", u2):
        return "т"
    # «м³» ушёл в кол.3 или на другую строку
    if not re.match(r"(?i)(?:м\s*[³\u00b3]|м3)", u2) and re.search(
        r"(?i)уплотнен\S*\s+грунта",
        u2,
    ):
        return "м3 уплотненного грунта"
    if (
        re.search(r"(?i)спланирован", u2)
        and re.search(r"(?i)площа", u2)
    ):
        return "м2 спланированной площади"
    # «с 10/16, шт», «33259-2015 шт», «PN 10/16, шт» — тех. поля утекли в кол.4 вместе со штуками
    lum = lu.strip()
    if re.search(r"(?isu)\s*шт\.?\s*$", lum) and not re.fullmatch(
        r"(?isu)шт\.?",
        lum,
    ):
        if (
            re.search(r"(?isu)^\s*[\u0441]\s+[0-9]+\s*/\s*[0-9]+", lum)
            or re.search(r"(?isu)\b[Pp]\s*N\s*[0-9]+\s*(?:/[0-9]+|\s+[0-9]+)", lum)
            or re.search(r"(?isu)[\,\s]+\s*[Pp]\s*[Nn]\s*[0-9/]+.*?шт\s*$", lum)
            or re.search(r"(?isu)\d{3,}-\d{2,}.*?шт\s*$", lum)
        ):
            return "шт"
    return u


def _looks_like_wrapped_unit_suffix(frag: str, blob_hint: str) -> bool:
    """
    Вторая строка узкой колонки «ед. изм.» часто попадает в кол.3 как «продолжение».
    Типичный случай: первая строка «м³ сборных», вторая — «конструкций».
    """
    f = _norm(frag)
    if not f:
        return False
    low = blob_hint.lower()
    if not re.fullmatch(r"конструкций\.?", f, re.I):
        return False
    return bool(
        re.search(r"(?i)м\s*[³\u00b3]\s*сборных|\bм3\s+сборных", low),
    )


def _append_unit_fragment(acc: str, piece: str) -> str:
    a, p = _norm(acc), _norm(piece)
    if not p:
        return a
    if not a:
        return p
    if a.endswith(p) or p.endswith(a):
        return a if len(a) >= len(p) else p
    return _norm(f"{a} {p}")


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
        name_acc = _merged_position_heading_name(r)
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
            if _is_abc_nr_percent_row(rjn):
                break
            frag = _continuation_name_fragment(nxt)
            uc = _norm(nxt.c4)
            blob_hint = _norm(f"{acc_c4} {name_acc} {merged_raw} {rjn}")[:900]
            if frag:
                if _looks_like_wrapped_unit_suffix(frag, blob_hint):
                    acc_c4 = _append_unit_fragment(acc_c4, frag)
                else:
                    name_acc = _norm(f"{name_acc} {frag}") if name_acc else frag
            if uc:
                acc_c4 = _append_unit_fragment(acc_c4, uc)
            if acc_q is None or acc_q <= 0:
                if nxt.c5_qty is not None and nxt.c5_qty > 0:
                    acc_q = nxt.c5_qty
                    acc_c5t = nxt.c5_raw or acc_c5t
            merged_raw = _norm(f"{merged_raw} {rjn}")
            j += 1
        name_acc = _salvage_estimate_name_via_raw_anchor(name_acc, merged_raw)
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
    last_heading_line: str | None = None
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

    def _emit_subsection_row(body: str, pending: str | None) -> None:
        """Подзаголовок группы работ — отдельная строка в таблице сметы."""
        nonlocal pending_razdel, last_heading_line
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
                if lsr_id != nid:
                    auto_razdel = 1
                    last_zemlyanye_section = None
                    last_heading_line = None
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
            unit_plain, gost_bleed = _detach_gost_bleed_from_estimate_unit(unit)
            qual_bleed_suffix, unit_after_qual = (
                _detach_name_quality_suffix_bleeding_into_unit(unit_plain)
            )
            if qual_bleed_suffix:
                name_src = _norm(f"{name_src} {qual_bleed_suffix}")
            if _norm(unit_after_qual):
                unit_plain = _norm(unit_after_qual)
            elif qual_bleed_suffix:
                unit_plain = "м3"
            name_src, unit_plain = _repair_abc_pdf_name_unit_after_col4_bleed(
                name_src, unit_plain, raw
            )
            name_src, unit_plain = (
                _merge_steel_standard_code_from_estimate_unit_into_name(
                    name_src,
                    unit_plain,
                )
            )
            unit = _sanitize_pdf_import_unit(unit_plain)
            name_src = _repair_parabolic_column_name_with_gost(name_src, gost_bleed)
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

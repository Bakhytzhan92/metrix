from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Iterator, Union

import pdfplumber

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

# Позиция: 1 1137-0401-0203 Текст…  или  1. 1101-0104-0201 …
RE_POS = re.compile(
    r"^(\d{1,4})\.?\s+"
    r"((?:\d+-\d+-\d+)(?:'[0-9+,\s.]+'[0-9'+\s.]*)?)\s*"
    r"(.*)$"
)
RE_NAIM_OBJ = re.compile(
    r"^Наименование\s+объекта\s*[-–—:]\s*(.+?)\s*$",
    re.IGNORECASE,
)


def _normalize_re_pos_line(
    s: str,
) -> str:
    """
    В ABC-выписке иногда печатают «17 С3412-…» (кир. «С»), из‑за чего
    шифр не сходится с шаблоном цифр-дефис-цифр. Убираем лишний префикс
    у типичного «3412-102-0312».
    """
    return re.sub(
        r"^(\d{1,4}\.?\s+)[\u0421C](?=\d{3,4}-\d+-\d+)",
        r"\1",
        s.strip(),
    )

RE_TABLE_COLS = re.compile(
    r"^\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+\d{1,2}\s+"
    r"[\d-]"
)

RE_SECTION = re.compile(
    r"^(?:КАНАЛ|П КАНАЛ)|\(ГР-\d+\)|"
    r"ДЕМОНТАЖНЫЕ РАБОТЫ|СТРОИТЕЛЬНЫЕ РАБОТЫ|МОНТАЖНЫЕ РАБОТЫ|"
    r"ЗЕМЛЯНЫЕ РАБОТЫ|КОНЦЕВОЙ КОЛОДЕЦ|ЛОТКОВЫЙ КАНАЛ",
    re.IGNORECASE,
)
RE_RAZDEL = re.compile(
    r"^РАЗДЕЛ\s*(\d+)\s*[\.\:]\s*(.+?)\s*$",
    re.IGNORECASE,
)
# та же сущность, для подстроки (без $ — переносы в PDF)
RE_RAZDEL_INNER = re.compile(
    r"^РАЗДЕЛ\s*\d+\s*[\.\:]",
    re.IGNORECASE,
)
RE_LSR_NO = re.compile(
    r"№\s*([\d\.\-]+)\s*",
    re.IGNORECASE,
)

RE_SKIP = re.compile(
    r"^(?:РСНБ|НР\s|СП\s-?|Кзтр|1\s+2\s+3|"
    r"№\s*Шифр|Наименование работ|п/п|"
    r"Программный комплекс|Форма\s|Страниц|"
    r"Составлен\(|Составлена\(|"
    r"Сметная заработн|Сметн)",
    re.IGNORECASE,
)

RE_SKIP_NAME = re.compile(
    r"^НР\s*-\s*\d|"
    r"^СП\s*-\s*\d|"
    r"^--\s+--\s*",
    re.IGNORECASE,
)

RE_REG_FALLBACK = re.compile(
    r"([^\n]{12,1000}?\S)\s+"
    r"(м2|м3|м²|м³|шт|кг|т|т·км|т\.км)\s+"
    r"(-?[0-9][0-9\s,]*[,.]?\d*)\b",
    re.IGNORECASE,
)

MAX_QTY = 1_000_000.0  # в локальной смете количество обычно существенно меньше

# Коэффициенты (Кзтр=1,2, Кэм=1,04) идут сразу после «=» и не являются количеством
_EQ_COEFF_MAX = 2.5


def _is_equals_coefficient_decimal(
    sl: str, dec_start: int, q: float
) -> bool:
    """
    True, если десятичное сразу после «=» в диапазоне коэффициентов (Kэм, Kзтр).
    Тогда это не количество по АВС.
    """
    if dec_start < 1 or sl[dec_start - 1] != "=":
        return False
    return 0.0001 < abs(q) < _EQ_COEFF_MAX


def _norm(s: str) -> str:
    s = s.replace("\u00a0", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s.strip())
    return s


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


def _is_noise_line(low: str) -> bool:
    if not _norm(low):
        return True
    return any(w in low for w in STOP_SUBSTR)


def _is_end(ln: str, low: str) -> bool:
    t = low.strip()
    for ex in END_EXACT:
        if t == ex or (
            t.startswith(
                ex + " "
            )
            and ex != "материалы"
        ):
            return True
    for px in END_PREFIX:
        if t.startswith(px):
            return True
    if t.startswith("материал") and len(
        t
    ) < 35 and "тенге" not in t and "тыс" not in t:
        return True
    return False


def _is_lsr_start(low: str) -> bool:
    return any(k in low for k in START_KEYWORDS)


def _format_section(lsr: str | None, body: str) -> str:
    t = _norm(
        body
    )
    if lsr:
        return f"ЛС № {lsr} | {t}"
    return t


def _try_m23_loose_qty(
    s: str,
) -> tuple[str, float] | None:
    """
    «м3 грунта 8012 93,88» — 8012 шифр норм/ресурса; кол-во с запятой
    (или не «код» 1000–99999) берём после м2/м3. Ед. изм. может стоять
    в конце строки («грунтов 2. м2») — отрезаем с первого м2/м3.
    """
    sl0 = s.strip()
    mpos = re.search(
        r"(м2|м3|м²|м³)(?:\b|[.·])",
        sl0,
        re.IGNORECASE,
    )
    if mpos is not None and mpos.start() > 0:
        sl0 = sl0[
            mpos.start() :
        ]
    sl = sl0
    m = re.match(
        r"^(м2|м3|м²|м³)(?:\b|[.·])\s*",
        sl,
        re.IGNORECASE,
    )
    if not m or re.search(
        r"сборн",
        s[:30],
    ):
        return None
    u = m.group(1)
    u = u.replace("м²", "м2").replace("м³", "м3")
    for mdec in re.finditer(
        r"\b[0-9]+,[0-9]{1,4}\b",
        sl,
    ):
        dec_s = mdec.group(0)
        q = _fnum(
            dec_s
        )
        if not q or not (0.0001 < abs(q) < MAX_QTY):
            continue
        if _is_equals_coefficient_decimal(
            sl, mdec.start(), q
        ):
            continue
        return u, q
    for mdec in re.finditer(
        r"\b[0-9]{1,4}\.[0-9]{1,4}\b",
        sl,
    ):
        dec_s = mdec.group(0)
        q = _fnum(
            dec_s
        )
        if not q or not (0.0001 < abs(q) < MAX_QTY):
            continue
        if _is_equals_coefficient_decimal(
            sl, mdec.start(), q
        ):
            continue
        return u, q
    for mnum in re.finditer(
        r"\b[0-9]+\b",
        sl,
    ):
        a, b = mnum.start(), mnum.end()
        if b < len(
            sl
        ) and sl[
            b
        ] == ",":
            continue
        if a > 0 and sl[
            a - 1
        ] == ",":
            continue
        num_s = mnum.group(
            0
        )
        if not num_s or not num_s.isdigit():
            continue
        n = int(
            num_s
        )
        if 1000 <= n <= 99999:
            continue
        q = _fnum(
            num_s
        )
        if q and 0.0001 < abs(
            q
        ) < MAX_QTY:
            return u, q
    return None


def _is_section(ln: str) -> bool:
    l = ln.lower()
    if "локальн" in l:
        return False
    if re.match(r"^1\s+2\s+3", ln) or len(ln) < 8:
        return False
    if RE_SECTION.search(ln) or re.search(r"\(ГР-\d+\)", ln):
        return True
    return False


def _iter_lines(pdf) -> list[str]:
    out: list[str] = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        for raw in text.splitlines():
            out.append(raw)
    return out


def _unit_qty_from_line(s: str) -> tuple[str, float] | None:
    """
    Одна строка АВС с единицей и количеством: берём **первое** число объёма
    (не цены: после него идут «крупные» суммы, их отсекаем по MAX_QTY).
    """
    sl = s.lower().strip()
    if "тенге" in sl or (("тыс" in sl) and ("т" in sl[:3])):
        return None

    m_k = re.match(
        r"^конструкций\s+"
        r"([0-9]+(?:[.,][0-9]+)?)\b",
        sl,
    )
    if m_k:
        q = _fnum(
            m_k.group(1)
        )
        if q:
            return "м3 сборных конструкций", q
        return None

    if s.startswith("т·км") or re.match(
        r"^т·км[.\s]",
        s,
    ):
        m = re.match(
            r"^т·км[.\s]+"
            r"([0-9]+(?:[.,][0-9]+)?)\b",
            s,
        )
        if m:
            q = _fnum(
                m.group(1)
            )
            if q:
                return "т·км", q
        return None

    if re.match(
        r"^т[.\s]([0-9\-])",
        s
    ) and "чел" not in sl and "тенг" not in sl:
        m = re.match(
            r"^т[.\s]+"
            r"([0-9]+(?:[.,][0-9]+)?)\b",
            s,
        )
        if m:
            q = _fnum(
                m.group(1)
            )
            if q:
                return "т", q
        return None

    s_vol = s
    m_vol = re.search(
        r"(м2|м3|м²|м³|кг|шт)(?:\b|[.·])",
        s,
        re.IGNORECASE,
    )
    if m_vol and m_vol.start() > 0 and m_vol.group(
        1
    ).lower().startswith(
        "м"
    ):
        s_vol = s[
            m_vol.start() :
        ]
    m = re.match(
        r"^(м2|м3|м²|м³|кг|шт)\.?\s+"
        r"([0-9]+(?:[.,][0-9]+)?)\b",
        s_vol,
        re.IGNORECASE,
    )
    if m and not re.search(
        r"сборн",
        s[:20],
    ):
        u = m.group(1)
        u = u.replace("м²", "м2").replace("м³", "м3")
        q = _fnum(
            m.group(2)
        )
        if q:
            return u, q
    t = _try_m23_loose_qty(
        s_vol
    )
    if t:
        return t
    return None


def _is_abc_sp_or_nr_subline(sll: str) -> bool:
    """Подстрока СП/НР той же позиции (АВС), ещё не «Итого по смете»."""
    t = sll.strip().lower()
    if not t or t.startswith("итого") or t.startswith("всего "):
        return False
    if re.match(
        r"^сп\s*[-–—]",
        t,
    ) or re.match(
        r"^сп\s*-\s*8\%",
        t,
    ):
        return True
    if re.match(
        r"^нр\s*[-–—]",
        t,
    ) or re.match(
        r"^нр\s*-\s*\d",
        t,
    ):
        return True
    if t.startswith("нр") and "сп" in t and "%" in t:
        return True
    return False


def _skip_abc_sp_nr_after_qty(
    i: int, lines: list[str], n: int
) -> int:
    while i < n and _is_abc_sp_or_nr_subline(
        _norm(lines[i]).lower()
    ):
        i += 1
    return i


@dataclass
class _Row:
    name: list[str] = field(
        default_factory=list
    )
    shifr: str = ""
    unit: str = ""
    qty: float | None = None
    m3_lead: str = ""


def _flush(
    row: _Row | None, section: str | None, dedupe: set
) -> list[dict[str, Any]]:
    if not row or row.qty is None:
        return []
    name = _norm(" ".join(row.name))
    if row.m3_lead and "конструкц" in (row.unit or "").lower():
        unit = "м3 сборных конструкций"
    elif row.m3_lead and row.unit:
        unit = _norm(f"{row.m3_lead} {row.unit}")
    else:
        unit = _norm(row.unit or row.m3_lead)
    if not name or len(
        name
    ) < 2 or not unit or len(
        unit
    ) < 1:
        return []
    if name.lower().count(
        "тенге"
    ) or "тыс" in name.lower()[:5]:
        return []
    dedup_name = (
        f"{row.shifr}\x1f{name.lower()}"
        if row.shifr
        else name.lower()
    )
    k = (section, dedup_name, unit.lower(), round(row.qty, 4))
    if k in dedupe:
        return []
    dedupe.add(k)
    return [
        {
            "section": section,
            "name": name[:500],
            "unit": unit[:80],
            "quantity": row.qty,
        }
    ]


def parse_lines_abc(
    lines: list[str], dedupe: set
) -> list[dict[str, Any]]:
    in_lsr = False
    section: str | None = None
    lsr_id: str | None = None
    object_name: str | None = None
    auto_razdel: int = 1
    pending_razdel: str | None = None
    cur: _Row | None = None
    out: list[dict] = []
    i, n = 0, len(
        lines
    )
    while i < n:
        raw = lines[i]
        low = raw.lower(
        )
        if _is_lsr_start(
            low
        ):
            in_lsr = True
        if not in_lsr:
            i += 1
            continue
        if _is_end(
            raw, low
        ):
            out.extend(
                _flush(
                    cur, section, dedupe
                )
            )
            cur = None
            in_lsr = False
            pending_razdel = None
            object_name = None
            auto_razdel = 1
            i += 1
            continue
        if _is_noise_line(
            low
        ):
            i += 1
            continue
        if re.match(
            r"^всего\s*$|"
            r"^итого\s*$",
            low.strip(),
        ):
            i += 1
            continue
        if re.match(
            r"^1\s+2\s+3",
            low.strip(
            )
        ) or re.match(
            r"^№\s*п/п|"
            r"^№\s*шифр|"
            r"^наименование работ|"
            r"^шифр норм",
            low,
        ) or re.search(
            r"шифр норм,",
            low,
        ):
            i += 1
            continue
        if (
            RE_TABLE_COLS.match(
                raw.strip()
            )
            and "шифр" not in low
        ):
            i += 1
            continue
        nline = _norm(
            raw
        )
        m_obj = RE_NAIM_OBJ.match(
            nline
        )
        if m_obj:
            object_name = m_obj.group(
                1
            ).strip()[:200] or object_name
            i += 1
            continue
        if in_lsr and "локальная смета" in low:
            m_no = RE_LSR_NO.search(
                raw
            )
            if m_no:
                nid = m_no.group(
                    1
                ).strip()[:32]
                if lsr_id != nid:
                    auto_razdel = 1
                lsr_id = nid
        m_raz = RE_RAZDEL.match(
            nline
        )
        if m_raz and in_lsr:
            out.extend(
                _flush(
                    cur, section, dedupe
                )
            )
            cur = None
            rnum = m_raz.group(
                1
            )
            rtitle = m_raz.group(
                2
            ).strip()
            pending_razdel = (
                f"РАЗДЕЛ {rnum}. {rtitle}"[:200]
            )
            try:
                auto_razdel = int(
                    rnum
                ) + 1
            except (
                ValueError
            ):
                pass
            i += 1
            continue
        if _is_section(
            nline
        ) and not RE_POS.match(
            _normalize_re_pos_line(
                nline
            )
        ):
            out.extend(
                _flush(
                    cur, section, dedupe
                )
            )
            cur = None
            if pending_razdel:
                body = f"{pending_razdel}  {nline.strip()}"
                pending_razdel = None
            elif lsr_id and object_name and re.search(
                r"ЗЕМЛЯНЫЕ|ГР-",
                nline,
                re.I,
            ):
                body = (
                    f"РАЗДЕЛ {auto_razdel}. {object_name}  {nline.strip()}"
                )
                auto_razdel += 1
            else:
                body = nline.strip()
            section = _format_section(
                lsr_id, body
            )[:255]
            i += 1
            continue
        npos = _normalize_re_pos_line(
            nline
        )
        m = RE_POS.match(
            npos
        )
        if m:
            out.extend(
                _flush(
                    cur, section, dedupe
                )
            )
            rest = m.group(
                3
            ) or ""
            shf = (m.group(2) or "").strip(
            )[:32]
            cur = _Row(
                name=[rest] if rest and not RE_SKIP.match(
                    rest
                ) else [],
                shifr=shf,
            )
            i += 1
            while i < n:
                s = _norm(
                    lines[i]
                )
                sl = s.lower(
                )
                if _is_end(
                    s, sl
                ):
                    break
                if RE_POS.match(
                    _normalize_re_pos_line(
                        s
                    )
                ):
                    break
                if RE_RAZDEL_INNER.match(
                    s
                ):
                    break
                if _is_section(
                    s
                ) and not re.match(
                    r"^т[.\s·]",
                    s,
                ) and not re.match(
                    r"^т·км",
                    s
                ) and not re.match(
                    r"^м3",
                    s,
                ):
                    break
                if RE_SKIP.match(
                    s
                ) and re.search(
                    r"РСНБ\s+РК",
                    s,
                ):
                    tail = re.sub(
                        r"^РСНБ\s+РК\s*\d{4}\s*",
                        "",
                        s,
                    )
                    if tail and cur is not None:
                        cur.name.append(
                            tail
                        )
                    i += 1
                    continue
                if re.match(
                    r"^Кзтр\b",
                    s,
                    re.IGNORECASE,
                ) and cur is not None:
                    # только хвост после РСНБ (м2/м3 в конце), не шапка с «1000 м3» и т.п.
                    merge_from_name: str | None = None
                    nb0 = (cur.name or [])[
                        -1
                    ] if cur.name else None
                    if (
                        nb0
                        and re.search(
                            r"м2|м3|м²|м³",
                            nb0,
                            re.IGNORECASE,
                        )
                    ):
                        merge_from_name = _norm(
                            f"{nb0} {s}"
                        )
                    if merge_from_name:
                        uq_k = _unit_qty_from_line(
                            merge_from_name
                        )
                        acc_k = merge_from_name
                        jk = i
                        for _mk in range(
                            4
                        ):
                            if uq_k and uq_k[1]:
                                break
                            if jk + 1 >= n:
                                break
                            jk += 1
                            acc_k = _norm(
                                f"{acc_k} {_norm(lines[jk])}"
                            )
                            uq_k = _unit_qty_from_line(
                                acc_k
                            )
                        if (
                            not uq_k or not uq_k[1]
                        ) and re.search(
                            r"м2|м3|м²|м³",
                            acc_k,
                            re.IGNORECASE,
                        ):
                            u2k = _try_m23_loose_qty(
                                acc_k
                            )
                            if u2k and u2k[1]:
                                uq_k = (u2k[0], u2k[1])
                        if uq_k and uq_k[1]:
                            cur.unit, cur.qty = uq_k[0], uq_k[1]
                            i = jk + 1
                            i = _skip_abc_sp_nr_after_qty(
                                i, lines, n
                            )
                            break
                if (
                    RE_SKIP.match(
                        s
                    ) or _is_noise_line(
                        sl
                    ) or RE_SKIP_NAME.match(
                        s
                    )
                ):
                    i += 1
                    continue
                if re.match(
                    r"^м3\s*сборн|"
                    r"^м2\s*сборн",
                    sl
                ) and cur is not None and not cur.m3_lead:
                    cur.m3_lead = s
                    i += 1
                    if i < n and cur:
                        s2 = _norm(
                            lines[i]
                        )
                        uq = _unit_qty_from_line(
                            s2
                        )
                        if (
                            uq
                            and uq[1] > 0
                        ):
                            cur.unit, cur.qty = uq[0], uq[1]
                            i += 1
                            i = _skip_abc_sp_nr_after_qty(
                                i, lines, n
                            )
                            break
                    continue
                uq = _unit_qty_from_line(
                    s
                ) if s else None
                acc2 = s
                j2 = i
                stp = s.strip() if s else ""
                m23_merge = (
                    s
                    and (not uq or not uq[1])
                    and not re.search(
                        r"0,25\s*м3|0\.25\s*м3",
                        stp,
                        re.I,
                    )
                    and (
                        re.match(
                            r"^\s*м2|^\s*м3",
                            s,
                            re.I,
                        )
                        or re.search(
                            r"(?i)м2\s*$",
                            stp,
                        )
                        or re.match(
                            r"^\s*м3\s*$|^\s*м2\s*$",
                            stp,
                            re.I,
                        )
                    )
                )
                if m23_merge:
                    for _m in range(
                        4
                    ):
                        uq = _unit_qty_from_line(
                            acc2
                        )
                        if uq and uq[1]:
                            i = j2
                            break
                        if j2 + 1 >= n:
                            break
                        j2 += 1
                        acc2 = _norm(
                            f"{acc2} {_norm(lines[j2])}"
                        )
                    if (not uq or not uq[1]) and acc2 and re.search(
                        r"м2|м3",
                        acc2,
                        re.I,
                    ):
                        u2 = _try_m23_loose_qty(
                            acc2
                        )
                        if u2 and u2[1]:
                            uq = (u2[0], u2[1])
                            i = j2
                if uq and cur and uq[1]:
                    cur.unit, cur.qty = uq[0], uq[1]
                    i += 1
                    i = _skip_abc_sp_nr_after_qty(
                        i, lines, n
                    )
                    break
                if re.search(
                    r"===\s*PAGE|"
                    r"^Страниц\s",
                    s,
                ):
                    i += 1
                    continue
                if cur and not (
                    re.match(
                        r"^м3\s*сборн",
                        sl
                    ) or re.match(
                        r"^м2\s*сборн",
                        sl
                    )
                ) and s:
                    if not RE_SKIP_NAME.match(
                        s
                    ) and not re.match(
                        r"^т[.\s][0-9]",
                        s
                    ) and "т·км" not in s[:6]:
                        cur.name.append(
                            s
                        )
                i += 1
            out.extend(
                _flush(
                    cur, section, dedupe
                )
            )
            cur = None
            continue
        i += 1
    out.extend(
        _flush(
            cur, section, dedupe
        )
    )
    return out


def _regex_fallback(
    text: str, section: str | None, dedupe: set
) -> list[dict[str, Any]]:
    out: list[dict] = []
    t = re.sub(
        r"\s+",
        " ",
        text
    )
    for m in RE_REG_FALLBACK.finditer(
        t
    ):
        name = _norm(
            m.group(1)
        )
        u = m.group(2)
        q = _fnum(
            m.group(3)
        )
        if not q or _is_noise_line(
            name.lower(
            )
        ):
            continue
        k = (section, name[:400].lower(), u.lower(), round(q, 4))
        if k in dedupe:
            continue
        dedupe.add(k)
        out.append(
            {
                "section": section,
                "name": name[:500],
                "unit": u,
                "quantity": q,
            }
        )
    return out


def _open_src(
    file: Union[str, os.PathLike, bytes, bytearray, BinaryIO],
) -> bytes:
    if isinstance(
        file, (str, os.PathLike)
    ):
        with open(
            os.fspath(
                file
            ),
            "rb",
        ) as f:
            return f.read(
            )
    if isinstance(
        file, (bytes, bytearray)
    ):
        return bytes(
            file
        )
    d = file.read(
    )
    if isinstance(
        d, str
    ):
        d = d.encode(
            "utf-8"
        )
    if isinstance(
        d, (bytes, bytearray)
    ):
        return bytes(
            d
        )
    return b""


def parse_local_estimate(
    file: Union[str, os.PathLike, bytes, bytearray, BinaryIO],
) -> list[dict[str, Any]]:
    data = _open_src(
        file
    )
    dedupe: set = set(
    )
    with pdfplumber.open(
        io.BytesIO(
            data
        )
    ) as pdf:
        line_list = _iter_lines(
            pdf
        )
        res = parse_lines_abc(
            line_list, dedupe
        )
        if not res:
            with pdfplumber.open(
                io.BytesIO(
                    data
                )
            ) as pdf2:
                full = " ".join(
                    _iter_lines(
                        pdf2
                    )
                )
            res = _regex_fallback(
                full, None, dedupe
            )
    for r in res:
        if r.get(
            "section"
        ) is None:
            r["section"] = "Локальная смета"
    return res


__all__ = [
    "parse_local_estimate",
    "START_KEYWORDS",
    "END_KEYWORDS",
]

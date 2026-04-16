from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

# Ограничение на объём текста для API (символов)
MAX_TEXT_CHARS = 120_000

PROJECT_TYPE_LABELS = {
    "residential": "жилой дом",
    "commercial": "коммерческий объект",
    "renovation": "ремонт / реконструкция",
}


def generate_project_plan(text: str, project_type: str = "residential") -> dict[str, Any]:
    """
    Отправляет текст сметы/проекта в OpenAI, возвращает распарсенный JSON с этапами и задачами.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Не задана переменная окружения OPENAI_API_KEY")

    type_label = PROJECT_TYPE_LABELS.get(project_type, project_type)
    trimmed = text[:MAX_TEXT_CHARS]
    if len(text) > MAX_TEXT_CHARS:
        trimmed += "\n\n[… текст обрезан для анализа …]"

    prompt = f"""Ты строительный инженер. Тип объекта заказчика: {type_label}.
На основе приведённого ниже текста сметы или проектной документации составь план работ.

Текст документа:
---
{trimmed}
---

Составь:
1. Этапы строительства (список)
2. Для каждого этапа:
   - список задач
   - примерная длительность каждой задачи (в днях, целое число ≥ 1)
   - зависимости: список имён задач (name), от которых зависит данная задача (если нет — пустой массив)
3. У каждой задачи поле type одно из: materials | labor | machinery (материалы | работы людей | техника)

Ответ верни строго в JSON формате без markdown и пояснений:
{{
  "stages": [
    {{
      "name": "",
      "tasks": [
        {{
          "name": "",
          "duration_days": 0,
          "type": "materials",
          "depends_on": []
        }}
      ]
    }}
  ]
}}
"""

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Ты помощник по строительному планированию. Отвечай только валидным JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    raw = (response.choices[0].message.content or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            return json.loads(m.group(0))
        raise

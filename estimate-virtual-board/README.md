# Виртуализация таблицы «Смета»

Сборка **React + react-window → IIFE**, выход в статику Django:

`backend/core/static/core/estimate/virtual-table.js`

После правок во `src/`:

```bash
npm install
npm run build
```

Порог включения виртуального режима: `ESTIMATE_VIRTUAL_ROW_THRESHOLD` в `backend/core/views.py` (по умолчанию 120 строк включая подзаголовки).

# Виртуализация «График работ»

Сборка **React + react-window → IIFE**, выход в статику Django:

`backend/core/static/core/schedule/virtual-gantt.js`

```bash
npm install
npm run build
```

Порог включения: `SCHEDULE_VIRTUAL_ROW_THRESHOLD` в `backend/core/views.py`.

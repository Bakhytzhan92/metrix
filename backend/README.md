# Metrix SaaS (Django + PostgreSQL + Tailwind)

Минимальное SaaS‑приложение: проекты, задачи, финансы, склад, отчёты.

## Запуск локально

1. **Создать и активировать виртуальное окружение**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS
```

2. **Установить зависимости**

```bash
pip install -r ../requirements.txt
```

3. **Настроить базу данных PostgreSQL**

- Создайте БД `Metrix_saas` и пользователя/пароль в PostgreSQL.
- Установите переменную окружения `DATABASE_URL`, например:

```bash
set DATABASE_URL=postgres://postgres:postgres@localhost:5432/gectaro_saas  # Windows PowerShell: $env:DATABASE_URL="..."
```

4. **Применить миграции и создать суперпользователя**

```bash
python manage.py migrate
python manage.py createsuperuser
```

5. **Запустить дев‑сервер**

```bash
python manage.py runserver
```

Откройте `http://127.0.0.1:8000/` — вы увидите панель проектов.

## Структура

- `core/models.py` — модели: `Company`, `Project`, `Task`, `Finance`, `InventoryItem`, `GeneratedContent`.
- `core/views.py` — дашборд проектов, детали проекта (задачи, финансы, склад, отчёты), настройки компании.
- `core/forms.py` — формы для CRUD.
- `core/admin.py` — регистрация моделей в админке.
- `templates/` — Tailwind‑шаблоны (панель, проекты, логин/регистрация и др.).

### AI‑интеграция

Модель `GeneratedContent` в `core/models.py` — место, где можно вызывать AI‑модель (OpenAI, локальная LLM и т.п.).  
В шаблоне `core/project_detail.html` добавлен комментарий, где можно подключить генерацию отчёта по проекту через AI.


# Добавление колонок материалов/движений, если 0029 была помечена применённой без SQL (например --fake).

from django.db import connection, migrations


def _columns(cursor, table: str) -> set[str]:
    if connection.vendor == "sqlite":
        cursor.execute(f'PRAGMA table_info("{table}")')
        return {row[1] for row in cursor.fetchall()}
    if connection.vendor == "postgresql":
        cursor.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            [table],
        )
        return {row[0] for row in cursor.fetchall()}
    if connection.vendor == "mysql":
        cursor.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = %s
            """,
            [table],
        )
        return {row[0] for row in cursor.fetchall()}
    return set()


def _add_column_safe(cursor, table: str, ddl: str, cols: set[str], col_name: str) -> None:
    if col_name in cols:
        return
    cursor.execute(ddl)


def forwards(apps, schema_editor):
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute(
                'ALTER TABLE core_material ADD COLUMN IF NOT EXISTS supplier varchar(255) NOT NULL DEFAULT ""'
            )
            cursor.execute(
                "ALTER TABLE core_material ADD COLUMN IF NOT EXISTS description text NOT NULL DEFAULT ''"
            )
        else:
            m_cols = _columns(cursor, "core_material")
            _add_column_safe(
                cursor,
                "core_material",
                'ALTER TABLE core_material ADD COLUMN supplier varchar(255) NOT NULL DEFAULT ""',
                m_cols,
                "supplier",
            )
            m_cols = _columns(cursor, "core_material")
            _add_column_safe(
                cursor,
                "core_material",
                'ALTER TABLE core_material ADD COLUMN description text NOT NULL DEFAULT ""',
                m_cols,
                "description",
            )

        sm_cols = _columns(cursor, "core_stockmovement")
        if "supplier" not in sm_cols:
            if connection.vendor == "postgresql":
                cursor.execute(
                    'ALTER TABLE core_stockmovement ADD COLUMN IF NOT EXISTS supplier varchar(255) NOT NULL DEFAULT ""'
                )
            else:
                cursor.execute(
                    'ALTER TABLE core_stockmovement ADD COLUMN supplier varchar(255) NOT NULL DEFAULT ""'
                )
        sm_cols = _columns(cursor, "core_stockmovement")
        if "writeoff_reason" not in sm_cols:
            if connection.vendor == "postgresql":
                cursor.execute(
                    "ALTER TABLE core_stockmovement ADD COLUMN IF NOT EXISTS writeoff_reason varchar(20) NOT NULL DEFAULT ''"
                )
            else:
                cursor.execute(
                    'ALTER TABLE core_stockmovement ADD COLUMN writeoff_reason varchar(20) NOT NULL DEFAULT ""'
                )
        sm_cols = _columns(cursor, "core_stockmovement")
        if "user_id" not in sm_cols:
            if connection.vendor == "postgresql":
                cursor.execute(
                    "ALTER TABLE core_stockmovement ADD COLUMN IF NOT EXISTS user_id bigint NULL"
                )
            else:
                cursor.execute("ALTER TABLE core_stockmovement ADD COLUMN user_id bigint NULL")
        sm_cols = _columns(cursor, "core_stockmovement")
        if "schedule_phase_id" not in sm_cols:
            if connection.vendor == "postgresql":
                cursor.execute(
                    "ALTER TABLE core_stockmovement ADD COLUMN IF NOT EXISTS schedule_phase_id bigint NULL"
                )
            else:
                cursor.execute(
                    "ALTER TABLE core_stockmovement ADD COLUMN schedule_phase_id bigint NULL"
                )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_materials_check"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.RunPython(forwards, migrations.RunPython.noop),
            ],
        ),
    ]

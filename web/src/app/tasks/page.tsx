import { supabase } from '@/lib/supabase'

export const dynamic = 'force-dynamic'

type TaskRow = {
  id?: string | number
  name: string | null
  status: string | null
  project_id?: string | number | null
}

export default async function TasksPage() {
  try {
    const { data, error } = await supabase
      .from('tasks')
      .select('id,name,status,project_id')
      .limit(50)

    if (error) {
      return (
        <main style={{ padding: 24, fontFamily: 'sans-serif' }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>
            Ошибка Supabase
          </h1>
          <p style={{ marginTop: 12, marginBottom: 0, color: '#b00020' }}>
            {error.message}
          </p>
        </main>
      )
    }

    const tasks = (data ?? []) as TaskRow[]

    return (
      <main style={{ padding: 24, fontFamily: 'sans-serif' }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Задачи</h1>

        {tasks.length === 0 ? (
          <p style={{ marginTop: 12, marginBottom: 0, color: '#555' }}>
            Нет данных в таблице `tasks`.
          </p>
        ) : (
          <ul style={{ marginTop: 16, paddingLeft: 18 }}>
            {tasks.map((t, idx) => (
              <li key={String(t.id ?? idx)} style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 700 }}>{t.name ?? '—'}</div>
                <div style={{ color: '#333', marginTop: 4 }}>
                  Проект: {t.project_id ?? '—'}
                </div>
                <div style={{ color: '#666', marginTop: 4, fontSize: 12 }}>
                  Статус: {t.status ?? '—'}
                </div>
              </li>
            ))}
          </ul>
        )}
      </main>
    )
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    return (
      <main style={{ padding: 24, fontFamily: 'sans-serif' }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>
          Ошибка конфигурации
        </h1>
        <p style={{ marginTop: 12, marginBottom: 0, color: '#b00020' }}>
          {message}
        </p>
      </main>
    )
  }
}

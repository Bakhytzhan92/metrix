import { supabase } from '@/lib/supabase'

export const dynamic = 'force-dynamic'

type UserRow = {
  id?: string | number
  email: string | null
  role: string | null
}

export default async function UsersPage() {
  try {
    const { data, error } = await supabase
      .from('users')
      .select('id,email,role')
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

    const users = (data ?? []) as UserRow[]

    return (
      <main style={{ padding: 24, fontFamily: 'sans-serif' }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>
          Пользователи
        </h1>

        {users.length === 0 ? (
          <p style={{ marginTop: 12, marginBottom: 0, color: '#555' }}>
            Нет данных в таблице `users`.
          </p>
        ) : (
          <ul style={{ marginTop: 16, paddingLeft: 18 }}>
            {users.map((u, idx) => (
              <li key={String(u.id ?? idx)} style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 700 }}>{u.email ?? '—'}</div>
                <div style={{ color: '#666', marginTop: 4, fontSize: 12 }}>
                  Роль: {u.role ?? '—'}
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

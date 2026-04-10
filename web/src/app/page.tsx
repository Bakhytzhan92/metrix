import { supabase } from '@/lib/supabase'
import Navbar from '@/components/Navbar'

export const dynamic = 'force-dynamic'

type Project = {
  id?: string | number
  name: string | null
  description: string | null
  created_at: string | null
}

export default async function HomePage() {
  try {
    const { data, error } = await supabase
      .from('projects')
      .select('*')
      .limit(5)

    if (error) {
      return (
        <div style={{ fontFamily: 'sans-serif' }}>
          <Navbar />
          <main style={{ padding: 24 }}>
            <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>
              Ошибка Supabase
            </h1>
            <p style={{ marginTop: 12, marginBottom: 0, color: '#b00020' }}>
              {error.message}
            </p>
          </main>
        </div>
      )
    }

    const projects = (data ?? []) as Project[]

    return (
      <div
        style={{
          fontFamily: 'sans-serif',
          minHeight: '100vh',
          backgroundColor: '#f7f7f7',
        }}
      >
        <Navbar />
        <main style={{ padding: 24 }}>
          <h1 style={{ fontSize: 28, fontWeight: 700, margin: 0 }}>Проекты</h1>

          {projects.length === 0 ? (
            <p style={{ marginTop: 16, color: '#555' }}>
              Нет данных в таблице `projects`.
            </p>
          ) : (
            <div
              style={{
                marginTop: 24,
                display: 'flex',
                flexWrap: 'wrap',
                gap: 16,
              }}
            >
              {projects.map((p, idx) => {
                const createdAtText = p.created_at
                  ? new Date(p.created_at).toLocaleString()
                  : '—'

                return (
                  <article
                    key={String(p.id ?? idx)}
                    style={{
                      flex: '1 1 260px',
                      maxWidth: 360,
                      backgroundColor: '#ffffff',
                      border: '1px solid #e0e0e0',
                      borderRadius: 8,
                      padding: 16,
                      boxShadow: '0 2px 6px rgba(0, 0, 0, 0.05)',
                    }}
                  >
                    <h2
                      style={{
                        fontSize: 18,
                        fontWeight: 700,
                        margin: 0,
                        marginBottom: 8,
                        color: '#111827',
                      }}
                    >
                      {p.name || 'Без названия'}
                    </h2>
                    <p
                      style={{
                        margin: 0,
                        marginBottom: 12,
                        color: '#374151',
                        fontSize: 14,
                        lineHeight: 1.5,
                      }}
                    >
                      {p.description || 'Описание отсутствует'}
                    </p>
                    <small
                      style={{
                        display: 'block',
                        color: '#6b7280',
                        fontSize: 12,
                      }}
                    >
                      Создано: {createdAtText}
                    </small>
                  </article>
                )
              })}
            </div>
          )}
        </main>
      </div>
    )
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    return (
      <div style={{ fontFamily: 'sans-serif' }}>
        <Navbar />
        <main style={{ padding: 24 }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>
            Ошибка конфигурации
          </h1>
          <p style={{ marginTop: 12, marginBottom: 0, color: '#b00020' }}>
            {message}
          </p>
        </main>
      </div>
    )
  }
}
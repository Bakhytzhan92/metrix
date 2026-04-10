import { supabase } from '@/lib/supabase'

export const dynamic = 'force-dynamic'

export default async function Home() {
  try {
    const { data, error } = await supabase
      .from('projects')
      .select('*')
      .limit(5)

    if (error) {
      return (
        <main style={{ padding: 24 }}>
          <h1 style={{ fontSize: 20, fontWeight: 600 }}>Supabase error</h1>
          <pre style={{ marginTop: 12, whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(
              { message: error.message, details: error.details, hint: error.hint },
              null,
              2
            )}
          </pre>
        </main>
      )
    }

    return (
      <main style={{ padding: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 600 }}>
          Первые 5 записей из `projects`
        </h1>
        <pre style={{ marginTop: 12, whiteSpace: 'pre-wrap' }}>
          {JSON.stringify(data ?? [], null, 2)}
        </pre>
      </main>
    )
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    return (
      <main style={{ padding: 24 }}>
        <h1 style={{ fontSize: 20, fontWeight: 600 }}>Config error</h1>
        <pre style={{ marginTop: 12, whiteSpace: 'pre-wrap' }}>{message}</pre>
      </main>
    )
  }
}

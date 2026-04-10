import { createClient } from '@supabase/supabase-js'

function requireEnv(name: string) {
  const v = process.env[name]
  if (!v) {
    throw new Error(
      `Missing ${name}. Fill it in .env.local and restart the dev server.`
    )
  }
  return v
}

export const supabase = createClient(
  requireEnv('NEXT_PUBLIC_SUPABASE_URL'),
  requireEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY')
)

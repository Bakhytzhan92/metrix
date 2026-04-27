"use client";

import { useEffect } from "react";

/**
 * Панель супер-администратора в Django (/superadmin/).
 * NEXT_PUBLIC_DJANGO_ORIGIN — базовый URL бэкенда (например http://127.0.0.1:8000).
 */
export default function SuperAdminRedirectPage() {
  useEffect(() => {
    const origin =
      process.env.NEXT_PUBLIC_DJANGO_ORIGIN?.replace(/\/$/, "") ||
      "http://127.0.0.1:8000";
    window.location.replace(`${origin}/superadmin/`);
  }, []);

  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      <p className="text-slate-600">Переход в панель платформы…</p>
    </main>
  );
}

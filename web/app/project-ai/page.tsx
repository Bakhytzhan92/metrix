/**
 * Умный импорт PDF + ИИ реализован в Django: Проекты → откройте проект → вкладка «ИИ».
 * API (с cookie-сессией и CSRF того же сайта): POST /api/upload-pdf/, GET /api/document/<id>/, POST /api/document/<id>/apply/
 */
export default function ProjectAIPage() {
  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-xl font-semibold text-slate-900">
        Умный импорт (PDF + ИИ)
      </h1>
      <p className="mt-4 text-slate-600">
        Полный сценарий с загрузкой файла и предпросмотром плана доступен в веб-приложении
        Metrix (Django): выберите проект и перейдите на вкладку{" "}
        <strong>«ИИ»</strong>.
      </p>
      <p className="mt-3 text-sm text-slate-500">
        Отдельный фронтенд на другом origin не передаёт cookie сессии Django; для
        интеграции Next.js используйте общий домен (reverse proxy) или токены
        API — при необходимости можно добавить позже.
      </p>
    </main>
  );
}

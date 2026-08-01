type StatusService = { name: string; status: "ok" | "degraded" | "incident"; detail: string };
type StatusResponse = { status: "ok" | "degraded" | "incident"; checked_at: string; services: StatusService[] };

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "https://api.alanet.ru");

async function loadStatus(): Promise<StatusResponse | null> {
  try {
    const response = await fetch(`${API_URL}/api/v1/status`, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as StatusResponse;
  } catch {
    return null;
  }
}

function label(status: StatusService["status"]) {
  if (status === "ok") return "Работает";
  if (status === "degraded") return "Есть риск";
  return "Инцидент";
}

export default async function StatusPage() {
  const report = await loadStatus();
  const services = report?.services ?? [
    { name: "api", status: "degraded" as const, detail: "status endpoint unavailable" },
  ];
  const status = report?.status ?? "degraded";

  return (
    <main className="checkout-page status-page">
      <section className="shell checkout-shell status-shell">
        <div>
          <a className="text-link" href="/">← На главную</a>
          <p className="section-index">LIVE STATUS</p>
          <h1>Статус сервиса</h1>
          <p className="hero-lead">Короткая публичная сводка по API, биллингу, нодам и платежам. Если здесь есть риск, это уже повод смотреть мониторинг глубже.</p>
          <div className="status-summary">
            <span className={`status-badge ${status}`}>{label(status)}</span>
            <span>Последняя проверка: {report ? new Date(report.checked_at).toLocaleString("ru-RU", { dateStyle: "long", timeStyle: "short" }) : "недоступна"}</span>
          </div>
        </div>

        <div className="status-card">
          {services.map((service) => (
            <article className="status-row" key={service.name}>
              <div>
                <strong>{service.name}</strong>
                <p>{service.detail}</p>
              </div>
              <span className={`status-pill ${service.status}`}>{label(service.status)}</span>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}

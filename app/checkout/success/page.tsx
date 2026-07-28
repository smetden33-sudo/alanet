"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import AccountPage from "../../account/page";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type OrderResult = { status: string; subscription_url?: string | null; expires_at?: string | null };

export default function CheckoutSuccessPage() {
  const search = useSearchParams();
  const [bindUrl, setBindUrl] = useState<string | null>(null);
  const [order, setOrder] = useState<OrderResult | null>(null);
  const [pollError, setPollError] = useState(false);
  const isSessionLogin = Boolean(search.get("session"));
  const orderId = search.get("order");

  useEffect(() => {
    if (isSessionLogin) return;
    const value = window.sessionStorage.getItem("alanet_telegram_bind_url");
    if (value) {
      setBindUrl(value);
      window.sessionStorage.removeItem("alanet_telegram_bind_url");
    }
  }, [isSessionLogin]);

  useEffect(() => {
    if (isSessionLogin || !orderId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const response = await fetch(`${API_URL}/api/v1/orders/${orderId}`);
        if (!response.ok) throw new Error("status unavailable");
        const result = await response.json();
        if (cancelled) return;
        setOrder(result);
        setPollError(false);
        if (!["ACTIVE", "PROVISIONING_FAILED", "CANCELED", "REFUNDED"].includes(result.status)) timer = setTimeout(poll, 2500);
      } catch {
        if (!cancelled) { setPollError(true); timer = setTimeout(poll, 5000); }
      }
    }
    poll();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [isSessionLogin, orderId]);

  if (isSessionLogin) return <AccountPage />;

  const failed = order && ["PROVISIONING_FAILED", "CANCELED", "REFUNDED"].includes(order.status);
  const active = order?.status === "ACTIVE";

  return <main className="checkout-page">
    <nav className="nav shell"><a className="brand" href="/"><span className="brand-mark">Т</span><span>тихая сеть</span></a><a className="text-link" href="/">← На главную</a></nav>
    <div className="checkout-shell shell"><section className="checkout-form">
      <p className="section-index">{active ? "ДОСТУП ГОТОВ" : failed ? "НУЖНА ПОМОЩЬ" : "ЗАКАЗ ПРИНЯТ"}</p>
      <h1>{active ? "Подписка активна." : failed ? "Не удалось завершить оформление." : "Спасибо за оформление."}</h1>
      <p className="hero-lead">{active ? "Оплата подтверждена, доступ создан. Сохраните ссылку подключения и привяжите Telegram." : failed ? "Повторно оплачивать не нужно. Заказ сохранён — напишите в поддержку, и мы проверим его." : "Проверяем оплату и создаём доступ автоматически. Обычно это занимает несколько секунд."}</p>
      {active && order?.subscription_url && <a className="button" href={order.subscription_url}>Открыть подписку →</a>}
      {bindUrl ? <a className="button" href={bindUrl}>Привязать Telegram →</a> : <a className="button" href="https://t.me/alanet_bot">Открыть Telegram-бота →</a>}
      {failed && <a className="text-link" href="https://t.me/alanet_bot">Написать в поддержку</a>}
      {pollError && <p className="form-error">Статус временно недоступен. Проверка повторится автоматически.</p>}
      <p className="secure-note">Ссылка привязки одноразовая и действует 7 дней. Не пересылайте ссылку подписки другим людям.</p>
    </section></div>
  </main>;
}

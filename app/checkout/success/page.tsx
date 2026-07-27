"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import AccountPage from "../../account/page";

export default function CheckoutSuccessPage() {
  const search = useSearchParams();
  const [bindUrl, setBindUrl] = useState<string | null>(null);
  if (search.get("session")) return <AccountPage />;

  useEffect(() => {
    const value = window.sessionStorage.getItem("alanet_telegram_bind_url");
    if (value) {
      setBindUrl(value);
      window.sessionStorage.removeItem("alanet_telegram_bind_url");
    }
  }, []);

  return <main className="checkout-page">
    <nav className="nav shell"><a className="brand" href="/"><span className="brand-mark">Т</span><span>тихая сеть</span></a><a className="text-link" href="/">← На главную</a></nav>
    <div className="checkout-shell shell"><section className="checkout-form">
      <p className="section-index">ЗАКАЗ ПРИНЯТ</p>
      <h1>Спасибо за оформление.</h1>
      <p className="hero-lead">После подтверждения оплаты доступ будет создан автоматически. Привяжите Telegram, чтобы получать ссылку подключения и видеть статус подписки в боте.</p>
      {bindUrl ? <a className="button" href={bindUrl}>Привязать Telegram →</a> : <a className="button" href="https://t.me/alanet_bot">Открыть Telegram-бота →</a>}
      <p className="secure-note">Ссылка привязки одноразовая и действует 7 дней.</p>
    </section></div>
  </main>;
}

"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type AccountData = {
  customer: { email: string; telegram_username?: string | null };
  subscription: { status: string; expires_at: string; subscription_url: string; plan: string; locations: string } | null;
};

export default function AccountPage() {
  const [account, setAccount] = useState<AccountData | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const params = new URLSearchParams(window.location.search);
      const loginToken = params.get("session");
      try {
        if (loginToken) {
          const exchange = await fetch(`${API_URL}/api/v1/auth/telegram/exchange`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: loginToken }) });
          if (!exchange.ok) throw new Error("login failed");
          window.history.replaceState({}, "", "/account");
        }
        const response = await fetch(`${API_URL}/api/v1/me`, { credentials: "include" });
        if (!response.ok) throw new Error("session missing");
        const result = await response.json();
        if (!cancelled) { setAccount(result); setState("ready"); }
      } catch { if (!cancelled) setState("error"); }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  async function logout() {
    await fetch(`${API_URL}/api/v1/auth/logout`, { method: "POST", credentials: "include" });
    window.location.reload();
  }

  return <main className="checkout-page">
    <nav className="nav shell"><a className="brand" href="/"><span className="brand-mark">Т</span><span>тихая сеть</span></a><a className="text-link" href="/">← На главную</a></nav>
    <div className="account-shell shell">
      <section className="account-heading"><p className="section-index">ЛИЧНЫЙ КАБИНЕТ</p><h1>Моя подписка.</h1><p className="hero-lead">Здесь собраны текущий тариф, срок действия и персональная ссылка подключения.</p></section>
      {state === "loading" && <section className="checkout-form"><p>Проверяем защищённую сессию…</p></section>}
      {state === "error" && <section className="checkout-form"><h2>Ссылка устарела</h2><p className="account-muted">Откройте бота и запросите новую ссылку в личный кабинет.</p><a className="button" href="https://t.me/alanet_bot">Открыть Telegram →</a></section>}
      {state === "ready" && account && <section className="checkout-form account-card">
        <div className="account-row"><span>Аккаунт</span><strong>{account.customer.telegram_username || account.customer.email}</strong></div>
        {account.subscription ? <><div className="account-row"><span>Тариф</span><strong>{account.subscription.plan}</strong></div><div className="account-row"><span>Статус</span><strong>{account.subscription.status === "ACTIVE" ? "Активна" : account.subscription.status}</strong></div><div className="account-row"><span>Действует до</span><strong>{new Date(account.subscription.expires_at).toLocaleString("ru-RU", { dateStyle: "long", timeStyle: "short" })}</strong></div><div className="account-row"><span>Доступ</span><strong>{account.subscription.locations}</strong></div><a className="button" href={account.subscription.subscription_url}>Открыть ссылку подключения →</a></> : <p className="account-muted">Активной подписки пока нет. Выберите тариф на главной странице.</p>}
        <button className="text-link account-logout" onClick={logout}>Выйти</button>
      </section>}
    </div>
  </main>;
}

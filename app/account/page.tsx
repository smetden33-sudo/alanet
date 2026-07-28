"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type AccountData = {
  customer: { email: string; telegram_username?: string | null };
  subscription: { status: string; expires_at: string; subscription_url: string; plan: string; locations: string } | null;
};

export default function AccountPage() {
  const [account, setAccount] = useState<AccountData | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [renewPlan, setRenewPlan] = useState("start");
  const [renewState, setRenewState] = useState<"idle" | "loading" | "error">("idle");

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

  async function renew() {
    setRenewState("loading");
    try {
      const response = await fetch(`${API_URL}/api/v1/me/checkout`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan_slug: renewPlan }),
      });
      if (response.status === 401) {
        setState("error");
        return;
      }
      if (!response.ok) throw new Error("renewal checkout failed");
      const result = await response.json();
      window.location.assign(result.confirmation_url);
    } catch {
      setRenewState("error");
    }
  }

  return <main className="checkout-page">
    <nav className="nav shell"><Link className="brand" href="/"><span className="brand-mark">Т</span><span>тихая сеть</span></Link><Link className="text-link" href="/">← На главную</Link></nav>
    <div className="account-shell shell">
      <section className="account-heading"><p className="section-index">ЛИЧНЫЙ КАБИНЕТ</p><h1>Моя подписка.</h1><p className="hero-lead">Здесь собраны текущий тариф, срок действия и персональная ссылка подключения.</p></section>
      {state === "loading" && <section className="checkout-form"><p>Проверяем защищённую сессию…</p></section>}
      {state === "error" && <section className="checkout-form"><h2>Ссылка устарела</h2><p className="account-muted">Откройте бота и запросите новую ссылку в личный кабинет.</p><a className="button" href="https://t.me/alanet_bot">Открыть Telegram →</a></section>}
      {state === "ready" && account && <section className="checkout-form account-card">
        <div className="account-row"><span>Аккаунт</span><strong>{account.customer.telegram_username || account.customer.email}</strong></div>
        {account.subscription ? <><div className="account-row"><span>Тариф</span><strong>{account.subscription.plan}</strong></div><div className="account-row"><span>Статус</span><strong>{account.subscription.status === "ACTIVE" ? "Активна" : account.subscription.status}</strong></div><div className="account-row"><span>Действует до</span><strong>{new Date(account.subscription.expires_at).toLocaleString("ru-RU", { dateStyle: "long", timeStyle: "short" })}</strong></div><div className="account-row"><span>Доступ</span><strong>{account.subscription.locations}</strong></div><a className="button" href={account.subscription.subscription_url}>Открыть ссылку подключения →</a><div className="account-renew"><h2>Продлить подписку</h2><p className="account-muted">Новый срок добавится к текущей дате окончания.</p><label>Тариф<select value={renewPlan} onChange={(event) => setRenewPlan(event.target.value)} disabled={renewState === "loading"}><option value="start">Старт · 30 дней · 299 ₽</option><option value="calm">Спокойный · 90 дней · 749 ₽</option><option value="year">На год · 365 дней · 2 490 ₽</option></select></label><button className="button button-ghost" type="button" onClick={renew} disabled={renewState === "loading"}>{renewState === "loading" ? "Создаём платёж…" : "Продлить через ЮKassa →"}</button>{renewState === "error" && <p className="form-error" role="alert">Не удалось создать платёж. Попробуйте ещё раз или напишите в поддержку.</p>}</div></> : <p className="account-muted">Активной подписки пока нет. Выберите тариф на главной странице.</p>}
        <button className="text-link account-logout" onClick={logout}>Выйти</button>
      </section>}
    </div>
  </main>;
}

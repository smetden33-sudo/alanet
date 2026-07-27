"use client";
import { FormEvent, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CHECKOUT_ENABLED = process.env.NEXT_PUBLIC_CHECKOUT_ENABLED === "true";

export default function CheckoutPage() {
  const search = useSearchParams();
  const initialPlan = search.get("plan") ?? "Старт";
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState("");
  const plans = useMemo(() => ([{slug:"start",name:"Старт",price:"299 ₽"},{slug:"calm",name:"Спокойно",price:"749 ₽"},{slug:"year",name:"На год",price:"2 490 ₽"}]), []);
  const initialSlug = plans.find((plan) => plan.name === initialPlan)?.slug ?? "start";
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setStatus("loading"); setMessage("");
    const data = new FormData(event.currentTarget);
    try {
      const response = await fetch(`${API_URL}/api/v1/checkout`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({plan_slug:String(data.get("plan")),email:String(data.get("email")),telegram_username:String(data.get("telegram")??"")})});
      if (!response.ok) throw new Error("checkout failed");
      const result = await response.json();
      if (result.telegram_bind_url) window.sessionStorage.setItem("alanet_telegram_bind_url", result.telegram_bind_url);
      window.location.assign(result.confirmation_url);
    } catch { setStatus("error"); setMessage("Сервис оплаты пока недоступен. Попробуйте ещё раз или напишите в поддержку."); }
  }
  return <main className="checkout-page">
    <nav className="nav shell"><a className="brand" href="/"><span className="brand-mark">Т</span><span>тихая сеть</span></a><a className="text-link" href="/">← На главную</a></nav>
    <div className="checkout-shell shell"><section><p className="section-index">ОФОРМЛЕНИЕ</p><h1>Почти готово.</h1><p className="hero-lead">Оставьте email для чека. После оплаты здесь появится ваша ссылка подключения.</p></section>
      {CHECKOUT_ENABLED ? <form className="checkout-form" onSubmit={submit}>
        <label>Тариф<select name="plan" defaultValue={initialSlug}>{plans.map((plan)=><option key={plan.slug} value={plan.slug}>{plan.name} · {plan.price}</option>)}</select></label>
        <label>Email для чека<input name="email" type="email" required placeholder="you@example.com" autoComplete="email"/></label>
        <label>Telegram <small>необязательно</small><input name="telegram" type="text" placeholder="@username" autoComplete="off"/></label>
        <label className="consent"><input type="checkbox" required/><span>Принимаю условия <a href="/offer">оферты</a> и <a href="/privacy">политики конфиденциальности</a></span></label>
        <button className="button" disabled={status==="loading"} type="submit">{status==="loading"?"Создаём заказ…":"Перейти к оплате →"}</button>
        {message&&<p className="form-error" role="alert">{message}</p>}<small className="secure-note">Оплата проходит на защищённой странице ЮKassa. Данные карты не попадают к нам.</small>
      </form> : <section className="checkout-form checkout-paused">
        <p className="section-index">СКОРО</p>
        <h2>Оплата пока закрыта</h2>
        <p>Мы заканчиваем подключение платёжной системы. Сейчас деньги не принимаются и заказы не создаются.</p>
        <a className="button" href="https://t.me/alanet_bot">Узнать о запуске в Telegram →</a>
      </section>}
    </div>
  </main>;
}

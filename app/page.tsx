const plans = [
  { name: "Пробный", price: "0", period: "24 часа", traffic: "Безлимитный", devices: "1 устройство", locations: "1 локация", href: "https://t.me/alanet_bot?start=trial" },
  { name: "Старт", price: "299", period: "30 дней", traffic: "Безлимитный", devices: "1 устройство", locations: "Все доступные локации" },
  { name: "Спокойно", price: "749", period: "90 дней", traffic: "Безлимитный", devices: "1 устройство", locations: "Все доступные локации", featured: true },
  { name: "На год", price: "2 490", period: "365 дней", traffic: "Безлимитный", devices: "1 устройство", locations: "Все доступные локации" },
];

export default function Home() {
  return (
    <main>
      <nav className="nav shell" aria-label="Основная навигация">
        <a className="brand" href="#top" aria-label="Тихая сеть — на главную"><span className="brand-mark" aria-hidden="true">Т</span><span>тихая сеть</span></a>
        <div className="nav-links"><a href="#plans">Тарифы</a><a href="#how">Как подключиться</a><a href="#faq">Вопросы</a></div>
        <a className="button button-small button-ghost" href="/checkout">Личный кабинет</a>
      </nav>

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow"><span /> Простой доступ без сложных настроек</p>
          <h1>Интернет, который<br />не отвлекает.</h1>
        <p className="hero-lead">Одно подключение для телефона или компьютера. Быстрый старт, понятный личный кабинет и поддержка, которая отвечает по-человечески.</p>
          <div className="hero-actions"><a className="button" href="#plans">Выбрать тариф <span aria-hidden="true">→</span></a><a className="text-link" href="#how">Как это работает <span aria-hidden="true">↘</span></a></div>
          <div className="trust-row" aria-label="Преимущества сервиса"><span>Без автосписаний</span><span>Оплата через ЮKassa</span><span>Запуск за 3 минуты</span></div>
        </div>
        <div className="signal-card" aria-label="Карточка состояния подключения">
          <div className="signal-top"><span>Статус подключения</span><span className="status-dot">активно</span></div>
          <div className="orb" aria-hidden="true"><div className="orb-core">✓</div></div>
          <strong>Всё работает</strong><p>Москва · 38 мс</p>
          <div className="usage"><div><span>Использовано</span><b>18,4 ГБ</b></div><div className="usage-track"><span /></div><small>безлимитный трафик · ещё 24 дня</small></div>
        </div>
      </section>

      <section className="manifesto"><div className="shell manifesto-grid"><p className="section-index">01 / ПОДХОД</p><div><h2>Технологии должны быть<br />тихими и надёжными.</h2><p>Мы убрали лишние экраны, запутанные инструкции и скрытые условия. Вы оплачиваете доступ, получаете ссылку и подключаете устройство.</p></div></div></section>

      <section className="features shell" id="how">
        <article><span className="feature-num">01</span><h3>Оплатите</h3><p>Выберите срок и оплатите банковской картой через защищённую страницу ЮKassa.</p></article>
        <article><span className="feature-num">02</span><h3>Получите ссылку</h3><p>Ссылка появится в личном кабинете и придёт в Telegram, если вы его привяжете.</p></article>
        <article><span className="feature-num">03</span><h3>Подключитесь</h3><p>Откройте ссылку в рекомендованном приложении. Остальные настройки применятся сами.</p></article>
      </section>

      <section className="plans-section" id="plans"><div className="shell">
        <div className="section-heading"><div><p className="section-index">02 / ТАРИФЫ</p><h2>Выберите свой ритм</h2></div><p>Платные тарифы открывают все локации. Пробный доступ работает на 1 локации.</p></div>
        <div className="plans">{plans.map((plan) => (
          <article className={`plan ${plan.featured ? "featured" : ""}`} key={plan.name}>
            {plan.featured && <span className="plan-label">ПОПУЛЯРНЫЙ</span>}<h3>{plan.name}</h3><div className="price"><b>{plan.price}</b><span>₽</span></div><p>{plan.period}</p>
            <ul><li>{plan.traffic === "Безлимитный" ? "Безлимитный трафик" : `${plan.traffic} трафика`}</li><li>{plan.devices}</li><li>{plan.locations}</li><li>Поддержка в Telegram</li></ul>
            <a className={`button ${plan.featured ? "button-light" : "button-outline"}`} href={plan.href ?? `/checkout?plan=${encodeURIComponent(plan.name)}`}>Выбрать</a>
          </article>
        ))}</div>
        <p className="plan-note">Продление только вручную — никаких неожиданных списаний.</p>
      </div></section>

      <section className="faq shell" id="faq"><p className="section-index">03 / ВОПРОСЫ</p><div className="faq-layout"><h2>Коротко о важном</h2><div>
        <details open><summary>Какие устройства поддерживаются?</summary><p>Android, iOS, Windows и macOS. После оплаты вы получите инструкции для каждой системы.</p></details>
        <details><summary>Есть ли автоматические списания?</summary><p>Нет. Каждый новый период вы оплачиваете самостоятельно.</p></details>
        <details><summary>Что делать, если не получилось подключиться?</summary><p>Напишите в поддержку через Telegram. Поможем проверить приложение и подключение.</p></details>
        <details><summary>Можно ли вернуть оплату?</summary><p>Да, по условиям возврата. Заявку можно создать через поддержку.</p></details>
      </div></div></section>

      <footer><div className="shell footer-grid">
        <div><a className="brand brand-light" href="#top"><span className="brand-mark">Т</span><span>тихая сеть</span></a><p>Связь без лишнего шума.</p></div>
        <div><b>Сервис</b><a href="#plans">Тарифы</a><a href="/checkout">Личный кабинет</a><a href="#how">Инструкции</a></div>
        <div><b>Документы</b><a href="/offer">Оферта</a><a href="/privacy">Конфиденциальность</a><a href="/refund">Возвраты</a></div>
        <div><b>Поддержка</b><a href="https://t.me/alanet_bot">Telegram</a><a href="mailto:help@alanet.ru">help@alanet.ru</a></div>
      </div><div className="shell footer-bottom"><span>© 2026 Тихая сеть</span><span>Оплата защищена ЮKassa</span></div></footer>
    </main>
  );
}

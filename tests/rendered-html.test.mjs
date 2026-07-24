import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(new Request(`http://localhost${path}`, { headers: { accept: "text/html" } }), {
    ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
  }, { waitUntil() {}, passThroughOnException() {} });
}

test("server-renders the finished Russian landing page", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /lang="ru"/);
  assert.match(html, /<title>Тихая сеть — простой доступ в интернет<\/title>/i);
  assert.match(html, /Интернет, который/);
  assert.match(html, /Выберите свой ритм/);
  assert.match(html, /\/checkout\?plan=/);
  assert.match(html, /property="og:image"/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});

test("checkout is safely paused while YooKassa is not configured", async () => {
  const response = await render("/checkout?plan=start");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /Почти готово/);
  assert.match(html, /Оплата пока закрыта/);
  assert.match(html, /деньги не принимаются/);
  assert.doesNotMatch(html, /Перейти к оплате/);
});

test("starter preview dependency is removed", async () => {
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);
  assert.doesNotMatch(page, /SkeletonPreview|codex-preview/);
  assert.match(layout, /Тихая сеть/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
});

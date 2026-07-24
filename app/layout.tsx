import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin", "cyrillic"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin", "cyrillic"] });

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: { default: "Тихая сеть — простой доступ в интернет", template: "%s — Тихая сеть" },
  description: "Доступ для телефона и компьютера: понятные тарифы, оплата через ЮKassa и подключение за несколько минут.",
  openGraph: {
    title: "Тихая сеть",
    description: "Интернет, который не отвлекает.",
    images: [{ url: "/og.png", width: 1733, height: 877, alt: "Тихая сеть — интернет, который не отвлекает" }],
    locale: "ru_RU",
    type: "website",
  },
  twitter: { card: "summary_large_image", title: "Тихая сеть", description: "Интернет, который не отвлекает.", images: ["/og.png"] },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body className={`${geistSans.variable} ${geistMono.variable}`}>{children}</body></html>;
}

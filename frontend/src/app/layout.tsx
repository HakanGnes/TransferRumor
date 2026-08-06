import type { Metadata } from "next";
import { Barlow_Condensed, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

/*
  Tipografi secimi:
  - Barlow Condensed: skorboard / forma numarasi hissi. Display rolunde,
    olculu kullaniliyor (basliklar ve buyuk sayilar).
  - Inter: govde metni, yogun veri ekraninda okunurluk icin.
  - JetBrains Mono: tabular sayilar - skor ve deger sutunlari hizali dursun.
*/
const display = Barlow_Condensed({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

const body = Inter({
  variable: "--font-body",
  subsets: ["latin"],
});

const data = JetBrains_Mono({
  variable: "--font-data",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "TransferRumor — Scouting & Transfer Analysis",
  description:
    "Kadro analizine dayali transfer onerileri. 12 lig, 8.800+ oyuncu, performans segmentasyonu ve ulasilabilirlik skorlari.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr">
      <body className={`${display.variable} ${body.variable} ${data.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}

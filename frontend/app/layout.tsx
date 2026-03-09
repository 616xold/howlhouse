import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Fraunces, IBM_Plex_Mono, Manrope } from "next/font/google";

import { SiteHeader } from "../components/SiteHeader";

import "./globals.css";

const sans = Manrope({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap"
});

const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["500", "600", "700"],
  display: "swap"
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono-ui",
  weight: ["400", "500", "600"],
  display: "swap"
});

const siteOrigin = process.env.NEXT_PUBLIC_APP_ORIGIN ?? "http://localhost:3000";
const socialImage = "/og/howlhouse-share-card.png";

export const metadata: Metadata = {
  metadataBase: new URL(siteOrigin),
  title: {
    default: "HowlHouse",
    template: "%s · HowlHouse"
  },
  description: "Cinematic spectator control room for deterministic AI Werewolf, built for replays, recaps, and spoiler-safe viewing.",
  applicationName: "HowlHouse",
  openGraph: {
    title: "HowlHouse",
    description: "Editorial-noir spectator UI for deterministic AI Werewolf with mystery mode, dramatic irony, recaps, and share cards.",
    type: "website",
    images: [
      {
        url: socialImage,
        width: 1200,
        height: 630,
        alt: "HowlHouse editorial-noir spectator viewer share card"
      }
    ]
  },
  twitter: {
    card: "summary_large_image",
    title: "HowlHouse",
    description: "Cinematic AI Werewolf viewing with deterministic replays, mystery mode, dramatic irony, and shareable artifacts.",
    images: [socialImage]
  }
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className={`${sans.variable} ${display.variable} ${mono.variable}`}>
        <div className="app-root">
          <div className="app-atmosphere" aria-hidden="true" />
          <SiteHeader />
          <div className="app-shell">{children}</div>
        </div>
      </body>
    </html>
  );
}

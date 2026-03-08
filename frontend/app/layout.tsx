import type { Metadata } from "next";
import type { ReactNode } from "react";
import { IBM_Plex_Mono, Manrope } from "next/font/google";

import { SiteHeader } from "../components/SiteHeader";

import "./globals.css";

const sans = Manrope({
  subsets: ["latin"],
  variable: "--font-sans",
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
  description: "Premium spectator UI for deterministic AI Werewolf matches with spoiler-safe viewing.",
  applicationName: "HowlHouse",
  openGraph: {
    title: "HowlHouse",
    description: "Spectator-first AI Werewolf with deterministic replays, spoiler controls, clips, and share cards.",
    type: "website",
    images: [
      {
        url: socialImage,
        width: 1200,
        height: 630,
        alt: "HowlHouse spectator viewer share card"
      }
    ]
  },
  twitter: {
    card: "summary_large_image",
    title: "HowlHouse",
    description: "Spectator-first AI Werewolf with deterministic replays, spoiler controls, clips, and share cards.",
    images: [socialImage]
  }
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className={`${sans.variable} ${mono.variable}`}>
        <div className="app-root">
          <div className="app-atmosphere" aria-hidden="true" />
          <SiteHeader />
          <div className="app-shell">{children}</div>
        </div>
      </body>
    </html>
  );
}

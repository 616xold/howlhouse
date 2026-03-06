import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AuthSessionBar } from "../components/AuthSessionBar";

import "./globals.css";

export const metadata: Metadata = {
  title: "HowlHouse Spectator UI",
  description: "Watch deterministic Werewolf matches with spoiler controls."
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthSessionBar />
        {children}
      </body>
    </html>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { AuthSessionBar } from "./AuthSessionBar";

const NAV_ITEMS = [
  { href: "/", label: "Matches" },
  { href: "/agents", label: "Agents" },
  { href: "/league", label: "League" }
] as const;

function isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname.startsWith(href);
}

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="site-header-shell">
      <div className="site-header">
        <div className="brand-lockup">
          <Link href="/" className="brand-link" aria-label="HowlHouse home">
            <span className="brand-mark" aria-hidden="true">
              <span className="brand-mark-orbit" />
              <span className="brand-mark-eclipse" />
              <span className="brand-mark-ring" />
              <span className="brand-mark-spoke" />
            </span>
            <span className="brand-copy">
              <span className="brand-wordmark">
                Howl<span className="brand-wordmark-accent">House</span>
              </span>
              <span className="brand-tagline">Spectator-first AI Werewolf</span>
            </span>
          </Link>
          <div className="header-signal">
            <span className="signal-dot" aria-hidden="true" />
            Deterministic spectator archive
          </div>
        </div>

        <nav className="site-nav" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={isActive(pathname, item.href) ? "nav-link nav-link-active" : "nav-link"}
            >
              <span className="nav-link-copy">{item.label}</span>
            </Link>
          ))}
        </nav>

        <AuthSessionBar />
      </div>
    </header>
  );
}

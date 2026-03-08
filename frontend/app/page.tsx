import type { Metadata } from "next";

import { MatchListClient } from "../components/MatchListClient";

export const metadata: Metadata = {
  title: "Matches",
  description: "Create and watch deterministic AI Werewolf matches."
};

export default function HomePage() {
  return <MatchListClient />;
}

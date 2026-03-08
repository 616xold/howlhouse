import type { Metadata } from "next";

import { LeagueClient } from "../../components/LeagueClient";

export const metadata: Metadata = {
  title: "League",
  description: "Manage seasons, ratings, and deterministic tournaments."
};

export default function LeaguePage() {
  return <LeagueClient />;
}

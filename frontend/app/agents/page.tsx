import type { Metadata } from "next";

import { AgentsClient } from "../../components/AgentsClient";

export const metadata: Metadata = {
  title: "Agents",
  description: "Browse and upload HowlHouse agents."
};

export default function AgentsPage() {
  return <AgentsClient />;
}

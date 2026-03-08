import type { Metadata } from "next";

import { AgentDetailClient } from "../../../components/AgentDetailClient";

interface AgentDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

export async function generateMetadata({ params }: AgentDetailPageProps): Promise<Metadata> {
  const { id } = await params;
  return {
    title: `Agent ${id.slice(0, 8)}`,
    description: "Inspect an uploaded HowlHouse agent profile."
  };
}

export default async function AgentDetailPage({ params }: AgentDetailPageProps) {
  const { id } = await params;
  return <AgentDetailClient agentId={id} />;
}

import type { Metadata } from "next";

import { SeasonAgentProfileClient } from "../../../../../../components/SeasonAgentProfileClient";

interface SeasonAgentPageProps {
  params: Promise<{
    id: string;
    agentId: string;
  }>;
}

export async function generateMetadata({ params }: SeasonAgentPageProps): Promise<Metadata> {
  const { agentId } = await params;
  return {
    title: `Season Agent ${agentId.slice(0, 8)}`,
    description: "Review a season-specific HowlHouse agent profile."
  };
}

export default async function SeasonAgentPage({ params }: SeasonAgentPageProps) {
  const { id, agentId } = await params;
  return <SeasonAgentProfileClient seasonId={id} agentId={agentId} />;
}

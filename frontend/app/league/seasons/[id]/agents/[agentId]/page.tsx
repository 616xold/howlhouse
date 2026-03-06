import { SeasonAgentProfileClient } from "../../../../../../components/SeasonAgentProfileClient";

interface SeasonAgentPageProps {
  params: Promise<{
    id: string;
    agentId: string;
  }>;
}

export default async function SeasonAgentPage({ params }: SeasonAgentPageProps) {
  const { id, agentId } = await params;
  return <SeasonAgentProfileClient seasonId={id} agentId={agentId} />;
}

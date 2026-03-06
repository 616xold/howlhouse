import { MatchViewerClient } from "../../../components/MatchViewerClient";

interface MatchPageProps {
  params: Promise<{
    id: string;
  }>;
}

export default async function MatchPage({ params }: MatchPageProps) {
  const { id } = await params;
  return <MatchViewerClient matchId={id} />;
}

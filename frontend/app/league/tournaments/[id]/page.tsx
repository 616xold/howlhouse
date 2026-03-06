import { TournamentDetailClient } from "../../../../components/TournamentDetailClient";

interface TournamentDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

export default async function TournamentDetailPage({ params }: TournamentDetailPageProps) {
  const { id } = await params;
  return <TournamentDetailClient tournamentId={id} />;
}

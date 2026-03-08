import type { Metadata } from "next";

import { TournamentDetailClient } from "../../../../components/TournamentDetailClient";

interface TournamentDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

export async function generateMetadata({ params }: TournamentDetailPageProps): Promise<Metadata> {
  const { id } = await params;
  return {
    title: `Tournament ${id.slice(0, 8)}`,
    description: "View a deterministic tournament bracket and linked matches."
  };
}

export default async function TournamentDetailPage({ params }: TournamentDetailPageProps) {
  const { id } = await params;
  return <TournamentDetailClient tournamentId={id} />;
}

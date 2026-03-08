import type { Metadata } from "next";

import { SeasonDetailClient } from "../../../../components/SeasonDetailClient";

interface SeasonDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

export async function generateMetadata({ params }: SeasonDetailPageProps): Promise<Metadata> {
  const { id } = await params;
  return {
    title: `Season ${id.slice(0, 8)}`,
    description: "Inspect a HowlHouse season leaderboard and configuration."
  };
}

export default async function SeasonDetailPage({ params }: SeasonDetailPageProps) {
  const { id } = await params;
  return <SeasonDetailClient seasonId={id} />;
}

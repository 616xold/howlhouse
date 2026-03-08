import type { Metadata } from "next";

import { MatchViewerClient } from "../../../components/MatchViewerClient";

interface MatchPageProps {
  params: Promise<{
    id: string;
  }>;
}

export async function generateMetadata({ params }: MatchPageProps): Promise<Metadata> {
  const { id } = await params;
  return {
    title: `Match ${id.slice(0, 8)}`,
    description: "Watch a deterministic Werewolf replay with spoiler controls."
  };
}

export default async function MatchPage({ params }: MatchPageProps) {
  const { id } = await params;
  return <MatchViewerClient matchId={id} />;
}

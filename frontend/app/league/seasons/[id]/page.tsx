import { SeasonDetailClient } from "../../../../components/SeasonDetailClient";

interface SeasonDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

export default async function SeasonDetailPage({ params }: SeasonDetailPageProps) {
  const { id } = await params;
  return <SeasonDetailClient seasonId={id} />;
}

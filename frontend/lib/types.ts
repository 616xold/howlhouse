export type VisibilityMode = "public" | "spoilers";
export type MatchEventMode = "live" | "replay";

export interface ReplayEvent {
  v: number;
  id: string;
  t: number;
  ts: string;
  match_id: string;
  type: string;
  visibility: string;
  payload: Record<string, unknown>;
}

export interface MatchRecord {
  match_id: string;
  seed: number;
  agent_set: string;
  config: Record<string, unknown>;
  names: Record<string, string>;
  season_id: string | null;
  tournament_id: string | null;
  created_by_identity_id?: string | null;
  created_by_ip: string | null;
  hidden_at: string | null;
  hidden_reason: string | null;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  replay_path?: string | null;
  replay_key?: string | null;
  replay_uri?: string | null;
  winner: string | null;
  error: string | null;
  postprocess_error?: string | null;
  links: Record<string, string>;
}

export interface PredictionSummary {
  match_id: string;
  total_predictions: number;
  by_player: Record<string, number>;
  top_pairs: Array<{ pair: string[]; count: number }>;
}

export interface RosterEntry {
  player_id: string;
  name: string;
}

export interface AgentRecord {
  agent_id: string;
  name: string;
  version: string;
  runtime_type: "docker_py_v1" | "local_py_v1";
  created_by_identity_id?: string | null;
  created_by_ip?: string | null;
  hidden_at?: string | null;
  hidden_reason?: string | null;
  created_at: string;
  updated_at: string;
  strategy_text?: string;
  package_path?: string;
  entrypoint?: string;
}

export interface ClipSuggestion {
  clip_id: string;
  kind: "death" | "vote" | "close_vote" | "contradiction" | "claim" | "ending";
  title: string;
  reason: string;
  start_event_id: string;
  end_event_id: string;
  score: number;
}

export interface RecapPayload {
  v: number;
  match_id: string;
  generated_from: {
    last_event_id: string;
    last_event_ts: string;
  };
  winner: {
    team: string;
    reason: string;
    day: number;
  };
  stats: {
    days: number;
    public_messages: number;
    votes: number;
    night_kills: number;
    eliminations: number;
  };
  roles?: Record<string, string>;
  bullets: string[];
  narration_15s: string;
  key_quotes: Array<{
    event_id: string;
    player_id: string;
    text: string;
    day: number;
    phase: string;
  }>;
  confessional_highlights?: Array<{
    event_id: string;
    player_id: string;
    text: string;
    phase: string;
  }>;
  clips: ClipSuggestion[];
}

export interface SeasonRecord {
  season_id: string;
  name: string;
  status: "active" | "archived";
  initial_rating: number;
  k_factor: number;
  created_at: string;
  updated_at: string;
}

export interface LeaderboardEntry {
  rank: number;
  agent_id: string;
  name: string;
  version: string;
  rating: number;
  games: number;
  wins: number;
  losses: number;
}

export interface LeaderboardResponse {
  season_id: string;
  entries: LeaderboardEntry[];
}

export interface AgentSeasonProfile {
  season_id: string;
  agent_id: string;
  name: string;
  version: string;
  rating: number;
  games: number;
  wins: number;
  losses: number;
  recent_matches: Array<{
    match_id: string;
    won: boolean;
    team: string;
    winning_team: string;
    link: string;
  }>;
}

export interface TournamentGame {
  game_index: number;
  seed: number | null;
  match_id: string | null;
  winner_agent_id: string | null;
  winning_team: "town" | "werewolves" | null;
}

export interface TournamentMatchup {
  matchup_id: string;
  agent_a: string | null;
  agent_b: string | null;
  games: TournamentGame[];
  winner_agent_id: string | null;
}

export interface TournamentRound {
  round: number;
  matchups: TournamentMatchup[];
}

export interface TournamentBracket {
  v: number;
  tournament_id: string;
  season_id: string;
  seed: number;
  games_per_matchup: number;
  participants: Array<{ agent_id: string; seed_rank: number }>;
  rounds: TournamentRound[];
  champion_agent_id: string | null;
}

export interface TournamentRecord {
  tournament_id: string;
  season_id: string;
  name: string;
  seed: number;
  status: "created" | "running" | "completed" | "failed";
  champion_agent_id: string | null;
  error: string | null;
  created_by_identity_id?: string | null;
  created_by_ip?: string | null;
  hidden_at?: string | null;
  hidden_reason?: string | null;
  created_at: string;
  updated_at: string;
  bracket: TournamentBracket;
  links: Record<string, string>;
}

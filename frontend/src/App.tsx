import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ChartNoAxesCombined, Check, ChevronDown, Eye, RefreshCw, Star, Trash2, UserRound } from 'lucide-react';
import './index.css';
import { fetchEvent, fetchIndividualSeasonStats, fetchMatchGameStats, fetchPlayerSeasonOptions, fetchSeasonProgress, fetchSharedViewerProfile, fetchTournamentStats, saveSharedViewerProfile, type Match, type PlayerSeasonOption, type PlayerStat, type RoundRow } from './lib/api';
import { ScoreHero } from './components/ScoreHero';
import { MetricPill } from './components/MetricPill';
import { PlayerBars } from './components/PlayerBars';
import { MomentumChart } from './components/MomentumChart';
import { RoundTimeline } from './components/RoundTimeline';
import { RoundWalkthrough } from './components/RoundWalkthrough';
import { TaleOfTheTape } from './components/TaleOfTheTape';
import { ChampionshipDoubleDip } from './components/ChampionshipDoubleDip';
import { PlayerProfileTrajectory } from './components/PlayerProfileTrajectory';
import { LiveWinProbabilityChart } from './components/LiveWinProbabilityChart';
import StandingsView from './components/StandingsView';
import { BracketFlowView, TournamentView } from './components/TournamentView';
import TournamentStatsView from './components/TournamentStatsView';
import PredictionOperationsView from './components/PredictionOperationsView';
import ModelResearchLabView from './components/ModelResearchLabView';
import VenueAnalyticsView from './components/VenueAnalyticsView';
import PredictivePlayerProfileView from './components/PredictivePlayerProfileView';
import PlayerAnalyticsLeaderboardView from './components/PlayerAnalyticsLeaderboardView';
import PlayerDirectoryView from './components/PlayerDirectoryView';
import DirectorDirectoryView from './components/DirectorDirectoryView';
import { BracketProbabilities } from './components/BracketProbabilities';
import { PlayerMode } from './components/PlayerMode';
import { ViewerMode } from './components/ViewerMode';

type FavoritePlayer = {
  playerId: number;
  name?: string;
  photo?: string;
};

type PlayerEvent = {
  eventId: number;
  name: string;
  date?: string;
  time?: string;
  status?: string;
  matchType?: string;
  bracketType?: string;
  blindDraw?: boolean;
  bracketStarted?: boolean;
  scheduleCount?: number;
  location?: {
    name?: string;
    city?: string;
    state?: string;
  };
};

const BRACKET_REFRESH_MS = 120000;
const MATCH_STATS_REFRESH_MS = 10000;
type AppView = 'TOURNAMENT' | 'BRACKET_FLOW' | 'BRACKET_PREDICTIONS' | 'GAME' | 'STANDINGS' | 'STATISTICS' | 'PREDICTIONS' | 'RESEARCH' | 'PROFILE' | 'LEADERBOARD' | 'DIRECTORY' | 'DIRECTORS' | 'VENUES';
const SEASON_SETTINGS_KEY = 'cornhole.lastSeasonSettings';
const SEASON_DATA_KEY = 'cornhole.lastSeasonStandings';

class PanelErrorBoundary extends React.Component<
  { children: React.ReactNode; resetKey?: string | null },
  { error?: Error }
> {
  state: { error?: Error } = {};

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidUpdate(previous: { resetKey?: string | null }) {
    if (previous.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: undefined });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <section className="mt-4 rounded-[28px] border border-red-400/30 bg-red-950/30 p-4 text-red-100">
          <h2 className="text-lg font-black">This section hit a display error</h2>
          <div className="mt-2 text-sm">{this.state.error.message}</div>
        </section>
      );
    }

    return this.props.children;
  }
}

function useQueryParam(name: string, fallback: string) {
  return new URLSearchParams(location.search).get(name) || fallback;
}

function getInitialEventId() {
  const route = getStatusRoute();
  if (route) return route.eventId;
  const params = new URLSearchParams(location.search);
  const stored = loadStoredSeasonSettings();
  return params.get('event_id') || params.get('seedEventId') || stored.seedEventId || '248182';
}

function getInitialView(): AppView {
  if (getStatusRoute()) return 'GAME';
  const value = (new URLSearchParams(location.search).get('view') || '').toLowerCase();

  if (value === 'standings' || value === 'season' || value === 'season-stats') {
    return 'STANDINGS';
  }

  if (value === 'statistics' || value === 'tournament-stats') {
    return 'STATISTICS';
  }

  if (value === 'predictions' || value === 'prediction-operations') {
    return 'PREDICTIONS';
  }
  if (value === 'research' || value === 'model-research' || value === 'research-lab') return 'RESEARCH';
  if (value === 'profile' || value === 'predictive-profile') return 'PROFILE';
  if (value === 'leaderboard' || value === 'player-rankings') return 'LEADERBOARD';
  if (value === 'directory' || value === 'player-directory') return 'DIRECTORY';
  if (value === 'directors' || value === 'director-directory') return 'DIRECTORS';
  if (value === 'venues' || value === 'venue-analytics') return 'VENUES';

  if (value === 'bracket-flow') {
    return 'BRACKET_FLOW';
  }
  if (value === 'bracket-predictions') {
    return 'BRACKET_PREDICTIONS';
  }

  if (value === 'game') {
    return 'GAME';
  }

  return 'TOURNAMENT';
}

function getStatusRoute(): { eventId: string; playerId?: string; teamId?: string } | null {
  const teamMatch = window.location.pathname.match(/^\/status\/(\d+)\/team\/([^/?#]+)\/?$/i);
  if (teamMatch) return { eventId: teamMatch[1], teamId: decodeURIComponent(teamMatch[2]) };
  const playerMatch = window.location.pathname.match(/^\/status\/(\d+)\/(\d+)\/?$/i);
  return playerMatch ? { eventId: playerMatch[1], playerId: playerMatch[2] } : null;
}

function statusMatchForPlayer(matches: (Match & any)[], playerId: string) {
  const playerMatches = matches.filter(match => matchIncludesPlayer(match, playerId) && !matchHasBye(match));
  return playerMatches.find(match => matchLooksLive(match))
    || playerMatches.find(match => !matchLooksCompleted(match))
    || [...playerMatches].sort((a, b) => (
      statusStageOrder(b) - statusStageOrder(a)
      || Number(b.matchId || 0) - Number(a.matchId || 0)
    ))[0];
}

function statusMatchForTeam(matches: (Match & any)[], teamId: string) {
  const teamMatches = matches.filter(match => (
    [match.teams?.top?.id, match.teams?.bottom?.id].some(id => String(id) === String(teamId))
    && !matchHasBye(match)
  ));
  return teamMatches.find(match => matchLooksLive(match))
    || teamMatches.find(match => !matchLooksCompleted(match))
    || [...teamMatches].sort((a, b) => (
      statusStageOrder(b) - statusStageOrder(a)
      || Number(b.matchId || 0) - Number(a.matchId || 0)
    ))[0];
}

function statusStageOrder(match: Match & any) {
  const label = String(match.roundDescription || '');
  const number = Number(label.match(/(\d+)/)?.[1] || 0);
  if (/champ/i.test(label)) return 1000;
  if (/final/i.test(label)) return 900;
  if (/semi/i.test(label)) return 800;
  if (/qtr|quarter/i.test(label)) return 700;
  return number;
}

function updateQueryParams(updates: Record<string, string | undefined>) {
  const url = new URL(window.location.href);

  Object.entries(updates).forEach(([key, value]) => {
    if (value) {
      url.searchParams.set(key, value);
    } else {
      url.searchParams.delete(key);
    }
  });

  window.history.replaceState({}, '', url.toString());
}

function formatTime(value?: string) {
  if (!value) return '-';
  return new Date(value).toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  });
}

function statusIcon(status?: string) {
  if (status === 'live') return '🟢';
  if (status === 'completed') return '✅';
  if (status === 'upcoming') return '⚪';
  return '🟡';
}

function statusLabel(status?: string) {
  if (status === 'live') return 'LIVE';
  if (status === 'completed') return 'COMPLETE';
  if (status === 'upcoming') return 'NOT STARTED';
  return 'UNKNOWN';
}

function isCompleteStatus(value: unknown) {
  const status = String(value ?? '').trim().toUpperCase();
  return status === 'C' || status === 'COMPLETE' || status === 'COMPLETED' || status.includes('COMPLETE');
}

function matchLooksCompleted(match: Match & any) {
  const games = match.games || [];

  if (match.status === 'completed' || match.statusId === 5 || match.matchStatusID === 5) {
    return true;
  }

  if (games.length > 0) {
    return games.every((game: any) => (
      game.statusId === 5 ||
      game.matchStatusID === 5 ||
      isCompleteStatus(game.status) ||
      game.matchEndTime ||
      game.endTime
    ));
  }

  return false;
}

function matchLooksLive(match: Match & any) {
  const games = match.games || [];
  return (
    match.status === 'live' ||
    match.statusId === 0 ||
    match.matchStatusID === 0 ||
    games.some((game: any) => game.statusId === 0 || game.matchStatusID === 0)
  );
}

function hasRealTeams(match: Match & any) {
  return Boolean(match?.teams?.top?.id && match?.teams?.bottom?.id);
}

function matchIncludesPlayer(match: Match & any, playerId: string) {
  const target = String(playerId || '');
  if (!target) return false;
  const rosterPlayers = [
    ...(match?.teams?.top?.players || []),
    ...(match?.teams?.bottom?.players || []),
    ...(match?.raw?.top?.player_info || []),
    ...(match?.raw?.bottom?.player_info || []),
  ];
  if (rosterPlayers.some((player: any) => (
    String(player?.id ?? player?.playerid ?? player?.playerId ?? '') === target
  ))) return true;
  const games = [
    ...(match?.games || []),
    ...(match?.activeGame ? [match.activeGame] : []),
  ];
  return games.some((game: any) => (
    (game?.players || []).some((player: any) => (
      String(player?.id ?? player?.playerId ?? player?.playerID ?? '') === target
    ))
    || (game?.rounds || []).some((round: any) => (
      (round?.players || []).some((player: any) => (
        String(player?.playerId ?? player?.id ?? '') === target
      ))
    ))
  ));
}

function matchHasBye(match: Match & any) {
  const names = [
    match?.teams?.top?.name,
    match?.teams?.bottom?.name,
    match?.raw?.top?.bracketteamname,
    match?.raw?.bottom?.bracketteamname,
  ];

  return names.some(name => String(name || '').toLowerCase().includes('bye'));
}

function shouldAutoRefreshTournament(payload: any) {
  if (!payload) return true;

  if (isCompleteStatus(payload?.event?.status) || isCompleteStatus(payload?.event?.leagueStatus)) {
    return false;
  }

  const matches = payload.matches || [];
  const playableMatches = matches.filter(hasRealTeams);

  if (playableMatches.length === 0) {
    return true;
  }

  return playableMatches.some((match: Match & any) => !matchLooksCompleted(match));
}

function isSwapLikeEvent(event: any) {
  const name = String(event?.name || event?.eventName || event?.leagueName || '').toLowerCase();
  const bracketType = String(event?.bracketType || event?.brackettype || '').toUpperCase();
  const playerPoolSize = Number(event?.playerPoolSize || 0);
  const roundLimitBracket = Number(event?.roundLimitBracket || 0);

  // ACL final brackets often retain "Swap" in their generated name. Once a
  // structured bracket type exists, it is authoritative over that inherited name.
  if (bracketType && !['P', 'W'].includes(bracketType)) return false;

  return (
    bracketType === 'W' ||
    (bracketType === 'P' && (playerPoolSize > 0 || roundLimitBracket > 0)) ||
    (!bracketType && (
      name.includes('swap') ||
      name.includes('rounders') ||
      name.includes('round robin')
    ))
  );
}

function playerStatsThroughRounds(players: PlayerStat[], rounds: RoundRow[]): PlayerStat[] {
  return players.map(player => {
    const playerId = String(player.id ?? '');
    const rows = rounds.flatMap(round => {
      const current = (round.players || []).find(row => String(row.playerId) === playerId);
      if (!current) return [];
      const opponent = (round.players || []).find(row => String(row.teamId) !== String(current.teamId));
      return [{ current, opponent }];
    });
    const points = rows.reduce((sum, row) => sum + Number(row.current.grossPoints || 0), 0);
    const opponentPoints = rows.reduce((sum, row) => sum + Number(row.opponent?.grossPoints || 0), 0);
    const roundsPlayed = rows.length;
    const wins = rows.filter(row => Number(row.current.grossPoints) > Number(row.opponent?.grossPoints)).length;
    const losses = rows.filter(row => Number(row.current.grossPoints) < Number(row.opponent?.grossPoints)).length;
    const ties = roundsPlayed - wins - losses;
    const bagsIn = rows.reduce((sum, row) => sum + Number(row.current.bagsIn || 0), 0);
    const bagsOn = rows.reduce((sum, row) => sum + Number(row.current.bagsOn || 0), 0);
    const bagsOff = rows.reduce((sum, row) => sum + Number(row.current.bagsOff || 0), 0);
    const fourBaggers = rows.filter(row => row.current.fourBagger || Number(row.current.bagsIn) === 4).length;
    return {
      ...player,
      points,
      opponentPoints,
      rounds: roundsPlayed,
      ppr: roundsPlayed ? points / roundsPlayed : 0,
      dpr: roundsPlayed ? (points - opponentPoints) / roundsPlayed : 0,
      roundsWon: wins,
      roundsLost: losses,
      roundsTied: ties,
      roundWinPct: roundsPlayed ? wins * 100 / roundsPlayed : 0,
      roundLossPct: roundsPlayed ? losses * 100 / roundsPlayed : 0,
      roundTiePct: roundsPlayed ? ties * 100 / roundsPlayed : 0,
      bagsIn,
      bagsOn,
      bagsOff,
      bagsInPct: roundsPlayed ? bagsIn * 25 / roundsPlayed : 0,
      fourBaggers,
      fourBaggerPct: roundsPlayed ? fourBaggers * 100 / roundsPlayed : 0,
      pprVsSeason: player.seasonPpr == null || !roundsPlayed
        ? null
        : points / roundsPlayed - Number(player.seasonPpr),
    } as PlayerStat;
  });
}

function getSelectionId(m: Match & any) {
  return `${m.eventId || 'event'}:${m.matchId}:${m.gameId || m.activeGame?.gameId || 1}`;
}

function gameLabel(m: Match & any) {
  const gameId = m.gameId || m.activeGame?.gameId || 1;
  return gameId > 1 ? `Game ${gameId}` : '';
}

function getMatchGameId(m?: Match & any) {
  return Number(m?.gameId || m?.activeGame?.gameId || m?.games?.[0]?.gameId || 1);
}

function normalizeLoadedMatch(m: Match & any) {
  return {
    ...m,
    id: getSelectionId(m),
    gameId: getMatchGameId(m),
    status: forceMatchStatus(m),
  };
}

function forceMatchStatus(m: Match & any) {
  const games = m.games || [];
  const activeGame = m.activeGame;

  const hasEndedGame = games.some((g: any) => g.matchEndTime || g.endTime);
  const allGamesEnded =
    games.length > 0 &&
    games.every((g: any) => g.matchEndTime || g.endTime || g.matchStatusID === 5 || g.statusId === 5);

  if (
    m.matchStatusID === 5 ||
    m.status === 'completed' ||
    allGamesEnded ||
    hasEndedGame
  ) {
    return 'completed';
  }

  if (activeGame && !activeGame.matchEndTime && !activeGame.endTime) {
    return 'live';
  }

  return m.status || 'upcoming';
}

function loadStoredFavorites(): FavoritePlayer[] {
  try {
    const raw = localStorage.getItem('cornhole.favoritePlayers');
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function loadStoredDefaultPlayerId() {
  return localStorage.getItem('cornhole.defaultPlayerId') || '';
}

function saveFavorites(players: FavoritePlayer[]) {
  localStorage.setItem('cornhole.favoritePlayers', JSON.stringify(players));
}

function saveDefaultPlayerId(playerId: string) {
  localStorage.setItem('cornhole.defaultPlayerId', playerId);
}

function loadInitialGameMobileMode(): 'PLAYER' | 'VIEWER' | 'ANALYSIS' {
  if (getStatusRoute()) return 'VIEWER';
  const mode = new URLSearchParams(location.search).get('mode')?.toLowerCase();
  if (mode === 'viewer') return 'VIEWER';
  if (mode === 'analysis') return 'ANALYSIS';
  return 'PLAYER';
}

function loadStoredSeasonSettings() {
  try {
    const raw = localStorage.getItem(SEASON_SETTINGS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveStoredSeasonSettings(settings: any) {
  localStorage.setItem(SEASON_SETTINGS_KEY, JSON.stringify(settings));
}

function loadStoredSeasonData() {
  try {
    const raw = localStorage.getItem(SEASON_DATA_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed?.data || parsed;
  } catch {
    return null;
  }
}

function loadStoredSeasonRecord() {
  try {
    const raw = localStorage.getItem(SEASON_DATA_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed?.data ? parsed : parsed ? { data: parsed, settings: null, loadedAt: null } : null;
  } catch {
    return null;
  }
}

function saveStoredSeasonData(payload: any, settings: any) {
  localStorage.setItem(SEASON_DATA_KEY, JSON.stringify({
    data: payload,
    settings,
    loadedAt: new Date().toISOString(),
  }));
}

async function fetchPlayerEvents(playerId: number, eventStatus = 'ACTIVE') {
  const res = await fetch(
    `/api/player/${playerId}/events?bucket_id=11&eventStatus=${eventStatus}`
  );

  if (!res.ok) {
    throw new Error(`Failed to fetch ${eventStatus.toLowerCase()} events for player ${playerId}`);
  }

  return res.json();
}

async function fetchPlayerCompare(playerId: number) {
  const res = await fetch(`/api/player/${playerId}/compare?bucket_id=11`);

  if (!res.ok) {
    return null;
  }

  return res.json();
}

function ApiStatusBar({
  activeRequests,
  autoRefreshActive,
  lastStartedAt,
  lastFinishedAt,
  lastError,
  stoppedReason,
}: {
  activeRequests: number;
  autoRefreshActive: boolean;
  lastStartedAt: Date | null;
  lastFinishedAt: Date | null;
  lastError?: string;
  stoppedReason?: string;
}) {
  const isActive = activeRequests > 0;
  const apiState = isActive ? `API active (${activeRequests})` : 'API idle';
  const refreshState = autoRefreshActive ? 'Auto-refresh on' : `Auto-refresh off${stoppedReason ? `: ${stoppedReason}` : ''}`;
  const lastEvent = isActive ? lastStartedAt : lastFinishedAt;

  return (
    <section className="rounded-xl border border-white/10 bg-zinc-950/80 px-3 py-2 lg:border-0 lg:bg-transparent lg:px-0 lg:py-0">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-bold text-zinc-300">
        <div className="flex items-center gap-2">
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              isActive ? 'animate-pulse bg-green-400' : lastError ? 'bg-red-400' : 'bg-zinc-500'
            }`}
          />
          <span>{apiState}</span>
        </div>

        <span className={autoRefreshActive ? 'text-green-300' : 'text-blue-300'}>
          {refreshState}
        </span>

        {lastEvent && (
          <span className="text-zinc-500">
            {isActive ? 'Started' : 'Last API'}: {formatTime(lastEvent.toISOString())}
          </span>
        )}

        {lastError && <span className="max-w-xl truncate text-red-300" title={lastError}>Last error: {lastError}</span>}
      </div>
    </section>
  );
}

function topPpr(players: any[]) {
  const best = Math.max(
    0,
    ...(players || []).map(player => Number(player?.ppr || 0)).filter(Number.isFinite)
  );
  return best.toFixed(2);
}

function App() {
  const storedSeasonSettings = loadStoredSeasonSettings();
  const storedSeasonRecord = loadStoredSeasonRecord();
  const initialEventId = getInitialEventId();
  const initialPlayerId = getStatusRoute()?.playerId || useQueryParam('playerId', storedSeasonSettings.playerId || loadStoredDefaultPlayerId() || '');

  const [eventInput, setEventInput] = useState(initialEventId);
  const [eventId, setEventId] = useState(initialEventId);
  const [data, setData] = useState<any>(null);
  const [selected, setSelected] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | undefined>();
  const [standingsData, setStandingsData] = useState<any>(() => (
    getInitialView() === 'STANDINGS' ? storedSeasonRecord?.data || null : null
  ));
  const [standingsLoading, setStandingsLoading] = useState(false);
  const [standingsError, setStandingsError] = useState<string | undefined>();
  const [seasonProgressKey, setSeasonProgressKey] = useState('');
  const [seasonProgress, setSeasonProgress] = useState<any>(null);
  const [standingsLastLoadedAt, setStandingsLastLoadedAt] = useState<Date | null>(
    getInitialView() === 'STANDINGS' && storedSeasonRecord?.data
      ? new Date(storedSeasonRecord.loadedAt || Date.now())
      : null
  );
  const [tournamentStatsData, setTournamentStatsData] = useState<any>(null);
  const [tournamentStatsLoading, setTournamentStatsLoading] = useState(false);
  const [view, setView] = useState<AppView>(getInitialView);
  const [hideByeGames, setHideByeGames] = useState(true);
  const [seasonStartDate, setSeasonStartDate] = useState(useQueryParam('startDate', storedSeasonSettings.startDate || '2026-01-01'));
  const [seasonEndDate, setSeasonEndDate] = useState(useQueryParam('endDate', storedSeasonSettings.endDate || '2026-08-31'));
  const [seasonDateRangeEnabled, setSeasonDateRangeEnabled] = useState(false);
  const [seasonBucketId, setSeasonBucketId] = useState(useQueryParam('bucketId', storedSeasonSettings.bucketId || '11'));
  const [compareBucketId, setCompareBucketId] = useState(useQueryParam('compareBucketId', storedSeasonSettings.compareBucketId || ''));
  const [seasonOptions, setSeasonOptions] = useState<PlayerSeasonOption[]>([]);
  const [seasonOptionsLoading, setSeasonOptionsLoading] = useState(false);
  const [seasonOptionsError, setSeasonOptionsError] = useState<string | undefined>();
  const [playerEventStatus, setPlayerEventStatus] = useState<'ACTIVE' | 'COMPLETED'>(
  'ACTIVE'
);
  const [favorites, setFavorites] = useState<FavoritePlayer[]>(loadStoredFavorites);
  const [defaultPlayerId, setDefaultPlayerId] = useState(loadStoredDefaultPlayerId);
  const [playerInput, setPlayerInput] = useState('');
  const [playerEvents, setPlayerEvents] = useState<PlayerEvent[]>([]);
  const [playerEventsLoading, setPlayerEventsLoading] = useState(false);
  const [playerEventsError, setPlayerEventsError] = useState<string | undefined>();
  const [lastRefreshAt, setLastRefreshAt] = useState<Date | null>(null);
  const [activeApiRequests, setActiveApiRequests] = useState(0);
  const [lastApiStartedAt, setLastApiStartedAt] = useState<Date | null>(null);
  const [lastApiFinishedAt, setLastApiFinishedAt] = useState<Date | null>(null);
  const [lastApiError, setLastApiError] = useState<string | undefined>();
  const [autoRefreshActive, setAutoRefreshActive] = useState(true);
  const [refreshStoppedReason, setRefreshStoppedReason] = useState<string | undefined>();
  const [selectedPlayerId, setSelectedPlayerId] = useState<string>(initialPlayerId);
  const [playersPanelOpen, setPlayersPanelOpen] = useState(false);
  const [eventLoaderOpen, setEventLoaderOpen] = useState(false);
  const [gameMobileMode, setGameMobileMode] = useState<'PLAYER' | 'VIEWER' | 'ANALYSIS'>(loadInitialGameMobileMode);

  useEffect(() => {
    let cancelled = false;
    async function hydrateSharedProfile() {
      try {
        const profile = await fetchSharedViewerProfile();
        if (cancelled) return;
        const nextFavorites = Array.isArray(profile.favoritePlayers) ? profile.favoritePlayers : [];
        const nextDefault = profile.defaultPlayerId ? String(profile.defaultPlayerId) : '';
        setFavorites(nextFavorites);
        setDefaultPlayerId(nextDefault);
        saveFavorites(nextFavorites);
        saveDefaultPlayerId(nextDefault);
        if (!selectedPlayerId && nextDefault) setSelectedPlayerId(nextDefault);
      } catch {
        // Local storage remains a deliberate offline fallback.
      }
    }
    hydrateSharedProfile();
    const onVisible = () => {
      if (document.visibilityState === 'visible') hydrateSharedProfile();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  function persistSharedProfile(nextDefault: string, nextFavorites: FavoritePlayer[]) {
    saveDefaultPlayerId(nextDefault);
    saveFavorites(nextFavorites);
    saveSharedViewerProfile(nextDefault, nextFavorites).catch(() => {
      // Do not block player navigation when the server is temporarily offline.
    });
  }

  useEffect(() => {
    const missingPhotos = favorites.filter(player => !player.photo);
    if (!missingPhotos.length) return;
    let cancelled = false;
    Promise.all(missingPhotos.map(async player => {
      try {
        const profile = await fetchPlayerCompare(player.playerId);
        return {
          ...player,
          name: profile?.name || player.name,
          photo: String(profile?.photo || '').trim() || undefined,
        };
      } catch {
        return player;
      }
    })).then(updates => {
      if (cancelled) return;
      const byId = new Map(updates.map(player => [player.playerId, player]));
      const next = favorites.map(player => byId.get(player.playerId) || player);
      if (next.some((player, index) => player.photo !== favorites[index]?.photo || player.name !== favorites[index]?.name)) {
        setFavorites(next);
        saveFavorites(next);
        saveSharedViewerProfile(defaultPlayerId, next).catch(() => undefined);
      }
    });
    return () => { cancelled = true; };
  }, [favorites.length]);

  function buildSeasonProgressKey(playerId: string, bucketId: string, startDate: string, endDate: string) {
    return [playerId, bucketId, startDate || '', endDate || '', Date.now()].join(':');
  }

  async function trackApiCall<T>(request: () => Promise<T>): Promise<T> {
    setActiveApiRequests(count => count + 1);
    setLastApiStartedAt(new Date());
    setLastApiError(undefined);

    try {
      return await request();
    } catch (e: any) {
      setLastApiError(e?.message || 'API request failed');
      throw e;
    } finally {
      setActiveApiRequests(count => Math.max(0, count - 1));
      setLastApiFinishedAt(new Date());
    }
  }

  function mergeTournamentData(previous: any, nextData: any) {
    if (!previous?.matches?.length || !nextData?.matches?.length) {
      return nextData;
    }

    const previousById = new Map(
      previous.matches.map((match: Match & any) => [
        `${match.matchId}:${getMatchGameId(match)}`,
        match,
      ])
    );

    return {
      ...nextData,
      matches: nextData.matches.map((nextMatch: Match & any) => {
        const previousMatch = previousById.get(`${nextMatch.matchId}:${getMatchGameId(nextMatch)}`);
        if (!previousMatch) return nextMatch;

        const nextGame = nextMatch.activeGame || nextMatch.games?.[0];
        const previousGame = previousMatch.activeGame || previousMatch.games?.[0];
        const nextHasPlayers = (nextGame?.players || []).length > 0;
        const previousHasPlayers = (previousGame?.players || []).length > 0;

        if (nextHasPlayers || !previousHasPlayers) {
          return nextMatch;
        }

        return {
          ...nextMatch,
          games: previousMatch.games,
          activeGame: previousMatch.activeGame,
        };
      }),
    };
  }

  async function load(stats = false, overrideEventId?: string, options: { background?: boolean } = {}) {
    const targetEventId = overrideEventId || eventId;

    if (!options.background) {
      setLoading(true);
    }
    setErr(undefined);

    try {
      const d = await trackApiCall(() => fetchEvent(targetEventId, stats));
	  setLastRefreshAt(new Date());
      const normalizedMatches = (d.matches || []).map((m: Match & any) => normalizeLoadedMatch(m));

      const normalizedData = {
        ...d,
        matches: normalizedMatches,
      };
      const eventNotice = d.notifications?.find((notice: any) => notice?.type === 'event_data_unavailable' && notice?.message);
      if (!normalizedMatches.length && eventNotice?.message) {
        if (!isSwapLikeEvent(normalizedData.event)) {
          setErr(`${eventNotice.message}. ACL has the event record, but the bracket/schedule data is not available from the public bracket endpoint yet.`);
        }
      }
      const shouldKeepRefreshing = shouldAutoRefreshTournament(normalizedData);

      setData((current: any) => (
        options.background ? mergeTournamentData(current, normalizedData) : normalizedData
      ));
      setAutoRefreshActive(shouldKeepRefreshing);
      setRefreshStoppedReason(shouldKeepRefreshing ? undefined : 'Tournament complete');

      setSelected(current => {
        const route = getStatusRoute();
        if (route && String(route.eventId) === String(targetEventId)) {
          return (
            route.teamId
              ? statusMatchForTeam(normalizedMatches, route.teamId)
              : statusMatchForPlayer(normalizedMatches, route.playerId || '')
          )?.id;
        }
        if (current && normalizedMatches.some((m: any) => m.id === current)) {
          return current;
        }

        return (
          normalizedMatches.find((m: Match) => m.status === 'live') ||
          normalizedMatches[0]
        )?.id;
      });

      return normalizedData;
    } catch (e: any) {
      setErr(e.message);
      return null;
    } finally {
      if (!options.background) {
        setLoading(false);
      }
    }
  }

  async function loadMatchGameStats(targetMatch: Match & any) {
    if (!targetMatch?.matchId) return null;

    const targetGameId = getMatchGameId(targetMatch);
    const updated = await trackApiCall(() => (
      fetchMatchGameStats(targetMatch.eventId || eventId, targetMatch.matchId, targetGameId, true)
    ));
    const normalized = normalizeLoadedMatch(updated);

    setData((current: any) => {
      if (!current?.matches) return current;

      const matches = current.matches.map((existing: Match & any) => {
        const sameMatch = String(existing.matchId) === String(normalized.matchId);
        const sameGame = getMatchGameId(existing) === getMatchGameId(normalized);

        if (!sameMatch || !sameGame) return existing;

        const nextGame = normalized.activeGame || normalized.games?.[0];
        const existingGame = existing.activeGame || existing.games?.[0];
        const nextHasPlayers = (nextGame?.players || []).length > 0;
        const existingHasPlayers = (existingGame?.players || []).length > 0;
        const preserveBracketFinal = matchLooksCompleted(existing) && hasMeaningfulFinalScore(existingGame?.score || existing.score);
        const resolvedScore = preserveBracketFinal
          ? (existingGame?.score || existing.score)
          : (nextGame?.score || normalized.score || existingGame?.score || existing.score);

        if (!nextHasPlayers && existingHasPlayers) {
          return {
            ...existing,
            status: normalized.status,
            statusId: normalized.statusId,
            championshipDoubleDip: normalized.championshipDoubleDip || existing.championshipDoubleDip,
            score: resolvedScore,
            activeGame: {
              ...existingGame,
              score: resolvedScore,
              currentRound: nextGame?.currentRound || existingGame?.currentRound,
              status: nextGame?.status || existingGame?.status,
              statusId: nextGame?.statusId || existingGame?.statusId,
            },
          };
        }

        const merged = { ...existing, ...normalized };
        if (!preserveBracketFinal) return merged;
        const mergedGame = merged.activeGame || merged.games?.[0];
        return {
          ...merged,
          score: resolvedScore,
          activeGame: mergedGame ? { ...mergedGame, score: resolvedScore } : mergedGame,
          games: (merged.games || []).map((item: any, index: number) => (
            index === 0 ? { ...item, score: resolvedScore } : item
          )),
        };
      });

      return { ...current, matches };
    });

    setSelected(normalized.id);
    return normalized;
  }

  function hasMeaningfulFinalScore(score: any) {
    const top = Number(score?.top || 0);
    const bottom = Number(score?.bottom || 0);
    return Number.isFinite(top) && Number.isFinite(bottom) && (top > 0 || bottom > 0);
  }

  function openTournamentGame(matchOrId: string | (Match & any)) {
    if (typeof matchOrId === 'string') {
      setSelected(matchOrId);
      setView('GAME');
      return;
    }

    const normalized = normalizeLoadedMatch(matchOrId);
    setData((current: any) => {
      if (!current) return { event: data?.event, matches: [normalized] };

      const matches = current.matches || [];
      const key = `${normalized.matchId}:${getMatchGameId(normalized)}`;
      const nextMatches = matches.some((existing: Match & any) => `${existing.matchId}:${getMatchGameId(existing)}` === key)
        ? matches.map((existing: Match & any) => `${existing.matchId}:${getMatchGameId(existing)}` === key ? normalized : existing)
        : [...matches, normalized];

      return { ...current, matches: nextMatches };
    });
    setSelected(normalized.id);
    setView('GAME');
  }
async function loadStandings(overrides: {
  playerId?: string;
  bucketId?: string;
  startDate?: string;
  endDate?: string;
  useSaved?: boolean;
  detectSeason?: boolean;
} = {}) {
  if (standingsLoading) return;

  const playerId = overrides.playerId || selectedPlayerId || defaultPlayerId || storedSeasonSettings.playerId || '142125';
  const bucketId = overrides.bucketId || seasonBucketId || storedSeasonSettings.bucketId || '11';
  const explicitDateRange = seasonDateRangeEnabled || overrides.startDate !== undefined || overrides.endDate !== undefined;
  const startDate = overrides.detectSeason || !explicitDateRange ? '' : (overrides.startDate || seasonStartDate);
  const endDate = overrides.detectSeason || !explicitDateRange ? '' : (overrides.endDate || seasonEndDate);
  const settings = { playerId, bucketId, startDate, endDate };

  if (overrides.useSaved) {
    const saved = loadStoredSeasonRecord();
    if (saved?.data) {
      setStandingsData(saved.data);
      setStandingsLastLoadedAt(saved.loadedAt ? new Date(saved.loadedAt) : new Date());
      setStandingsError(undefined);
      setLastApiError(undefined);
      if (saved.settings) {
        if (saved.settings.playerId) setSelectedPlayerId(String(saved.settings.playerId));
        if (saved.settings.bucketId) setSeasonBucketId(String(saved.settings.bucketId));
        if (saved.settings.compareBucketId) setCompareBucketId(String(saved.settings.compareBucketId));
        if (saved.settings.startDate) setSeasonStartDate(saved.settings.startDate);
        if (saved.settings.endDate) setSeasonEndDate(saved.settings.endDate);
        updateQueryParams({
          view: 'season-stats',
          seedEventId: undefined,
          playerId: saved.settings.playerId,
          bucketId: saved.settings.bucketId,
          compareBucketId: saved.settings.compareBucketId || undefined,
          startDate: saved.settings.startDate || undefined,
          endDate: saved.settings.endDate || undefined,
        });
      }
    }
    return;
  }

  updateQueryParams({
    view: 'season-stats',
    seedEventId: undefined,
    playerId,
    bucketId,
    compareBucketId: compareBucketId || undefined,
    startDate,
    endDate,
  });

  saveStoredSeasonSettings(settings);

  setStandingsLoading(true);
  setStandingsError(undefined);
  setSeasonProgress(null);
  const progressKey = buildSeasonProgressKey(playerId, bucketId, startDate, endDate);
  setSeasonProgressKey(progressKey);

  try {
    const result = await trackApiCall(() => fetchIndividualSeasonStats({
      playerId,
      bucketId,
      startDate: startDate || undefined,
      endDate: endDate || undefined,
      progressKey,
      refreshIndex: true,
    }));
    const detected = result?.manifest?.seasonDefinition;
    const detectedStartDate = detected?.selectedStartDate || detected?.startDate;
    const detectedEndDate = detected?.selectedEndDate || detected?.endDate;
    const savedSettings = {
      playerId,
      bucketId,
      compareBucketId,
      startDate: detectedStartDate || startDate,
      endDate: detectedEndDate || endDate,
    };

    setStandingsData(result);
    if (detectedStartDate) setSeasonStartDate(detectedStartDate);
    if (detectedEndDate) setSeasonEndDate(detectedEndDate);
    saveStoredSeasonSettings(savedSettings);
    saveStoredSeasonData(result, savedSettings);
    setStandingsLastLoadedAt(new Date());
  } catch (e: any) {
    setStandingsError(e?.message || 'Unable to load season stats.');
  } finally {
    setStandingsLoading(false);
  }
}

useEffect(() => {
  if (!standingsLoading || !seasonProgressKey) return;

  let cancelled = false;
  let timer: number | undefined;

  async function pollProgress() {
    try {
      const progress = await fetchSeasonProgress(seasonProgressKey);
      if (!cancelled) {
        setSeasonProgress(progress);
      }
    } catch {
      // Loading state already remains visible if progress polling misses.
    }
  }

  pollProgress();
  timer = window.setInterval(pollProgress, 1000);

  return () => {
    cancelled = true;
    if (timer) {
      window.clearInterval(timer);
    }
  };
}, [standingsLoading, seasonProgressKey]);

async function loadSeasonOptions(playerIdValue?: string, refreshIndex = false) {
  const playerId = playerIdValue || selectedPlayerId || defaultPlayerId || storedSeasonSettings.playerId;
  if (!playerId) return;

  setSeasonOptionsLoading(true);
  setSeasonOptionsError(undefined);

  try {
    const result = await fetchPlayerSeasonOptions(playerId, refreshIndex);
    const seasons = result.seasons || [];
    setSeasonOptions(seasons);
    setLastApiError(undefined);

    if (seasons.length > 0 && !seasons.some(season => String(season.bucketId) === String(seasonBucketId))) {
      const first = seasons.find(season => season.bucketId !== 'career') || seasons[0];
      setSeasonBucketId(String(first.bucketId));
      setSeasonStartDate(first.startDate);
      setSeasonEndDate(first.endDate);
    }
  } catch (e: any) {
    setSeasonOptionsError(e?.message || 'Unable to load season list.');
  } finally {
    setSeasonOptionsLoading(false);
  }
}

async function loadTournamentStats() {
  if (!eventId) return;

  setTournamentStatsLoading(true);

  try {
    const result = await trackApiCall(() => fetchTournamentStats(eventId));
    setTournamentStatsData(result);
  } finally {
    setTournamentStatsLoading(false);
  }
}
useEffect(() => {
  if (view === 'STANDINGS') {
    loadStandings({ useSaved: true });
    loadSeasonOptions();
  }

  if (view === 'STATISTICS') {
    loadTournamentStats();
  }
}, [view, seasonStartDate, seasonEndDate, eventId, selectedPlayerId, defaultPlayerId]);


async function loadPlayerEvents(
  playerIdValue?: string,
  requestedStatus: 'ACTIVE' | 'COMPLETED' = playerEventStatus
) {
  const id = Number(playerIdValue || selectedPlayerId || defaultPlayerId);

  if (!id) {
    setPlayerEvents([]);
    return;
  }

  setPlayerEventsLoading(true);
  setPlayerEventsError(undefined);

  try {
    const activePayload = await trackApiCall(() => fetchPlayerEvents(id, requestedStatus));
    const activeEvents = activePayload.events || [];

    if (requestedStatus === 'ACTIVE' && activeEvents.length === 0) {
      const completedPayload = await trackApiCall(() => fetchPlayerEvents(id, 'COMPLETED'));
      setPlayerEvents(completedPayload.events || []);
      setPlayerEventStatus('COMPLETED');
    } else {
      setPlayerEvents(activeEvents);
      setPlayerEventStatus(requestedStatus);
    }
  } catch (e: any) {
    setPlayerEventsError(e.message);
    setPlayerEvents([]);
  } finally {
    setPlayerEventsLoading(false);
  }
}

  async function addFavoritePlayer() {
    const id = Number(playerInput.trim());

    if (!id) {
      setPlayerEventsError('Enter a valid player ID.');
      return;
    }

    const alreadyExists = favorites.some(p => p.playerId === id);

    let name: string | undefined;
    let photo: string | undefined;

    try {
      const profile = await trackApiCall(() => fetchPlayerCompare(id));
      name = profile?.name;
      photo = String(profile?.photo || '').trim() || undefined;
    } catch {
      name = undefined;
    }

    const next = alreadyExists
      ? favorites.map(p => (p.playerId === id ? { ...p, name: name || p.name, photo: photo || p.photo } : p))
      : [...favorites, { playerId: id, name, photo }];

    setFavorites(next);

    setPlayerInput('');
    setSelectedPlayerId(String(id));

    if (!defaultPlayerId) {
      setDefaultPlayerId(String(id));
      persistSharedProfile(String(id), next);
    } else {
      persistSharedProfile(defaultPlayerId, next);
    }

    await loadPlayerEvents(String(id), 'ACTIVE');
  }

  function removeFavoritePlayer(playerId: number) {
    const next = favorites.filter(p => p.playerId !== playerId);
    setFavorites(next);

    let nextDefault = defaultPlayerId;
    if (defaultPlayerId === String(playerId)) {
      nextDefault = next[0]?.playerId ? String(next[0].playerId) : '';
      setDefaultPlayerId(nextDefault);
    }
    persistSharedProfile(nextDefault, next);

    if (selectedPlayerId === String(playerId)) {
      const nextSelected = next[0]?.playerId ? String(next[0].playerId) : '';
      setSelectedPlayerId(nextSelected);
      setPlayerEvents([]);
      if (nextSelected) {
        loadPlayerEvents(nextSelected, 'ACTIVE');
      }
    }
  }

  function chooseFavoritePlayer(playerId: number) {
    setSelectedPlayerId(String(playerId));
    loadPlayerEvents(String(playerId), 'ACTIVE');
    if (view === 'STANDINGS') {
      loadStandings({ playerId: String(playerId) });
    }
  }

  function makeDefaultPlayer(playerId: number) {
    setDefaultPlayerId(String(playerId));
    persistSharedProfile(String(playerId), favorites);
    setSelectedPlayerId(String(playerId));
    loadPlayerEvents(String(playerId), 'ACTIVE');
    if (view === 'STANDINGS') {
      loadStandings({ playerId: String(playerId) });
    }
  }

  function applySeasonOption(bucketId: string) {
    const option = seasonOptions.find(season => String(season.bucketId) === String(bucketId));
    setSeasonBucketId(bucketId);

    if (option) {
      setSeasonStartDate(option.startDate);
      setSeasonEndDate(option.endDate);
    }

    setSeasonDateRangeEnabled(false);
    setStandingsData(null);
    setStandingsLastLoadedAt(null);
  }

  function openPlayerEvent(event: PlayerEvent) {
    const nextEventId = String(event.eventId);
    setEventInput(nextEventId);
    setEventId(nextEventId);
    setEventLoaderOpen(true);

    updateQueryParams({ event_id: nextEventId, seedEventId: nextEventId });

    load(false, nextEventId);
	setView('TOURNAMENT');
  }

  async function submitEventLoad(nextEventId = eventInput.trim()) {
    if (!nextEventId || loading) return;

    setEventInput(nextEventId);
    setEventId(nextEventId);
    updateQueryParams({ event_id: nextEventId, seedEventId: nextEventId });
    await load(false, nextEventId);
    setView('TOURNAMENT');
  }

  async function refreshWithDefaultPlayerPriority() {
    if (!defaultPlayerId) {
      await load(false, undefined, { background: Boolean(data) });
      return;
    }

    setLoading(true);
    setErr(undefined);
    try {
      const activePayload = await trackApiCall(() => (
        fetchPlayerEvents(Number(defaultPlayerId), 'ACTIVE')
      ));
      const activeEvents = [...(activePayload.events || [])].sort((a: PlayerEvent, b: PlayerEvent) => (
        Number(Boolean(b.bracketStarted)) - Number(Boolean(a.bracketStarted))
        || String(b.date || '').localeCompare(String(a.date || ''))
      ));

      let activeTournament: PlayerEvent | undefined;
      for (const event of activeEvents) {
        if (!event.eventId) continue;
        activeTournament ||= event;
        const payload = await trackApiCall(() => fetchEvent(String(event.eventId), false));
        const matches = (payload.matches || []).map((row: Match & any) => normalizeLoadedMatch(row));
        const playingMatch = matches.find((row: Match & any) => (
          matchLooksLive(row) && matchIncludesPlayer(row, defaultPlayerId)
        ));
        if (!playingMatch) continue;

        const nextEventId = String(event.eventId);
        const normalizedData = { ...payload, matches };
        setEventInput(nextEventId);
        setEventId(nextEventId);
        setData(normalizedData);
        setSelected(playingMatch.id);
        setView('GAME');
        setLastRefreshAt(new Date());
        setAutoRefreshActive(true);
        setRefreshStoppedReason(undefined);
        updateQueryParams({
          event_id: nextEventId,
          seedEventId: nextEventId,
          view: 'game',
        });
        return;
      }

      if (activeTournament) {
        const nextEventId = String(activeTournament.eventId);
        setEventInput(nextEventId);
        setEventId(nextEventId);
        updateQueryParams({
          event_id: nextEventId,
          seedEventId: nextEventId,
          view: 'tournament',
        });
        await load(false, nextEventId);
        setView('TOURNAMENT');
        return;
      }

      await load(false, undefined, { background: Boolean(data) });
    } catch (e: any) {
      setErr(e?.message || 'The default player’s live match could not be checked.');
      await load(false, undefined, { background: Boolean(data) });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    async function startRefreshLoop() {
      setAutoRefreshActive(true);
      setRefreshStoppedReason(undefined);

      const initialData = await load(false);

      if (cancelled || !shouldAutoRefreshTournament(initialData)) {
        return;
      }

      timer = window.setInterval(async () => {
        const latestData = await load(false, undefined, { background: true });

        if (!shouldAutoRefreshTournament(latestData) && timer) {
          window.clearInterval(timer);
          timer = undefined;
        }
      }, BRACKET_REFRESH_MS);
    }

    startRefreshLoop();

    return () => {
      cancelled = true;
      if (timer) {
        window.clearInterval(timer);
      }
    };
  }, [eventId]);

  useEffect(() => {
    const id = selectedPlayerId || defaultPlayerId;
    if (id) {
      loadPlayerEvents(id, 'ACTIVE');
    }
  }, []);

  const match: (Match & any) | undefined = useMemo(
    () => {
      const route = getStatusRoute();
      if (route && data?.matches) {
        return data.matches.find((m: any) => m.id === selected)
          || (
            route.teamId
              ? statusMatchForTeam(data.matches, route.teamId)
              : statusMatchForPlayer(data.matches, route.playerId || '')
          );
      }
      return data?.matches?.find((m: any) => m.id === selected) || data?.matches?.[0];
    },
    [data, selected]
  );

  const game = match?.activeGame || match?.games?.[0];
  const players = game?.players || [];
  const rounds = game?.rounds || [];
  const [selectedReplayRound, setSelectedReplayRound] = useState<number | null>(null);
  const displayedRound = selectedReplayRound ?? (rounds.length ? Number(rounds[rounds.length - 1].round) : null);
  const latestRound = rounds.length ? Number(rounds[rounds.length - 1].round) : 0;
  const replayRounds = displayedRound == null
    ? rounds
    : rounds.filter((round: any) => Number(round.round) <= displayedRound);
  const replayState = replayRounds[replayRounds.length - 1]?.gameState;
  const replayScore = displayedRound === 0 ? { top: 0, bottom: 0 } : replayState ? {
    top: Number(replayState.scoreAfter?.[String(match?.teams?.top?.id)] || 0),
    bottom: Number(replayState.scoreAfter?.[String(match?.teams?.bottom?.id)] || 0),
  } : game?.score;
  const replayPlayers = playerStatsThroughRounds(players, replayRounds);
  const replayGame = game ? {
    ...game,
    currentRound: displayedRound,
    rounds: replayRounds,
    score: replayScore,
  } : game;
  const replayMatch = match ? {
    ...match,
    status: displayedRound === 0 ? 'upcoming' : displayedRound != null && displayedRound < latestRound ? 'live' : match.status,
    currentRound: displayedRound,
    score: replayScore,
    activeGame: replayGame,
    games: replayGame ? [replayGame] : [],
  } : match;

  useEffect(() => {
    setSelectedReplayRound(null);
    if (!new URLSearchParams(location.search).get('mode')) setGameMobileMode('PLAYER');
  }, [match?.eventId, match?.matchId, game?.gameId]);

  useEffect(() => {
    if (view !== 'GAME' || !match?.matchId) return;
    if (!matchLooksLive(match) && !matchLooksCompleted(match)) return;

    let cancelled = false;
    let timer: number | undefined;

    async function refreshSelectedGame() {
      try {
        const updated = await loadMatchGameStats(match);

        if (!cancelled && updated && matchLooksCompleted(updated) && timer) {
          window.clearInterval(timer);
          timer = undefined;
        }
      } catch {
        // The API status bar already surfaces the request failure.
      }
    }

    refreshSelectedGame();

    if (matchLooksLive(match) && !matchLooksCompleted(match)) {
      timer = window.setInterval(refreshSelectedGame, MATCH_STATS_REFRESH_MS);
    }

    return () => {
      cancelled = true;
      if (timer) {
        window.clearInterval(timer);
      }
    };
  }, [view, eventId, selected]);

  const sortedMatches = useMemo(() => {
    return [...(data?.matches || [])].sort((a: any, b: any) => {
      const aMatch = Number(a.matchId);
      const bMatch = Number(b.matchId);

      if (aMatch !== bMatch) return aMatch - bMatch;

      const aGame = Number(a.gameId || a.activeGame?.gameId || 1);
      const bGame = Number(b.gameId || b.activeGame?.gameId || 1);

      return aGame - bGame;
    });
  }, [data]);

  const visibleTournamentMatches = useMemo(() => {
    return hideByeGames
      ? sortedMatches.filter((match: Match & any) => !matchHasBye(match))
      : sortedMatches;
  }, [sortedMatches, hideByeGames]);

  const selectedFavorite = favorites.find(player => selectedPlayerId === String(player.playerId));
  const defaultFavorite = favorites.find(player => defaultPlayerId === String(player.playerId));
  const favoriteSummary = defaultFavorite?.name || selectedFavorite?.name || (defaultPlayerId ? `Player ${defaultPlayerId}` : 'No default player');
  const stagedEventId = eventInput.trim() || eventId;
  const stagedPlayerEvent = playerEvents.find(event => String(event.eventId) === String(stagedEventId));
  const currentEventName = data?.event?.name || `Event ${eventId}`;
  const stagedEventName = stagedPlayerEvent?.name || (String(stagedEventId) === String(eventId) ? currentEventName : 'Ready to load');
  const isSwapEvent = isSwapLikeEvent(data?.event);
  const selectedSeasonOption = seasonOptions.find(season => String(season.bucketId) === String(seasonBucketId));
  const compareSeasonOption = seasonOptions.find(season => String(season.bucketId) === String(compareBucketId));
  const pageWidthClass = view === 'BRACKET_FLOW' ? 'max-w-[1600px]' : 'max-w-6xl';
  const statusRoute = getStatusRoute();

  useEffect(() => {
    if (isSwapEvent && !['TOURNAMENT', 'GAME', 'PROFILE', 'LEADERBOARD', 'PREDICTIONS', 'VENUES'].includes(view)) {
      setView('TOURNAMENT');
      updateQueryParams({ view: undefined });
    }
  }, [isSwapEvent, view]);

  return (
    <main className={`min-h-screen w-full overflow-x-hidden safe-x py-2 lg:py-1 ${pageWidthClass} mx-auto`}>
      {!statusRoute && <div className="sticky top-0 z-20 bg-black/85 backdrop-blur">
      <header className="flex items-center justify-between gap-3 py-2">
	  {view === 'GAME' && (
							  <button
								onClick={() => setView('TOURNAMENT')}
								className="rounded-xl border border-white/10 px-3 py-2 text-sm"
							  >
								← Tournament View
							  </button>
							)}
        <div>
          <div className="text-[10px] uppercase tracking-[.25em] text-amber-300">
            Cornhole Live
          </div>

          <h1 className="mobile-event-title max-w-[270px] text-lg font-black leading-tight sm:max-w-none lg:text-xl">
            {data?.event?.name || 'Live Scoreboard'}
          </h1>

          <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-zinc-400">
            <span>Refresh: {lastRefreshAt ? formatTime(lastRefreshAt.toISOString()) : '-'}</span>
			<span>ACL: {formatTime(data?.meta?.aclResponseDate)}</span>
            {match && (
              <span>
                {statusIcon(match.status)} {statusLabel(match.status)}
              </span>
            )}
          </div>
        </div>

          <button
            type="button"
            onClick={refreshWithDefaultPlayerPriority}
            disabled={loading}
            className="rounded-full border border-white/10 bg-zinc-900 p-2.5 transition hover:border-white/25 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
            title={loading ? 'Refreshing' : 'Refresh and check the default player’s active match'}
          >
          <RefreshCw className={loading ? 'animate-spin' : ''} size={18} />
        </button>
      </header>

      <div className="pb-2">
        <ApiStatusBar
          activeRequests={activeApiRequests}
          autoRefreshActive={autoRefreshActive}
          lastStartedAt={lastApiStartedAt}
          lastFinishedAt={lastApiFinishedAt}
          lastError={lastApiError}
          stoppedReason={refreshStoppedReason}
        />
      </div>
      </div>}

      {view !== 'GAME' && (<>
      <div className="mt-2 grid gap-2 lg:grid-cols-2">
      <section className={`glass min-w-0 rounded-2xl ${playersPanelOpen ? 'p-4' : 'px-4 py-3'}`}>
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setPlayersPanelOpen(open => !open)}
            className="flex min-w-0 flex-1 items-center gap-3 text-left"
            aria-expanded={playersPanelOpen}
          >
            <ChevronDown
              size={20}
              className={`shrink-0 transition-transform ${playersPanelOpen ? '' : '-rotate-90'}`}
            />
            <div className="min-w-0">
              <h2 className="text-base font-black leading-tight">Favorite Players</h2>
              <div className="truncate text-xs text-zinc-400">
                {favoriteSummary} / {playerEventStatus === 'ACTIVE' ? 'Active events' : 'Completed events'} / {playerEvents.length} shown
              </div>
            </div>
          </button>

          <button
            type="button"
            onClick={() => loadPlayerEvents()}
            disabled={playerEventsLoading}
            className="rounded-full border border-white/10 bg-zinc-900 p-2.5 transition hover:border-white/25 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
            title={playerEventsLoading ? 'Refreshing player events' : 'Refresh player events'}
          >
            <RefreshCw
              className={playerEventsLoading ? 'animate-spin' : ''}
              size={16}
            />
          </button>
        </div>

        {playersPanelOpen && (
          <div className="mt-4">
            <form
              onSubmit={e => {
                e.preventDefault();
                addFavoritePlayer();
              }}
              className="grid grid-cols-[1fr_auto] gap-2"
            >
              <input
                className="flex-1 rounded-2xl bg-zinc-900 border border-white/10 px-4 py-3"
                value={playerInput}
                onChange={e => setPlayerInput(e.target.value)}
                placeholder="ACL Player ID"
                inputMode="numeric"
              />
              <button className="min-h-12 rounded-2xl bg-amber-400 px-5 font-black text-black">
                Add
              </button>
            </form>

            {favorites.length > 0 && (
              <div className="mt-3 grid gap-2 sm:flex sm:overflow-x-auto sm:pb-1">
                {favorites.map(player => {
                  const isSelected = selectedPlayerId === String(player.playerId);
                  const isDefault = defaultPlayerId === String(player.playerId);

                  return (
                    <div
                      key={player.playerId}
                      className={`w-full rounded-2xl border px-3 py-3 sm:w-auto sm:shrink-0 sm:py-2 ${
                        isSelected
                          ? 'bg-white text-black border-white'
                          : 'bg-zinc-900 border-white/10'
                      }`}
                    >
                      <button
                        onClick={() => chooseFavoritePlayer(player.playerId)}
                        className="flex w-full items-center gap-3 text-left"
                      >
                        <PlayerAvatar name={player.name} photo={player.photo} size="sm" />
                        <div>
                          <div className="text-xs opacity-70">
                            Player {player.playerId}
                          </div>
                          <div className="font-black sm:max-w-[180px] sm:truncate">
                            {player.name || `Player ${player.playerId}`}
                          </div>
                        </div>
                      </button>

                      <div className="mt-2 flex items-center gap-2">
                        <button
                          onClick={() => makeDefaultPlayer(player.playerId)}
                          className={`rounded-full px-2 py-1 text-xs border ${
                            isDefault
                              ? 'bg-amber-400 text-black border-amber-400'
                              : 'border-white/20'
                          }`}
                          title="Set default"
                        >
                          <Star size={12} className="inline mr-1" />
                          Default
                        </button>

                        <button
                          onClick={() => removeFavoritePlayer(player.playerId)}
                          className="rounded-full px-2 py-1 text-xs border border-white/20"
                          title="Remove player"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {playerEventsError && (
              <div className="mt-3 rounded-2xl bg-red-950 border border-red-500/40 p-3 text-sm">
                {playerEventsError}
              </div>
            )}

            <div className="mt-3">
              <div className="mb-2 flex items-center justify-between">
                <div className="text-xs uppercase tracking-[.2em] text-zinc-500">
                  {playerEventStatus === 'ACTIVE' ? 'Active Events' : 'Completed Events'}
                </div>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => loadPlayerEvents(undefined, 'ACTIVE')}
                    className={`min-h-11 rounded-xl border px-3 py-2 text-sm font-bold sm:min-h-0 sm:rounded sm:px-2 sm:py-1 sm:text-xs ${
                      playerEventStatus === 'ACTIVE'
                        ? 'bg-amber-400 text-black'
                        : 'bg-zinc-900 border-white/10'
                    }`}
                  >
                    Active
                  </button>

                  <button
                    type="button"
                    onClick={() => loadPlayerEvents(undefined, 'COMPLETED')}
                    className={`min-h-11 rounded-xl border px-3 py-2 text-sm font-bold sm:min-h-0 sm:rounded sm:px-2 sm:py-1 sm:text-xs ${
                      playerEventStatus === 'COMPLETED'
                        ? 'bg-amber-400 text-black'
                        : 'bg-zinc-900 border-white/10'
                    }`}
                  >
                    Completed
                  </button>
                </div>
              </div>

              {playerEventsLoading && (
                <div className="text-sm text-zinc-400">Loading events...</div>
              )}

              {!playerEventsLoading && playerEvents.length === 0 && (
                <div className="text-sm text-zinc-400">
                  No events found for the selected player.
                </div>
              )}

              {playerEvents.length > 0 && (
                <div className="max-h-[360px] space-y-2 overflow-y-auto pr-1 sm:flex sm:max-h-none sm:space-y-0 sm:overflow-x-auto sm:overflow-y-hidden sm:pb-1 sm:pr-0">
                  {playerEvents.map(event => (
                    <button
                      key={event.eventId}
                      type="button"
                      onClick={() => openPlayerEvent(event)}
                      className={`w-full rounded-2xl border px-4 py-3 text-left sm:w-auto sm:shrink-0 ${
                        String(event.eventId) === String(eventInput || eventId)
                          ? 'bg-amber-400 text-black border-amber-400'
                          : 'bg-zinc-900 border-white/10'
                      }`}
                    >
                      <div className="text-sm opacity-70 sm:text-xs">
                        Event {event.eventId} / {event.matchType || '?'}
                        {event.blindDraw ? ' / Blind Draw' : ''}
                      </div>

                      <div className="mt-1 whitespace-normal text-base font-black leading-snug sm:mt-0 sm:max-w-[260px] sm:truncate">
                        {event.name}
                      </div>

                      <div className="mt-1 whitespace-normal text-sm opacity-70 sm:mt-0 sm:max-w-[260px] sm:truncate sm:text-xs">
                        {event.date || '-'} / {event.location?.name || 'Location TBD'}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      <section className={`min-w-0 rounded-2xl border border-white/10 bg-zinc-900/80 ${eventLoaderOpen ? 'p-4' : 'px-4 py-3'}`}>
        <button
          type="button"
          onClick={() => setEventLoaderOpen(open => !open)}
          className="flex w-full items-center gap-3 text-left"
          aria-expanded={eventLoaderOpen}
        >
          <ChevronDown
            size={20}
            className={`shrink-0 transition-transform ${eventLoaderOpen ? '' : '-rotate-90'}`}
          />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-black leading-tight text-zinc-300">Load Event</div>
            <div className="truncate text-xs text-zinc-500">
              {stagedEventId} / {stagedEventName}
            </div>
          </div>
        </button>

        {eventLoaderOpen && (
          <form
            onSubmit={e => {
              e.preventDefault();
              submitEventLoad();
            }}
            className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto]"
          >
            <input
              className="min-w-0 rounded-2xl bg-zinc-950 border border-white/10 px-4 py-3 text-base font-semibold"
              value={eventInput}
              onChange={e => setEventInput(e.target.value)}
              placeholder="Event ID"
              inputMode="numeric"
            />
            <button
              type="submit"
              disabled={loading || !eventInput.trim()}
              className="inline-flex min-h-[48px] items-center justify-center gap-2 rounded-2xl border border-amber-300 bg-amber-400 px-5 font-black text-black transition hover:bg-amber-300 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-zinc-800 disabled:text-zinc-500"
            >
              <RefreshCw className={loading ? 'animate-spin' : ''} size={17} />
              {loading ? 'Loading Event' : 'Load Event'}
            </button>
          </form>
        )}
      </section>
      </div>

      {err && (
        <div className="mt-3 rounded-2xl bg-red-950 border border-red-500/40 p-3 text-sm">
          {err}
        </div>
      )}
	  <div className="mt-2 flex flex-wrap items-center gap-2">
        {isSwapEvent && (
          <div className="w-full rounded-xl border border-amber-300/30 bg-amber-300/10 px-3 py-2 text-sm font-black text-amber-100">
            Swap Seeding Event
          </div>
        )}
        {!isSwapEvent ? (
          <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-4">
            {(['TOURNAMENT', 'BRACKET_FLOW', 'BRACKET_PREDICTIONS', 'STATISTICS', 'STANDINGS', 'PREDICTIONS', 'RESEARCH', 'PROFILE', 'LEADERBOARD', 'DIRECTORY', 'DIRECTORS', 'VENUES'] as const).map(nextView => (
              <button
                key={nextView}
                type="button"
                onClick={() => {
                  setView(nextView);
                  updateQueryParams({
                    view: nextView === 'TOURNAMENT'
                      ? undefined
                      : nextView === 'BRACKET_FLOW'
                        ? 'bracket-flow'
                        : nextView === 'BRACKET_PREDICTIONS'
                          ? 'bracket-predictions'
                        : nextView === 'STANDINGS'
                          ? 'season'
                          : nextView === 'PREDICTIONS'
                            ? 'predictions'
                            : nextView === 'RESEARCH'
                              ? 'model-research'
                            : nextView === 'LEADERBOARD'
                              ? 'leaderboard'
                            : nextView === 'DIRECTORY'
                              ? 'directory'
                            : nextView === 'DIRECTORS'
                              ? 'directors'
                              : nextView === 'VENUES'
                                ? 'venues'
                              : nextView === 'PROFILE'
                                ? 'profile'
                              : 'statistics',
                    playerId: nextView === 'PROFILE'
                      ? (selectedPlayerId || defaultPlayerId || '142125')
                      : undefined,
                  });
                }}
                className={`min-h-[58px] rounded-2xl border px-4 py-3 text-base font-black transition-all duration-150 active:translate-y-1 active:scale-[.98] ${
                  view === nextView
                    ? 'translate-y-[2px] border-amber-300 bg-amber-400 text-black shadow-[inset_0_3px_0_rgba(255,255,255,.35),0_2px_0_rgb(146,96,0),0_0_22px_rgba(252,211,77,.18)]'
                    : 'border-white/15 bg-zinc-900 text-zinc-100 shadow-[0_4px_0_rgb(24,24,27)] hover:-translate-y-[1px] hover:border-white/35 hover:bg-zinc-800 hover:shadow-[0_5px_0_rgb(24,24,27)]'
                }`}
                aria-pressed={view === nextView}
              >
                {nextView === 'TOURNAMENT' ? 'Matches' : nextView === 'BRACKET_FLOW' ? 'Bracket Flow' : nextView === 'BRACKET_PREDICTIONS' ? 'Bracket Predictions' : nextView === 'STATISTICS' ? 'Tournament Stats' : nextView === 'STANDINGS' ? 'Season Stats' : nextView === 'PREDICTIONS' ? 'Predictions' : nextView === 'RESEARCH' ? 'Model Research Lab' : nextView === 'PROFILE' ? 'Player Profile' : nextView === 'DIRECTORY' ? 'Player Directory' : nextView === 'DIRECTORS' ? 'Directors' : nextView === 'VENUES' ? 'Venues' : 'Player Rankings'}
              </button>
            ))}
          </div>
        ) : (
          <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-4">
            {([
              ['TOURNAMENT', 'Swap Event'],
              ['PREDICTIONS', 'Predictions'],
              ['RESEARCH', 'Model Research Lab'],
              ['PROFILE', 'Player Profile'],
              ['LEADERBOARD', 'Player Rankings'],
              ['DIRECTORY', 'Player Directory'],
              ['DIRECTORS', 'Directors'],
              ['VENUES', 'Venues'],
            ] as const).map(([nextView, label]) => (
              <button
                key={nextView}
                type="button"
                onClick={() => {
                  setView(nextView);
                  updateQueryParams({
                    view: nextView === 'TOURNAMENT'
                      ? undefined
                      : nextView === 'PREDICTIONS'
                        ? 'predictions'
                        : nextView === 'RESEARCH'
                          ? 'model-research'
                        : nextView === 'VENUES'
                          ? 'venues'
                        : nextView === 'DIRECTORY'
                          ? 'directory'
                        : nextView === 'DIRECTORS'
                          ? 'directors'
                        : nextView === 'PROFILE'
                          ? 'profile'
                          : 'leaderboard',
                    playerId: nextView === 'PROFILE' ? (selectedPlayerId || defaultPlayerId || '142125') : undefined,
                  });
                }}
                className={`min-h-[58px] rounded-2xl border px-4 py-3 text-base font-black transition-all active:translate-y-1 ${
                  view === nextView
                    ? 'border-amber-300 bg-amber-400 text-black'
                    : 'border-white/15 bg-zinc-900 text-zinc-100'
                }`}
                aria-pressed={view === nextView}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        {!isSwapEvent && (view === 'TOURNAMENT' || view === 'BRACKET_FLOW') && (
          <button
            type="button"
            onClick={() => setHideByeGames(value => !value)}
            className={`w-full rounded-xl border px-3 py-3 text-sm font-black sm:w-auto sm:py-2 sm:text-xs ${
              hideByeGames
                ? 'border-amber-300 bg-amber-300 text-black'
                : 'border-white/10 bg-zinc-800 text-zinc-300'
            }`}
            aria-pressed={hideByeGames}
            title="Toggle bye games"
          >
            Byes {hideByeGames ? 'hidden' : 'shown'}
            {hideByeGames && sortedMatches.length !== visibleTournamentMatches.length
              ? ` (${sortedMatches.length - visibleTournamentMatches.length})`
              : ''}
          </button>
        )}
	</div>
      </>)}
{view === 'TOURNAMENT' && data && (
  <TournamentView
    data={data}
    matches={visibleTournamentMatches}
    onOpenMatch={openTournamentGame}
  />
)}
{view === 'BRACKET_FLOW' && data && (
  <BracketFlowView
    matches={visibleTournamentMatches}
    onOpenMatch={openTournamentGame}
    eventId={String(data.event?.id || eventId)}
  />
)}
{view === 'BRACKET_PREDICTIONS' && data && (
  <div className="mt-4">
    <BracketProbabilities eventId={String(data.event?.eventId || data.event?.id || eventId)} event={data.event} />
  </div>
)}
{view === 'STANDINGS' && (
  <section className="glass rounded-[28px] p-4 mt-4">
    <h2 className="text-lg font-black mb-3">
      Player Season Stats
    </h2>

    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      <div>
        <label className="text-xs text-zinc-400">
          Player ID
        </label>

        <input
          value={selectedPlayerId}
          onChange={(e) => {
            setSelectedPlayerId(e.target.value);
            setStandingsData(null);
            setStandingsLastLoadedAt(null);
          }}
          className="w-full rounded-xl bg-zinc-900 border border-white/10 p-2"
          inputMode="numeric"
          placeholder="ACL Player ID"
        />
      </div>

      <div>
        <label className="text-xs text-zinc-400">
          Season / Career
        </label>

        <select
          value={seasonBucketId}
          onChange={(e) => applySeasonOption(e.target.value)}
          className="w-full rounded-xl bg-zinc-900 border border-white/10 p-2"
        >
          {seasonOptions.length === 0 && (
            <option value={seasonBucketId}>
              Bucket {seasonBucketId}
            </option>
          )}
          {seasonOptions.map(season => (
            <option key={season.bucketId} value={String(season.bucketId)}>
              {season.bucketId === 'career'
                ? `${season.label} / ${season.eventCount} events`
                : `${season.label} / Bucket ${season.bucketId} / ${season.eventCount} events`}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-xs text-zinc-400">
          Compare To
        </label>

        <select
          value={compareBucketId}
          onChange={(e) => setCompareBucketId(e.target.value)}
          className="w-full rounded-xl bg-zinc-900 border border-white/10 p-2"
        >
          <option value="">No comparison</option>
          {seasonOptions.filter(season => String(season.bucketId) !== String(seasonBucketId)).map(season => (
            <option key={season.bucketId} value={String(season.bucketId)}>
              {season.bucketId === 'career'
                ? season.label
                : `${season.label} / Bucket ${season.bucketId}`}
            </option>
          ))}
        </select>
      </div>
    </div>

    <details className="mt-3 rounded-xl border border-white/10 bg-zinc-950 p-3">
      <summary className="cursor-pointer text-xs font-black uppercase tracking-[.2em] text-zinc-500">
        Advanced Date Range
      </summary>

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div>
          <label className="text-xs text-zinc-400">
            Start Date
          </label>

          <input
            type="date"
            value={seasonStartDate}
            onChange={(e) => {
              setSeasonDateRangeEnabled(true);
              setSeasonStartDate(e.target.value);
              setStandingsData(null);
              setStandingsLastLoadedAt(null);
            }}
            className="w-full rounded-xl bg-zinc-900 border border-white/10 p-2"
          />
        </div>

        <div>
          <label className="text-xs text-zinc-400">
            End Date
          </label>

          <input
            type="date"
            value={seasonEndDate}
            onChange={(e) => {
              setSeasonDateRangeEnabled(true);
              setSeasonEndDate(e.target.value);
              setStandingsData(null);
              setStandingsLastLoadedAt(null);
            }}
            className="w-full rounded-xl bg-zinc-900 border border-white/10 p-2"
          />
        </div>
      </div>
    </details>

    <div className="mt-3 grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-2">
      <div className="rounded-xl border border-white/10 bg-zinc-950 p-3 text-xs text-zinc-400">
        Player career and season stats. Season choices come from the ACL bucket flag returned with player events.
        {selectedSeasonOption && (
          <span className="ml-1 text-zinc-300">
            Selected: {selectedSeasonOption.startDate} - {selectedSeasonOption.endDate}.
          </span>
        )}
        <span className="ml-1 text-zinc-300">
          {seasonDateRangeEnabled ? 'Manual date filter is on.' : 'Date range follows the selected season.'}
        </span>
        {compareSeasonOption && (
          <span className="ml-1 text-zinc-300">
            Comparing against {compareSeasonOption.label}.
          </span>
        )}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <button
          type="button"
          onClick={() => loadSeasonOptions(undefined, true)}
          disabled={standingsLoading || seasonOptionsLoading}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-zinc-900 px-4 py-2 font-black text-zinc-100 transition hover:bg-zinc-800 disabled:cursor-wait disabled:text-zinc-500 sm:w-auto"
        >
          {seasonOptionsLoading ? 'Loading...' : 'Refresh Seasons'}
        </button>
        <button
          type="button"
          onClick={() => loadStandings()}
          disabled={standingsLoading}
          className={`flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2 font-black transition ${
            standingsLoading
              ? 'cursor-wait bg-zinc-700 text-zinc-300'
              : 'bg-amber-400 text-black hover:bg-amber-300 active:scale-[0.99]'
          }`}
          aria-busy={standingsLoading}
        >
          <RefreshCw
            size={16}
            className={standingsLoading ? 'animate-spin' : ''}
          />
          {standingsLoading ? 'Loading...' : standingsData ? 'Check Season Stats' : 'Load Season Stats'}
        </button>
      </div>
    </div>

    <div className="mt-2 space-y-1 rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-xs">
      {!standingsLoading && seasonOptionsError && (
        <div className="font-bold text-amber-300">
          Season list could not refresh. Saved season stats can still be used.
        </div>
      )}
      {standingsLoading && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 font-bold text-amber-300">
            <RefreshCw size={14} className="animate-spin" />
            <span>{seasonProgress?.message || 'Loading individual season stats. This can take a moment the first time event data needs to be saved.'}</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-zinc-300 md:grid-cols-7">
            <div className="rounded-lg bg-zinc-900 px-2 py-1">
              <div className="font-black text-white">{seasonProgress?.coverage?.eventsInRange ?? 0}</div>
              <div className="text-[10px] uppercase tracking-wider text-zinc-500">Events</div>
            </div>
            <div className="rounded-lg bg-zinc-900 px-2 py-1">
              <div className="font-black text-white">{seasonProgress?.coverage?.eventsSkippedCached ?? 0}</div>
              <div className="text-[10px] uppercase tracking-wider text-zinc-500">Skipped</div>
            </div>
            <div className="rounded-lg bg-zinc-900 px-2 py-1">
              <div className="font-black text-white">{seasonProgress?.coverage?.bracketsChecked ?? 0}</div>
              <div className="text-[10px] uppercase tracking-wider text-zinc-500">Brackets</div>
            </div>
            <div className="rounded-lg bg-zinc-900 px-2 py-1">
              <div className="font-black text-white">{seasonProgress?.coverage?.matchesTargeted ?? 0}</div>
              <div className="text-[10px] uppercase tracking-wider text-zinc-500">Targets</div>
            </div>
            <div className="rounded-lg bg-zinc-900 px-2 py-1">
              <div className="font-black text-white">{seasonProgress?.coverage?.matchStatsChecked ?? 0}</div>
              <div className="text-[10px] uppercase tracking-wider text-zinc-500">Stats Checked</div>
            </div>
            <div className="rounded-lg bg-zinc-900 px-2 py-1">
              <div className="font-black text-white">{seasonProgress?.coverage?.matchStatsSkippedCached ?? 0}</div>
              <div className="text-[10px] uppercase tracking-wider text-zinc-500">Saved Stats</div>
            </div>
            <div className="rounded-lg bg-zinc-900 px-2 py-1">
              <div className="font-black text-white">{seasonProgress?.coverage?.playerRoundsSaved ?? 0}</div>
              <div className="text-[10px] uppercase tracking-wider text-zinc-500">Round Rows</div>
            </div>
          </div>
        </div>
      )}
      {!standingsLoading && standingsError && (
        <span className="font-bold text-red-300">
          Season stats failed to load: {standingsError}
        </span>
      )}
      {!standingsLoading && !standingsError && standingsLastLoadedAt && (
        <span className="text-zinc-400">
          Showing saved season stats from {formatTime(standingsLastLoadedAt.toISOString())}. Press the button only when you want to check ACL/cache again.
        </span>
      )}
      {!standingsLoading && !standingsError && !standingsLastLoadedAt && (
        <span className="text-zinc-400">
          Choose a favorite player or enter a Player ID, then load season stats.
        </span>
      )}
    </div>

    {favorites.length > 0 && (
      <div className="mt-3">
        <div className="mb-2 text-xs uppercase tracking-[.2em] text-zinc-500">
          Favorite Players
        </div>
        <div className="flex gap-2 overflow-x-auto pb-1">
          {favorites.map(player => {
            const isSelected = selectedPlayerId === String(player.playerId);

            return (
              <button
                key={player.playerId}
                type="button"
                onClick={() => {
                  const id = String(player.playerId);
                  setSelectedPlayerId(id);
                  loadStandings({ playerId: id });
                }}
                className={`shrink-0 rounded-xl border px-3 py-2 text-left ${
                  isSelected
                    ? 'border-amber-400 bg-amber-400 text-black'
                    : 'border-white/10 bg-zinc-900 text-white'
                }`}
              >
                <div className="text-[11px] opacity-70">Player {player.playerId}</div>
                <div className="max-w-[190px] truncate text-sm font-black">
                  {player.name || `Player ${player.playerId}`}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    )}
  </section>
)}
{view === 'STANDINGS' && (
  <section className="mt-4">
    <PanelErrorBoundary resetKey={`${selectedPlayerId}:${seasonBucketId}:${standingsLastLoadedAt?.toISOString() || ''}`}>
      <StandingsView standingsData={standingsData} />
    </PanelErrorBoundary>
  </section>
)}
{view === 'STATISTICS' && (
  <TournamentStatsView
    eventId={eventId}
    statsData={tournamentStatsData}
    loading={tournamentStatsLoading}
  />
)}
{view === 'PREDICTIONS' && <PredictionOperationsView />}
{view === 'RESEARCH' && <ModelResearchLabView />}
{view === 'PROFILE' && <PredictivePlayerProfileView playerId={new URLSearchParams(location.search).get('playerId') || '142125'} />}
{view === 'LEADERBOARD' && <PlayerAnalyticsLeaderboardView />}
{view === 'DIRECTORY' && <PlayerDirectoryView />}
{view === 'DIRECTORS' && <DirectorDirectoryView />}
{view === 'VENUES' && <VenueAnalyticsView />}
{statusRoute && loading && (
  <section className="mx-auto mt-6 max-w-xl rounded-[28px] border border-sky-300/20 bg-zinc-950 p-8 text-center">
    <RefreshCw className="mx-auto animate-spin text-sky-300" size={36}/>
    <div className="mt-4 text-2xl font-black">Loading tournament status</div>
  </section>
)}
{statusRoute && !loading && data && !match && (
  <section className="mx-auto mt-6 max-w-xl rounded-[28px] border border-amber-300/25 bg-amber-300/[.06] p-6 text-center">
    <div className="text-2xl font-black text-white">Shared team or player not found</div>
    <div className="mt-2 text-sm leading-6 text-zinc-400">
      Event {statusRoute.eventId} is available, but {statusRoute.teamId ? `Team ${statusRoute.teamId}` : `Player ${statusRoute.playerId}`} does not appear in its cached roster or match history.
    </div>
  </section>
)}
     {view === 'GAME' && match && (
  <div className="mt-3 space-y-3">
    {!statusRoute && <div className="sticky top-[92px] z-10 grid grid-cols-3 gap-2 rounded-2xl border border-white/15 bg-black/95 p-2 shadow-2xl backdrop-blur lg:hidden" role="tablist" aria-label="Game view mode">
      <button type="button" onClick={() => { setGameMobileMode('PLAYER'); updateQueryParams({ mode: 'player', playerId: selectedPlayerId || defaultPlayerId || undefined }); }} aria-pressed={gameMobileMode === 'PLAYER'}
        role="tab" aria-selected={gameMobileMode === 'PLAYER'}
        className={`flex min-h-16 flex-col items-center justify-center rounded-xl border px-1 text-sm font-black transition-all duration-150 active:scale-95 ${gameMobileMode === 'PLAYER' ? 'border-amber-200 bg-amber-400 text-black shadow-[0_0_22px_rgba(251,191,36,.35)] ring-2 ring-amber-300/70' : 'border-white/10 bg-zinc-900 text-zinc-400'}`}>
        <span className="flex items-center gap-1.5"><UserRound size={17}/>Player</span>
        <span className={`mt-1 text-[9px] font-black uppercase tracking-[.16em] ${gameMobileMode === 'PLAYER' ? 'text-black/70' : 'text-zinc-600'}`}>{gameMobileMode === 'PLAYER' ? <span className="flex items-center gap-1"><Check size={10}/>Selected</span> : 'Select'}</span>
      </button>
      <button type="button" onClick={() => { setGameMobileMode('VIEWER'); updateQueryParams({ mode: 'viewer', playerId: selectedPlayerId || defaultPlayerId || undefined }); }} aria-pressed={gameMobileMode === 'VIEWER'}
        role="tab" aria-selected={gameMobileMode === 'VIEWER'}
        className={`flex min-h-16 flex-col items-center justify-center rounded-xl border px-1 text-sm font-black transition-all duration-150 active:scale-95 ${gameMobileMode === 'VIEWER' ? 'border-violet-200 bg-violet-400 text-black shadow-[0_0_22px_rgba(167,139,250,.35)] ring-2 ring-violet-300/70' : 'border-white/10 bg-zinc-900 text-zinc-400'}`}>
        <span className="flex items-center gap-1.5"><Eye size={17}/>Viewer</span>
        <span className={`mt-1 text-[9px] font-black uppercase tracking-[.16em] ${gameMobileMode === 'VIEWER' ? 'text-black/70' : 'text-zinc-600'}`}>{gameMobileMode === 'VIEWER' ? <span className="flex items-center gap-1"><Check size={10}/>Selected</span> : 'Select'}</span>
      </button>
      <button type="button" onClick={() => { setGameMobileMode('ANALYSIS'); updateQueryParams({ mode: 'analysis', playerId: selectedPlayerId || defaultPlayerId || undefined }); }} aria-pressed={gameMobileMode === 'ANALYSIS'}
        role="tab" aria-selected={gameMobileMode === 'ANALYSIS'}
        className={`flex min-h-16 flex-col items-center justify-center rounded-xl border px-1 text-sm font-black transition-all duration-150 active:scale-95 ${gameMobileMode === 'ANALYSIS' ? 'border-sky-200 bg-sky-400 text-black shadow-[0_0_22px_rgba(56,189,248,.35)] ring-2 ring-sky-300/70' : 'border-white/10 bg-zinc-900 text-zinc-400'}`}>
        <span className="flex items-center gap-1.5"><ChartNoAxesCombined size={17}/>Analysis</span>
        <span className={`mt-1 text-[9px] font-black uppercase tracking-[.16em] ${gameMobileMode === 'ANALYSIS' ? 'text-black/70' : 'text-zinc-600'}`}>{gameMobileMode === 'ANALYSIS' ? <span className="flex items-center gap-1"><Check size={10}/>Selected</span> : 'Select'}</span>
      </button>
      </div>}

    {!statusRoute && gameMobileMode === 'PLAYER' && <PlayerMode
      match={match}
      players={players}
      rounds={rounds}
      playerId={selectedPlayerId || defaultPlayerId}
      winProbability={game?.liveWinProbability}
    />}

    {(statusRoute || gameMobileMode === 'VIEWER') && <ViewerMode
      match={match}
      matches={data?.matches || []}
      players={players}
      playerId={selectedPlayerId || defaultPlayerId}
      subjectTeamId={statusRoute?.teamId}
      event={data?.event}
      winProbability={game?.liveWinProbability}
      standalone={Boolean(statusRoute)}
    />}

    <div className={`${!statusRoute && gameMobileMode === 'ANALYSIS' ? 'block' : 'hidden'} space-y-3 ${statusRoute ? '' : 'lg:block'}`}>
    <ScoreHero match={replayMatch} players={replayPlayers} rounds={replayRounds} event={event} />

    <RoundWalkthrough
      rounds={rounds}
      topTeamName={match.teams.top.name}
      bottomTeamName={match.teams.bottom.name}
      topTeamId={match.teams.top.id}
      bottomTeamId={match.teams.bottom.id}
      selectedRound={selectedReplayRound}
      onSelectRound={setSelectedReplayRound}
    />

    <LiveWinProbabilityChart
      model={game?.liveWinProbability}
      topTeamName={match.teams.top.name}
      bottomTeamName={match.teams.bottom.name}
      selectedRound={displayedRound}
      onSelectRound={setSelectedReplayRound}
    />

    <PlayerProfileTrajectory
      data={game?.profileTrajectories}
      selectedRound={selectedReplayRound}
      completed={matchLooksCompleted(match)}
    />

    <ChampionshipDoubleDip profile={match.championshipDoubleDip} />

    {displayedRound === 0 && <TaleOfTheTape
      players={players}
      topTeamName={match.teams.top.name}
      bottomTeamName={match.teams.bottom.name}
      topTeamId={match.teams.top.id}
      bottomTeamId={match.teams.bottom.id}
      pregameTopProbability={game?.liveWinProbability?.pregameTopProbability}
      pregameEvidence={game?.liveWinProbability?.pregameEvidence}
      eventId={String(data?.event?.eventId || data?.event?.id || eventId)}
      event={data?.event}
      match={{ courtId: match.courtId, roundDescription: match.roundDescription }}
      pregame
    />}

    {displayedRound > 0 && <>
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
      <MetricPill
        label="Round"
        value={displayedRound || '-'}
      />

      <MetricPill
        label="Top PPR"
        value={topPpr(players)}
      />

      <MetricPill
        label="Limit"
        value="N/A"
      />
    </div>

    <MomentumChart
      rounds={replayRounds}
      topTeamId={match.teams.top.id}
      bottomTeamId={match.teams.bottom.id}
      topTeamName={match.teams.top.name}
      bottomTeamName={match.teams.bottom.name}
    />

    <RoundTimeline
      rounds={replayRounds}
      topTeamName={match.teams.top.name}
      bottomTeamName={match.teams.bottom.name}
      topTeamId={match.teams.top.id}
      bottomTeamId={match.teams.bottom.id}
    />

    <PlayerBars players={replayPlayers} rounds={replayRounds} />
    </>}
    </div>
  </div>
)}
    </main>
  );
}

function PlayerAvatar({ name, photo, size = 'sm' }: { name?: string; photo?: string; size?: 'sm' | 'lg' }) {
  const [failed, setFailed] = useState(false);
  const dimensions = size === 'lg' ? 'h-24 w-24 text-2xl' : 'h-12 w-12 text-sm';
  const initials = (name || 'Player').split(/\s+/).filter(Boolean).slice(0, 2).map(value => value[0]).join('').toUpperCase();
  if (photo && !failed) {
    return <img src={photo.trim()} alt={`${name || 'Player'} profile`} onError={() => setFailed(true)} className={`${dimensions} shrink-0 rounded-full border-2 border-amber-300/60 object-cover bg-zinc-900`} />;
  }
  return <div className={`${dimensions} grid shrink-0 place-items-center rounded-full border-2 border-white/15 bg-zinc-800 font-black text-amber-300`}>{initials}</div>;
}
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

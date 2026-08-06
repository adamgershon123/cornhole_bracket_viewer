export type PlayerStat = { id:string; name:string; teamId?:string; points:number; opponentPoints:number; rounds:number; ppr:number; dpr:number; roundsWon:number; roundsLost:number; roundsTied:number; roundWinPct:number; roundLossPct:number; roundTiePct:number; fourBaggers:number; fourBaggerPct:number; bagsInPct:number; bagsIn?:number; bagsOn?:number; bagsOff?:number; seasonPpr?:number; seasonDpr?:number; seasonFourBagPct?:number; seasonBagsInPct?:number; seasonRoundWinPct?:number; pprVsSeason?:number|null }
export type GameState = {
  roundNumber:number;
  scoreBefore:Record<string,number>;
  scoreAfter:Record<string,number>;
  firstThrowTeamId:string|null;
  firstThrowPlayerId:string|null;
  firstThrowTeamStatus:'UNKNOWN'|'MANUAL'|'INFERRED_FROM_SCORE'|'INFERRED_FROM_ROTATION'|'ACL_REPORTED';
  firstThrowPlayerStatus:'UNKNOWN'|'MANUAL'|'INFERRED_FROM_SCORE'|'INFERRED_FROM_ROTATION'|'ACL_REPORTED';
  roundScoringTeamId:string|null;
  roundScoringPlayerId:string|null;
  netPoints:number;
  wasWash:boolean;
  lastScoringTeamId:string|null;
  lastScoringPlayerId:string|null;
  nextFirstThrowTeamId:string|null;
  nextFirstThrowPlayerId:string|null;
}
export type RoundRow = { round:number; netPoints:number; scoringTeamId:string|null; gameState?:GameState; players:{playerId:string; teamId:string; name:string; grossPoints:number; teamScoreAfter:number; bagsIn?:number; bagsOn?:number; bagsOff?:number; fourBagger?:boolean}[] }
export type Game = { gameId:number; statusId:number; status?:string; currentRound?:number|string; score:{top:number|null;bottom:number|null}; players:PlayerStat[]; rounds:RoundRow[]; liveWinProbability?:any; profileTrajectories?:any }
export type Match = { eventId:string; matchId:string; courtId:string; roundDescription:string; bracketSide:string; statusId:number; status:string; currentRound?:number|string; teams:{top:{id:string;name:string};bottom:{id:string;name:string}}; score:{top:number|null;bottom:number|null}; games:Game[]; activeGame?:Game; championshipDoubleDip?:any }
export type EventResponse = { event:{id:string; name:string; status?:string; leagueStatus?:string; courts:string[]; lastUpdated:number}; matches:Match[]; notifications?:{type?:string; message?:string; source?:string}[] }
const API_BASE = import.meta.env.VITE_API_BASE || ''
export async function fetchEvent(eventId:string, stats=false): Promise<EventResponse>{
  const url = `${API_BASE}/api/events/${eventId}/matches?stats=${stats?'1':'0'}`;
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    await new Promise(resolve => window.setTimeout(resolve, 1500));
    response = await fetch(url);
  }
  if(!response.ok) throw new Error(await readableApiError(response));
  return response.json();
}
export async function fetchMatch(eventId:string, matchId:string): Promise<Match>{ const r=await fetch(`${API_BASE}/api/events/${eventId}/matches/${matchId}`); if(!r.ok) throw new Error(await r.text()); return r.json() }
export async function fetchBracketProbabilities(eventId:string, simulations=10000): Promise<any>{ const r=await fetch(`${API_BASE}/api/events/${eventId}/bracket-probabilities?simulations=${simulations}`); if(!r.ok) throw new Error(await readableApiError(r)); return r.json() }
export async function fetchMatchGameStats(eventId:string, matchId:string, gameId:number|string, refresh=true): Promise<Match>{ const r=await fetch(`${API_BASE}/api/events/${eventId}/matches/${matchId}/games/${gameId}/stats?refresh=${refresh?'1':'0'}`); if(!r.ok) throw new Error(await r.text()); return r.json() }

export type TournamentStatsPlayer = {
  name:string; rounds:number; points:number; sum_positive_round_net_points:number; scored_pts_per_round:number; ppr:number; point_diff:number; opp_ppr:number; ['4baggers']:number; ['4bagger_pct']:number; rounds_won_pct:number; rounds_lost_pct:number; rounds_tied_pct:number; bagsin_pct:number; bagson_pct:number; bagsoff_pct:number; bagsin:number; bagson:number; bagsoff:number; match_wins?:number; match_losses?:number; match_ties?:number; match_record?:string; finish_place?:number|null;
}
export type TournamentStatsResponse = { eventId:string; players:Record<string,TournamentStatsPlayer>|TournamentStatsPlayer[]; highlights?:any; matchStats?:{targets:number; attempted:number; failed:number; eligibleGames?:number; usableGames?:number; complete?:boolean; missingGames?:{matchId:string;gameId:number}[]} }
export async function fetchTournamentStats(
  eventId:string,
  options: { refresh?: boolean; refreshLive?: boolean; cachedOnly?: boolean; teamId?: string } = {},
): Promise<TournamentStatsResponse>{
  const query = new URLSearchParams({
    refresh: options.refresh === false ? '0' : '1',
    refresh_live: options.refreshLive === false ? '0' : '1',
    cached_only: options.cachedOnly ? '1' : '0',
  });
  if (options.teamId) query.set('team_id', options.teamId);
  const r=await fetch(`${API_BASE}/api/events/${eventId}/tournament-stats?${query.toString()}`);
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}

export type SeasonStatsParams = {
  playerId:string;
  seedEventId:string;
  startDate:string;
  endDate:string;
  bucketId?:string;
  exclude?:string;
}

export async function fetchSeasonStats(params: SeasonStatsParams): Promise<any>{
  const query = new URLSearchParams({
    playerId: params.playerId,
    seedEventId: params.seedEventId,
    startDate: params.startDate,
    endDate: params.endDate,
    bucketId: params.bucketId || '11',
  });

  if (params.exclude) query.set('exclude', params.exclude);

  const r = await fetch(`${API_BASE}/api/season-stats?${query.toString()}`);
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}

export type IndividualSeasonStatsParams = {
  playerId:string;
  startDate?:string;
  endDate?:string;
  bucketId?:string;
  progressKey?:string;
  profiles?:boolean;
  refreshIndex?:boolean;
  force?:boolean;
}

export type PlayerSeasonOption = {
  bucketId:number|string;
  bucketIds?:number[];
  label:string;
  startDate:string;
  endDate:string;
  eventCount:number;
  leagueYears?:Record<string, number>;
  statuses?:Record<string, number>;
}

export async function fetchPlayerSeasonOptions(playerId:string, refreshIndex=false): Promise<{playerId:number; seasons:PlayerSeasonOption[]}>{
  const query = new URLSearchParams({
    playerId,
  });

  if (refreshIndex) query.set('refreshIndex', '1');

  const r = await fetch(`${API_BASE}/api/season-platform/seasons?${query.toString()}`);
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function fetchIndividualSeasonStats(params: IndividualSeasonStatsParams): Promise<any>{
  const query = new URLSearchParams({
    playerId: params.playerId,
    bucketId: params.bucketId || '11',
  });

  if (params.startDate) query.set('startDate', params.startDate);
  if (params.endDate) query.set('endDate', params.endDate);
  if (params.progressKey) query.set('progressKey', params.progressKey);
  if (params.profiles) query.set('profiles', '1');
  if (params.refreshIndex) query.set('refreshIndex', '1');
  if (params.force) query.set('force', '1');
  query.set('background', '1');

  const r = await fetch(`${API_BASE}/api/season-platform/gather?${query.toString()}`);
  if(!r.ok) throw new Error(await readableApiError(r));
  const accepted = await r.json();
  if (r.status !== 202) return accepted;

  const progressKey = accepted.progressKey || params.progressKey;
  if (!progressKey) throw new Error('Season history started without a tracking key.');
  for (;;) {
    await new Promise(resolve => window.setTimeout(resolve, 1000));
    const progress = await fetchSeasonProgress(progressKey);
    if (progress?.error) throw new Error(progress.message || 'Season history could not be loaded.');
    if (progress?.done && progress?.result) return progress.result;
  }
}

export async function fetchSeasonProgress(key:string): Promise<any>{
  const query = new URLSearchParams({ key });
  const r = await fetch(`${API_BASE}/api/season-platform/progress?${query.toString()}`);
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}

async function readableApiError(response: Response): Promise<string> {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const payload = await response.json().catch(() => null);
    return payload?.error || payload?.message || `Request failed (${response.status}).`;
  }
  const text = await response.text();
  if (response.status === 524 || /A timeout occurred/i.test(text)) {
    return 'The server took too long to respond. Please try again; previously collected data is retained.';
  }
  return `Request failed (${response.status}).`;
}

export async function fetchPredictionOperations(): Promise<any> {
  const response = await fetch(`${API_BASE}/api/prediction-operations`);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function fetchHistoricalBackfill(): Promise<any> {
  const response = await fetch(`${API_BASE}/api/historical-backfill`, {
    cache: 'no-store',
  });
  if (!response.ok) throw new Error(await readableApiError(response));
  return response.json();
}

export async function controlHistoricalBackfill(
  action: 'pause' | 'resume',
  lane?: 'PREDICTION' | 'ACL_CLASSIFIED',
): Promise<any> {
  const response = await fetch(`${API_BASE}/api/historical-backfill/control`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ action, lane }),
  });
  if (!response.ok) throw new Error(await readableApiError(response));
  return response.json();
}

export async function downloadHistoricalVenueCsv(): Promise<void> {
  const response = await fetch(
    `${API_BASE}/api/historical-backfill/venues.csv`,
    { cache: 'no-store' },
  );
  if (!response.ok) throw new Error(await readableApiError(response));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'cheesebaggers-google-my-maps-venues.csv';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function fetchVenues(): Promise<any> {
  const response = await fetch(`${API_BASE}/api/venues`, { cache: 'no-store' });
  if (!response.ok) throw new Error(await readableApiError(response));
  return response.json();
}

export async function fetchVenueEvents(
  venueKey: string,
  options: { seasonStart?: number; startDate?: string; endDate?: string },
): Promise<any> {
  const query = new URLSearchParams();
  if (options.seasonStart != null) query.set('season_start', String(options.seasonStart));
  if (options.startDate) query.set('start_date', options.startDate);
  if (options.endDate) query.set('end_date', options.endDate);
  const response = await fetch(
    `${API_BASE}/api/venues/${encodeURIComponent(venueKey)}/events?${query}`,
    { cache: 'no-store' },
  );
  if (!response.ok) throw new Error(await readableApiError(response));
  return response.json();
}

export async function fetchVenueCourtPpr(
  venueKey: string,
  options: { startDate?: string; endDate?: string; playerIds?: number[] },
): Promise<any> {
  const query = new URLSearchParams();
  if (options.startDate) query.set('start_date', options.startDate);
  if (options.endDate) query.set('end_date', options.endDate);
  if (options.playerIds?.length) query.set('player_ids', options.playerIds.join(','));
  const response = await fetch(
    `${API_BASE}/api/venues/${encodeURIComponent(venueKey)}/court-ppr?${query}`,
    { cache: 'no-store' },
  );
  if (!response.ok) throw new Error(await readableApiError(response));
  return response.json();
}

export async function prioritizeVenueEvents(
  venueKey: string,
  options: {
    seasonStart?: number;
    startDate?: string;
    endDate?: string;
    eventIds?: number[];
  },
): Promise<any> {
  const response = await fetch(
    `${API_BASE}/api/venues/${encodeURIComponent(venueKey)}/priority`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(options),
    },
  );
  if (!response.ok) throw new Error(await readableApiError(response));
  return response.json();
}

export async function fetchPredictivePlayerProfile(playerId:string): Promise<any> {
  const response = await fetch(
    `${API_BASE}/api/predictive-player-profile/${encodeURIComponent(playerId)}`,
    { cache: 'no-store' },
  );
  if (!response.ok) throw new Error(await readableApiError(response));
  return response.json();
}

export async function fetchPlayerAnalyticsLeaderboard(
  sort='currentFormRating',
  limit=100,
  classification='ALL',
  membership='ALL',
): Promise<any> {
  const query = new URLSearchParams({ sort, limit: String(limit), classification, membership });
  const response = await fetch(`${API_BASE}/api/player-analytics-leaderboard?${query}`);
  if (!response.ok) throw new Error(await readableApiError(response));
  return response.json();
}

export async function fetchPrivatePlayerDirectory(
  token:string,
  options: {
    search?:string;
    classification?:string;
    membership?:string;
    contact?:string;
    limit?:number;
    offset?:number;
  } = {},
): Promise<any> {
  const query = new URLSearchParams({
    search: options.search || '',
    classification: options.classification || 'ALL',
    membership: options.membership || 'ALL',
    contact: options.contact || 'ALL',
    limit: String(options.limit || 100),
    offset: String(options.offset || 0),
  });
  const response = await fetch(`${API_BASE}/api/private/player-directory?${query}`, {
    cache: 'no-store',
    headers: { 'X-Player-Directory-Token': token },
  });
  if (!response.ok) throw new Error(await readableApiError(response));
  return response.json();
}

export async function refreshPrivatePlayerDirectory(token:string): Promise<any> {
  const response = await fetch(`${API_BASE}/api/private/player-directory/refresh`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'X-Player-Directory-Token': token,
    },
    body: JSON.stringify({ force: false }),
  });
  if (!response.ok) throw new Error(await readableApiError(response));
  return response.json();
}

export async function runPredictionLifecycle(): Promise<any> {
  const response = await fetch(`${API_BASE}/api/prediction-operations/run`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ discover: true, lookaheadMinutes: 180 }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function monitorPredictionEvent(params: {
  eventId: string;
  format: 'SWISS' | 'SWAP' | 'BRACKET';
  timezone: string;
}): Promise<any> {
  const response = await fetch(`${API_BASE}/api/prediction-operations/monitor`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

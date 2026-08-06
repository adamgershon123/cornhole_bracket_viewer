import { useEffect, useMemo, useRef, useState } from 'react';
import { Match } from '../lib/api';
import { TournamentMatchCard } from './TournamentMatchCard';

type Props = {
  data: any;
  matches: (Match & any)[];
  onOpenMatch: (match: string | (Match & any)) => void;
};

type EnrichedMatch = Match & any & {
  flow: {
    label: string;
    sort: number;
    winnerName?: string;
    loserName?: string;
    winnerId?: string;
    loserId?: string;
    winnerNext?: Match & any;
    loserNext?: Match & any;
    loserPlace?: number;
    side?: BracketSideKind;
    waitingOn: string[];
  };
};

type PathSummary = {
  wins: number;
  losses: number;
  alive: boolean;
  status: string;
  place?: number;
};

type SwapSortKey = 'rank' | 'ppr' | 'differential' | 'record' | 'wins' | 'losses' | 'rounds' | 'fourBaggers' | 'fourBaggerPct' | 'seasonPpr';
type BracketSideKind = 'winners' | 'losers' | 'finals' | 'mixed' | 'unknown';

function isSwapSortKey(value: unknown): value is SwapSortKey {
  return [
    'rank',
    'ppr',
    'differential',
    'record',
    'wins',
    'losses',
    'rounds',
    'fourBaggers',
    'fourBaggerPct',
    'seasonPpr',
  ].includes(String(value));
}

function isSwapLikeEvent(event: any) {
  const name = String(event?.name || event?.eventName || event?.leagueName || '').toLowerCase();
  const bracketType = String(event?.bracketType || event?.brackettype || '').toUpperCase();
  const playerPoolSize = Number(event?.playerPoolSize || 0);
  const roundLimitBracket = Number(event?.roundLimitBracket || 0);

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

export function TournamentView({ data, matches, onOpenMatch }: Props) {
  const enriched = enrichBracketFlow(matches);
  const live = enriched.filter(m => m.status === 'live');
  const completed = enriched.filter(m => m.status === 'completed');
  const upcoming = enriched.filter(m => m.status === 'upcoming');
  const isBlindDraw = Boolean(data?.event?.blindDraw);
  const isSwapEvent = isSwapLikeEvent(data?.event);
  const eventFormat = [
    data?.event?.matchType,
    data?.event?.bracketType,
    isBlindDraw ? 'Blind Draw' : undefined,
  ].filter(Boolean).join(' / ');

  if (isSwapEvent) {
    return <SwapLiveMobile eventId={String(data?.event?.id || '')} fallbackEvent={data?.event || {}} onOpenMatch={onOpenMatch} />;
  }

  return (
    <section className="mt-4 space-y-5">
      <section className="rounded-[32px] border border-white/10 bg-zinc-950 p-5 shadow-xl">
        <div className="text-xs uppercase tracking-[0.24em] text-amber-300">
          Tournament
        </div>

        <h2 className="mt-1 text-[clamp(1.6rem,5vw,3rem)] font-black leading-none">
          {data?.event?.name || 'Current Event'}
        </h2>

        <div className="mt-3 text-base text-zinc-300">
          {data?.event?.date || 'Date TBD'} / {data?.event?.venue || data?.event?.location?.name || 'Venue TBD'}
        </div>
        {eventFormat && (
          <div className="mt-1 text-sm font-bold text-zinc-500">
            {eventFormat}
          </div>
        )}

        <div className="mt-5 grid grid-cols-3 gap-3">
          <SummaryStat label="Live" value={live.length} tone="text-green-400" />
          <SummaryStat label="Done" value={completed.length} tone="text-blue-300" />
          <SummaryStat label="Next" value={upcoming.length} tone="text-yellow-300" />
        </div>
      </section>

      {live.length > 0 && (
        <MatchSection title="Live Matches" matches={live} onOpenMatch={onOpenMatch} />
      )}

      {upcoming.length > 0 && (
        <MatchSection title="Upcoming Matches" matches={upcoming} onOpenMatch={onOpenMatch} />
      )}

      {completed.length > 0 && (
        <MatchSection title="Completed Matches" matches={completed} onOpenMatch={onOpenMatch} />
      )}

      {matches.length === 0 && (
        <section className="rounded-[28px] border border-white/10 bg-zinc-950 p-4">
          <h3 className="text-lg font-black">
            {isBlindDraw ? 'Schedule Not Available Yet' : 'No Matches Loaded'}
          </h3>
          <div className="mt-2 text-sm text-zinc-400">
            {isBlindDraw
              ? 'This blind draw event is saved in the player event list, but ACL has not returned bracket matches for it yet.'
              : 'No bracket matches were returned for this event.'}
          </div>
        </section>
      )}
    </section>
  );
}

export function BracketFlowView({ matches, onOpenMatch }: Omit<Props, 'data'> & {eventId?:string}) {
  const [selectedPathTeamId, setSelectedPathTeamId] = useState<string | undefined>();
  const enriched = enrichBracketFlow(matches);
  const selectedPathTeamName = selectedPathTeamId ? teamNameForId(enriched, selectedPathTeamId) : undefined;
  const selectedPathSummary = selectedPathTeamId ? pathSummaryForTeam(enriched, selectedPathTeamId) : undefined;

  return (
    <section className="mt-4">
      <MobileBracketFlow
        matches={enriched}
        onOpenMatch={onOpenMatch}
        selectedPathTeamId={selectedPathTeamId}
        selectedPathTeamName={selectedPathTeamName}
        selectedPathSummary={selectedPathSummary}
        onSelectPath={(teamId) => setSelectedPathTeamId(current => current === teamId ? undefined : teamId)}
        onClearPath={() => setSelectedPathTeamId(undefined)}
      />
    </section>
  );
}

function SummaryStat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-zinc-900 p-4 text-center">
      <div className={`text-[clamp(2rem,9vw,4rem)] font-black leading-none ${tone}`}>
        {value}
      </div>
      <div className="mt-1 text-xs font-bold uppercase tracking-widest text-zinc-400">
        {label}
      </div>
    </div>
  );
}

function SwapSummaryStat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-zinc-900 px-3 py-3">
      <div className={`text-2xl font-black leading-none sm:text-3xl ${tone}`}>
        {value}
      </div>
      <div className="mt-1 text-[11px] font-bold uppercase tracking-widest text-zinc-400">
        {label}
      </div>
    </div>
  );
}

function SwapLiveMobile({ eventId, fallbackEvent, onOpenMatch }: { eventId: string; fallbackEvent: any; onOpenMatch: Props['onOpenMatch'] }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [sortKey, setSortKey] = useState<SwapSortKey>(() => {
    const saved = window.localStorage.getItem('swapLeaderboardSort');
    return isSwapSortKey(saved) ? saved : 'ppr';
  });

  async function load(refresh = true) {
    if (!eventId) return;
    setLoading(true);
    setError(undefined);
    try {
      const query = new URLSearchParams({
        refresh: refresh ? '1' : '0',
        t: String(Date.now()),
      });
      const response = await fetch(`/api/swap-live/${eventId}?${query.toString()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(await response.text());
      setData(await response.json());
    } catch (e: any) {
      setError(e?.message || 'Unable to load swap live data.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(true);
  }, [eventId]);

  useEffect(() => {
    window.localStorage.setItem('swapLeaderboardSort', sortKey);
  }, [sortKey]);

  const event = data?.event || fallbackEvent || {};
  const formatLabel = event.formatLabel || (String(event.bracketType || '').toUpperCase() === 'W' ? 'Rounders' : 'Swap');
  const leaderboard = useMemo(() => {
    const rows = [...(data?.leaderboard || [])];
    return rows.sort((a, b) => {
      if (sortKey === 'rank') return Number(a.rank || 9999) - Number(b.rank || 9999);
      if (sortKey === 'ppr') return swapPpr(b) - swapPpr(a);
      if (sortKey === 'record') {
        const aDiff = Number(a.wins || 0) - Number(a.losses || 0);
        const bDiff = Number(b.wins || 0) - Number(b.losses || 0);
        return bDiff - aDiff || Number(b.wins || 0) - Number(a.wins || 0) || Number(a.rank || 9999) - Number(b.rank || 9999);
      }
      if (sortKey === 'rounds') return Number(b.swapStats?.rounds || 0) - Number(a.swapStats?.rounds || 0);
      if (sortKey === 'fourBaggers') return Number(b.swapStats?.fourBaggers || 0) - Number(a.swapStats?.fourBaggers || 0);
      if (sortKey === 'fourBaggerPct') return Number(b.swapStats?.fourBaggerPct || 0) - Number(a.swapStats?.fourBaggerPct || 0);
      if (sortKey === 'seasonPpr') return Number(b.season?.ppr || 0) - Number(a.season?.ppr || 0);
      return Number(b[sortKey] || 0) - Number(a[sortKey] || 0);
    });
  }, [data, sortKey]);
  const liveMatches = data?.matches?.live || [];
  const nextMatches = data?.matches?.next || [];
  const completedMatches = data?.matches?.completed || [];
  const upNextPlayers = data?.upNextPlayers || [];

  return (
    <section className="mt-4 space-y-4">
      <section className="rounded-[28px] border border-white/10 bg-zinc-950 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-amber-300">{formatLabel} Event</div>
            <h2 className="mt-1 text-2xl font-black leading-tight">{event.name || fallbackEvent.name || `Event ${eventId}`}</h2>
            <div className="mt-1 text-sm text-zinc-400">
              {event.date || fallbackEvent.date || 'Date TBD'} / {event.location?.name || fallbackEvent.venue || fallbackEvent.location?.name || 'Venue TBD'}
            </div>
          </div>
          <button
            type="button"
            onClick={() => load(true)}
            disabled={loading}
            className="rounded-xl border border-white/10 bg-zinc-900 px-3 py-2 text-sm font-black text-zinc-100 disabled:opacity-50"
          >
            {loading ? 'Loading' : 'Refresh'}
          </button>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <SwapSummaryStat label="Live" value={liveMatches.length} tone="text-green-400" />
          <SwapSummaryStat label="Next" value={nextMatches.length} tone="text-yellow-300" />
          <SwapSummaryStat label="Done" value={completedMatches.length} tone="text-blue-300" />
          <SwapSummaryStat label="Players" value={data?.counts?.leaderboard || 0} tone="text-amber-300" />
        </div>
        {error && <div className="mt-3 rounded-xl border border-red-400/30 bg-red-950/30 p-3 text-sm text-red-100">{error}</div>}
      </section>

      {formatLabel === 'Swap' && <section className="rounded-2xl border border-sky-400/25 bg-sky-400/10 p-4">
        <div className="text-xs font-black uppercase tracking-[.2em] text-sky-300">Swap Seeding Phase</div>
        <div className="mt-2 text-sm leading-6 text-zinc-200">
          Each player completes four games with four different partners. Individual PPR performance establishes the seeding order:
          the top 30 advance to Tier 1, with the remaining players divided into Tier 2 and Tier 3 brackets.
        </div>
        <div className="mt-2 text-xs text-zinc-400">
          The final tier brackets are created after swap play, so their absence during this phase is expected.
        </div>
      </section>}

      <SwapMatchSection
        title="Current Games"
        matches={liveMatches}
        onOpenMatch={onOpenMatch}
        upNextPlayers={upNextPlayers}
      />
      <SwapMatchSection
        title="Next Up Games"
        matches={nextMatches}
        onOpenMatch={onOpenMatch}
      />

      <section className="rounded-[28px] border border-white/10 bg-zinc-950 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-lg font-black">{formatLabel} Leaderboard</h3>
          <select
            value={sortKey}
            onChange={event => setSortKey(event.target.value as SwapSortKey)}
            className="rounded-xl border border-white/10 bg-zinc-900 px-2 py-2 text-sm"
          >
            <option value="ppr">PPR</option>
            <option value="differential">DPR / +/-</option>
            <option value="record">W/L Record</option>
            <option value="rounds">Rounds</option>
            <option value="fourBaggers">4 Baggers</option>
            <option value="fourBaggerPct">4B%</option>
            <option value="rank">W/L Rank</option>
            <option value="wins">Wins</option>
            <option value="losses">Losses</option>
            <option value="seasonPpr">Season PPR</option>
          </select>
        </div>
        <div className="space-y-2">
          {leaderboard.slice(0, 80).map((player: any, index: number) => {
            const ppr = swapPpr(player);
            const pprDelta = numDelta(ppr, player.season?.ppr);
            return (
              <div key={player.playerId} className="rounded-2xl border border-white/10 bg-zinc-900 p-3.5">
                <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(360px,480px)]">
                  <div className="min-w-0">
                    <div className="truncate text-base font-black leading-tight sm:text-lg">#{index + 1} {player.name}</div>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3 xl:grid-cols-6">
                      <MiniMetric label="W/L Rank" value={player.rank ? `#${player.rank}` : '-'} />
                      <MiniMetric label="+/-" value={player.differential ?? '-'} />
                      <MiniMetric label="DPR" value={num(player.swapStats?.dpr, 2)} />
                      <MiniMetric label="ACL Points" value={player.totalPoints ?? '-'} />
                      <MiniMetric label="Thrown Rounds" value={player.swapStats?.rounds ?? '-'} />
                      <MiniMetric label="Season PPR" value={num(player.season?.ppr, 2)} />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <PrimaryMetric label="W/L Record" value={`${player.wins ?? 0}-${player.losses ?? 0}`} tone="text-zinc-100" />
                    <PrimaryMetric label="PPR" value={num(ppr, 2)} tone="text-amber-300" />
                    <PrimaryMetric label="4B# / 4B%" value={`${player.swapStats?.fourBaggers ?? '-'} / ${num(player.swapStats?.fourBaggerPct, 1)}`} tone="text-zinc-100" emphasized />
                    <PrimaryMetric label="Vs Season" value={delta(pprDelta)} tone={deltaTone(pprDelta)} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

    </section>
  );
}

function SwapMatchSection({
  title,
  matches,
  onOpenMatch,
  upNextPlayers = [],
}: {
  title: string;
  matches: any[];
  onOpenMatch: Props['onOpenMatch'];
  upNextPlayers?: any[];
}) {
  if (!matches.length && !upNextPlayers.length) return null;
  return (
    <section className="rounded-[28px] border border-white/10 bg-zinc-950 p-4">
      <h3 className="mb-3 text-lg font-black">{title}</h3>
      <div className="space-y-3">
        {matches.map(match => (
          <SwapMatchCard
            key={match.matchId}
            match={match}
            onOpen={() => onOpenMatch(convertSwapMatchToStandardMatch(match))}
          />
        ))}
        {upNextPlayers.length > 0 && (
          <div className="rounded-2xl border border-amber-300/30 bg-amber-300/10 p-3">
            <div className="mb-2 text-xs font-black uppercase tracking-widest text-amber-200">
              On Deck Players
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {upNextPlayers.map(player => (
                <div key={player.playerId} className="rounded-xl bg-black/25 px-3 py-2">
                  <div className="truncate text-sm font-black">{player.name}</div>
                  <div className="text-xs text-zinc-400">W/L rank #{player.rank || '-'} / W/L {player.wins}-{player.losses} / PPR {num(player.ppr, 2)}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function SwapMatchCard({ match, onOpen }: { match: any; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-2xl border border-white/10 bg-zinc-900 p-3 text-left active:scale-[0.99]"
    >
      <div className="mb-2 flex items-center justify-between text-xs text-zinc-400">
        <span>Court {match.courtId || '-'} / Match {match.matchId}</span>
        <span className="font-black text-amber-200">Open game</span>
      </div>
      <SwapTeamLine team={match.homeTeam} score={match.homeScore} tone="text-blue-300" />
      <div className="my-2 border-t border-white/10" />
      <SwapTeamLine team={match.awayTeam} score={match.awayScore} tone="text-red-300" />
    </button>
  );
}

function convertSwapMatchToStandardMatch(match: any) {
  const homeId = String(match.homeTeam?.id || match.homeTeam?.teamId || `home-${match.matchId}`);
  const awayId = String(match.awayTeam?.id || match.awayTeam?.teamId || `away-${match.matchId}`);
  const players = (match?.stats?.players || []).map((player: any) => {
    const isHome = String(player.side || '').toUpperCase() === 'HOME';
    return {
      ...player,
      id: String(player.playerId || player.id || player.name),
      teamId: isHome ? homeId : awayId,
      bagsIn: player.bagsIn,
      bagsOn: player.bagsOn,
      bagsOff: player.bagsOff,
    };
  });
  const rounds = (match?.stats?.rounds || []).map((round: any) => ({
    ...round,
    netPoints: round.netPoints ?? 0,
    scoringTeamId: round.scoringTeamId ?? null,
    players: round.players || [],
  }));
  const gameId = Number(match.gameId || match?.stats?.gameId || 1);

  return {
    id: `${match.matchId}:${gameId}`,
    eventId: String(match.eventId || ''),
    matchId: String(match.matchId),
    gameId,
    courtId: String(match.courtId || '?'),
    roundDescription: match.roundDescription || match.statusText || 'Rounders Game',
    status: match.status || 'upcoming',
    statusId: match.status === 'completed' ? 5 : match.status === 'live' ? 0 : 1,
    teams: {
      top: { id: homeId, name: match.homeTeam?.name || 'Home' },
      bottom: { id: awayId, name: match.awayTeam?.name || 'Away' },
    },
    score: {
      top: match?.stats?.homeScore ?? match.homeScore ?? 0,
      bottom: match?.stats?.awayScore ?? match.awayScore ?? 0,
    },
    games: [{
      gameId,
      status: match.status || 'upcoming',
      statusId: match.status === 'completed' ? 5 : match.status === 'live' ? 0 : 1,
      currentRound: match?.stats?.currentRound,
      score: {
        top: match?.stats?.homeScore ?? match.homeScore ?? 0,
        bottom: match?.stats?.awayScore ?? match.awayScore ?? 0,
      },
      players,
      rounds,
    }],
    activeGame: {
      gameId,
      status: match.status || 'upcoming',
      statusId: match.status === 'completed' ? 5 : match.status === 'live' ? 0 : 1,
      currentRound: match?.stats?.currentRound,
      score: {
        top: match?.stats?.homeScore ?? match.homeScore ?? 0,
        bottom: match?.stats?.awayScore ?? match.awayScore ?? 0,
      },
      players,
      rounds,
    },
  };
}

function SwapTeamLine({ team, score, tone }: { team: any; score: any; tone: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="truncate text-sm font-black">{team?.name || '-'}</div>
        <div className="text-xs text-zinc-400">Avg PPR {num(team?.avgPpr, 2)}</div>
      </div>
      <div className={`text-2xl font-black ${tone}`}>{score ?? 0}</div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: any }) {
  return (
    <div className="rounded-xl bg-zinc-950 px-2.5 py-2">
      <div className="text-sm font-black leading-tight text-zinc-100 sm:text-base">{value}</div>
      <div className="mt-0.5 text-[11px] uppercase tracking-wider text-zinc-500">{label}</div>
    </div>
  );
}

function PrimaryMetric({ label, value, tone, emphasized = false }: { label: string; value: any; tone: string; emphasized?: boolean }) {
  return (
    <div className="rounded-xl bg-zinc-950 px-3 py-2.5">
      <div className={`${emphasized ? 'text-[1.7rem]' : 'text-2xl'} font-black leading-none ${tone}`}>{value}</div>
      <div className="mt-1 text-[11px] uppercase tracking-wider text-zinc-500">{label}</div>
    </div>
  );
}

function num(value: any, digits = 0) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return n.toFixed(digits);
}

function swapPpr(player: any) {
  const detail = Number(player?.swapStats?.ppr);
  if (Number.isFinite(detail) && detail > 0) return detail;
  const acl = Number(player?.ppr);
  return Number.isFinite(acl) ? acl : 0;
}

function numDelta(value: any, baseline: any) {
  const current = Number(value);
  const base = Number(baseline);
  if (!Number.isFinite(current) || !Number.isFinite(base)) return undefined;
  return current - base;
}

function delta(value: number | undefined) {
  if (!Number.isFinite(value)) return '-';
  const n = Number(value);
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}`;
}

function deltaTone(value: number | undefined) {
  if (!Number.isFinite(value)) return 'text-zinc-100';
  const n = Number(value);
  if (n > 0) return 'text-green-300';
  if (n < 0) return 'text-red-300';
  return 'text-zinc-100';
}

function MatchSection({ title, matches, onOpenMatch }: any) {
  return (
    <section>
      <h3 className="mb-3 px-1 text-xl font-black">{title}</h3>

      <div className="space-y-3">
        {matches.map((match: any) => {
          const matchId = match.id || match.matchId;

          return (
            <TournamentMatchCard
              key={matchId}
              match={match}
              onClick={() => onOpenMatch(matchId)}
            />
          );
        })}
      </div>
    </section>
  );
}

function MobileBracketFlow({
  matches,
  onOpenMatch,
  selectedPathTeamId,
  selectedPathTeamName,
  selectedPathSummary,
  onSelectPath,
  onClearPath,
}: {
  matches: EnrichedMatch[];
  onOpenMatch: (matchId: string) => void;
  selectedPathTeamId?: string;
  selectedPathTeamName?: string;
  selectedPathSummary?: PathSummary;
  onSelectPath: (teamId: string) => void;
  onClearPath: () => void;
}) {
  const roundScrollerRef = useRef<HTMLDivElement | null>(null);
  const availableSides = bracketSections(matches);
  const [activeSide, setActiveSide] = useState<BracketSideKind>(() =>
    availableSides.some(section => section.side === 'winners') ? 'winners' : (availableSides[0]?.side || 'unknown')
  );
  useEffect(() => {
    if (!availableSides.some(section => section.side === activeSide)) {
      setActiveSide(availableSides.some(section => section.side === 'winners') ? 'winners' : (availableSides[0]?.side || 'unknown'));
    }
  }, [matches, activeSide]);
  const current = matches.filter(m => m.status === 'live' || m.status === 'upcoming').slice(0, 8);
  const pathMatches = selectedPathTeamId
    ? matches.filter(match => teamIsInMatch(match, selectedPathTeamId))
    : matches;
  const visibleMatches = pathMatches.filter(match => bracketSide(match) === activeSide);
  const currentMatches = selectedPathTeamId
    ? visibleMatches.filter(m => m.status === 'live' || m.status === 'upcoming')
    : current;
  const columns = groupByRound(visibleMatches);

  function scrollRounds(direction: -1 | 1) {
    const scroller = roundScrollerRef.current;
    if (!scroller) return;

    scroller.scrollBy({
      left: direction * scroller.clientWidth,
      behavior: 'smooth',
    });
  }

  function selectSide(side: BracketSideKind) {
    setActiveSide(side);
    window.requestAnimationFrame(() => roundScrollerRef.current?.scrollTo({ left: 0, behavior: 'smooth' }));
  }

  return (
    <section className="space-y-4">
      {selectedPathTeamId && (
        <div className="rounded-2xl border border-amber-300/40 bg-amber-300/10 px-3 py-3">
          <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase tracking-widest text-amber-200">Team filter</div>
            <div className="truncate text-sm font-black text-amber-100">{selectedPathTeamName || 'Selected team'}</div>
            <div className="mt-1 text-xs font-bold text-amber-200/80">Showing only this team&apos;s matches</div>
          </div>
          <button
            type="button"
            onClick={onClearPath}
            className="shrink-0 rounded-xl border border-amber-200/40 px-3 py-1.5 text-xs font-black text-amber-100"
          >
            Clear
          </button>
          </div>
          {selectedPathSummary && (
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <PathStat label="Wins" value={selectedPathSummary.wins} tone="text-green-300" />
              <PathStat label="Losses" value={selectedPathSummary.losses} tone="text-red-300" />
              <PathStat
                label="Status"
                value={selectedPathSummary.status}
                tone={selectedPathSummary.alive ? 'text-green-300' : selectedPathSummary.place ? 'text-blue-300' : 'text-zinc-300'}
              />
            </div>
          )}
        </div>
      )}

      {currentMatches.length > 0 && (
        <section>
          <div className="mb-2 flex items-center justify-between px-1">
            <h3 className="text-lg font-black">Current State</h3>
            <div className="text-xs font-bold uppercase tracking-widest text-zinc-500">Live / next</div>
          </div>
          <div className="flex snap-x gap-3 overflow-x-auto pb-2">
            {currentMatches.map(match => (
              <div key={match.id || match.matchId} className="w-[86vw] max-w-[360px] shrink-0 snap-start">
                <FlowMatchCard
                  match={match}
                  onOpenMatch={onOpenMatch}
                  prominent
                  selectedPathTeamId={selectedPathTeamId}
                  onSelectPath={onSelectPath}
                />
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <div className="mb-2 px-1">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-lg font-black">Bracket Flow</h3>
              <div className="text-xs text-zinc-400">One round at a time. Swipe left or right to move through the bracket.</div>
            </div>
            <div className="flex shrink-0 gap-2 md:hidden">
              <button
                type="button"
                onClick={() => scrollRounds(-1)}
                className="rounded-xl border border-white/15 bg-zinc-900 px-3 py-2 text-sm font-black"
                aria-label="Previous round"
              >
                ←
              </button>
              <button
                type="button"
                onClick={() => scrollRounds(1)}
                className="rounded-xl border border-white/15 bg-zinc-900 px-3 py-2 text-sm font-black"
                aria-label="Next round"
              >
                →
              </button>
            </div>
          </div>
          <div className="mt-2 flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-zinc-900/70 px-3 py-2 text-xs font-black uppercase tracking-widest text-zinc-300 md:hidden">
            <span>←</span>
            <span>Swipe rounds</span>
            <span>→</span>
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {availableSides.map(section => (
              <button
                key={section.side}
                type="button"
                onClick={() => selectSide(section.side)}
                aria-pressed={activeSide === section.side}
                className={`min-h-14 rounded-xl border px-4 text-left transition active:translate-y-px ${
                  activeSide === section.side
                    ? section.side === 'winners'
                      ? 'border-emerald-300 bg-emerald-300/15 text-emerald-100'
                      : section.side === 'losers'
                        ? 'border-red-300 bg-red-300/15 text-red-100'
                        : 'border-amber-300 bg-amber-300/15 text-amber-100'
                    : 'border-white/10 bg-zinc-900 text-zinc-300'
                }`}
              >
                <div className="font-black">{sectionLabel(section.side)}</div>
                <div className="mt-0.5 text-xs font-bold opacity-70">{section.matches} matches · {section.rounds} rounds</div>
              </button>
            ))}
          </div>
          <div className="mt-3 rounded-xl border border-white/10 bg-black/25 px-3 py-2 text-sm text-zinc-400">
            Showing <span className="font-black text-white">{sectionLabel(activeSide)}</span> only. Select another path above to view the rest of the bracket.
          </div>
        </div>
        <div ref={roundScrollerRef} className="flex w-full snap-x snap-mandatory gap-3 overflow-x-auto scroll-smooth pb-3 lg:gap-4">
          {columns.map(column => {
            const side = columnSide(column.matches);
            return (
            <section key={column.label} className={`w-full min-w-full shrink-0 snap-center rounded-2xl border p-3 sm:w-[88vw] sm:min-w-[88vw] md:w-[360px] md:min-w-[360px] md:snap-start xl:w-[390px] xl:min-w-[390px] ${columnSideClass(side)}`}>
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-black">{column.label}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-widest text-zinc-500">
                    <span>{column.matches.length} matches</span>
                    <span className={`rounded px-1.5 py-0.5 font-black tracking-widest ${sideBadgeClass(side)}`}>
                      {sideLabel(side)}
                    </span>
                  </div>
                </div>
                <RoundStatusCounts matches={column.matches} />
              </div>
              <div className="space-y-2">
                {column.matches.map(match => (
                  <FlowMatchCard
                    key={match.id || match.matchId}
                    match={match}
                    onOpenMatch={onOpenMatch}
                    selectedPathTeamId={selectedPathTeamId}
                    onSelectPath={onSelectPath}
                  />
                ))}
              </div>
            </section>
            );
          })}
        </div>
      </section>
    </section>
  );
}

function RoundStatusCounts({ matches }: { matches: EnrichedMatch[] }) {
  const live = matches.filter(m => m.status === 'live').length;
  const next = matches.filter(m => m.status === 'upcoming').length;
  const done = matches.filter(m => m.status === 'completed').length;
  return (
    <div className="flex gap-1 text-[10px] font-black">
      {live > 0 && <span className="rounded bg-green-400 px-1.5 py-1 text-black">{live} LIVE</span>}
      {next > 0 && <span className="rounded bg-yellow-300 px-1.5 py-1 text-black">{next} NEXT</span>}
      {done > 0 && <span className="rounded bg-blue-400 px-1.5 py-1 text-black">{done} DONE</span>}
    </div>
  );
}

function bracketSide(match: Match & any): BracketSideKind {
  if (match.flow?.side) return match.flow.side;
  const explicit = explicitBracketSide(match);
  if (explicit !== 'unknown') return explicit;

  const text = [
    match.bracketSide,
    match.bracketside,
    match.roundDescription,
    match.rounddesc,
    match.bracketRoundDescription,
    match.flow?.label,
  ].filter(Boolean).join(' ').toLowerCase();

  if (text.includes('champion') || text.includes('final')) return 'finals';
  if (text.includes('loser') || text.includes('elimination') || text.includes('consolation')) return 'losers';
  if (text.includes('winner') || text.includes('winners')) return 'winners';

  const winnerTo = roundLabel(match.flow?.winnerNext || {}).toLowerCase();
  const loserTo = roundLabel(match.flow?.loserNext || {}).toLowerCase();
  if (winnerTo.includes('loser') && loserTo.includes('loser')) return 'losers';
  if (winnerTo.includes('winner') || winnerTo.includes('round')) return 'winners';

  return 'unknown';
}

function inferBracketSides(matches: EnrichedMatch[]) {
  const losses = new Map<string, number>();
  const sideByMatch = new Map<string, BracketSideKind>();

  [...matches].sort(compareMatchProgress).forEach(match => {
    const top = match.teams?.top;
    const bottom = match.teams?.bottom;
    const topId = top?.id ? String(top.id) : undefined;
    const bottomId = bottom?.id ? String(bottom.id) : undefined;
    const textSide = textBracketSide(match);
    const explicitSide = explicitBracketSide(match);
    const hasPriorLoss = [topId, bottomId].some(id => id && (losses.get(id) || 0) > 0);
    const side = textSide === 'finals'
      ? 'finals'
      : explicitSide === 'winners' || explicitSide === 'losers'
        ? explicitSide
        : hasPriorLoss
          ? 'losers'
          : textSide === 'unknown' ? 'winners' : textSide;

    sideByMatch.set(matchKey(match), side);

    if (match.status !== 'completed') return;

    const topScore = Number(getScore(match, 'top'));
    const bottomScore = Number(getScore(match, 'bottom'));
    if (!Number.isFinite(topScore) || !Number.isFinite(bottomScore) || topScore === bottomScore) return;

    const loserId = topScore > bottomScore ? bottomId : topId;
    if (loserId) {
      losses.set(loserId, (losses.get(loserId) || 0) + 1);
    }
  });

  return sideByMatch;
}

function textBracketSide(match: Match & any): BracketSideKind {
  const text = [
    match.bracketSide,
    match.bracketside,
    match.roundDescription,
    match.rounddesc,
    match.bracketRoundDescription,
    match.flow?.label,
  ].filter(Boolean).join(' ').toLowerCase();

  if (text.includes('champion') || text.includes('final')) return 'finals';
  const explicit = explicitBracketSide(match);
  if (explicit !== 'unknown') return explicit;
  if (text.includes('loser') || text.includes('elimination') || text.includes('consolation')) return 'losers';
  if (text.includes('winner') || text.includes('winners')) return 'winners';
  return 'unknown';
}

function explicitBracketSide(match: Match & any): BracketSideKind {
  const value = String(match.bracketSide ?? match.bracketside ?? '').trim().toUpperCase();
  if (['W', 'WINNER', 'WINNERS', 'WB'].includes(value)) return 'winners';
  if (['L', 'LOSER', 'LOSERS', 'LB'].includes(value)) return 'losers';
  if (['F', 'FINAL', 'FINALS', 'CHAMPIONSHIP'].includes(value)) return 'finals';
  return 'unknown';
}

function bracketSections(matches: EnrichedMatch[]) {
  const sides: BracketSideKind[] = ['winners', 'losers', 'finals'];
  return sides.map(side => {
    const sideMatches = matches.filter(match => bracketSide(match) === side);
    return {
      side,
      matches: sideMatches.length,
      rounds: new Set(sideMatches.map(match => match.flow.label)).size,
    };
  }).filter(section => section.matches > 0);
}

function sectionLabel(side: BracketSideKind) {
  if (side === 'winners') return 'Winners Bracket';
  if (side === 'losers') return 'Elimination Bracket';
  if (side === 'finals') return 'Championship';
  return 'Unclassified Matches';
}

function columnSide(matches: EnrichedMatch[]): BracketSideKind {
  const counts = matches.reduce<Record<BracketSideKind, number>>((acc, match) => {
    const side = bracketSide(match);
    acc[side] += 1;
    return acc;
  }, { winners: 0, losers: 0, finals: 0, mixed: 0, unknown: 0 });

  const known = counts.winners + counts.losers + counts.finals;
  if (!known) return 'unknown';
  if (counts.finals === known) return 'finals';
  if (counts.winners && counts.losers) return 'mixed';
  if (counts.winners) return 'winners';
  if (counts.losers) return 'losers';
  return 'unknown';
}

function sideLabel(side: BracketSideKind) {
  if (side === 'winners') return 'Winners';
  if (side === 'losers') return 'Losers';
  if (side === 'finals') return 'Finals';
  if (side === 'mixed') return 'Mixed';
  return 'Side ?';
}

function sideBadgeClass(side: BracketSideKind) {
  if (side === 'winners') return 'bg-emerald-400/15 text-emerald-200';
  if (side === 'losers') return 'bg-red-400/15 text-red-200';
  if (side === 'finals') return 'bg-blue-400/15 text-blue-200';
  if (side === 'mixed') return 'bg-amber-300/15 text-amber-100';
  return 'bg-white/10 text-zinc-300';
}

function sideCardClass(side: BracketSideKind) {
  if (side === 'winners') return 'border-emerald-300/20 bg-emerald-950/10 shadow-[inset_4px_0_0_rgba(110,231,183,.22)]';
  if (side === 'losers') return 'border-red-300/20 bg-red-950/10 shadow-[inset_4px_0_0_rgba(248,113,113,.22)]';
  if (side === 'finals') return 'border-blue-300/20 bg-blue-950/10 shadow-[inset_4px_0_0_rgba(147,197,253,.24)]';
  if (side === 'mixed') return 'border-amber-200/20 bg-amber-950/10 shadow-[inset_4px_0_0_rgba(253,230,138,.2)]';
  return 'border-white/10 bg-zinc-900/80';
}

function sideProminentClass(side: BracketSideKind) {
  if (side === 'unknown') return 'border-amber-300/40 bg-zinc-900';
  return sideCardClass(side);
}

function columnSideClass(side: BracketSideKind) {
  if (side === 'winners') return 'border-emerald-300/15 bg-emerald-950/5';
  if (side === 'losers') return 'border-red-300/15 bg-red-950/5';
  if (side === 'finals') return 'border-blue-300/15 bg-blue-950/5';
  if (side === 'mixed') return 'border-amber-200/15 bg-amber-950/5';
  return 'border-white/10 bg-zinc-950/80';
}

function FlowMatchCard({
  match,
  onOpenMatch,
  prominent = false,
  selectedPathTeamId,
  onSelectPath,
}: {
  match: EnrichedMatch;
  onOpenMatch: (matchId: string) => void;
  prominent?: boolean;
  selectedPathTeamId?: string;
  onSelectPath: (teamId: string) => void;
}) {
  const top = match?.teams?.top;
  const bottom = match?.teams?.bottom;
  const topScore = getScore(match, 'top');
  const bottomScore = getScore(match, 'bottom');
  const matchId = match.id || match.matchId;
  const hasResult = match.status === 'completed';
  const side = bracketSide(match);
  const isPathMatch = Boolean(
    selectedPathTeamId &&
    (String(top?.id) === selectedPathTeamId || String(bottom?.id) === selectedPathTeamId)
  );

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpenMatch(matchId)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpenMatch(matchId);
        }
      }}
      className={`block w-full rounded-2xl border text-left active:scale-[0.99] ${
        isPathMatch
          ? 'border-amber-300 bg-amber-300/10 shadow-[0_0_0_2px_rgba(252,211,77,.45)]'
          : prominent
            ? sideProminentClass(side)
            : sideCardClass(side)
      } ${prominent ? 'p-4' : 'p-3'}`}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-zinc-500">
          <span>M{match.matchId} / Court {courtLabel(match)}</span>
          <span className={`rounded px-1.5 py-0.5 ${sideBadgeClass(side)}`}>
            {sideLabel(side)}
          </span>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-1 text-[10px] font-black ${statusClass(match.status)}`}>
          {statusLabel(match.status)}
        </span>
      </div>

      <TeamLine
        teamId={top?.id}
        name={top?.name || 'TBD'}
        score={topScore}
        won={hasResult && match.flow.winnerName === top?.name}
        completed={hasResult}
        selected={String(top?.id) === selectedPathTeamId}
        onSelectPath={onSelectPath}
      />
      <div className="my-2 h-px bg-white/10" />
      <TeamLine
        teamId={bottom?.id}
        name={bottom?.name || 'TBD'}
        score={bottomScore}
        won={hasResult && match.flow.winnerName === bottom?.name}
        completed={hasResult}
        selected={String(bottom?.id) === selectedPathTeamId}
        onSelectPath={onSelectPath}
      />

      <div className="mt-3 space-y-1 rounded-xl bg-black/25 p-2 text-xs text-zinc-300">
        {hasResult && match.flow.winnerName && (
          <FlowLine label="Result" value={`${match.flow.winnerName} won${scoreLine(topScore, bottomScore)}`} tone="text-blue-300" />
        )}
        {match.status !== 'completed' && match.flow.waitingOn.length > 0 && (
          <FlowLine label="Waiting" value={match.flow.waitingOn.join(' / ')} tone="text-yellow-300" />
        )}
        {match.status !== 'completed' && match.flow.waitingOn.length === 0 && (
          <FlowLine label="Matchup" value="Teams set" tone="text-green-300" />
        )}
        {match.flow.winnerNext && (
          <FlowLine label="Winner to" value={nextMatchLabel(match.flow.winnerNext, match.flow.winnerId)} tone="text-green-300" />
        )}
        {match.flow.loserNext && (
          <FlowLine label="Loser to" value={nextMatchLabel(match.flow.loserNext, match.flow.loserId)} tone="text-red-300" />
        )}
        {!match.flow.loserNext && hasResult && match.flow.loserName && (
          <FlowLine
            label="Loser"
            value={`${match.flow.loserName} finished ${match.flow.loserPlace ? ordinal(match.flow.loserPlace) : 'out'}`}
            tone="text-red-300"
          />
        )}
        {!match.flow.winnerNext && hasResult && (
          <FlowLine label="Next" value="No later match found" tone="text-zinc-500" />
        )}
      </div>
    </div>
  );
}

function PathStat({ label, value, tone }: { label: string; value: string | number; tone: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/25 px-2 py-2">
      <div className={`text-lg font-black leading-none ${tone}`}>{value}</div>
      <div className="mt-1 text-[10px] font-bold uppercase tracking-widest text-zinc-500">{label}</div>
    </div>
  );
}

function TeamLine({
  teamId,
  name,
  score,
  won,
  completed,
  selected,
  onSelectPath,
}: {
  teamId?: string | number;
  name: string;
  score: number | string;
  won?: boolean;
  completed?: boolean;
  selected?: boolean;
  onSelectPath: (teamId: string) => void;
}) {
  const canTrace = Boolean(teamId);

  return (
    <div className="grid grid-cols-[1fr_auto_auto] items-center gap-2">
      <div className={`min-w-0 rounded-lg px-2 py-1 text-base leading-tight ${
        won
          ? 'bg-emerald-400/12 font-black text-emerald-200'
          : completed
            ? 'font-semibold text-white/85'
            : 'font-black text-white'
      }`}>
        {name}
      </div>
      <div className={`min-w-[2.25rem] text-right text-2xl tabular-nums ${won ? 'font-black text-emerald-200' : 'font-semibold text-white'}`}>{displayScore(score)}</div>
      {canTrace && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onSelectPath(String(teamId));
          }}
          className={`rounded-lg border px-2 py-1 text-[10px] font-black uppercase tracking-widest ${
            selected
              ? 'border-amber-300 bg-amber-300 text-black'
              : 'border-white/15 bg-white/5 text-zinc-300'
          }`}
          title={`Filter to ${name}`}
        >
          Filter
        </button>
      )}
    </div>
  );
}

function FlowLine({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="grid grid-cols-[5rem_1fr] gap-2">
      <div className="font-bold uppercase tracking-widest text-zinc-500">{label}</div>
      <div className={`min-w-0 font-bold ${tone}`}>{value}</div>
    </div>
  );
}

function enrichBracketFlow(matches: (Match & any)[]): EnrichedMatch[] {
  const base = matches.map(match => ({ ...match, flow: emptyFlow(match) })) as EnrichedMatch[];
  const appearances = new Map<string, EnrichedMatch[]>();

  base.forEach(match => {
    [match.teams?.top, match.teams?.bottom].forEach(team => {
      if (!team?.id) return;
      const list = appearances.get(String(team.id)) || [];
      list.push(match);
      appearances.set(String(team.id), list);
    });
  });

  appearances.forEach(list => list.sort(compareMatchProgress));

  const sideByMatch = inferBracketSides(base);

  const enriched = base.map(match => {
    const top = match.teams?.top;
    const bottom = match.teams?.bottom;
    const topScore = Number(getScore(match, 'top'));
    const bottomScore = Number(getScore(match, 'bottom'));
    const hasScores = Number.isFinite(topScore) && Number.isFinite(bottomScore);
    const winner = match.status === 'completed' && hasScores
      ? topScore >= bottomScore ? top : bottom
      : undefined;
    const loser = match.status === 'completed' && hasScores
      ? topScore >= bottomScore ? bottom : top
      : undefined;

    const waitingOn = [top, bottom]
      .filter(team => isPlaceholderTeam(team?.name))
      .map(team => `${team?.name || 'TBD'}`);

    return {
      ...match,
      flow: {
        label: roundLabel(match),
        sort: roundSort(match),
        winnerName: winner?.name,
        loserName: loser?.name,
        winnerId: winner?.id ? String(winner.id) : undefined,
        loserId: loser?.id ? String(loser.id) : undefined,
        winnerNext: winner?.id ? nextAppearance(match, appearances.get(String(winner.id)) || []) : undefined,
        loserNext: loser?.id ? nextAppearance(match, appearances.get(String(loser.id)) || []) : undefined,
        side: sideByMatch.get(matchKey(match)),
        waitingOn,
      },
    };
  });

  return enriched.map(match => {
    if (match.status !== 'completed' || !match.flow.loserId || match.flow.loserNext) {
      return match;
    }

    return {
      ...match,
      flow: {
        ...match.flow,
        loserPlace: estimatePlace(enriched, match.flow.loserId),
      },
    };
  });
}

function emptyFlow(match: Match & any) {
  return {
    label: roundLabel(match),
    sort: roundSort(match),
    waitingOn: [],
  };
}

function groupByRound(matches: EnrichedMatch[]) {
  const groups = new Map<string, EnrichedMatch[]>();

  matches.forEach(match => {
    const label = match.flow.label;
    groups.set(label, [...(groups.get(label) || []), match]);
  });

  return [...groups.entries()]
    .map(([label, groupMatches]) => ({
      label,
      sort: Math.min(...groupMatches.map(m => m.flow.sort)),
      matches: groupMatches.sort(compareMatchProgress),
    }))
    .sort((a, b) => a.sort - b.sort || a.label.localeCompare(b.label));
}

function nextAppearance(current: Match & any, list: (Match & any)[]) {
  const currentIndex = list.findIndex(item => String(item.matchId) === String(current.matchId) && getGameId(item) === getGameId(current));
  if (currentIndex < 0) return undefined;
  return list[currentIndex + 1];
}

function compareMatchProgress(a: Match & any, b: Match & any) {
  return roundSort(a) - roundSort(b) || Number(a.matchId || 0) - Number(b.matchId || 0) || getGameId(a) - getGameId(b);
}

function roundSort(match: Match & any) {
  const label = roundLabel(match).toLowerCase();
  const number = Number(label.match(/(\d+)/)?.[1] || 0);
  if (label.includes('champion')) return 1000;
  if (label.includes('quarter')) return 700 + number;
  if (label.includes('semi')) return 800 + number;
  if (label.includes('final')) return 900 + number;
  if (label.includes('loser')) return 500 + number;
  return number || 100;
}

function roundLabel(match: any) {
  const raw = (
    match.roundDescription ||
    match.rounddesc ||
    match.bracketRoundDescription ||
    (match.round ? `Bracket Round ${match.round}` : 'Bracket Round ?')
  );
  const explicit = explicitBracketSide(match);
  if (explicit === 'winners' && /^losers?\b/i.test(raw)) {
    return raw.replace(/^losers?/i, 'Winner');
  }
  if (explicit === 'losers' && /^winners?\b/i.test(raw)) {
    return raw.replace(/^winners?/i, 'Loser');
  }
  return raw;
}

function statusLabel(status?: string) {
  if (status === 'live') return 'LIVE';
  if (status === 'completed') return 'FINAL';
  if (status === 'upcoming') return 'NEXT';
  return 'UNKNOWN';
}

function statusClass(status?: string) {
  if (status === 'live') return 'bg-green-400 text-black';
  if (status === 'completed') return 'bg-blue-400 text-black';
  if (status === 'upcoming') return 'bg-yellow-300 text-black';
  return 'bg-zinc-600 text-white';
}

function getScore(match: any, side: 'top' | 'bottom') {
  const game = match?.activeGame || match?.games?.[0];
  return game?.score?.[side] ?? match?.score?.[side] ?? null;
}

function displayScore(score: unknown) {
  return typeof score === 'number' && Number.isFinite(score) ? String(score) : '';
}

function scoreLine(topScore: unknown, bottomScore: unknown) {
  const top = displayScore(topScore);
  const bottom = displayScore(bottomScore);
  return top || bottom ? `, ${top}-${bottom}` : '';
}

function courtLabel(match: any) {
  const court = String(match.courtId || '?');
  return court === '-1' ? '?' : court;
}

function nextMatchLabel(match: Match & any, teamId?: string) {
  const opponent = nextOpponentName(match, teamId);
  return `M${match.matchId} / ${roundLabel(match)}${opponent ? ` / vs ${opponent}` : ''}${match.status === 'live' ? ' / live' : ''}`;
}

function getGameId(match: Match & any) {
  return Number(match.gameId || match.activeGame?.gameId || match.games?.[0]?.gameId || 1);
}

function matchKey(match: Match & any) {
  return `${match.matchId || match.id}:${getGameId(match)}`;
}

function isPlaceholderTeam(name?: string) {
  const value = String(name || '').toLowerCase();
  return !value || value.includes('tbd') || value.includes('winner of') || value.includes('loser of') || value === 'bye' || value.startsWith('bye user');
}

function nextOpponentName(match: Match & any, teamId?: string) {
  if (!teamId) return '';

  const teams = [match.teams?.top, match.teams?.bottom].filter(Boolean);
  const opponent = teams.find(team => String(team.id) !== String(teamId));

  if (!opponent?.name || isPlaceholderTeam(opponent.name)) {
    return 'TBD';
  }

  return opponent.name;
}

function teamNameForId(matches: EnrichedMatch[], teamId: string) {
  for (const match of matches) {
    for (const team of [match.teams?.top, match.teams?.bottom]) {
      if (String(team?.id) === String(teamId)) {
        return team.name;
      }
    }
  }

  return undefined;
}

function pathSummaryForTeam(matches: EnrichedMatch[], teamId: string): PathSummary {
  const pathMatches = matches
    .filter(match => teamIsInMatch(match, teamId))
    .sort(compareMatchProgress);
  let wins = 0;
  let losses = 0;

  pathMatches.forEach(match => {
    if (match.status !== 'completed') return;
    if ([match.teams?.top?.name, match.teams?.bottom?.name].some(name => isPlaceholderTeam(name))) return;

    if (String(match.flow.winnerId) === String(teamId)) {
      wins += 1;
    } else if (String(match.flow.loserId) === String(teamId)) {
      losses += 1;
    }
  });

  const hasActiveOrUpcoming = pathMatches.some(match => match.status === 'live' || match.status === 'upcoming');
  const eventComplete = matches.every(match => match.status === 'completed');
  const place = eventComplete || !hasActiveOrUpcoming ? estimatePlace(matches, teamId) : undefined;
  const alive = hasActiveOrUpcoming || (!eventComplete && losses < 2);

  let status = 'In';
  if (place) {
    status = ordinal(place);
  } else if (alive) {
    status = hasActiveOrUpcoming ? 'Alive' : 'Waiting';
  } else {
    status = 'Out';
  }

  return { wins, losses, alive, status, place };
}

function teamIsInMatch(match: Match & any, teamId: string) {
  return [match.teams?.top, match.teams?.bottom].some(team => String(team?.id) === String(teamId));
}

function estimatePlace(matches: EnrichedMatch[], targetTeamId: string) {
  const teams = new Map<string, { id: string; wins: number; losses: number; lastLossOrder: number; champion: boolean }>();

  matches.forEach(match => {
    [match.teams?.top, match.teams?.bottom].forEach(team => {
      if (!team?.id || isPlaceholderTeam(team.name)) return;
      const id = String(team.id);
      if (!teams.has(id)) {
        teams.set(id, { id, wins: 0, losses: 0, lastLossOrder: -1, champion: false });
      }
    });
  });

  matches.forEach(match => {
    if (match.status !== 'completed') return;

    const order = roundSort(match) * 10000 + Number(match.matchId || 0);
    const winnerId = match.flow.winnerId;
    const loserId = match.flow.loserId;

    if (winnerId && teams.has(winnerId)) {
      const winner = teams.get(winnerId)!;
      winner.wins += 1;
      if (!match.flow.winnerNext) {
        winner.champion = true;
      }
    }

    if (loserId && teams.has(loserId)) {
      const loser = teams.get(loserId)!;
      loser.losses += 1;
      loser.lastLossOrder = Math.max(loser.lastLossOrder, order);
    }
  });

  const rows = [...teams.values()].sort((a, b) => {
    if (a.champion !== b.champion) return a.champion ? -1 : 1;
    if (a.lastLossOrder !== b.lastLossOrder) return b.lastLossOrder - a.lastLossOrder;
    if (a.wins !== b.wins) return b.wins - a.wins;
    return a.id.localeCompare(b.id);
  });

  const index = rows.findIndex(team => team.id === String(targetTeamId));
  return index >= 0 ? index + 1 : undefined;
}

function ordinal(value: number) {
  const mod100 = value % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${value}th`;

  switch (value % 10) {
    case 1: return `${value}st`;
    case 2: return `${value}nd`;
    case 3: return `${value}rd`;
    default: return `${value}th`;
  }
}

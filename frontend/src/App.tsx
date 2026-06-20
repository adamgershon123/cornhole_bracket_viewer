import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { RefreshCw, Star, Trash2 } from 'lucide-react';
import './index.css';
import { fetchEvent, type Match } from './lib/api';
import { ScoreHero } from './components/ScoreHero';
import { MetricPill } from './components/MetricPill';
import { PlayerBars } from './components/PlayerBars';
import { MomentumChart } from './components/MomentumChart';
import { RoundTimeline } from './components/RoundTimeline';
import StandingsView from './components/StandingsView';
import { TournamentView } from './components/TournamentView';

type FavoritePlayer = {
  playerId: number;
  name?: string;
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

function useQueryParam(name: string, fallback: string) {
  return new URLSearchParams(location.search).get(name) || fallback;
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

function getSelectionId(m: Match & any) {
  return m.id || `${m.matchId}:${m.gameId || m.activeGame?.gameId || 1}`;
}

function gameLabel(m: Match & any) {
  const gameId = m.gameId || m.activeGame?.gameId || 1;
  return gameId > 1 ? `Game ${gameId}` : '';
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

function App() {
  
  const [eventInput, setEventInput] = useState(useQueryParam('event_id', '248182'));
  const [eventId, setEventId] = useState(useQueryParam('event_id', '248182'));
  const [data, setData] = useState<any>(null);
  const [selected, setSelected] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | undefined>();
  const [standingsData, setStandingsData] = useState<any>(null);
  const [view, setView] = useState<'TOURNAMENT' | 'GAME' | 'STANDINGS'>('TOURNAMENT');
  const [seasonStartDate, setSeasonStartDate] = useState('2026-01-01');
const [seasonEndDate, setSeasonEndDate] = useState('2026-08-31');
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
  const [selectedPlayerId, setSelectedPlayerId] = useState<string>(
    loadStoredDefaultPlayerId() || ''
  );

  async function load(stats = true, overrideEventId?: string) {
    const targetEventId = overrideEventId || eventId;

    setLoading(true);
    setErr(undefined);

    try {
      const d = await fetchEvent(targetEventId, stats);
	  setLastRefreshAt(new Date());
	  function forceMatchStatus(m: any) {
		  const games = m.games || [];
		  const activeGame = m.activeGame;

		  const hasEndedGame = games.some((g: any) => g.matchEndTime || g.endTime);
		  const allGamesEnded =
			games.length > 0 &&
			games.every((g: any) => g.matchEndTime || g.endTime || g.matchStatusID === 5);

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
      const normalizedMatches = (d.matches || []).map((m: Match & any) => ({
		  ...m,
		  id: getSelectionId(m),
		  status: forceMatchStatus(m),
		}));

      const normalizedData = {
        ...d,
        matches: normalizedMatches,
      };

      setData(normalizedData);

      setSelected(current => {
        if (current && normalizedMatches.some((m: any) => m.id === current)) {
          return current;
        }

        return (
          normalizedMatches.find((m: Match) => m.status === 'live') ||
          normalizedMatches[0]
        )?.id;
      });
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }
async function loadStandings() {
  const playerId = selectedPlayerId || defaultPlayerId || '142125';
  console.log({
    eventId,
    seasonStartDate,
    seasonEndDate,
    selectedPlayerId,
    defaultPlayerId,
  });
  const r = await fetch(
    `/api/standings/consolidated?playerId=${playerId}` +
      `&seedEventId=${eventId}` +
      `&startDate=${seasonStartDate}` +
      `&endDate=${seasonEndDate}`
  );

  const result = await r.json();
  setStandingsData(result);
}
useEffect(() => {
  if (view === 'STANDINGS') {
    loadStandings();
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
    const activePayload = await fetchPlayerEvents(id, requestedStatus);
    const activeEvents = activePayload.events || [];

    if (requestedStatus === 'ACTIVE' && activeEvents.length === 0) {
      const completedPayload = await fetchPlayerEvents(id, 'COMPLETED');
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

    try {
      const profile = await fetchPlayerCompare(id);
      name = profile?.name;
    } catch {
      name = undefined;
    }

    const next = alreadyExists
      ? favorites.map(p => (p.playerId === id ? { ...p, name: name || p.name } : p))
      : [...favorites, { playerId: id, name }];

    setFavorites(next);
    saveFavorites(next);

    setPlayerInput('');
    setSelectedPlayerId(String(id));

    if (!defaultPlayerId) {
      setDefaultPlayerId(String(id));
      saveDefaultPlayerId(String(id));
    }

    await loadPlayerEvents(String(id), 'ACTIVE');
  }

  function removeFavoritePlayer(playerId: number) {
    const next = favorites.filter(p => p.playerId !== playerId);
    setFavorites(next);
    saveFavorites(next);

    if (defaultPlayerId === String(playerId)) {
      const nextDefault = next[0]?.playerId ? String(next[0].playerId) : '';
      setDefaultPlayerId(nextDefault);
      saveDefaultPlayerId(nextDefault);
    }

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
  }

  function makeDefaultPlayer(playerId: number) {
    setDefaultPlayerId(String(playerId));
    saveDefaultPlayerId(String(playerId));
    setSelectedPlayerId(String(playerId));
    loadPlayerEvents(String(playerId), 'ACTIVE');
  }

  function openPlayerEvent(event: PlayerEvent) {
    const nextEventId = String(event.eventId);
    setEventId(nextEventId);

    const url = new URL(window.location.href);
    url.searchParams.set('event_id', nextEventId);
    window.history.replaceState({}, '', url.toString());

    load(true, nextEventId);
	setView('TOURNAMENT');
  }

  useEffect(() => {
    load(true);
    const id = setInterval(() => load(true), 30000);
    return () => clearInterval(id);
  }, [eventId]);

  useEffect(() => {
    const id = selectedPlayerId || defaultPlayerId;
    if (id) {
      loadPlayerEvents(id, 'ACTIVE');
    }
  }, []);

  const match: (Match & any) | undefined = useMemo(
    () => data?.matches?.find((m: any) => m.id === selected) || data?.matches?.[0],
    [data, selected]
  );

  const game = match?.activeGame || match?.games?.[0];
  const players = game?.players || [];
  const rounds = game?.rounds || [];

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

  return (
    <main className="min-h-screen safe-x py-4 max-w-6xl mx-auto">
      <header className="flex items-center justify-between gap-3 sticky top-0 z-20 bg-black/75 backdrop-blur py-3">
	  {view === 'GAME' && (
							  <button
								onClick={() => setView('TOURNAMENT')}
								className="mb-3 rounded-xl border border-white/10 px-4 py-2"
							  >
								← Tournament View
							  </button>
							)}
        <div>
          <div className="text-xs uppercase tracking-[.25em] text-amber-300">
            Cornhole Live
          </div>

          <h1 className="text-xl font-black leading-tight truncate max-w-[240px] sm:max-w-none">
            {data?.event?.name || 'Live Scoreboard'}
          </h1>

          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-zinc-400">
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
          onClick={() => load(true)}
          className="rounded-full border border-white/10 bg-zinc-900 p-3"
        >
          <RefreshCw className={loading ? 'animate-spin' : ''} size={18} />
        </button>
      </header>

      <section className="mt-3 glass rounded-[28px] p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-black">Favorite Players</h2>
            <div className="text-xs text-zinc-400">
              Add ACL player IDs, set a default, then tap an active event to load it.
            </div>
          </div>

          <button
            onClick={() => loadPlayerEvents()}
            className="rounded-full border border-white/10 bg-zinc-900 p-3"
          >
            <RefreshCw
              className={playerEventsLoading ? 'animate-spin' : ''}
              size={16}
            />
          </button>
        </div>

        <form
          onSubmit={e => {
            e.preventDefault();
            addFavoritePlayer();
          }}
          className="mt-3 flex gap-2"
        >
          <input
            className="flex-1 rounded-2xl bg-zinc-900 border border-white/10 px-4 py-3"
            value={playerInput}
            onChange={e => setPlayerInput(e.target.value)}
            placeholder="ACL Player ID"
            inputMode="numeric"
          />
          <button className="rounded-2xl bg-amber-400 text-black font-black px-5">
            Add
          </button>
        </form>

        {favorites.length > 0 && (
          <div className="mt-3 flex overflow-x-auto gap-2 pb-1">
            {favorites.map(player => {
              const isSelected = selectedPlayerId === String(player.playerId);
              const isDefault = defaultPlayerId === String(player.playerId);

              return (
                <div
                  key={player.playerId}
                  className={`shrink-0 rounded-2xl border px-3 py-2 ${
                    isSelected
                      ? 'bg-white text-black border-white'
                      : 'bg-zinc-900 border-white/10'
                  }`}
                >
                  <button
                    onClick={() => chooseFavoritePlayer(player.playerId)}
                    className="text-left"
                  >
                    <div className="text-xs opacity-70">
                      Player {player.playerId}
                    </div>
                    <div className="font-black max-w-[180px] truncate">
                      {player.name || `Player ${player.playerId}`}
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
                      {isDefault ? 'Default' : 'Default'}
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
    {playerEventStatus === 'ACTIVE'
      ? 'Active Events'
      : 'Completed Events'}
  </div>

  <div className="flex gap-2">
    <button
      type="button"
      onClick={() => loadPlayerEvents(undefined, 'ACTIVE')}
      className={`rounded px-2 py-1 text-xs border ${
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
      className={`rounded px-2 py-1 text-xs border ${
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
            <div className="text-sm text-zinc-400">Loading active events...</div>
          )}

          {!playerEventsLoading && playerEvents.length === 0 && (
            <div className="text-sm text-zinc-400">
              No active events found for the selected player.
            </div>
          )}

          {playerEvents.length > 0 && (
            <div className="flex overflow-x-auto gap-2 pb-1">
              {playerEvents.map(event => (
                <button
                  key={event.eventId}
                  onClick={() => openPlayerEvent(event)}
                  className={`shrink-0 rounded-2xl px-4 py-3 border text-left ${
                    String(event.eventId) === String(eventId)
                      ? 'bg-amber-400 text-black border-amber-400'
                      : 'bg-zinc-900 border-white/10'
                  }`}
                >
                  <div className="text-xs opacity-70">
                    Event {event.eventId} · {event.matchType || '?'}
                    {event.blindDraw ? ' · Blind Draw' : ''}
                  </div>

                  <div className="font-black max-w-[260px] truncate">
                    {event.name}
                  </div>

                  <div className="text-xs opacity-70 max-w-[260px] truncate">
                    {event.date || '-'} · {event.location?.name || 'Location TBD'}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      <form
        onSubmit={e => {
		  e.preventDefault();

		  const nextEventId = eventInput.trim();

		  if (!nextEventId) return;

		  setEventId(nextEventId);

		  const url = new URL(window.location.href);
		  url.searchParams.set('event_id', nextEventId);
		  window.history.replaceState({}, '', url.toString());

		  load(true, nextEventId);
		}}
        className="mt-3 flex gap-2"
      >
        <input
          className="flex-1 rounded-2xl bg-zinc-900 border border-white/10 px-4 py-3"
          value={eventInput}
		  onChange={e => setEventInput(e.target.value)}
          placeholder="Event ID"
        />
        <button className="rounded-2xl bg-amber-400 text-black font-black px-5">
          Load
        </button>
      </form>

      {err && (
        <div className="mt-3 rounded-2xl bg-red-950 border border-red-500/40 p-3 text-sm">
          {err}
        </div>
      )}
	  <div className="mt-4 flex gap-2">
	  <button
		type="button"
		onClick={() => setView('TOURNAMENT')}
		className={`rounded-xl px-4 py-2 font-bold ${
		  view === 'TOURNAMENT' ? 'bg-amber-400 text-black' : 'bg-zinc-800 text-white'
		}`}
	  >
		Tournament
	  </button>

	  <button
		type="button"
		onClick={() => setView('STANDINGS')}
		className={`rounded-xl px-4 py-2 font-bold ${
		  view === 'STANDINGS' ? 'bg-amber-400 text-black' : 'bg-zinc-800 text-white'
		}`}
	  >
		Standings
	  </button>
	</div>
{view === 'TOURNAMENT' && data && (
  <TournamentView
    data={data}
    matches={sortedMatches}
    onOpenMatch={(matchId) => {
      setSelected(matchId);
      setView('GAME');
    }}
  />
)}
{view === 'STANDINGS' && (
  <section className="glass rounded-[28px] p-4 mt-4">
    <h2 className="text-lg font-black mb-3">
      Season Settings
    </h2>

    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">

      <div>
        <label className="text-xs text-zinc-400">
          Start Date
        </label>

        <input
          type="date"
          value={seasonStartDate}
          onChange={(e) => setSeasonStartDate(e.target.value)}
          className="w-full rounded-xl bg-zinc-900 border border-white/10 p-2"
        />
      </div>

     /* <div>
        <label className="text-xs text-zinc-400">
          End Date
        </label>

        <input
          type="date"
          value={seasonEndDate}
          onChange={(e) => setSeasonEndDate(e.target.value)}
          className="w-full rounded-xl bg-zinc-900 border border-white/10 p-2"
        />
      </div>

      <div className="flex items-end">
        <button
          onClick={loadStandings}
          className="w-full rounded-xl bg-amber-400 text-black font-black p-2"
        >
          Refresh Standings
        </button>
      </div>
*/
<input
  type="date"
  value={seasonStartDate}
  onChange={(e) => {
    console.log("NEW START DATE", e.target.value);
    setSeasonStartDate(e.target.value);
  }}
  className="w-full rounded-xl bg-zinc-900 border border-white/10 p-2"
/>

<input
  type="date"
  value={seasonEndDate}
  onChange={(e) => {
    console.log("NEW END DATE", e.target.value);
    setSeasonEndDate(e.target.value);
  }}
  className="w-full rounded-xl bg-zinc-900 border border-white/10 p-2"
/>
    </div>
  </section>
)}
{view === 'STANDINGS' && (
  <section className="mt-4">
    <StandingsView standingsData={standingsData} />
  </section>
)}
     {view === 'GAME' && match && (
  <div className="mt-4 grid grid-cols-1 lg:grid-cols-[1.05fr_.95fr] gap-4">
    <div className="space-y-4">
      <ScoreHero match={match} />

      <div className="grid grid-cols-3 gap-2">
  <MetricPill
    label="Round"
    value={game?.currentRound || match.currentRound || '-'}
  />

  <MetricPill
    label="Top PPR"
    value={players[0]?.ppr?.toFixed(2) || '0.00'}
  />

  <MetricPill
    label="Limit"
    value="N/A"
  />
</div>

      <PlayerBars players={players} />
    </div>

    <div className="space-y-4">
      <MomentumChart
        rounds={rounds}
        topTeamId={match.teams.top.id}
        bottomTeamId={match.teams.bottom.id}
      />
	<RoundTimeline
	  rounds={rounds}
	  topTeamName={match.teams.top.name}
	  bottomTeamName={match.teams.bottom.name}
	  topTeamId={match.teams.top.id}
	  bottomTeamId={match.teams.bottom.id}
	/>
    </div>
  </div>
)}
    </main>
  );
}
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
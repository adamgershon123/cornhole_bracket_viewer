import { ChevronDown, RefreshCw, Search, Users } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { fetchVenueCourtPpr } from '../lib/api';

export default function VenueCourtPprView({
  venueKey,
  startDate,
  endDate,
}: {
  venueKey: string;
  startDate: string;
  endDate: string;
}) {
  const [data, setData] = useState<any>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [playerSearch, setPlayerSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load(playerIds = selected) {
    if (!venueKey) return;
    setLoading(true);
    setError('');
    try {
      setData(await fetchVenueCourtPpr(venueKey, { startDate, endDate, playerIds }));
    } catch (err: any) {
      setError(err?.message || 'Court PPR could not be loaded.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setSelected([]);
    load([]);
  }, [venueKey, startDate, endDate]);

  const visiblePlayers = useMemo(() => (
    (data?.players || []).filter((player: any) =>
      `${player.playerName} ${player.playerId}`.toLowerCase().includes(playerSearch.toLowerCase())
    )
  ), [data?.players, playerSearch]);

  function togglePlayer(playerId: number) {
    setSelected(current =>
      current.includes(playerId)
        ? current.filter(value => value !== playerId)
        : [...current, playerId]
    );
  }

  return (
    <div className="space-y-4">
      <section className="rounded-[26px] border border-cyan-300/20 bg-zinc-950 p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-xs font-black uppercase tracking-[.2em] text-cyan-300">PPR by court</div>
            <h3 className="mt-1 text-2xl font-black text-white">{data?.venue?.displayName || 'Venue court performance'}</h3>
            <p className="mt-1 text-sm text-zinc-500">
              {startDate} through {endDate}. PPR is recalculated from the selected players’ downloaded rounds.
            </p>
          </div>
          <button onClick={() => load()} disabled={loading} className="flex min-h-12 items-center gap-2 rounded-xl border border-cyan-300/25 bg-cyan-300/10 px-4 font-black text-cyan-200 active:translate-y-1 disabled:opacity-50">
            <RefreshCw size={17} className={loading ? 'animate-spin' : ''} />
            {loading ? 'Calculating…' : 'Apply player filter'}
          </button>
        </div>

        <div className="mt-4 rounded-2xl border border-white/10 bg-black/30 p-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <Users size={17} className="text-zinc-500" />
              <div>
                <div className="font-black text-white">{selected.length ? `${selected.length} players selected` : 'All players'}</div>
                <div className="text-xs text-zinc-500">Select any combination, then apply the filter.</div>
              </div>
            </div>
            <button onClick={() => { setSelected([]); load([]); }} className={`min-h-11 rounded-xl border px-4 font-black active:translate-y-1 ${selected.length === 0 ? 'border-amber-300 bg-amber-300 text-black' : 'border-white/10 bg-zinc-900 text-white'}`}>
              All players
            </button>
          </div>
          <div className="mt-3 flex items-center gap-2 rounded-xl border border-white/10 bg-zinc-900 px-3">
            <Search size={15} className="text-zinc-500" />
            <input value={playerSearch} onChange={event => setPlayerSearch(event.target.value)} placeholder="Find player by name or ACL ID" className="min-h-11 w-full bg-transparent text-sm text-white outline-none" />
          </div>
          <div className="mt-3 max-h-56 overflow-y-auto rounded-xl border border-white/10 bg-zinc-950 p-2">
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {visiblePlayers.map((player: any) => {
                const active = selected.includes(player.playerId);
                return (
                  <button key={player.playerId} onClick={() => togglePlayer(player.playerId)} className={`min-h-12 rounded-xl border px-3 py-2 text-left transition active:translate-y-1 ${active ? 'border-cyan-300 bg-cyan-300/15 text-white' : 'border-white/10 bg-zinc-900 text-zinc-300'}`}>
                    <div className="font-black">{player.playerName}</div>
                    <div className="text-[10px] text-zinc-500">Player {player.playerId} · {player.rounds} available rounds</div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {error && <div className="rounded-2xl border border-red-400/25 bg-red-950/30 p-4 text-red-200">{error}</div>}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <HeroMetric label="Overall PPR" value={number(data.summary?.ppr)} tone="cyan" />
            <HeroMetric label="Events" value={data.summary?.events || 0} />
            <HeroMetric label="Courts" value={data.summary?.courts || 0} />
            <HeroMetric label="Games" value={data.summary?.games || 0} />
            <HeroMetric label="Player rounds" value={data.summary?.playerRounds || 0} />
          </div>

          {!!data.courtBreakdown?.length && (
            <section className="rounded-[26px] border border-cyan-300/20 bg-zinc-950 p-4 sm:p-5">
              <div>
                <div className="text-xs font-black uppercase tracking-[.2em] text-cyan-300">Overall breakdown by court</div>
                <h4 className="mt-1 text-xl font-black text-white">Combined court performance</h4>
                <p className="mt-1 text-sm text-zinc-500">Every downloaded event in the selected period. Results reflect the active player filter.</p>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {data.courtBreakdown.map((court: any) => (
                  <div key={court.courtId} className="rounded-2xl border border-white/10 bg-zinc-900 p-4">
                    <div className="text-xs font-black uppercase tracking-wider text-zinc-500">Court {court.courtId}</div>
                    <div className="mt-1 text-3xl font-black text-cyan-300">{number(court.ppr)} <span className="text-sm text-zinc-500">PPR</span></div>
                    <div className="mt-3 grid grid-cols-3 gap-2 border-t border-white/10 pt-3 text-center">
                      <CourtTotal label="Events" value={court.events} />
                      <CourtTotal label="Games" value={court.games} />
                      <CourtTotal label="Rounds" value={court.playerRounds} />
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          <div className="space-y-4">
            {(data.events || []).map((event: any) => (
              <section key={event.eventId} className="rounded-[26px] border border-white/10 bg-zinc-950 p-4 sm:p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-black uppercase tracking-wider text-zinc-500">{event.eventDate} · Event {event.eventId}</div>
                    <h4 className="mt-1 text-xl font-black text-white">{event.eventName}</h4>
                  </div>
                  <div className="rounded-2xl border border-amber-300/20 bg-amber-300/10 px-5 py-3 text-center">
                    <div className="text-3xl font-black text-amber-300">{number(event.ppr)}</div>
                    <div className="text-[10px] font-black uppercase tracking-wider text-zinc-500">Event PPR · {event.rounds} rounds</div>
                  </div>
                </div>
                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  {event.courts.map((court: any) => (
                    <details key={court.courtId} className="group rounded-2xl border border-white/10 bg-zinc-900">
                      <summary className="flex min-h-20 cursor-pointer list-none items-center justify-between gap-3 p-4">
                        <div>
                          <div className="text-xs font-black uppercase tracking-wider text-zinc-500">Court {court.courtId}</div>
                          <div className="mt-1 text-3xl font-black text-cyan-300">{number(court.ppr)} PPR</div>
                          <div className="mt-1 text-xs text-zinc-500">{court.games.length} games · {court.rounds} player rounds</div>
                        </div>
                        <ChevronDown className="text-zinc-500 transition group-open:rotate-180" />
                      </summary>
                      <div className="space-y-2 border-t border-white/10 p-3">
                        {court.games.map((game: any) => (
                          <div key={`${game.matchId}:${game.gameId}`} className="rounded-xl bg-zinc-950 p-3">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <div className="font-black text-white">Match {game.matchId} · Game {game.gameId}</div>
                                <div className="mt-1 text-xs text-zinc-500">
                                  {game.homeScore == null || game.awayScore == null ? 'Score unavailable' : `Final score ${game.homeScore}–${game.awayScore}`}
                                </div>
                              </div>
                              <div className="text-right">
                                <div className="text-2xl font-black text-amber-300">{number(game.ppr)}</div>
                                <div className="text-[10px] uppercase tracking-wider text-zinc-500">Game PPR</div>
                              </div>
                            </div>
                            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                              {game.players.map((player: any) => (
                                <div key={player.playerId} className="rounded-lg border border-white/10 bg-white/[.025] px-3 py-2">
                                  <a href={`/?view=profile&playerId=${player.playerId}`} className="font-black text-white hover:text-amber-300 hover:underline">{player.playerName}</a>
                                  <div className="mt-1 text-sm"><span className="font-black text-cyan-300">{number(player.ppr)} PPR</span><span className="text-zinc-600"> · {player.rounds} rounds · {player.fourBaggers} four-baggers</span></div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </details>
                  ))}
                </div>
              </section>
            ))}
            {!data.events?.length && <div className="rounded-2xl border border-white/10 bg-zinc-950 p-8 text-center text-zinc-400">No downloaded court-level rounds match this selection.</div>}
          </div>
        </>
      )}
    </div>
  );
}

function HeroMetric({ label, value, tone = 'white' }: any) {
  return <div className="rounded-2xl border border-white/10 bg-zinc-950 p-4"><div className={`text-3xl font-black ${tone === 'cyan' ? 'text-cyan-300' : 'text-white'}`}>{value ?? '—'}</div><div className="mt-1 text-[10px] font-black uppercase tracking-wider text-zinc-500">{label}</div></div>;
}

function CourtTotal({ label, value }: any) {
  return <div><div className="text-lg font-black text-white">{value}</div><div className="text-[9px] font-black uppercase tracking-wider text-zinc-600">{label}</div></div>;
}

function number(value: any) {
  return value == null ? '—' : Number(value).toFixed(2);
}

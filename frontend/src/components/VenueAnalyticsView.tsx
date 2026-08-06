import { BarChart3, CheckCircle2, Clock3, MapPin, RefreshCw, Search, Zap } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { fetchVenueEvents, fetchVenues, prioritizeVenueEvents } from '../lib/api';
import VenueCourtPprView from './VenueCourtPprView';

const currentSeasonStart = new Date().getMonth() >= 8
  ? new Date().getFullYear()
  : new Date().getFullYear() - 1;
const seasonYears = Array.from({ length: 7 }, (_, index) => currentSeasonStart - index);

function stateTone(state: string) {
  if (state === 'FULLY_DOWNLOADED') return 'border-emerald-300/25 bg-emerald-300/10 text-emerald-200';
  if (state === 'PARTIAL') return 'border-sky-300/25 bg-sky-300/10 text-sky-200';
  if (state === 'BRACKET_DOWNLOADED') return 'border-violet-300/25 bg-violet-300/10 text-violet-200';
  return 'border-zinc-600 bg-zinc-900 text-zinc-300';
}

function stateLabel(state: string) {
  return ({
    FULLY_DOWNLOADED: 'Fully downloaded',
    PARTIAL: 'Partially downloaded',
    BRACKET_DOWNLOADED: 'Bracket downloaded',
    NOT_DOWNLOADED: 'Not downloaded',
  } as Record<string, string>)[state] || state;
}

export default function VenueAnalyticsView() {
  const [venues, setVenues] = useState<any[]>([]);
  const [venueKey, setVenueKey] = useState('');
  const [search, setSearch] = useState('');
  const [mode, setMode] = useState<'season' | 'dates'>('season');
  const [seasonFrom, setSeasonFrom] = useState(currentSeasonStart);
  const [seasonTo, setSeasonTo] = useState(currentSeasonStart);
  const [startDate, setStartDate] = useState(`${currentSeasonStart}-09-01`);
  const [endDate, setEndDate] = useState(`${currentSeasonStart + 1}-08-31`);
  const [schedule, setSchedule] = useState<any>(null);
  const [venueSection, setVenueSection] = useState<'statistics' | 'courtPpr' | 'schedule'>('statistics');
  const [eventGroup, setEventGroup] = useState<'ALL'|'SIT_AND_GO'|'STANDARD'>('ALL');
  const [loading, setLoading] = useState(true);
  const [prioritizing, setPrioritizing] = useState<number | 'all' | null>(null);
  const [error, setError] = useState('');

  const range = useMemo(() => (
    mode === 'season'
      ? {
          startDate: `${Math.min(seasonFrom, seasonTo)}-09-01`,
          endDate: `${Math.max(seasonFrom, seasonTo) + 1}-08-31`,
        }
      : { startDate, endDate }
  ), [mode, seasonFrom, seasonTo, startDate, endDate]);

  const filteredVenues = venues.filter(venue => {
    const haystack = [
      venue.displayName,
      venue.city,
      venue.state,
      ...(venue.aliases || []),
    ].join(' ').toLowerCase();
    return haystack.includes(search.toLowerCase());
  });
  const visibleEvents = (schedule?.events || []).filter((event: any) => (
    eventGroup === 'ALL' || event.eventGroup === eventGroup
  ));

  async function loadSchedule(targetKey = venueKey) {
    if (!targetKey) return;
    setLoading(true);
    setError('');
    try {
      setSchedule(await fetchVenueEvents(targetKey, range));
    } catch (err: any) {
      setError(err?.message || 'Venue schedule could not be loaded.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchVenues()
      .then(payload => {
        const rows = payload?.venues || [];
        setVenues(rows);
        const hurricanes = rows.find((venue: any) =>
          String(venue.displayName || '').toLowerCase().includes('hurricane')
        );
        setVenueKey(hurricanes?.venueKey || rows[0]?.venueKey || '');
      })
      .catch(err => setError(err?.message || 'Venues could not be loaded.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (venueKey) loadSchedule(venueKey);
  }, [venueKey]);

  async function prioritize(eventIds?: number[]) {
    if (!venueKey) return;
    setPrioritizing(eventIds?.[0] || 'all');
    setError('');
    try {
      const result = await prioritizeVenueEvents(venueKey, {
        ...range,
        eventIds,
      });
      setSchedule(result.schedule);
    } catch (err: any) {
      setError(err?.message || 'Events could not be prioritized.');
    } finally {
      setPrioritizing(null);
    }
  }

  return (
    <section className="mt-4 space-y-4">
      <div className="rounded-[28px] border border-white/10 bg-zinc-950 p-5 sm:p-6">
        <div className="text-xs font-black uppercase tracking-[.24em] text-amber-300">Venue analytics</div>
        <h2 className="mt-2 text-3xl font-black text-white">Venue event schedule</h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-500">
          Review one or multiple seasons, see exactly what has been downloaded, and move missing events to the front of the historical queue.
        </p>

        <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(260px,1fr)_2fr]">
          <div>
            <label className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Find venue</label>
            <div className="mt-2 flex items-center gap-2 rounded-xl border border-white/10 bg-black px-3">
              <Search size={16} className="text-zinc-500" />
              <input value={search} onChange={event => setSearch(event.target.value)} placeholder="Venue, city, or state" className="min-h-12 w-full bg-transparent text-white outline-none" />
            </div>
            <select value={venueKey} onChange={event => setVenueKey(event.target.value)} className="mt-2 min-h-12 w-full rounded-xl border border-white/10 bg-zinc-900 px-3 font-bold text-white">
              {filteredVenues.map(venue => (
                <option key={venue.venueKey} value={venue.venueKey}>
                  {venue.displayName} · {venue.city || 'Unknown city'}, {venue.state || '—'} · {venue.eventCount} events
                </option>
              ))}
            </select>
          </div>

          <div>
            <div className="grid grid-cols-2 gap-2">
              <button onClick={() => setMode('season')} className={`min-h-12 rounded-xl border px-4 font-black active:translate-y-1 ${mode === 'season' ? 'border-amber-300 bg-amber-300 text-black' : 'border-white/10 bg-zinc-900 text-white'}`}>Season range</button>
              <button onClick={() => setMode('dates')} className={`min-h-12 rounded-xl border px-4 font-black active:translate-y-1 ${mode === 'dates' ? 'border-amber-300 bg-amber-300 text-black' : 'border-white/10 bg-zinc-900 text-white'}`}>Custom dates</button>
            </div>
            {mode === 'season' ? (
              <div className="mt-2 grid grid-cols-2 gap-2">
                <select value={seasonFrom} onChange={event => setSeasonFrom(Number(event.target.value))} className="min-h-12 rounded-xl border border-white/10 bg-zinc-900 px-3 text-white">
                  {seasonYears.map(year => <option key={year} value={year}>{year}–{year + 1}</option>)}
                </select>
                <select value={seasonTo} onChange={event => setSeasonTo(Number(event.target.value))} className="min-h-12 rounded-xl border border-white/10 bg-zinc-900 px-3 text-white">
                  {seasonYears.map(year => <option key={year} value={year}>{year}–{year + 1}</option>)}
                </select>
              </div>
            ) : (
              <div className="mt-2 grid grid-cols-2 gap-2">
                <input type="date" value={startDate} onChange={event => setStartDate(event.target.value)} className="min-h-12 rounded-xl border border-white/10 bg-zinc-900 px-3 text-white" />
                <input type="date" value={endDate} onChange={event => setEndDate(event.target.value)} className="min-h-12 rounded-xl border border-white/10 bg-zinc-900 px-3 text-white" />
              </div>
            )}
            <button onClick={() => loadSchedule()} disabled={!venueKey || loading} className="mt-2 flex min-h-12 w-full items-center justify-center gap-2 rounded-xl border border-sky-300/30 bg-sky-300/10 px-4 font-black text-sky-200 active:translate-y-1 disabled:opacity-50">
              <RefreshCw size={17} className={loading ? 'animate-spin' : ''} />
              Load venue schedule
            </button>
          </div>
        </div>
      </div>

      {error && <div className="rounded-2xl border border-red-400/25 bg-red-950/30 p-4 text-red-200">{error}</div>}

      {schedule && (
        <>
          <div className="grid grid-cols-1 gap-2 rounded-2xl border border-white/10 bg-zinc-950 p-2 min-[430px]:grid-cols-3">
            <button onClick={() => setVenueSection('statistics')} className={`min-h-14 rounded-xl border px-4 text-base font-black transition active:translate-y-1 ${venueSection === 'statistics' ? 'border-sky-300 bg-sky-300 text-black shadow-[0_0_24px_rgba(125,211,252,.15)]' : 'border-white/10 bg-zinc-900 text-zinc-300'}`}>
              Venue Statistics
            </button>
            <button onClick={() => setVenueSection('courtPpr')} className={`min-h-14 rounded-xl border px-4 text-base font-black transition active:translate-y-1 ${venueSection === 'courtPpr' ? 'border-cyan-300 bg-cyan-300 text-black shadow-[0_0_24px_rgba(103,232,249,.15)]' : 'border-white/10 bg-zinc-900 text-zinc-300'}`}>
              PPR by Court
            </button>
            <button onClick={() => setVenueSection('schedule')} className={`min-h-14 rounded-xl border px-4 text-base font-black transition active:translate-y-1 ${venueSection === 'schedule' ? 'border-amber-300 bg-amber-300 text-black shadow-[0_0_24px_rgba(252,211,77,.15)]' : 'border-white/10 bg-zinc-900 text-zinc-300'}`}>
              Schedule & Data
            </button>
          </div>

          <div className={`${venueSection === 'schedule' ? 'grid' : 'hidden'} grid-cols-2 gap-3 md:grid-cols-5`}>
            <Summary label="Events" value={schedule.summary.events} />
            <Summary label="Fully downloaded" value={schedule.summary.fullyDownloaded} tone="green" />
            <Summary label="Partial" value={schedule.summary.partial} tone="blue" />
            <Summary label="Bracket only" value={schedule.summary.bracketOnly} tone="violet" />
            <Summary label="Not downloaded" value={schedule.summary.notDownloaded} />
          </div>

          {venueSection === 'courtPpr' && (
            <VenueCourtPprView
              venueKey={venueKey}
              startDate={range.startDate}
              endDate={range.endDate}
            />
          )}

          <div className={`${venueSection === 'statistics' ? 'block' : 'hidden'} rounded-[26px] border border-sky-300/20 bg-zinc-950 p-4 sm:p-5`}>
            <div className="flex items-center gap-2 text-sky-200">
              <BarChart3 size={19} />
              <h3 className="text-xl font-black">Venue statistics</h3>
            </div>
            <p className="mt-1 text-sm text-zinc-500">
              Calculated from downloaded player rounds in the selected period. Events that have not been downloaded are not included.
            </p>
            <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Events analyzed" value={`${schedule.statistics?.eventsWithStatistics || 0} / ${schedule.summary.events}`} />
              <Stat label="Games" value={schedule.statistics?.games} />
              <Stat label="Players" value={schedule.statistics?.players} />
              <Stat label="Player rounds" value={schedule.statistics?.playerRounds} />
              <Stat label="Venue PPR" value={formatNumber(schedule.statistics?.ppr)} />
              <Stat label="Avg scoring swing" value={formatNumber(schedule.statistics?.averageScoringSwing)} />
              <Stat label="Round win rate" value={formatPercent(schedule.statistics?.roundWinRate)} />
              <Stat label="Four-bagger rate" value={formatPercent(schedule.statistics?.fourBaggerRate)} />
              <Stat label="Bags-in rate" value={formatPercent(schedule.statistics?.bagsInRate)} />
              <Stat label="Courts represented" value={schedule.statistics?.courts} />
            </div>
            <div className="mt-6 border-t border-white/10 pt-5">
              <div className="text-xs font-black uppercase tracking-[.2em] text-zinc-500">Event statistics</div>
              <div className="mt-3 space-y-3">
                {(schedule.events || []).filter((event: any) => event.statistics).map((event: any) => (
                  <div key={event.eventId} className="rounded-2xl border border-white/10 bg-zinc-900 p-4">
                    <div className="text-xs font-black uppercase tracking-wider text-zinc-500">{event.eventDate} · Event {event.eventId}</div>
                    <div className="mt-1 text-lg font-black leading-tight text-white">{event.eventName}</div>
                    <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
                      <AnalyticsMetric label="PPR" value={formatNumber(event.statistics.ppr)} tone="amber" primary />
                      <AnalyticsMetric label="Players" value={event.statistics.players} />
                      <AnalyticsMetric label="Games" value={event.statistics.games} />
                      <AnalyticsMetric label="Player rounds" value={event.statistics.playerRounds} />
                      <AnalyticsMetric label="Average swing" value={formatNumber(event.statistics.averageScoringSwing)} />
                      <AnalyticsMetric label="Four-bagger rate" value={formatPercent(event.statistics.fourBaggerRate)} />
                      <AnalyticsMetric label="Bags in" value={formatPercent(event.statistics.bagsInRate)} />
                    </div>
                  </div>
                ))}
                {!schedule.events?.some((event: any) => event.statistics) && (
                  <div className="rounded-2xl border border-white/10 bg-zinc-900 p-6 text-center text-zinc-400">
                    No downloaded match statistics are available for this venue and time period yet.
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className={`${venueSection === 'schedule' ? 'block' : 'hidden'} rounded-[26px] border border-white/10 bg-zinc-950 p-4 sm:p-5`}>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="flex items-center gap-2 text-amber-300"><MapPin size={18} /><span className="font-black">{schedule.venue.displayName}</span></div>
                <div className="mt-1 text-xs text-zinc-500">{schedule.startDate} through {schedule.endDate} · aliases: {(schedule.venue.aliases || []).join(', ')}</div>
              </div>
              <button onClick={() => prioritize()} disabled={prioritizing != null || schedule.summary.events === schedule.summary.fullyDownloaded} className="flex min-h-12 items-center justify-center gap-2 rounded-xl border border-amber-300/30 bg-amber-300/10 px-4 font-black text-amber-200 active:translate-y-1 disabled:opacity-40">
                <Zap size={17} /> {prioritizing === 'all' ? 'Prioritizing…' : 'Prioritize all missing'}
              </button>
            </div>
            <select value={eventGroup} onChange={event => setEventGroup(event.target.value as any)} className="mt-4 min-h-11 rounded-xl border border-white/10 bg-zinc-900 px-3 text-sm font-bold text-white">
              <option value="ALL">All event groups</option>
              <option value="SIT_AND_GO">Sit &amp; Go</option>
              <option value="STANDARD">Standard events</option>
            </select>

            <div className="mt-4 space-y-2">
              {visibleEvents.map((event: any) => (
                <div key={event.eventId} className="rounded-2xl border border-white/10 bg-black/30 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="min-w-0">
                      <div className="text-xs font-black text-zinc-500">{event.eventDate} · Event {event.eventId}</div>
                      <div className="mt-1 text-lg font-black text-white">{event.eventName}</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <span className={`rounded-lg border px-2 py-1 text-[10px] font-black uppercase ${stateTone(event.downloadState)}`}>{stateLabel(event.downloadState)}</span>
                        {event.priorityQueued && <span className="rounded-lg border border-amber-300/30 bg-amber-300/10 px-2 py-1 text-[10px] font-black uppercase text-amber-200">Priority queue</span>}
                        {event.eventGroup === 'SIT_AND_GO' && <span className="rounded-lg border border-violet-300/30 bg-violet-300/10 px-2 py-1 text-[10px] font-black uppercase text-violet-200">Sit &amp; Go</span>}
                        {event.queueStatus && !event.priorityQueued && <span className="rounded-lg border border-white/10 px-2 py-1 text-[10px] font-black uppercase text-zinc-400">{event.queueStatus}</span>}
                      </div>
                      <div className="mt-2 text-xs text-zinc-500">
                        Bracket {event.bracketDownloaded ? 'downloaded' : 'missing'} · Match files {event.matchStatsDownloaded}/{event.matchStatsTargets} · {event.gamesQueued} games queued
                      </div>
                      {!event.statistics && (
                        <div className="mt-3 text-xs font-bold text-zinc-600">Statistics will appear after match data is downloaded.</div>
                      )}
                    </div>
                    <button onClick={() => prioritize([event.eventId])} disabled={event.downloadState === 'FULLY_DOWNLOADED' || event.priorityQueued || prioritizing != null} className="flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-xl border border-white/15 bg-zinc-900 px-4 font-black text-white active:translate-y-1 disabled:opacity-35">
                      {event.downloadState === 'FULLY_DOWNLOADED' ? <CheckCircle2 size={17} /> : event.priorityQueued ? <Clock3 size={17} /> : <Zap size={17} />}
                      {event.downloadState === 'FULLY_DOWNLOADED' ? 'Downloaded' : event.priorityQueued ? 'Prioritized' : 'Prioritize event'}
                    </button>
                  </div>
                </div>
              ))}
              {!schedule.events?.length && <div className="p-8 text-center text-zinc-500">No events found for this venue and time period.</div>}
              {!!schedule.events?.length && !visibleEvents.length && (
                <div className="p-8 text-center text-zinc-500">No events match this event-group filter.</div>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function Summary({ label, value, tone = 'zinc' }: any) {
  const colors: Record<string, string> = {
    zinc: 'border-white/10 bg-zinc-950 text-white',
    green: 'border-emerald-300/25 bg-emerald-300/10 text-emerald-200',
    blue: 'border-sky-300/25 bg-sky-300/10 text-sky-200',
    violet: 'border-violet-300/25 bg-violet-300/10 text-violet-200',
  };
  return <div className={`rounded-2xl border p-4 ${colors[tone]}`}><div className="text-[10px] font-black uppercase tracking-wider opacity-65">{label}</div><div className="mt-2 text-3xl font-black">{value || 0}</div></div>;
}

function Stat({ label, value }: any) {
  return <div className="rounded-2xl border border-white/10 bg-black/30 p-4"><div className="text-[10px] font-black uppercase tracking-wider text-zinc-500">{label}</div><div className="mt-2 text-2xl font-black text-white">{value ?? '—'}</div></div>;
}

function EventStat({ label, value }: any) {
  return <div className="rounded-xl border border-white/10 bg-zinc-900/70 px-3 py-2"><div className="text-[9px] font-black uppercase tracking-wider text-zinc-600">{label}</div><div className="mt-1 text-base font-black text-white">{value ?? '—'}</div></div>;
}

function AnalyticsMetric({ label, value, tone = 'white', primary = false }: any) {
  const valueTone = tone === 'amber' ? 'text-amber-300' : 'text-white';
  return (
    <div className="rounded-xl bg-zinc-950 px-3 py-3">
      <div className={`${primary ? 'text-3xl' : 'text-2xl'} font-black leading-none ${valueTone}`}>{value ?? '—'}</div>
      <div className="mt-1.5 text-[10px] font-black uppercase tracking-wider text-zinc-500">{label}</div>
    </div>
  );
}

function formatNumber(value: any) {
  return value == null ? '—' : Number(value).toFixed(2);
}

function formatPercent(value: any) {
  return value == null ? '—' : `${Number(value).toFixed(1)}%`;
}

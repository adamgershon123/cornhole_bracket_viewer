import { Activity, AlertTriangle, BrainCircuit, CheckCircle2, Database, Download, MapPinned, Pause, Play, RefreshCw, Radar } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import {
  controlHistoricalBackfill,
  downloadHistoricalVenueCsv,
  fetchHistoricalBackfill,
  fetchPredictionOperations,
  monitorPredictionEvent,
  runPredictionLifecycle,
} from '../lib/api';

function pct(value?: number | null) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`;
}

function predictionLabel(row: any) {
  if (
    row.status !== 'PREDICTED'
    || row.side_a_probability == null
    || row.side_b_probability == null
  ) return null;
  const sideA = Number(row.side_a_probability || 0);
  const sideB = Number(row.side_b_probability || 0);
  return sideA >= sideB
    ? { winner: 'Side A', probability: sideA }
    : { winner: 'Side B', probability: sideB };
}

function confidenceLabel(probability: number) {
  if (probability >= 0.7) return 'High confidence';
  if (probability >= 0.55) return 'Lean';
  return 'Too close to call';
}

function Metric({
  label,
  value,
  detail,
  tone = 'amber',
}: {
  label: string;
  value: string | number;
  detail: string;
  tone?: 'amber' | 'green' | 'blue' | 'zinc';
}) {
  const tones = {
    amber: 'border-amber-400/30 bg-amber-400/10 text-amber-300',
    green: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300',
    blue: 'border-sky-400/30 bg-sky-400/10 text-sky-300',
    zinc: 'border-white/10 bg-white/5 text-zinc-200',
  };
  return (
    <div className={`rounded-2xl border p-4 ${tones[tone]}`}>
      <div className="text-[10px] font-black uppercase tracking-[.22em] opacity-70">{label}</div>
      <div className="mt-2 text-3xl font-black tracking-tight">{value}</div>
      <div className="mt-1 text-xs text-zinc-400">{detail}</div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded-xl border border-white/10 bg-black/20 p-3">
    <div className="text-[10px] font-black uppercase tracking-[.16em] text-zinc-500">{label}</div>
    <div className="mt-1 text-xl font-black text-white">{typeof value === 'number' ? value.toLocaleString() : value}</div>
  </div>;
}

export default function PredictionOperationsView() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [eventId, setEventId] = useState('');
  const [eventFormat, setEventFormat] = useState<'SWISS' | 'SWAP' | 'BRACKET'>('SWAP');
  const [eventTimezone, setEventTimezone] = useState('America/New_York');
  const [backfill, setBackfill] = useState<any>(null);
  const [backfillChanging, setBackfillChanging] = useState(false);
  const [venueExporting, setVenueExporting] = useState(false);
  const [predictionFilter, setPredictionFilter] = useState<'PREDICTED' | 'ALL' | 'ABSTAINED'>('PREDICTED');
  const [eventGroupFilter, setEventGroupFilter] = useState<'ALL'|'SIT_AND_GO'|'STANDARD'>('ALL');
  const [eventActivityFilter, setEventActivityFilter] = useState<'RECORDED'|'NO_ACTIVITY'|'ALL'>('RECORDED');
  const refreshInFlight = useRef(false);
  const geography = backfill?.geography || {};
  const regions = geography?.regions || [];
  const maxRegionVenues = Math.max(1, ...regions.map((region: any) => Number(region.venues || 0)));
  const pendingByType = Object.fromEntries(
    (backfill?.queue?.byType || [])
      .filter((row: any) => row.status === 'PENDING')
      .map((row: any) => [row.item_type, Number(row.count || 0)]),
  );

  async function refresh() {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    try {
      setError('');
      const historicalRequest = fetchHistoricalBackfill();
      const operations = await fetchPredictionOperations();
      setData(operations);
      setLoading(false);
      historicalRequest
        .then(setBackfill)
        .catch((err: any) => setError(err?.message || 'Historical collection could not be loaded.'));
    } catch (err: any) {
      setError(err?.message || 'Prediction operations could not be loaded.');
    } finally {
      refreshInFlight.current = false;
      setLoading(false);
    }
  }

  async function changeBackfill(action: 'pause' | 'resume', lane?: 'PREDICTION'|'ACL_CLASSIFIED') {
    setBackfillChanging(true);
    setError('');
    try {
      setBackfill(await controlHistoricalBackfill(action, lane));
    } catch (err: any) {
      setError(err?.message || 'Historical collection could not be updated.');
    } finally {
      setBackfillChanging(false);
    }
  }

  async function runCycle() {
    setRunning(true);
    setError('');
    try {
      await runPredictionLifecycle();
      await refresh();
    } catch (err: any) {
      setError(err?.message || 'Lifecycle cycle failed.');
    } finally {
      setRunning(false);
    }
  }

  async function addMonitor() {
    if (!eventId.trim() || !eventTimezone.trim()) {
      setError('Event ID and verified timezone are required.');
      return;
    }
    setRunning(true);
    setError('');
    try {
      setData(await monitorPredictionEvent({
        eventId: eventId.trim(),
        format: eventFormat,
        timezone: eventTimezone.trim(),
      }));
      setEventId('');
    } catch (err: any) {
      setError(err?.message || 'Event monitoring could not be configured.');
    } finally {
      setRunning(false);
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 60000);
    return () => window.clearInterval(timer);
  }, []);

  if (loading && !data) {
    return (
      <section className="mt-4 flex min-h-64 items-center justify-center rounded-[28px] border border-white/10 bg-zinc-950">
        <RefreshCw className="animate-spin text-amber-300" />
      </section>
    );
  }

  const shadow = data?.shadowPerformance || {};
  const queueGroups = data?.historyQueue?.groups || [];
  const queued = queueGroups.reduce((sum: number, row: any) => sum + Number(row.players || 0), 0);
  const complete = queueGroups.find((row: any) => row.status === 'COMPLETE')?.players || 0;
  const rapidAssistance = data?.rapidPredictionAssistance || {};
  const todayMonitoring = data?.todayMonitoring || {};
  const aclWorldsPriority = data?.prioritySeries?.aclWorlds || {};
  const highConfidence = data?.experimentalPerformance?.confidenceBuckets?.HIGH_CONFIDENCE_70_PLUS;
  const predictions = data?.recentPredictions || [];
  const displayedPredictions = predictions.filter((row: any) => (
    predictionFilter === 'ALL' || row.status === predictionFilter
  ));
  const evaluations = data?.predictionEvaluations?.evaluations || [];
  const learning = data?.predictionLearning || {};
  const performance = data?.predictionPerformance || {};
  const historicalBacktest = performance?.historicalBacktest || {};
  const historicalMatchPerformance = performance?.historicalMatchPerformance || {};
  const hourlyThroughput = backfill?.throughput?.lastHour || {};
  const dailyThroughput = backfill?.throughput?.last24Hours || {};
  const matchPerformance = performance?.matchPerformance || {};
  const tournamentPerformance = performance?.tournamentPerformance || {};
  const tournamentOverall = tournamentPerformance?.overall || {};
  const tournamentReplay = performance?.historicalTournamentReplay || {};
  const commonSample = shadow?.commonSample || {};
  const baselineModel = commonSample?.baseline || {};
  const challengerModel = commonSample?.challenger || {};
  const monitoredEvents = (data?.monitoredEvents || []).filter((event: any) => {
    const groupMatches = eventGroupFilter === 'ALL' || event.event_group === eventGroupFilter;
    const noActivity = event.tracking_status === 'NO_ACTIVITY' || event.last_poll_status === 'NO_ACTIVITY';
    const activityMatches = eventActivityFilter === 'ALL'
      || (eventActivityFilter === 'NO_ACTIVITY' ? noActivity : !noActivity);
    return groupMatches && activityMatches;
  });

  return (
    <section className="mt-4 space-y-4">
      <div className="overflow-hidden rounded-[30px] border border-white/10 bg-zinc-950">
        <div className="relative p-5 md:p-7">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(251,191,36,.16),transparent_42%),radial-gradient(circle_at_bottom_left,rgba(14,165,233,.10),transparent_38%)]" />
          <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.24em] text-amber-300">
                <Radar size={16} /> Prediction operations
              </div>
              <h2 className="mt-3 text-3xl font-black tracking-tight text-white md:text-4xl">
                From event discovery to scored outcomes
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-400">
                Watches ACL events, prepares player history, locks eligible pregame predictions,
                records abstentions, and scores completed matches.
              </p>
            </div>
            <button
              type="button"
              onClick={runCycle}
              disabled={running}
              className="flex min-w-48 items-center justify-center gap-2 rounded-2xl bg-amber-300 px-5 py-3 font-black text-black transition hover:bg-amber-200 disabled:cursor-wait disabled:bg-zinc-700 disabled:text-zinc-300"
            >
              <RefreshCw size={17} className={running ? 'animate-spin' : ''} />
              {running ? 'Running cycle…' : 'Run lifecycle cycle'}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-2xl border border-red-400/30 bg-red-950/40 p-4 text-sm font-bold text-red-200">
          <AlertTriangle size={17} /> {error}
        </div>
      )}

      {data?.snapshot && (
        <div className="rounded-2xl border border-sky-400/25 bg-sky-950/30 p-4 text-sm text-sky-100">
          <span className="font-black">
            {data.snapshot.prepared ? 'Prepared prediction snapshot' : 'Preparing prediction snapshot'}
          </span>
          {data.snapshot.generatedAt
            ? ` · displaying results prepared ${new Date(data.snapshot.generatedAt).toLocaleString()}`
            : ' · the page will populate after the background worker completes its first preparation.'}
          {data.snapshot.status === 'REFRESHING' && ' A newer snapshot is being calculated in the background.'}
          {data.snapshot.status === 'ERROR' && ' The last prepared results remain available while refresh is retried.'}
        </div>
      )}

      <div className="rounded-[28px] border border-sky-400/25 bg-sky-950/20 p-5">
        <div className="text-xs font-black uppercase tracking-[.22em] text-sky-300">
          Rapid prediction input
        </div>
        <div className="mt-2 text-xl font-black text-white">
          {rapidAssistance.status
            ? `${rapidAssistance.status}: ${Number(rapidAssistance.cachedAssistedPlayers || rapidAssistance.assistedPlayers || 0)} ACL-assisted profiles cached`
            : 'Awaiting the next lifecycle cycle'}
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-zinc-300">
            <span className="font-black text-white">{Number(todayMonitoring.eventCount || 0)}</span>
            {' '}today&apos;s events monitored · {todayMonitoring.status || 'IDLE'}
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-zinc-300">
            <span className="font-black text-white">{Math.max(0, queued - Number(complete || 0))}</span>
            {' '}deep-history profiles still queued
          </div>
        </div>
        <div className="mt-2 rounded-xl border border-amber-300/25 bg-amber-300/10 p-3 text-sm font-bold text-amber-200">
          ACL Worlds priority lane: {Number(aclWorldsPriority.monitored || 0)} events
        </div>
        <p className="mt-2 text-sm leading-6 text-zinc-400">
          One batch season-stat request supplies missing pregame PPR within the prediction
          window. Full round history remains queued in the background and upgrades later
          predictions without delaying today&apos;s initial output.
        </p>
      </div>

      <div className={`overflow-hidden rounded-[28px] border ${
        backfill?.paused
          ? 'border-amber-400/30 bg-amber-950/20'
          : 'border-emerald-400/30 bg-emerald-950/20'
      }`}>
        <div className="p-5 md:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.22em] text-sky-300">
                <Database size={16} /> Historical data engine
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <h3 className="text-2xl font-black text-white">
                  {backfill?.paused ? 'Paused' : backfill?.status === 'WORKING' ? 'Gathering history' : 'On'}
                </h3>
                <span className={`rounded-lg px-3 py-1 text-xs font-black uppercase tracking-wider ${
                  backfill?.paused
                    ? 'bg-amber-300 text-black'
                    : 'bg-emerald-300 text-black'
                }`}>
                  {backfill?.paused ? 'Off' : 'On'}
                </span>
              </div>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-400">
                Quietly expands through known players, completed events, brackets, and games.
                Progress and pause state survive platform restarts.
              </p>
              {backfill?.current?.type && (
                <div className="mt-2 text-xs font-bold text-zinc-500">
                  Now checking {String(backfill.current.type).toLowerCase()} {backfill.current.key}
                </div>
              )}
            </div>
            <button
              type="button"
              disabled={backfillChanging}
              onClick={() => changeBackfill(backfill?.paused ? 'resume' : 'pause')}
              className={`flex min-w-44 items-center justify-center gap-2 rounded-2xl border px-5 py-3 font-black transition active:scale-[.98] disabled:opacity-50 ${
                backfill?.paused
                  ? 'border-emerald-300 bg-emerald-300 text-black hover:bg-emerald-200'
                  : 'border-amber-300/40 bg-amber-300/10 text-amber-200 hover:bg-amber-300/20'
              }`}
            >
              {backfill?.paused ? <Play size={18} /> : <Pause size={18} />}
              {backfillChanging ? 'Updating…' : backfill?.paused ? 'Resume engine' : 'Pause engine'}
            </button>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Metric label="Player rounds" value={(backfill?.ledger?.rounds || 0).toLocaleString()} detail={`+${backfill?.gatheredSinceActivation?.rounds || 0} gathered`} tone="blue" />
            <Metric label="Downloaded games" value={(backfill?.ledger?.games || 0).toLocaleString()} detail={`+${backfill?.gatheredSinceActivation?.games || 0} ACL-complete files normalized`} tone="green" />
            <Metric label="Players" value={(backfill?.ledger?.players || 0).toLocaleString()} detail={`+${backfill?.gatheredSinceActivation?.players || 0} discovered`} tone="amber" />
            <Metric label="Venues" value={(backfill?.ledger?.venues || 0).toLocaleString()} detail={`${backfill?.ledger?.events || 0} event records`} tone="zinc" />
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {(['PREDICTION', 'ACL_CLASSIFIED'] as const).map(laneKey => {
              const lane = backfill?.lanes?.[laneKey] || {};
              return (
                <div key={laneKey} className="rounded-2xl border border-white/10 bg-black/25 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[10px] font-black uppercase tracking-widest text-sky-300">{lane.label || laneKey}</div>
                      <div className="mt-2 text-xl font-black text-white">{lane.paused ? 'Paused' : lane.status === 'WORKING' ? 'Collecting' : 'On'}</div>
                      <div className="mt-1 text-xs text-zinc-500">
                        {lane.queue?.pending || 0} pending · {lane.queue?.processing || 0} active · {lane.queue?.complete || 0} complete
                      </div>
                      {lane.current?.type && <div className="mt-2 text-xs font-bold text-zinc-400">Now checking {String(lane.current.type).toLowerCase()} {lane.current.key}</div>}
                      {lane.lastError && <div className="mt-2 text-xs text-red-300">{lane.lastError}</div>}
                    </div>
                    <button
                      type="button"
                      disabled={backfillChanging}
                      onClick={() => changeBackfill(lane.paused ? 'resume' : 'pause', laneKey)}
                      className={`flex min-h-11 shrink-0 items-center gap-2 rounded-xl border px-3 font-black active:scale-[.98] disabled:opacity-50 ${lane.paused ? 'border-emerald-300/40 text-emerald-200' : 'border-amber-300/40 text-amber-200'}`}
                    >
                      {lane.paused ? <Play size={16}/> : <Pause size={16}/>}
                      {lane.paused ? 'Resume' : 'Pause'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-4 rounded-2xl border border-sky-300/20 bg-sky-300/[.05] p-4">
            <div className="text-[10px] font-black uppercase tracking-widest text-sky-300">Actual collection throughput</div>
            <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
              <div><div className="text-2xl font-black text-white">{Number(hourlyThroughput.attempts || 0).toLocaleString()}</div><div className="text-xs text-zinc-500">tasks attempted · last hour</div></div>
              <div><div className="text-2xl font-black text-emerald-300">{Number(hourlyThroughput.productive || 0).toLocaleString()}</div><div className="text-xs text-zinc-500">productive tasks · last hour</div></div>
              <div><div className="text-2xl font-black text-sky-300">+{Number(hourlyThroughput.games_downloaded || 0).toLocaleString()}</div><div className="text-xs text-zinc-500">games · last hour</div></div>
              <div><div className="text-2xl font-black text-sky-300">+{Number(hourlyThroughput.rounds_added || 0).toLocaleString()}</div><div className="text-xs text-zinc-500">player rounds · last hour</div></div>
            </div>
            <div className="mt-3 border-t border-white/10 pt-3 text-xs text-zinc-500">
              Last 24 hours: {Number(dailyThroughput.completed || 0).toLocaleString()} completed · {Number(dailyThroughput.productive || 0).toLocaleString()} productive · {Number(dailyThroughput.failed_attempts || 0).toLocaleString()} failed attempts · {Number(dailyThroughput.terminal_failures || 0).toLocaleString()} terminal
            </div>
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <div className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Queue</div>
              <div className="mt-2 text-xl font-black text-white">{backfill?.queue?.pending || 0} pending</div>
              <div className="mt-1 text-xs text-zinc-500">
                {pendingByType.GAME || 0} games · {pendingByType.EVENT || 0} events · {pendingByType.PLAYER || 0} players
              </div>
              <div className="mt-1 text-xs text-zinc-600">{backfill?.queue?.complete || 0} tasks processed · {backfill?.queue?.failed || 0} terminal failures</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <div className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Engine output</div>
              <div className="mt-2 text-xl font-black text-white">{backfill?.session?.eventsDiscovered || 0} new events</div>
              <div className="mt-1 text-xs text-zinc-500">{backfill?.session?.gamesDownloaded || 0} games downloaded and normalized · {backfill?.session?.roundsAdded || 0} player-round rows added</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
              <div className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Access health</div>
              <div className="mt-2 text-xl font-black text-white">{backfill?.session?.authBlocked || 0} blocked files</div>
              <div className="mt-1 text-xs text-zinc-500">One request every {backfill?.pacing?.minimumSeconds || 20}–{backfill?.pacing?.maximumSeconds || 45} seconds · completed files are cached</div>
            </div>
          </div>

          <div className="mt-3 rounded-2xl border border-sky-300/15 bg-sky-300/[.05] p-4 text-xs leading-5 text-zinc-400">
            <span className="font-black text-sky-200">What “downloaded” means:</span>{' '}
            ACL marked the game complete, its match-stat file was retrieved, and its player rounds were normalized into the analytics ledger.
            Profile calculations and prediction-model evaluation are separate downstream operations and are not included in this count.
          </div>

          <div className="mt-3 rounded-2xl border border-emerald-300/20 bg-emerald-300/[.06] p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="text-[10px] font-black uppercase tracking-widest text-emerald-300">
                  Raw response archive
                </div>
                <div className="mt-2 text-lg font-black text-white">
                  {(backfill?.payloadArchive?.archivedPayloads || 0).toLocaleString()} verified
                  {' · '}
                  {(backfill?.payloadArchive?.pendingPayloads || 0).toLocaleString()} pending
                </div>
                <p className="mt-1 text-xs leading-5 text-zinc-400">
                  Complete ACL responses are compressed, hash-verified, and remain
                  available for recovery and future reprocessing.
                </p>
              </div>
              <div className={`self-start rounded-xl px-3 py-2 text-xs font-black uppercase tracking-wider ${
                backfill?.payloadArchive?.status === 'ATTENTION'
                  ? 'bg-red-300 text-black'
                  : 'bg-emerald-300 text-black'
              }`}>
                {backfill?.payloadArchive?.status || 'Starting'}
              </div>
            </div>
            {(backfill?.payloadArchive?.sourceBytesArchived || 0) > 0 && (
              <div className="mt-3 text-xs font-bold text-zinc-500">
                {(Number(backfill.payloadArchive.sourceBytesArchived) / 1048576).toFixed(1)} MB preserved
                {' · '}
                {(Number(backfill.payloadArchive.archiveBytes) / 1048576).toFixed(1)} MB compressed
                {' · '}
                {(Number(backfill.payloadArchive.spaceReductionRate || 0) * 100).toFixed(1)}% smaller
              </div>
            )}
          </div>

          <div className="mt-4 rounded-2xl border border-white/10 bg-black/20 p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-sky-300">
                  <MapPinned size={15} /> Geographic coverage
                </div>
                <div className="mt-2 text-xl font-black text-white">
                  {geography?.regionCount || 0} regions across {geography?.countryCount || 0} identified countries
                </div>
                <div className="mt-1 text-xs text-zinc-500">
                  Venue coverage from collected ACL event records. Country is marked unknown when ACL has not supplied enough location data.
                </div>
              </div>
              <button
                type="button"
                disabled={venueExporting}
                onClick={async () => {
                  setVenueExporting(true);
                  try {
                    await downloadHistoricalVenueCsv();
                  } catch (err: any) {
                    setError(err?.message || 'Venue export could not be downloaded.');
                  } finally {
                    setVenueExporting(false);
                  }
                }}
                className="flex min-h-12 shrink-0 items-center justify-center gap-2 rounded-xl border border-sky-300/30 bg-sky-300/10 px-4 py-3 font-black text-sky-200 transition hover:bg-sky-300/20 active:translate-y-1 disabled:opacity-50"
              >
                <Download size={17} />
                {venueExporting ? 'Preparing CSV…' : 'Export for Google My Maps'}
              </button>
            </div>

            <div className="mt-4 flex gap-2 overflow-x-auto pb-2">
              {(geography?.countries || []).map((country: any) => (
                <div
                  key={country.countryCode}
                  className="min-w-[135px] shrink-0 rounded-xl border border-white/10 bg-zinc-950 px-3 py-3"
                >
                  <div className="text-xs font-black uppercase tracking-wider text-zinc-400">
                    {country.countryCode === 'UNKNOWN' ? 'Unknown' : country.countryCode}
                  </div>
                  <div className="mt-1 text-xl font-black text-white">{Number(country.venues || 0).toLocaleString()}</div>
                  <div className="text-[11px] text-zinc-500">{Number(country.events || 0).toLocaleString()} events</div>
                </div>
              ))}
            </div>

            <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-10">
              {regions.slice(0, 60).map((region: any) => {
                const strength = Math.max(.12, Number(region.venues || 0) / maxRegionVenues);
                return (
                  <div
                    key={`${region.countryCode}:${region.region}`}
                    title={`${region.region}, ${region.countryCode}: ${region.venues} venues / ${region.events} events`}
                    className="rounded-xl border border-sky-300/20 p-2"
                    style={{ backgroundColor: `rgba(14, 165, 233, ${0.08 + strength * 0.42})` }}
                  >
                    <div className="truncate text-sm font-black text-white">{region.region}</div>
                    <div className="mt-1 text-[10px] font-bold text-sky-100">{region.venues} venues</div>
                    <div className="text-[9px] uppercase tracking-wider text-zinc-400">{region.countryCode}</div>
                  </div>
                );
              })}
            </div>

            {regions.length > 60 && (
              <details className="mt-3 rounded-xl border border-white/10 bg-zinc-950">
                <summary className="cursor-pointer p-3 text-sm font-black text-white">
                  Show all {regions.length} regions
                </summary>
                <div className="grid grid-cols-1 gap-1 border-t border-white/10 p-3 sm:grid-cols-2 lg:grid-cols-3">
                  {regions.map((region: any) => (
                    <div key={`all:${region.countryCode}:${region.region}`} className="flex justify-between gap-3 rounded-lg px-2 py-1 text-xs">
                      <span className="truncate text-zinc-300">{region.region}, {region.countryCode}</span>
                      <span className="shrink-0 font-black text-white">{region.venues} venues · {region.events} events</span>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>

          {backfill?.lastError && (
            <div className="mt-4 rounded-2xl border border-red-400/20 bg-red-950/30 p-3 text-xs text-red-200">
              Last collection error: {backfill.lastError}
            </div>
          )}
        </div>
      </div>

      <div className="rounded-[26px] border border-white/10 bg-zinc-950 p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="text-xs font-black uppercase tracking-[.22em] text-violet-300">Model learning</div>
            <h3 className="mt-2 text-2xl font-black text-white">Feedback and retraining readiness</h3>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-zinc-500">Historical matches fit and challenge the model with strict pre-event cutoffs. Forward-frozen predictions provide a separate real-world confirmation sample before weight changes are promoted.</p>
          </div>
          <div className={`rounded-xl px-4 py-2 text-xs font-black uppercase tracking-wider ${learning?.promotionGate?.eligibleForRetrainingReview ? 'bg-emerald-400/10 text-emerald-300' : 'bg-amber-300/10 text-amber-200'}`}>
            {learning?.promotionGate?.eligibleForRetrainingReview ? 'Ready for retraining review' : 'Collecting evidence'}
          </div>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Metric label="Historical eligible" value={Number(historicalBacktest.eligibleMatchups || 0).toLocaleString()} detail={`${Number(historicalBacktest.archiveMatchups || 0).toLocaleString()} resolved archive matchups`} tone="blue" />
          <Metric label="Development examples" value={Number(historicalBacktest.developmentMatchups || 0).toLocaleString()} detail="Used to fit candidate models" tone="blue" />
          <Metric label="Validation examples" value={Number(historicalBacktest.validationMatchups || 0).toLocaleString()} detail="Used to compare candidates" tone="blue" />
          <Metric label="Historical holdout" value={Number(historicalBacktest.holdoutMatchups || 0).toLocaleString()} detail="Untouched final historical test" tone="green" />
          <Metric label="Prospective confirmations" value={Number(learning.learningExamples || 0).toLocaleString()} detail="Forward-frozen and resolved" tone="green" />
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Metric label="Correct predictions" value={learning.correctPredictions || 0} detail={pct(learning.learningExamples ? learning.correctPredictions / learning.learningExamples : null)} tone="green" />
          <Metric label="Model misses" value={learning.incorrectPredictions || 0} detail={`${pct(learning.missRate)} miss rate`} tone="amber" />
          <Metric label="Prospective until review gate" value={learning?.promotionGate?.remaining ?? '—'} detail={`${learning?.promotionGate?.minimumCommonResolvedMatches || 500} live confirmations required`} tone="zinc" />
        </div>
        <div className="mt-4 overflow-hidden rounded-2xl border border-white/10">
          <div className="border-b border-white/10 bg-white/[.03] px-4 py-3 font-black text-white">Post-match findings</div>
          <div className="grid gap-px bg-white/10 sm:grid-cols-2 lg:grid-cols-3">
            {(learning.reasonDistribution || []).map((row: any) => (
              <div key={row.reason} className="bg-zinc-950 p-4">
                <div className="text-2xl font-black text-white">{row.predictions}</div>
                <div className="mt-1 text-xs font-bold uppercase tracking-wider text-zinc-500">{String(row.reason).replaceAll('_', ' ')}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-4 rounded-2xl border border-violet-300/15 bg-violet-300/[.04] p-4">
          <div className="font-black text-violet-200">Promotion requirements</div>
          <div className="mt-2 grid gap-2 text-sm text-zinc-400 sm:grid-cols-2 lg:grid-cols-4">
            <div>✓ 500 common resolved matches</div><div>✓ Better winner accuracy</div><div>✓ Better Brier and log loss</div><div>✓ Stable across time periods</div>
          </div>
          <div className="mt-3 text-xs leading-5 text-zinc-500">{learning.learningPolicy} Historical development, validation, and holdout samples remain separate from this prospective promotion gate.</div>
        </div>
      </div>

      <div className="rounded-[26px] border border-white/10 bg-zinc-950 p-5">
        <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="text-xs font-black uppercase tracking-[.22em] text-violet-300">Prediction performance</div>
            <h3 className="mt-2 text-2xl font-black text-white">Matches and tournaments</h3>
            <p className="mt-1 text-sm leading-6 text-zinc-500">
              Scores only frozen forecasts with known final results. Tournament accuracy is separated by field size because picking one champion from 64 teams is fundamentally different from picking one from eight.
            </p>
          </div>
        </div>

        <div className="mt-5 overflow-hidden rounded-2xl border border-sky-400/20 bg-sky-400/[.04]">
          <div className="border-b border-sky-400/15 p-4">
            <div className="text-xs font-black uppercase tracking-[.2em] text-sky-300">Historical chronological backtest</div>
            <div className="mt-1 text-sm leading-6 text-zinc-400">
              Uses only player rounds dated before each matchup. The middle 20% of event dates validates challengers and the newest 20% is reserved as the final out-of-time test.
            </div>
          </div>
          <div className="grid gap-px bg-white/10 sm:grid-cols-2 lg:grid-cols-4">
            <div className="bg-zinc-950 p-4"><div className="text-2xl font-black text-white">{historicalBacktest.archiveMatchups || 0}</div><div className="text-xs font-bold uppercase tracking-wider text-zinc-500">Resolved archive matchups</div></div>
            <div className="bg-zinc-950 p-4"><div className="text-2xl font-black text-white">{historicalBacktest.eligibleMatchups || 0}</div><div className="text-xs font-bold uppercase tracking-wider text-zinc-500">Cutoff-safe matchups</div></div>
            <div className="bg-zinc-950 p-4"><div className="text-2xl font-black text-white">{historicalBacktest.holdoutMatchups || 0}</div><div className="text-xs font-bold uppercase tracking-wider text-zinc-500">Held-out matchups</div></div>
            <div className="bg-zinc-950 p-4"><div className="text-2xl font-black text-white">{historicalBacktest.holdoutStartDate || '—'}</div><div className="text-xs font-bold uppercase tracking-wider text-zinc-500">Holdout begins</div></div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[650px] text-sm">
              <thead className="text-left text-[10px] font-black uppercase tracking-wider text-zinc-500">
                <tr><th className="p-4">Model</th><th>Validation</th><th>Final accuracy</th><th>Paired vs PPR</th><th>Brier</th><th>Log loss</th><th>Coverage</th></tr>
              </thead>
              <tbody>
                {(historicalBacktest.models || []).map((row: any) => (
                  <tr key={row.model} className="border-t border-white/10">
                    <td className="p-4 font-black text-white">{row.model}</td>
                    <td>{pct(row.validationMetrics?.accuracy)}</td>
                    <td className="font-black text-emerald-300">{pct(row.accuracy)}</td>
                    <td className="min-w-[220px] py-3 pr-4 text-xs text-zinc-400">
                      {row.pairedVsPpr?.finalTest ? (() => {
                        const comparison = row.pairedVsPpr.finalTest;
                        const net = Number(comparison.netAdditionalCorrect || 0);
                        const pValue = Number(comparison.mcnemarPValueApprox);
                        return (
                          <div className="space-y-1">
                            <div className={`font-black ${net > 0 ? 'text-emerald-300' : net < 0 ? 'text-red-300' : 'text-zinc-300'}`}>
                              {net >= 0 ? '+' : ''}{net} net correct
                            </div>
                            <div>{Number(comparison.disagreements || 0).toLocaleString()} changed decisions</div>
                            <div className="text-[11px] text-zinc-500">
                              Challenger won {Number(comparison.challengerOnlyCorrect || 0).toLocaleString()} · PPR won {Number(comparison.pprOnlyCorrect || 0).toLocaleString()}
                            </div>
                            <div className={`text-[11px] font-bold ${comparison.statisticallyClearAt95 ? 'text-emerald-300' : 'text-amber-200'}`}>
                              p {pValue.toFixed(3)} · {comparison.statisticallyClearAt95 ? 'clear at 95%' : 'not yet conclusive'}
                            </div>
                          </div>
                        );
                      })() : <span className="font-bold text-zinc-500">PPR baseline</span>}
                    </td>
                    <td>{row.brierScore == null ? '—' : Number(row.brierScore).toFixed(3)}</td>
                    <td>{row.logLoss == null ? '—' : Number(row.logLoss).toFixed(3)}</td>
                    <td>{pct(row.coverageRate)} · {row.evaluatedMatchups || 0}</td>
                  </tr>
                ))}
                {(historicalBacktest.models || []).length === 0 && (
                  <tr><td colSpan={7} className="p-6 text-center text-zinc-500">Historical backtest has not been generated yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="border-t border-white/10 px-4 py-3 text-xs text-zinc-500">
            365-day lookback · strict prior-date cutoff · generated {historicalBacktest.generatedAt ? new Date(historicalBacktest.generatedAt).toLocaleString() : 'not yet'}
            {historicalBacktest.cacheStatus === 'NEW_DATA_AVAILABLE' && <span className="ml-2 font-black text-amber-300">New archive data awaits the next backtest refresh.</span>}
            {historicalBacktest.refreshState && (
              <div className={`mt-3 rounded-xl border p-3 ${historicalBacktest.refreshState.due ? 'border-amber-300/30 bg-amber-300/10 text-amber-100' : 'border-white/10 bg-white/[.03] text-zinc-400'}`}>
                Automatic refresh: {historicalBacktest.refreshState.due ? 'queued now' : 'watching for meaningful growth'} · +{Number(historicalBacktest.refreshState.gameDelta || 0).toLocaleString()} games / +{Number(historicalBacktest.refreshState.roundDelta || 0).toLocaleString()} rounds since the saved evaluation.
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Metric label="Historical match accuracy" value={pct(historicalMatchPerformance?.accuracy)} detail={`${Number(historicalMatchPerformance?.resolvedMatches || 0).toLocaleString()} cutoff-safe holdout matches`} tone="green" />
          <Metric label="Forward frozen accuracy" value={pct(matchPerformance?.overall?.accuracy)} detail={`${Number(matchPerformance?.overall?.resolvedMatches || 0).toLocaleString()} live predictions resolved`} tone="green" />
          <Metric label="Tournament favorite won" value={pct(tournamentOverall?.favoriteAccuracy)} detail={`${tournamentOverall?.resolvedTournaments || 0} resolved tournaments`} tone="amber" />
          <Metric label="Champion in top 3" value={pct(tournamentOverall?.topThreeHitRate)} detail="Pregame forecast ranking" tone="blue" />
          <Metric label="Average champion rank" value={tournamentOverall?.averageChampionRank ?? '—'} detail={`Average field ${tournamentOverall?.averageFieldSize ?? '—'} teams`} tone="zinc" />
        </div>
        <div className="mt-3 rounded-2xl border border-sky-400/20 bg-sky-400/[.045] p-4">
          <div className="text-xs font-black uppercase tracking-[.18em] text-sky-300">Historical tournament replay</div>
          <div className="mt-2 grid gap-3 sm:grid-cols-4">
            <MiniMetric label="Reconstructed forecasts" value={tournamentReplay?.historicalReplaySnapshots || 0} />
            <MiniMetric label="Live frozen forecasts" value={tournamentReplay?.liveFrozenSnapshots || 0} />
            <MiniMetric label="Remaining candidates" value={tournamentReplay?.candidatesRemaining || 0} />
            <MiniMetric label="Replay engine" value={tournamentReplay?.status || 'NOT STARTED'} />
          </div>
          <p className="mt-3 text-xs leading-5 text-zinc-500">Historical forecasts use the original roster and only player evidence dated before that event. Results are joined only after the forecast has been saved.</p>
        </div>
        <div className={`mt-3 rounded-2xl border p-3 text-sm ${
          tournamentOverall?.sampleStatus === 'ESTABLISHED'
            ? 'border-emerald-400/25 bg-emerald-400/[.06] text-emerald-200'
            : 'border-amber-300/25 bg-amber-300/[.06] text-amber-100'
        }`}>
          {sampleMessage(tournamentOverall?.sampleStatus, tournamentOverall?.resolvedTournaments || 0)}
          {tournamentOverall?.favoriteAccuracy95 && (
            <> Favorite accuracy 95% interval: {pct(tournamentOverall.favoriteAccuracy95.low)}–{pct(tournamentOverall.favoriteAccuracy95.high)}.</>
          )}
        </div>

        <div className="mt-5 overflow-hidden rounded-2xl border border-white/10">
          <div className="border-b border-white/10 bg-white/[.03] px-4 py-3">
            <div className="font-black text-white">Impact of bracket size</div>
            <div className="mt-1 text-xs text-zinc-500">Use sample size and probability-quality scores alongside favorite accuracy.</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="text-left text-[10px] font-black uppercase tracking-wider text-zinc-500">
                <tr>
                  <th className="p-4">Field</th><th>Tournaments</th><th>Favorite won</th>
                  <th>Top-three hit</th><th>Champion rank</th><th>Brier skill</th><th>Sample</th>
                </tr>
              </thead>
              <tbody>
                {(tournamentPerformance?.byBracketSize || []).map((row: any) => (
                  <tr key={row.group} className="border-t border-white/10">
                    <td className="p-4 font-black text-white">{row.group}</td>
                    <td>{row.resolvedTournaments}</td>
                    <td className="font-black text-amber-300">{pct(row.favoriteAccuracy)}</td>
                    <td className="font-black text-sky-300">{pct(row.topThreeHitRate)}</td>
                    <td>{row.averageChampionRank ?? '—'}</td>
                    <td className={Number(row.brierSkillVsEqual || 0) > 0 ? 'font-black text-emerald-300' : 'font-black text-red-300'}>{pct(row.brierSkillVsEqual)}</td>
                    <td className="text-xs font-bold text-zinc-400">{sampleLabel(row.sampleStatus)}</td>
                  </tr>
                ))}
                {(tournamentPerformance?.byBracketSize || []).length === 0 && (
                  <tr><td colSpan={7} className="p-6 text-center text-zinc-500">Waiting for a frozen tournament forecast to receive a final champion.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <PerformanceBreakdown title="Match accuracy by confidence" rows={matchPerformance?.byConfidence || []} />
          <PerformanceBreakdown title="Match accuracy by final margin" rows={matchPerformance?.byActualMargin || []} />
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
            <div className="font-black text-white">Tournament probability calibration</div>
            <div className="mt-1 text-xs leading-5 text-zinc-500">If 20% predictions win approximately 20% of the time, the probabilities are calibrated.</div>
            <div className="mt-3 space-y-2">
              {(tournamentPerformance?.calibration || []).map((row: any) => (
                <div key={row.group} className="rounded-xl bg-white/[.03] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-black text-white">{row.group} forecast</div>
                    <div className="text-xs text-zinc-500">{row.teams} teams · {sampleLabel(row.sampleStatus)}</div>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
                    <div>Predicted <span className="font-black text-sky-300">{pct(row.averagePredictedProbability)}</span></div>
                    <div>Actually won <span className="font-black text-emerald-300">{pct(row.actualChampionshipRate)}</span></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
            <div className="font-black text-white">Tournament model comparison</div>
            <div className="mt-1 text-xs leading-5 text-zinc-500">Lower Brier and log loss are better. Positive skill means improvement over equal odds.</div>
            <div className="mt-3 space-y-2">
              {(tournamentPerformance?.modelComparison || []).map((row: any) => (
                <div key={row.model} className="rounded-xl bg-white/[.03] p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="font-black text-white">{row.model}</div>
                    <div className="text-[10px] font-black uppercase tracking-wider text-zinc-500">{row.status.replaceAll('_', ' ')}</div>
                  </div>
                  <div className="mt-2 text-xs text-zinc-400">
                    {row.multiclassBrierScore == null ? row.reason : <>Brier {Number(row.multiclassBrierScore).toFixed(3)} · Log loss {Number(row.championLogLoss).toFixed(3)}{row.brierSkillVsEqual != null && <> · Skill {pct(row.brierSkillVsEqual)}</>}</>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <details className="mt-5 rounded-2xl border border-white/10 bg-black/30">
          <summary className="cursor-pointer list-none p-4 font-black text-white">Resolved tournament details</summary>
          <div className="space-y-2 border-t border-white/10 p-4">
            {(tournamentPerformance?.events || []).map((event: any) => (
              <div key={event.eventId} className="rounded-xl bg-white/[.03] p-3">
                <div className="text-[10px] font-black uppercase tracking-widest text-zinc-600">
                  Event {event.eventId} · {event.teamCount} teams · frozen {new Date(event.frozenAt).toLocaleString()}
                </div>
                <div className="mt-1 font-black text-white">{event.eventName}</div>
                <div className="mt-2 text-xs leading-5 text-zinc-400">
                  Favorite: <span className="text-amber-200">{event.favoriteName} ({pct(event.favoriteProbability)})</span>
                  {' · '}Champion: <span className="text-emerald-200">{event.championName}</span>
                  {' · '}Predicted rank {event.championPredictedRank} at {pct(event.championProbability)}
                </div>
              </div>
            ))}
          </div>
        </details>
      </div>

      <div className="rounded-[26px] border border-white/10 bg-zinc-950 p-5">
        <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="text-xs font-black uppercase tracking-[.22em] text-sky-300">Prospective model test</div>
            <h3 className="mt-2 text-2xl font-black text-white">Baseline vs advanced challenger</h3>
            <p className="mt-1 text-sm text-zinc-500">Both predictions are frozen before play and scored only on matches where both models produced a probability.</p>
          </div>
          <div className="text-sm font-black text-zinc-300">{commonSample.resolvedPredictions || 0} common resolved matches</div>
        </div>
        {(commonSample.resolvedPredictions || 0) === 0 ? (
          <div className="mt-4 rounded-2xl border border-dashed border-white/10 p-6 text-center text-sm text-zinc-500">
            Collecting new pregame predictions. Existing completed matches are not backfilled into this prospective test.
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[680px] text-sm">
              <thead className="text-left text-[10px] font-black uppercase tracking-wider text-zinc-500">
                <tr><th className="pb-2">Model</th><th>Accuracy</th><th>Brier</th><th>Log loss</th><th>Status</th></tr>
              </thead>
              <tbody>
                {[
                  ['PPR baseline', baselineModel, 'fitted-ppr-logistic-v1'],
                  ['Advanced primary · prospective', challengerModel, shadow?.challengerModelVersion || 'ppr-round-loss-recent-form-v1'],
                ].map(([label, metrics, version]: any) => (
                  <tr key={version} className="border-t border-white/10">
                    <td className="py-4"><div className="font-black text-white">{label}</div><div className="text-[10px] text-zinc-600">{version}</div></td>
                    <td className="font-black text-white">{pct(metrics.accuracy)}</td>
                    <td className="font-black text-sky-300">{metrics.brierScore == null ? '—' : Number(metrics.brierScore).toFixed(4)}</td>
                    <td>{metrics.logLoss == null ? '—' : Number(metrics.logLoss).toFixed(4)}</td>
                    <td className={commonSample.leader === version ? 'font-black text-emerald-300' : 'text-zinc-500'}>
                      {commonSample.leader === version ? 'Leading on Brier' : 'Shadow'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-3 text-xs leading-5 text-zinc-500">Lower Brier score and log loss are better. No challenger is promoted from accuracy alone.</div>
        <details className="mt-4 rounded-2xl border border-white/10 bg-black/30">
          <summary className="cursor-pointer list-none p-4 font-black text-white">
            What currently influences the challenger?
          </summary>
          <div className="grid gap-4 border-t border-white/10 p-4 lg:grid-cols-2">
            <div>
              <div className="text-[10px] font-black uppercase tracking-widest text-emerald-300">Nonzero weight</div>
              <div className="mt-2 space-y-2">
                {(shadow?.challengerFactorPolicy?.weighted || []).map((factor: any) => (
                  <div key={factor.factor} className="rounded-xl bg-emerald-400/[.06] p-3">
                    <div className="text-sm font-black text-white">{factor.factor}</div>
                    <div className="mt-1 text-xs leading-5 text-zinc-500">{factor.reason}</div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="text-[10px] font-black uppercase tracking-widest text-amber-300">Profile rating · currently zero weight</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {(shadow?.challengerFactorPolicy?.shadowOnlyZeroWeight || []).map((factor: any) => (
                  <span key={factor.factor} title={factor.status} className="rounded-xl border border-white/10 bg-white/[.04] px-3 py-2 text-xs font-bold text-zinc-300">
                    {factor.factor}
                  </span>
                ))}
              </div>
              {(shadow?.challengerFactorPolicy?.validatedAlternatives || []).map((factor: any) => (
                <div key={factor.factor} className="mt-3 rounded-xl border border-sky-400/20 bg-sky-400/[.06] p-3">
                  <div className="text-sm font-black text-sky-200">{factor.factor}: validated separately</div>
                  <div className="mt-1 text-xs leading-5 text-zinc-500">{factor.reason}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="border-t border-white/10 px-4 py-3 text-xs leading-5 text-zinc-500">
            {shadow?.challengerFactorPolicy?.promotionRule}
          </div>
          {shadow?.challengerFactorPolicy?.historicalSpecialtyTests?.swingPerformance && (
            <div className="border-t border-white/10 p-4">
              <div className="text-[10px] font-black uppercase tracking-widest text-violet-300">Historical swing test</div>
              <div className="mt-2 text-sm font-black text-white">
                {shadow.challengerFactorPolicy.historicalSpecialtyTests.swingPerformance.rollingTestMatchups} rolling-origin matchups · no swing parameter promoted
              </div>
              <div className="mt-1 text-xs leading-5 text-zinc-500">
                {shadow.challengerFactorPolicy.historicalSpecialtyTests.swingPerformance.decision}
              </div>
            </div>
          )}
        </details>
      </div>

      <div className="rounded-[26px] border border-white/10 bg-zinc-950 p-5">
        <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="text-xs font-black uppercase tracking-[.22em] text-emerald-300">Prediction learning loop</div>
            <h3 className="mt-2 text-2xl font-black text-white">Prediction vs actual</h3>
            <p className="mt-1 text-sm text-zinc-500">
              Frozen forecasts compared with final ACL scores. Explanations describe the recorded evidence; they do not claim certainty about why a team won.
            </p>
          </div>
          <div className="text-sm font-black text-zinc-300">{evaluations.length} resolved predictions shown</div>
        </div>
        <div className="mt-4 space-y-3">
          {evaluations.length === 0 && (
            <div className="rounded-2xl border border-dashed border-white/10 p-6 text-center text-sm text-zinc-500">
              Waiting for a frozen pre-match prediction to receive its completed ACL result.
            </div>
          )}
          {evaluations.map((item: any) => {
            const predictedA = item.predictedWinner === 'SIDE_A';
            const actualA = item.actualWinner === 'SIDE_A';
            const predictedPlayers = predictedA ? item.sideAPlayerIds : item.sideBPlayerIds;
            const actualPlayers = actualA ? item.sideAPlayerIds : item.sideBPlayerIds;
            return (
              <details key={item.shadowRunId} className="group rounded-2xl border border-white/10 bg-white/[.03]">
                <summary className="grid cursor-pointer list-none gap-4 p-4 md:grid-cols-[1.3fr_.8fr_auto] md:items-center">
                  <div>
                    <div className="text-[10px] font-black uppercase tracking-widest text-zinc-500">
                      Event {item.eventId} · Match {item.matchId} · Evidence {item.evidenceTier}
                    </div>
                    <div className="mt-2 font-black text-white">
                      Final: Side A {item.homeScore}–{item.awayScore} Side B
                    </div>
                    <div className="mt-1 text-xs text-zinc-500">
                      Predicted {predictedA ? 'Side A' : 'Side B'} ({(Math.max(item.sideAProbability, item.sideBProbability) * 100).toFixed(1)}%) · Actual {actualA ? 'Side A' : 'Side B'}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-center">
                    <div className="rounded-xl bg-black/30 p-2">
                      <div className="text-[9px] font-black uppercase tracking-wider text-zinc-600">Brier</div>
                      <div className="mt-1 font-black text-sky-300">{Number(item.brierScore).toFixed(3)}</div>
                    </div>
                    <div className="rounded-xl bg-black/30 p-2">
                      <div className="text-[9px] font-black uppercase tracking-wider text-zinc-600">Winner probability</div>
                      <div className="mt-1 font-black text-white">{(item.winnerProbability * 100).toFixed(1)}%</div>
                    </div>
                  </div>
                  <div className={`rounded-xl px-4 py-2 text-center text-xs font-black ${item.correct ? 'bg-emerald-400/10 text-emerald-300' : 'bg-red-400/10 text-red-300'}`}>
                    {item.correct ? 'Correct' : 'Model miss'}
                  </div>
                </summary>
                <div className="border-t border-white/10 p-4">
                  <div className="grid gap-3 md:grid-cols-2">
                    <div className="rounded-xl bg-black/30 p-4">
                      <div className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Frozen prediction</div>
                      <div className="mt-2 text-sm font-bold text-white">
                        {predictedA ? 'Side A' : 'Side B'} · Players {(predictedPlayers || []).join(' / ') || 'unavailable'}
                      </div>
                      <div className="mt-2 text-xs leading-5 text-zinc-500">
                        Recorded {item.recordedAt} · {item.timingBasis}
                      </div>
                    </div>
                    <div className="rounded-xl bg-black/30 p-4">
                      <div className="text-[10px] font-black uppercase tracking-widest text-zinc-500">Actual winner</div>
                      <div className="mt-2 text-sm font-bold text-white">
                        {actualA ? 'Side A' : 'Side B'} · Players {(actualPlayers || []).join(' / ') || 'unavailable'}
                      </div>
                      <div className="mt-2 text-xs text-zinc-500">Won by {item.actualMargin} points</div>
                    </div>
                  </div>
                  <div className="mt-3 rounded-xl border border-amber-300/15 bg-amber-300/[.05] p-4">
                    <div className="font-black text-amber-200">{item.explanation?.headline}</div>
                    <div className="mt-1 text-sm leading-6 text-zinc-300">{item.explanation?.detail}</div>
                    <div className="mt-2 text-[11px] leading-5 text-zinc-600">{item.explanation?.caveat}</div>
                  </div>
                  {item.postmortem && (
                    <div className="mt-3 rounded-xl border border-violet-300/20 bg-violet-300/[.05] p-4">
                      <div className="text-[10px] font-black uppercase tracking-widest text-violet-300">Post-match learning review</div>
                      <div className="mt-2 font-black text-white">{String(item.postmortem.primaryReason || '').replaceAll('_', ' ')}</div>
                      <div className="mt-3 space-y-2">
                        {(item.postmortem.reasons || []).map((reason: any) => (
                          <div key={`${reason.code}-${reason.detail}`} className="rounded-lg bg-black/25 p-3 text-sm leading-5 text-zinc-300">
                            <span className="font-black text-violet-200">{String(reason.code).replaceAll('_', ' ')}</span> · {reason.detail}
                          </div>
                        ))}
                      </div>
                      <div className="mt-3 grid gap-2 sm:grid-cols-2">
                        {(['sideA', 'sideB'] as const).map((side) => {
                          const actual = item.postmortem.actualPerformance?.[side] || {};
                          return (
                            <div key={side} className="rounded-lg bg-black/25 p-3 text-xs text-zinc-400">
                              <div className="font-black uppercase tracking-wider text-white">{side === 'sideA' ? 'Side A actual' : 'Side B actual'}</div>
                              <div className="mt-1">PPR {actual.ppr ?? '—'} · Round loss {actual.roundLossRate == null ? '—' : pct(actual.roundLossRate)} · Large swings conceded {actual.largeSwingsConceded ?? '—'}</div>
                            </div>
                          );
                        })}
                      </div>
                      <div className="mt-3 text-[11px] text-zinc-500">Saved to the chronological candidate training pool. It cannot change production weights until batch retraining passes validation and a later holdout.</div>
                    </div>
                  )}
                </div>
              </details>
            );
          })}
        </div>
      </div>

      <div className="rounded-[26px] border border-white/10 bg-zinc-950 p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-xl font-black text-white">Latest predictions</h3>
            <p className="mt-1 text-sm text-zinc-500">Predictions are locked before play and scored against the final ACL result.</p>
          </div>
          <span className="rounded-full bg-white/5 px-3 py-1 text-xs font-bold text-zinc-400">{displayedPredictions.length} shown</span>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2">
          {[
            ['PREDICTED', 'Predictions'],
            ['ABSTAINED', 'Abstained'],
            ['ALL', 'All'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setPredictionFilter(value as 'PREDICTED' | 'ALL' | 'ABSTAINED')}
              className={`min-h-12 rounded-xl border px-3 text-sm font-black transition active:translate-y-1 ${
                predictionFilter === value
                  ? 'border-amber-300 bg-amber-300 text-black'
                  : 'border-white/10 bg-zinc-900 text-zinc-300'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="mt-4 space-y-3">
          {displayedPredictions.length === 0 && (
            <div className="rounded-2xl border border-dashed border-white/10 p-6 text-center text-sm text-zinc-500">
              {predictionFilter === 'PREDICTED'
                ? 'No issued predictions in this list. Abstentions are hidden by default.'
                : 'No prediction records match this filter.'}
            </div>
          )}
          {displayedPredictions.map((row: any) => {
            const pick = predictionLabel(row);
            const abstained = !pick;
            const resolved = row.side_a_won !== null && row.side_a_won !== undefined;
            const wasCorrect = Boolean(pick) && resolved && ((Boolean(row.side_a_won) && pick!.winner === 'Side A') || (!Boolean(row.side_a_won) && pick!.winner === 'Side B'));
            const playerIds = [...parsePlayerIds(row.side_a_player_ids_json), ...parsePlayerIds(row.side_b_player_ids_json)];
            return (
              <div key={row.shadow_run_id} className="grid gap-4 rounded-2xl border border-white/10 bg-white/[.03] p-4 md:grid-cols-[1fr_1fr_auto] md:items-center">
                <div>
                  <div className="text-xs font-black uppercase tracking-widest text-zinc-500">{row.event_name || `Event ${row.event_id}`} · Match {row.match_id}</div>
                  <div className="mt-2 text-lg font-black text-white">{abstained ? 'No prediction issued' : `${pick!.winner} to win`}</div>
                  <div className="mt-1 text-xs text-zinc-500">Scheduled {row.scheduled_start_at || 'time unavailable'}</div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {playerIds.map(id => (
                      <a key={id} href={`/?view=profile&playerId=${id}`} className="rounded-full bg-white/5 px-2 py-1 text-[10px] font-bold text-sky-300 hover:bg-sky-400/10">{row.player_names?.[String(id)] || `Player ${id}`}</a>
                    ))}
                  </div>
                </div>
                <div>
                  {abstained ? (
                    <div className="rounded-xl border border-amber-300/15 bg-amber-300/[.04] p-3">
                      <div className="text-xs font-black uppercase tracking-wider text-amber-200">Engine abstained</div>
                      <div className="mt-1 text-xs leading-5 text-zinc-400">{row.abstention_reason || 'Insufficient pregame evidence to make a defensible prediction.'}</div>
                    </div>
                  ) : (
                    <>
                      <div className="flex justify-between text-xs font-bold text-zinc-400">
                        <span>Side A {pct(row.side_a_probability)}</span>
                        <span>Side B {pct(row.side_b_probability)}</span>
                      </div>
                      <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-sky-400">
                        <div className="h-full bg-amber-300" style={{ width: `${Number(row.side_a_probability || 0) * 100}%` }} />
                      </div>
                      <div className="mt-2 text-xs font-bold text-amber-200">{confidenceLabel(pick!.probability)} · {pct(pick!.probability)}</div>
                    </>
                  )}
                  {row.challenger_status === 'PREDICTED' && (
                    <div className="mt-1 text-xs font-bold text-violet-300">
                      Challenger Side A {pct(row.challenger_side_a_probability)} · frozen pregame
                    </div>
                  )}
                  {row.challenger_status === 'ABSTAINED' && (
                    <div className="mt-1 text-xs text-zinc-600">Challenger abstained</div>
                  )}
                  {row.candidate_snapshot_version && (
                    <div className="mt-2 text-xs font-bold text-emerald-300">
                      Candidate profile snapshot {pct(row.candidate_snapshot_completeness)}
                      <span className="font-normal text-zinc-600">
                        {' '}· {row.candidate_available_factors}/{row.candidate_expected_factors} cutoff-safe factors
                      </span>
                    </div>
                  )}
                </div>
                <div className={`rounded-full px-3 py-1.5 text-center text-xs font-black ${
                  abstained ? 'bg-amber-400/10 text-amber-200' :
                  !resolved ? 'bg-sky-400/10 text-sky-300' :
                  wasCorrect ? 'bg-emerald-400/10 text-emerald-300' : 'bg-red-400/10 text-red-300'
                }`}>
                  {abstained ? 'Abstained' : !resolved ? 'Awaiting result' : wasCorrect ? 'Correct' : 'Incorrect'}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="pt-2 text-xs font-black uppercase tracking-[.22em] text-zinc-500">Engine status</div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="Events found" value={data?.discoveredEvents?.total || 0} detail="Current discovery index" tone="blue" />
        <Metric label="Monitored" value={(data?.monitoredEvents || []).filter((event: any) => Number(event.enabled) === 1).length} detail="Events actively polled" tone="amber" />
        <Metric label="History ready" value={`${complete}/${queued}`} detail="Queued players meeting threshold" tone="green" />
        <Metric label="Shadow coverage" value={pct(shadow.coverageRate)} detail={`${shadow.predictedRuns || 0} predictions recorded`} tone="zinc" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]">
        <div className="rounded-[26px] border border-white/10 bg-zinc-950 p-5">
          <div className="flex items-center gap-2">
            <Activity size={18} className="text-emerald-300" />
            <div>
              <h3 className="font-black text-white">Monitoring and tracking</h3>
              <p className="mt-1 text-xs text-zinc-500">Active polling plus recently archived tournament records.</p>
            </div>
            <div className="ml-auto flex flex-wrap justify-end gap-2">
              <select
                value={eventActivityFilter}
                onChange={event => setEventActivityFilter(event.target.value as any)}
                className="rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-xs font-bold text-white"
              >
                <option value="RECORDED">Events with activity</option>
                <option value="NO_ACTIVITY">No activity recorded</option>
                <option value="ALL">All scheduled events</option>
              </select>
              <select
                value={eventGroupFilter}
                onChange={event => setEventGroupFilter(event.target.value as any)}
                className="rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-xs font-bold text-white"
              >
                <option value="ALL">All event groups</option>
                <option value="SIT_AND_GO">Sit &amp; Go</option>
                <option value="STANDARD">Standard events</option>
              </select>
            </div>
          </div>
          <div className="mt-4 space-y-2">
            {(data?.monitoredEvents || []).length === 0 && (
              <div className="rounded-2xl border border-dashed border-white/10 p-5 text-sm text-zinc-500">
                No events have a verified format and timezone yet. Discovery results remain available for review.
              </div>
            )}
            {monitoredEvents.map((event: any) => (
              <a href={`/?event_id=${event.event_id}`} key={event.event_id} className="grid gap-2 rounded-2xl border border-white/10 bg-white/[.03] p-4 transition hover:border-amber-300/30 hover:bg-white/[.06] md:grid-cols-[1fr_auto]">
                <div>
                  <div className="font-black text-white">{event.event_name || `Event ${event.event_id}`}</div>
                  <div className="mt-1 text-xs text-zinc-500">
                    {event.event_date || 'Date unknown'} · {event.advertised_time || 'Time unknown'} · {event.location_city || 'Location unknown'}
                  </div>
                </div>
                <div className="flex items-center gap-2 text-xs font-bold">
                  {event.priority_label === 'ACL_WORLDS' && (
                    <span className="rounded-full bg-amber-300/15 px-2.5 py-1 text-amber-200">ACL WORLDS</span>
                  )}
                  {event.event_group === 'SIT_AND_GO' && (
                    <span className="rounded-full bg-violet-400/15 px-2.5 py-1 text-violet-200">SIT &amp; GO</span>
                  )}
                  <span className="rounded-full bg-sky-400/10 px-2.5 py-1 text-sky-300">{event.schedule_format}</span>
                  <span className={`rounded-full px-2.5 py-1 ${
                    event.tracking_status === 'NO_ACTIVITY'
                      ? 'bg-amber-400/10 text-amber-200'
                      : event.tracking_status === 'ACTIVE'
                      ? 'bg-emerald-400/10 text-emerald-300'
                      : event.last_poll_status === 'ERROR'
                        ? 'bg-red-400/10 text-red-300'
                        : 'bg-zinc-400/10 text-zinc-300'
                  }`}>
                    {event.tracking_status === 'ACTIVE'
                      ? (event.last_poll_status || 'WAITING')
                      : event.tracking_status === 'NO_ACTIVITY'
                        ? 'NO ACTIVITY RECORDED'
                        : (event.tracking_status || event.last_poll_status || 'ARCHIVED')}
                  </span>
                </div>
              </a>
            ))}
            <div className="mt-4 grid gap-2 rounded-2xl border border-white/10 bg-black/30 p-4 md:grid-cols-[1fr_130px_1fr_auto]">
              <input
                value={eventId}
                onChange={event => setEventId(event.target.value)}
                placeholder="ACL event ID"
                inputMode="numeric"
                className="rounded-xl border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none focus:border-amber-300/60"
              />
              <select
                value={eventFormat}
                onChange={event => setEventFormat(event.target.value as any)}
                className="rounded-xl border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white"
              >
                <option value="SWAP">Swap</option>
                <option value="SWISS">Swiss</option>
                <option value="BRACKET">Bracket</option>
              </select>
              <input
                value={eventTimezone}
                onChange={event => setEventTimezone(event.target.value)}
                placeholder="Verified timezone"
                className="rounded-xl border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none focus:border-amber-300/60"
              />
              <button
                type="button"
                onClick={addMonitor}
                disabled={running}
                className="rounded-xl border border-amber-300/30 bg-amber-300/10 px-4 py-2 text-sm font-black text-amber-200 hover:bg-amber-300/20 disabled:opacity-50"
              >
                Monitor
              </button>
            </div>
            <p className="text-[11px] leading-5 text-zinc-500">
              Timezone must be a verified IANA value such as America/New_York. The system does not infer it from an address.
            </p>
          </div>
        </div>

        <div className="rounded-[26px] border border-white/10 bg-zinc-950 p-5">
          <div className="flex items-center gap-2">
            <BrainCircuit size={18} className="text-amber-300" />
            <h3 className="font-black text-white">Validated reference</h3>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <Metric label="Accuracy" value={pct(data?.historicalReference?.accuracy)} detail="Rolling-origin" tone="green" />
            <Metric label="Coverage" value={pct(data?.historicalReference?.coverageRate)} detail="Safe predictions" tone="blue" />
          </div>
          <div className="mt-3 rounded-2xl border border-white/10 bg-white/[.03] p-4">
            <div className="text-xs font-black uppercase tracking-widest text-zinc-500">Live experiment</div>
            <div className="mt-2 flex items-end justify-between">
              <div>
                <div className="text-2xl font-black text-white">{highConfidence?.correct || 0}/{highConfidence?.predictions || 0}</div>
                <div className="text-xs text-zinc-500">High-confidence correct</div>
              </div>
              <CheckCircle2 className="text-emerald-300" />
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-[26px] border border-white/10 bg-zinc-950 p-5">
          <div className="flex items-center gap-2">
            <Database size={18} className="text-sky-300" />
            <h3 className="font-black text-white">Player-history queue</h3>
          </div>
          <div className="mt-4 space-y-2">
            {queueGroups.map((group: any) => (
              <div key={group.status} className="flex items-center justify-between rounded-xl bg-white/[.04] px-4 py-3">
                <span className="text-sm font-bold text-zinc-300">{group.status}</span>
                <span className="font-black text-white">{group.players}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-[26px] border border-white/10 bg-zinc-950 p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="font-black text-white">Prediction worker activity</h3>
              <div className="mt-1 text-xs text-zinc-500">Routine checks are collapsed unless they changed data or encountered an error.</div>
            </div>
            <span className={`rounded-lg px-3 py-1 text-xs font-black ${data?.lifecycleActivity?.lastCheck?.status === 'COMPLETE' ? 'bg-emerald-400/10 text-emerald-300' : 'bg-amber-300/10 text-amber-200'}`}>
              {data?.lifecycleActivity?.lastCheck?.status || 'Not started'}
            </span>
          </div>
          {data?.lifecycleActivity?.lastCheck && (
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              <div className="rounded-xl bg-white/[.04] p-3"><div className="text-[10px] font-black uppercase tracking-wider text-zinc-600">Last successful check</div><div className="mt-1 text-sm font-black text-white">{new Date(data.lifecycleActivity.lastCheck.finishedAt || data.lifecycleActivity.lastCheck.startedAt).toLocaleString()}</div></div>
              <div className="rounded-xl bg-white/[.04] p-3"><div className="text-[10px] font-black uppercase tracking-wider text-zinc-600">Next scheduled check</div><div className="mt-1 text-sm font-black text-white">{data.lifecycleActivity.nextScheduledCheckAt ? new Date(data.lifecycleActivity.nextScheduledCheckAt).toLocaleString() : '—'}</div></div>
            </div>
          )}
          {data?.lifecycleActivity?.activeCheck && (
            <div className="mt-3 rounded-xl border border-sky-400/20 bg-sky-400/[.05] p-3 text-sm font-bold text-sky-200">A worker check is currently running.</div>
          )}
          <div className="mt-3 rounded-xl border border-white/10 p-3 text-sm text-zinc-400">
            {data?.lifecycleActivity?.noChangeChecks || 0} of the last {data?.lifecycleActivity?.checksInspected || 0} checks completed with no material changes.
          </div>
          <div className="mt-4 space-y-2">
            {(data?.lifecycleActivity?.notableChecks || []).length === 0 && <div className="text-sm text-zinc-500">No recent check changed prediction data.</div>}
            {(data?.lifecycleActivity?.notableChecks || []).map((run: any) => (
              <div key={run.cycleId} className="rounded-xl bg-white/[.04] p-4">
                <div className="flex items-center justify-between gap-3"><div className="font-black text-white">{new Date(run.startedAt).toLocaleString()}</div><div className="text-xs text-zinc-500">{run.durationSeconds ?? '—'} sec</div></div>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-400">
                  <span>{run.eventsPolled} events polled</span><span>{run.matchupsIndexed} matchups indexed</span><span>{run.playersQueued} players queued</span><span>{run.predictionsFrozen} predictions frozen</span><span>{run.outcomesResolved} outcomes resolved</span><span>{run.reviewsCreated} reviews created</span><span className={run.errors ? 'font-black text-red-300' : ''}>{run.errors} errors</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function parsePlayerIds(value:any): string[] {
  try {
    const parsed = typeof value === 'string' ? JSON.parse(value) : value;
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function PerformanceBreakdown({ title, rows }: { title: string; rows: any[] }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
      <div className="font-black text-white">{title}</div>
      <div className="mt-3 space-y-2">
        {rows.map((row: any) => (
          <div key={row.group} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 rounded-xl bg-white/[.03] px-3 py-2">
            <div className="text-sm font-bold text-zinc-300">{row.group}</div>
            <div className="text-xs text-zinc-500">{row.resolvedMatches} matches</div>
            <div className="font-black text-emerald-300">{pct(row.accuracy)}</div>
          </div>
        ))}
        {rows.length === 0 && <div className="text-sm text-zinc-600">No resolved matches yet.</div>}
      </div>
    </div>
  );
}

function sampleLabel(status?: string) {
  if (status === 'ESTABLISHED') return 'Established';
  if (status === 'DIRECTIONAL') return 'Directional';
  if (status === 'TOO_EARLY') return 'Too early';
  return 'No sample';
}

function sampleMessage(status: string | undefined, tournaments: number) {
  if (status === 'ESTABLISHED') return `${tournaments} resolved tournaments provide an established initial sample.`;
  if (status === 'DIRECTIONAL') return `${tournaments} resolved tournaments are directional; avoid firm model conclusions until at least 30.`;
  if (status === 'TOO_EARLY') return `${tournaments} resolved tournaments are too few for a reliable conclusion. Results are shown transparently but should not drive model changes yet.`;
  return 'No frozen tournament forecast has a confirmed final champion yet.';
}

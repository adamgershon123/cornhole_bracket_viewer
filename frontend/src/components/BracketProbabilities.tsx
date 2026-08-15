import { AlertTriangle, BarChart3, Brackets, ChevronLeft, ChevronRight, LoaderCircle, Trophy } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { fetchBracketProbabilities, retryBracketProbabilities } from '../lib/api';
import { ShareBracketSnapshotButton } from './ShareSnapshotButton';

export function BracketProbabilities({ eventId, event }: { eventId: string; event?: any }) {
  const [data, setData] = useState<any>();
  const [error, setError] = useState('');
  const [retrying, setRetrying] = useState(false);
  const buildPollInFlight = useRef(false);

  useEffect(() => {
    setData(undefined);
    setError('');
    // Reopening the tab should read the saved forecast first. Live polling
    // below is the only path that asks ACL for newer bracket results.
    fetchBracketProbabilities(eventId, 10000, false)
      .then(result => {
        setData(result);
        setError('');
      })
      .catch(error => setError(error.message));
  }, [eventId]);

  useEffect(() => {
    const eventComplete = ['C', 'COMPLETE', 'COMPLETED'].includes(String(event?.leagueStatus || event?.status || '').toUpperCase());
    if (eventComplete && data?.timelineBuildStatus !== 'BUILDING') return;
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      if (cancelled || buildPollInFlight.current) return;
      buildPollInFlight.current = true;
      try {
        const result = await fetchBracketProbabilities(eventId, 10000, true);
        if (!cancelled) {
          setData(result);
          setError('');
        }
      } catch (error: any) {
        if (!cancelled) setError(error.message);
      } finally {
        buildPollInFlight.current = false;
        if (!cancelled) timer = window.setTimeout(poll, 15_000);
      }
    };

    timer = window.setTimeout(poll, 15_000);
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [data?.timelineBuildStatus, eventId, event?.leagueStatus, event?.status]);

  if (error) {
    return <div className="mb-4 rounded-2xl border border-red-400/20 bg-red-950/20 p-5 text-base text-red-200">{error}</div>;
  }
  if (!data) {
    return (
      <section className="mb-4 flex min-h-[240px] items-center justify-center rounded-[28px] border border-amber-300/25 bg-zinc-950 p-8 text-center">
        <div>
          <LoaderCircle className="mx-auto animate-spin text-amber-300" size={42} />
          <div className="mt-4 text-2xl font-black text-white">Loading Bracket Predictions</div>
          <div className="mt-2 text-base text-zinc-400">
            Running matchup simulations and calculating each team&apos;s path through the bracket.
          </div>
        </div>
      </section>
    );
  }
  if (data.status === 'PREGAME_PENDING') {
    const build = data.buildStatus || {};
    const failed = build.state === 'FAILED';
    const stale = Boolean(build.stale);
    const started = build.startedAt ? new Date(build.startedAt).getTime() : NaN;
    const elapsedSeconds = Number.isFinite(started) ? Math.max(0, Math.floor((Date.now() - started) / 1000)) : null;
    const stageLabels: Record<string, string> = {
      QUEUED: 'Queued',
      PREPARING_PLAYER_HISTORY: 'Preparing player history',
      RUNNING_SIMULATIONS: 'Running bracket simulations',
      WAITING_FOR_DATABASE: 'Waiting for the analytics database',
      FAILED: 'Build failed',
    };
    const restart = async () => {
      setRetrying(true);
      try {
        const result = await retryBracketProbabilities(eventId, 10000);
        setData(result);
        setError('');
      } catch (error: any) {
        setError(error.message);
      } finally {
        setRetrying(false);
      }
    };
    return (
      <section className={`mb-4 flex min-h-[240px] items-center justify-center rounded-[28px] border bg-zinc-950 p-8 text-center ${failed || stale ? 'border-red-300/30' : 'border-sky-300/25'}`}>
        <div>
          {failed || stale
            ? <AlertTriangle className="mx-auto text-red-300" size={42}/>
            : <LoaderCircle className="mx-auto animate-spin text-sky-300" size={42} />}
          <div className="mt-4 text-2xl font-black text-white">{failed ? 'Frozen Prediction Build Failed' : stale ? 'Frozen Prediction Build Appears Stuck' : 'Creating Frozen Pregame Prediction'}</div>
          <div className="mt-2 max-w-xl text-base leading-7 text-zinc-400">
            {failed || stale
              ? 'The saved frozen prediction has not been created. Restarting this build will not rewrite a completed frozen prediction.'
              : 'The roster is available. The engine is freezing the first official forecast from the pre-event history currently available.'}
          </div>
          <div className="mx-auto mt-5 grid max-w-xl gap-3 text-left sm:grid-cols-2">
            <div className="rounded-xl border border-white/10 bg-white/[.04] p-3">
              <div className="text-xs font-black uppercase tracking-widest text-zinc-500">Current stage</div>
              <div className="mt-1 font-bold text-sky-200">{stageLabels[build.stage] || build.stage || 'Starting'}</div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[.04] p-3">
              <div className="text-xs font-black uppercase tracking-widest text-zinc-500">Elapsed time</div>
              <div className="mt-1 font-bold text-white">{elapsedSeconds == null ? 'Just started' : `${Math.floor(elapsedSeconds / 60)}m ${elapsedSeconds % 60}s`}</div>
            </div>
          </div>
          {build.message && <div className="mt-3 text-sm font-semibold text-zinc-400">{build.message}</div>}
          {build.attempt > 0 && <div className="mt-2 text-xs font-bold uppercase tracking-widest text-zinc-500">Attempt {build.attempt} of {build.maxAttempts || 8} · checked every 15 seconds</div>}
          {data.historyPlayersPending != null && (
            <div className="mt-4 text-sm font-bold text-sky-200">
              {data.historyPlayersReady || 0} ready · {data.historyPlayersPending || 0} gathering · {data.historyPlayersUnavailable || 0} unavailable after retries
            </div>
          )}
          {(failed || stale) && (
            <button type="button" onClick={restart} disabled={retrying} className="mt-5 min-h-12 rounded-xl border border-red-300/40 bg-red-300/10 px-6 py-3 font-black text-red-100 transition active:scale-[.98] disabled:opacity-50">
              {retrying ? 'Restarting…' : 'Restart frozen prediction build'}
            </button>
          )}
        </div>
      </section>
    );
  }
  if (data.status === 'ROSTER_PENDING') {
    return (
      <section className="mb-4 rounded-[28px] border border-amber-300/25 bg-zinc-950 p-7 text-center">
        <div className="text-2xl font-black text-white">Waiting for Final Rosters</div>
        <div className="mx-auto mt-2 max-w-xl text-base leading-7 text-zinc-400">
          ACL has published the event, but at least two complete teams are not yet available.
          The event watcher will create the frozen prediction when the bracket roster is populated.
        </div>
      </section>
    );
  }
  if (data.status !== 'COMPLETE') {
    return <div className="mb-4 rounded-2xl border border-amber-300/20 bg-amber-300/5 p-5 text-base text-amber-100">Bracket predictions unavailable: {String(data.status).replaceAll('_', ' ')}</div>;
  }

  const possiblePairings = Number(data.coverage?.possiblePairingsEvaluated || 0);
  const modeledPairings = Number(data.coverage?.modelPredictedPairings || 0);
  const fallbackPairings = Number(data.coverage?.equalProbabilityFallbackPairings || 0);
  const internalPairings = Number(data.coverage?.fullyInternalPairings || 0);
  const aclAssistedPairings = Number(data.coverage?.aclAssistedPairings || 0);
  const currentIsStructureOnly = possiblePairings > 0 && modeledPairings === 0;
  const pregamePossiblePairings = Number(data.pregameSnapshot?.coverage?.possiblePairingsEvaluated || 0);
  const pregameModeledPairings = Number(data.pregameSnapshot?.coverage?.modelPredictedPairings || 0);
  const pregameIsStructureOnly = pregamePossiblePairings > 0 && pregameModeledPairings === 0;
  const rankedTeams = [...(data.teams || [])].sort((a: any, b: any) => Number(b.winEventProbability || 0) - Number(a.winEventProbability || 0));
  const leadingTeam = rankedTeams[0];
  const leadingPlayers = (leadingTeam?.players || []).map((player: any) => player.playerName).join(' / ');
  const validatedStructure = data.structure?.mode === 'VALIDATED_ACL_BRACKET_TEMPLATE';

  return <section className="mb-4 overflow-hidden rounded-[26px] border border-white/10 bg-zinc-950">
    <div className="flex flex-wrap items-start justify-between gap-4 border-b border-white/10 p-5">
      <div>
        <div className="flex items-center gap-2 text-sm font-black uppercase tracking-[.18em] text-amber-300">
          <Trophy size={19}/> Bracket Path Probabilities
        </div>
        <h2 className="mt-2 text-3xl font-black text-white">Current bracket forecast</h2>
        <div className="mt-1 text-sm font-semibold text-zinc-400">
          {data.simulationCount?.toLocaleString()} simulations · after {data.completedMatchesApplied || 0} of {data.completedMatchesAvailable || 0} available results
        </div>
        {data.frozenAt && (
          <div className="mt-2 text-sm font-bold text-sky-300">
            Pregame field frozen {formatTimestamp(data.frozenAt)}
          </div>
        )}
        {data.timelineBuildStatus === 'BUILDING' && (
          <div className="mt-3 flex items-center gap-2 text-sm font-bold text-amber-200">
            <LoaderCircle className="animate-spin" size={17}/>
            Reconstructing forecast history: {data.completedMatchesApplied || 0} of {data.completedMatchesAvailable || 0} results
          </div>
        )}
      </div>
      <div className="flex flex-col items-stretch gap-3 text-sm leading-6 text-zinc-400 sm:items-end">
        <div className="text-left sm:text-right">
          <div>{pct(data.coverage?.modelCoverageRate)} matchup coverage</div>
          <div>{data.coverage?.equalProbabilityFallbackPairings || 0} pairings used 50/50 fallback</div>
        </div>
        <ShareBracketSnapshotButton data={data} eventId={eventId} event={event}/>
      </div>
    </div>
    {currentIsStructureOnly && (
      <div className="border-b border-amber-300/20 bg-amber-300/[.08] px-5 py-4 text-base leading-7 text-amber-100">
        <span className="font-black text-amber-300">Structure-only estimate:</span> None of the remaining possible matchups has enough usable player history.
        These percentages come from bracket position, completed results, and 50/50 matchup assumptions—not a measured player-strength advantage.
      </div>
    )}
    {data.pregameSnapshot && (
      <div className="border-b border-white/10 p-5">
        <div className="grid gap-4 lg:grid-cols-[.8fr_1.2fr]">
          <div className="rounded-2xl border border-sky-300/20 bg-sky-300/[.05] p-4">
            <div className="text-xs font-black uppercase tracking-[.18em] text-sky-300">Frozen pregame prediction</div>
            <div className="mt-2 text-sm text-zinc-400">Saved once the bracket field was first available. It is never rewritten by later results.</div>
            <div className="mt-2 text-sm font-bold text-zinc-300">
              {(data.pregameSnapshot.simulationCount || 0).toLocaleString()} simulations · {pct(data.pregameSnapshot.coverage?.modelCoverageRate)} model coverage
            </div>
            {pregameIsStructureOnly && (
              <div className="mt-3 rounded-xl border border-amber-300/20 bg-amber-300/[.07] p-3 text-sm leading-6 text-amber-100">
                This frozen baseline was structure-only: all evaluated pregame matchups used 50/50 fallbacks.
              </div>
            )}
            <div className="mt-4 space-y-2">
              {[...(data.pregameSnapshot.teams || [])].sort((a: any, b: any) => Number(b.winEventProbability || 0) - Number(a.winEventProbability || 0)).map((team: any, index: number) => (
                <div key={team.teamId} className="flex items-center justify-between gap-3 rounded-xl bg-black/25 px-3 py-2">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="w-7 shrink-0 font-black text-sky-300">#{index + 1}</span>
                    <div className="min-w-0 truncate font-bold text-white">{teamPlayers(team)}</div>
                  </div>
                  <div className="shrink-0 font-black text-amber-300">{pct(team.winEventProbability)}</div>
                </div>
              ))}
            </div>
          </div>
          <BracketRoundSnapshots timeline={data.timeline || []} roundProgress={data.roundProgress || []} finalStandings={data.finalStandings || []}/>
        </div>
      </div>
    )}
    <div className="border-b border-white/10 bg-white/[.025] p-5">
      <div className="text-sm font-black uppercase tracking-[.16em] text-sky-300">Why the probabilities look this way</div>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <ExplanationCard
          icon={<BarChart3 size={20}/>}
          title={`${modeledPairings} of ${possiblePairings} matchups modeled`}
          text={possiblePairings
            ? `${internalPairings} used internal calculated PPR only; ${aclAssistedPairings} used a timestamp-safe ACL PPR snapshot for a player missing internal rounds.`
            : 'No unique matchup comparisons were available.'}
        />
        <ExplanationCard
          icon={<AlertTriangle size={20}/>}
          title={`${fallbackPairings} matchup${fallbackPairings === 1 ? '' : 's'} treated as even`}
          text={fallbackPairings
            ? 'Those pairings lacked sufficient usable history, so each team received a 50% chance instead of an inferred advantage.'
            : 'Every evaluated pairing had enough usable history for a model-based probability.'}
          warning={fallbackPairings > 0}
        />
        <ExplanationCard
          icon={<Brackets size={20}/>}
          title={validatedStructure ? 'ACL bracket path applied' : 'Bracket path approximated'}
          text={validatedStructure
            ? `Advancement follows a recurring ACL ${data.structure?.templateKey || ''} layout, including its match order and byes.`
            : 'No validated ACL layout matched this field, so the simulator used first-appearance seeding and single elimination.'}
        />
      </div>
      <div className="mt-4 rounded-xl border border-amber-300/20 bg-amber-300/[.06] p-4 text-base leading-7 text-zinc-200">
        <span className="font-black text-amber-300">Interpretation: </span>
        These are path probabilities, not a simple team ranking. A team&apos;s result reflects its calculated PPR advantage where data exists,
        its likely opponents, bracket position and byes{fallbackPairings ? ', plus 50/50 assumptions where history is insufficient' : ''}.
        {leadingTeam && <> The current simulation makes <span className="font-black text-white">{leadingPlayers || leadingTeam.teamName}</span> the most likely champion at <span className="font-black text-amber-300">{pct(leadingTeam.winEventProbability)}</span>. {fallbackPairings
          ? `Coverage is ${pct(data.coverage?.modelCoverageRate)}, so the result has limited confidence.`
          : aclAssistedPairings
          ? `${aclAssistedPairings} pairings use lower-confidence, pre-event ACL PPR assistance; bracket-layout uncertainty still applies.`
          : 'Every pairing uses internal calculated PPR; bracket-layout uncertainty still applies.'}</>}
      </div>
      <details className="mt-4 overflow-hidden rounded-2xl border border-white/10 bg-black/30">
        <summary className="cursor-pointer select-none px-4 py-4 text-base font-black text-white transition-colors hover:bg-white/[.04] active:bg-white/[.08]">
          Show all {possiblePairings} matchup coverage decisions
        </summary>
        <div className="space-y-3 border-t border-white/10 p-3 md:hidden">
          {(data.coverage?.pairingDetails || []).map((pairing: any) => {
            const predicted = pairing.status === 'PREDICTED';
            const aclAssisted = pairing.evidenceMode === 'ACL_ASSISTED';
            const missingNames = (pairing.missingPlayers || []).map((player: any) => player.playerName).join(', ');
            const assisted = (pairing.assistedPlayers || []).map((player: any) =>
              `${player.playerName}: ${number(player.value)} ACL PPR`
            ).join(', ');
            return <div key={`mobile:${pairing.teamAId}:${pairing.teamBId}`} className="rounded-xl border border-white/10 bg-white/[.03] p-4">
              <div className="text-base font-black text-white">{pairing.teamAName}</div>
              <div className="my-1 text-xs font-black text-zinc-600">VS</div>
              <div className="text-base font-black text-white">{pairing.teamBName}</div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-lg bg-black/30 p-3"><div className="text-xs font-bold text-zinc-500">PPR</div><div className="mt-1 font-black text-white">{number(pairing.teamACalculatedPpr)} / {number(pairing.teamBCalculatedPpr)}</div></div>
                <div className="rounded-lg bg-black/30 p-3"><div className="text-xs font-bold text-zinc-500">Probability</div><div className="mt-1 font-black text-white">{predicted ? `${pct(pairing.teamAProbability)} / ${pct(pairing.teamBProbability)}` : '50% / 50%'}</div></div>
              </div>
              <div className={`mt-3 inline-flex rounded-lg border px-3 py-2 text-sm font-black ${aclAssisted
                ? 'border-sky-300/25 bg-sky-300/10 text-sky-300'
                : predicted
                ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300'
                : 'border-amber-300/25 bg-amber-300/10 text-amber-300'}`}>
                {aclAssisted ? 'ACL-ASSISTED' : predicted ? 'INTERNAL MODEL' : '50 / 50 FALLBACK'}
              </div>
              <div className="mt-3 text-sm leading-6 text-zinc-400">
                {aclAssisted
                  ? <><span className="font-bold text-sky-200">{assisted}</span>. Reduced sample confidence applied.</>
                  : predicted
                  ? 'All players had pre-event internal calculated PPR history.'
                  : <><span className="font-bold text-amber-200">Missing history: {missingNames || 'unknown player'}</span>.</>}
              </div>
            </div>;
          })}
        </div>
        <div className="hidden overflow-x-auto border-t border-white/10 md:block">
          <table className="w-full min-w-[900px] text-sm">
            <thead className="bg-white/[.04] text-left text-xs font-black uppercase tracking-wider text-zinc-400">
              <tr><th className="p-4">Possible matchup</th><th className="p-4">PPR used</th><th className="p-4">Decision</th><th className="p-4">Why</th></tr>
            </thead>
            <tbody>{(data.coverage?.pairingDetails || []).map((pairing: any) => {
              const predicted = pairing.status === 'PREDICTED';
              const aclAssisted = pairing.evidenceMode === 'ACL_ASSISTED';
              const missingNames = (pairing.missingPlayers || []).map((player: any) => player.playerName).join(', ');
              const assisted = (pairing.assistedPlayers || []).map((player: any) =>
                `${player.playerName}: ${number(player.value)} ACL PPR`
              ).join(', ');
              return <tr key={`${pairing.teamAId}:${pairing.teamBId}`} className="border-t border-white/10 align-top">
                <td className="p-4">
                  <div className="font-bold text-white">{pairing.teamAName}</div>
                  <div className="my-1 font-black text-zinc-600">VS</div>
                  <div className="font-bold text-white">{pairing.teamBName}</div>
                </td>
                <td className="p-4 leading-6 text-zinc-300">
                  <div>{number(pairing.teamACalculatedPpr)} / {number(pairing.teamBCalculatedPpr)}</div>
                  {predicted && <div className="text-zinc-500">{pct(pairing.teamAProbability)} / {pct(pairing.teamBProbability)}</div>}
                </td>
                <td className="p-4">
                  <span className={`inline-flex rounded-lg border px-3 py-2 font-black ${aclAssisted
                    ? 'border-sky-300/25 bg-sky-300/10 text-sky-300'
                    : predicted
                    ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300'
                    : 'border-amber-300/25 bg-amber-300/10 text-amber-300'}`}>
                    {aclAssisted ? 'ACL-ASSISTED' : predicted ? 'INTERNAL MODEL' : '50 / 50 FALLBACK'}
                  </span>
                </td>
                <td className="p-4 leading-6 text-zinc-400">
                  {aclAssisted
                    ? <><span className="font-bold text-sky-200">{assisted}</span>. Snapshot existed before the event; reduced sample confidence is applied.</>
                    : predicted
                    ? 'All four players had pre-event internal calculated PPR history.'
                    : <><span className="font-bold text-amber-200">Missing internal history: {missingNames || 'unknown player'}</span>. The current rule rejects the entire matchup when any player has zero rounds.</>}
                </td>
              </tr>;
            })}</tbody>
          </table>
        </div>
      </details>
    </div>
    <div className="border-t border-white/10 bg-white/[.025] px-5 py-4">
      <div className="text-sm font-black uppercase tracking-[.16em] text-white">Current remaining-team forecast</div>
      <div className="mt-1 text-sm text-zinc-500">
        Conditional on the {data.completedMatchesApplied || 0} bracket results currently applied.
      </div>
    </div>
    <div className="divide-y divide-white/10 md:hidden">
      {rankedTeams.map((team: any, index: number) => {
        const playerNames = (team.players || []).map((player: any) => player.playerName).join(' / ');
        return <div key={`mobile:${team.teamId}`} className="p-4">
          <div className="text-sm font-black text-sky-300">Rank #{index + 1}</div>
          <div className="mt-1 text-lg font-black leading-snug text-white">{playerNames || team.teamName}</div>
          <div className="mt-1 text-sm font-semibold text-zinc-500">{team.teamName || `Team ${team.teamId}`}</div>
          <div className="mt-4 grid grid-cols-3 gap-2">
            <ProbabilityStat label="Semifinal" value={pct(team.reachSemifinalProbability)} />
            <ProbabilityStat label="Final" value={pct(team.reachFinalProbability)} tone="sky" />
            <ProbabilityStat label="Champion" value={pct(team.winEventProbability)} tone="amber" />
          </div>
        </div>;
      })}
    </div>
    <div className="hidden overflow-x-auto md:block">
      <table className="w-full min-w-[700px] text-base">
        <thead className="bg-white/[.04] text-left text-xs font-black uppercase tracking-wider text-zinc-400">
          <tr><th className="p-4">Rank</th><th className="p-4">Players</th><th>Reach semifinals</th><th>Reach final</th><th>Win event</th></tr>
        </thead>
        <tbody>{rankedTeams.map((team: any, index: number) => {
          const playerNames = (team.players || []).map((player: any) => player.playerName).join(' / ');
          return <tr key={team.teamId} className="border-t border-white/10 transition-colors hover:bg-white/[.035]">
            <td className="p-4 text-xl font-black text-sky-300">#{index + 1}</td>
            <td className="p-4">
              <div className="text-lg font-black text-white">{playerNames || team.teamName}</div>
              <div className="mt-1 text-sm font-semibold text-zinc-500">{team.teamName || `Team ${team.teamId}`}</div>
            </td>
            <td className="text-lg font-black text-zinc-200">{pct(team.reachSemifinalProbability)}</td>
            <td className="text-lg font-black text-sky-300">{pct(team.reachFinalProbability)}</td>
            <td className="text-xl font-black text-amber-300">{pct(team.winEventProbability)}</td>
          </tr>;
        })}</tbody>
      </table>
    </div>
    <div className="border-t border-white/10 p-4 text-sm leading-6 text-zinc-400">
      PPR-only model. Descriptive player ratings have zero weight. Structure: {data.structure?.mode === 'VALIDATED_ACL_BRACKET_TEMPLATE'
        ? `validated ACL ${data.structure.templateKey} layout inferred from ${data.structure.templateEventCount} completed events (${pct(data.structure.templateEdgeCoverageRate)} repeated-path coverage).`
        : 'seeded single-elimination fallback because no replicated ACL layout matched this field.'}
    </div>
  </section>;
}

function BracketRoundSnapshots({ timeline, roundProgress, finalStandings }: { timeline: any[]; roundProgress: any[]; finalStandings: any[] }) {
  const [selectedPage, setSelectedPage] = useState(0);
  const scroller = useRef<HTMLDivElement>(null);
  if (!timeline.length) return null;
  const pages = bracketRoundPages(timeline, roundProgress);
  const pregame = timeline[0];
  const initialIds = new Set((pregame.teams || []).map((team: any) => String(team.teamId)));
  const teamNames = new Map<string, string>((pregame.teams || []).map((team: any) => [String(team.teamId), teamPlayers(team)]));
  const showPage = (index: number) => {
    const next = Math.max(0, Math.min(index, pages.length - 1));
    setSelectedPage(next);
    (scroller.current?.children[next] as HTMLElement | undefined)?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'start' });
  };
  return <div className="min-w-0 rounded-2xl border border-white/10 bg-black/25 p-4">
    <div className="text-xs font-black uppercase tracking-[.18em] text-amber-300">Round-by-round forecast</div>
    <div className="mt-1 text-sm leading-6 text-zinc-400">Swipe from the frozen pre-tournament projection through each available bracket-round checkpoint.</div>
    <div className="mt-4 flex items-center justify-between gap-3">
      <button type="button" onClick={() => showPage(selectedPage - 1)} disabled={selectedPage === 0} className="flex min-h-11 items-center gap-1 rounded-xl border border-white/10 px-3 font-black text-white disabled:opacity-30"><ChevronLeft size={18}/> Previous</button>
      <div className="flex flex-wrap justify-center gap-2">{pages.map((page, index) => <button key={page.key} type="button" aria-label={`Show ${page.title}`} onClick={() => showPage(index)} className={`h-3 w-3 rounded-full ${selectedPage === index ? 'bg-amber-300 ring-4 ring-amber-300/15' : 'bg-zinc-700'}`}/>)}</div>
      <button type="button" onClick={() => showPage(selectedPage + 1)} disabled={selectedPage === pages.length - 1} className="flex min-h-11 items-center gap-1 rounded-xl border border-white/10 px-3 font-black text-white disabled:opacity-30">Next <ChevronRight size={18}/></button>
    </div>
    <div ref={scroller} onScroll={event => {
      const node = event.currentTarget;
      if (node.clientWidth) setSelectedPage(Math.max(0, Math.min(pages.length - 1, Math.round(node.scrollLeft / node.clientWidth))));
    }} className="mt-4 flex snap-x snap-mandatory overflow-x-auto overscroll-x-contain scroll-smooth [scrollbar-width:none]">
      {pages.map((page, pageIndex) => {
        const ranked = [...(page.snapshot.teams || [])].sort((a: any, b: any) => Number(b.winEventProbability || 0) - Number(a.winEventProbability || 0));
        const remaining = new Set(ranked.map((team: any) => String(team.teamId)));
        const eliminated = [...initialIds].filter(id => !remaining.has(id));
        return <article key={page.key} className="w-full shrink-0 snap-start">
          <div className="rounded-2xl border border-white/10 bg-zinc-950 p-4">
            <div className="flex items-start justify-between gap-3">
              <div><div className="text-[10px] font-black uppercase tracking-[.18em] text-zinc-500">Page {pageIndex + 1} of {pages.length}</div><div className="mt-1 text-2xl font-black text-white">{page.title}</div></div>
              <span className={`rounded-lg px-2 py-1 text-xs font-black ${page.current ? 'bg-emerald-400 text-black' : 'bg-sky-400/15 text-sky-200'}`}>{page.current ? 'ROLLING' : 'SAVED'}</span>
            </div>
            <div className="mt-2 text-sm text-zinc-400">{page.subtitle}</div>
            <div className="mt-4 text-xs font-black uppercase tracking-wider text-sky-300">{page.resolved ? 'Tournament result' : 'Remaining teams · projected champion chance'}</div>
            <div className="mt-2 max-h-80 space-y-2 overflow-y-auto pr-1">{ranked.map((team: any, index: number) => <div key={team.teamId} className="flex items-center gap-3 rounded-xl bg-white/[.04] px-3 py-3"><span className="w-7 shrink-0 font-black text-sky-300">#{index + 1}</span><span className="min-w-0 flex-1 font-bold leading-tight text-white">{teamPlayers(team)}</span><span className="shrink-0 font-black text-amber-300">{pct(team.winEventProbability)}</span></div>)}</div>
            {page.resolved && finalStandings.length > 0
              ? <div className="mt-4 border-t border-white/10 pt-4"><div className="text-xs font-black uppercase tracking-wider text-sky-300">Final standings</div><div className="mt-2 max-h-96 space-y-1 overflow-y-auto">{finalStandings.map((team: any) => <div key={team.teamId} className="flex items-center gap-3 rounded-lg bg-white/[.04] px-3 py-2 text-sm"><span className="w-8 shrink-0 font-black text-sky-300">#{team.place}</span><span className="font-bold text-zinc-200">{teamPlayers(team)}</span></div>)}</div></div>
              : eliminated.length > 0 && <div className="mt-4 border-t border-white/10 pt-4"><div className="text-xs font-black uppercase tracking-wider text-red-300">Eliminated by this checkpoint</div><div className="mt-2 space-y-1">{eliminated.map(id => <div key={id} className="rounded-lg bg-red-400/[.06] px-3 py-2 text-sm font-bold text-zinc-400">{teamNames.get(id) || `Team ${id}`}</div>)}</div></div>}
          </div>
        </article>;
      })}
    </div>
  </div>;
}

function bracketRoundPages(timeline: any[], roundProgress: any[]) {
  void roundProgress;
  const roundPages: any[] = [];
  timeline.slice(1).forEach((point, timelineIndex) => {
    const description = String(point.triggerMatch?.roundDescription || '').trim();
    const roundNumber = description.match(/(\d+)/)?.[1];
    const key = roundNumber ? `round:${roundNumber}` : `stage:${description || point.label}`;
    const remaining = Number((point.teams || []).length);
    const championship = Boolean(point.triggerMatch?.isChampionshipGame) || /final|champ/i.test(description);
    const gameId = Number(point.triggerMatch?.gameId || 0);
    const resultKey = String(point.triggerMatch?.resultKey || `${point.triggerMatch?.matchId || timelineIndex}:${gameId}`);
    let title = roundNumber ? `Round ${roundNumber}` : (description || point.label || 'Bracket update');
    if (remaining === 4) title = '4 teams remain';
    if (remaining === 3) title = '3 teams remain';
    if (remaining === 2 && championship && gameId <= 1) title = 'Championship game 1';
    if (remaining === 2 && championship && gameId > 1) title = `Championship game ${gameId}`;
    if (remaining === 1) title = 'Final result';
    const page = {
      key: remaining <= 4 || championship ? `checkpoint:${resultKey}` : key,
      title,
      snapshot: point,
      results: Number(point.completedMatches || 0),
      totalResults: Number(point.completedMatches || 0),
    };
    const previous = roundPages[roundPages.length - 1];
    // Early bracket updates are summarized at the end of their round. Once
    // four teams remain, retain every elimination and every championship game.
    if (remaining > 4 && !championship && previous?.key === key) roundPages[roundPages.length - 1] = page;
    else roundPages.push(page);
  });
  const pages = [{ key: 'pregame', title: 'Frozen pre-tournament', snapshot: timeline[0], results: 0, totalResults: 0 }, ...roundPages];
  return pages.map((page, index) => {
    const finalComplete = Number((page.snapshot?.teams || []).length) === 1;
    const winnerId = String(page.snapshot?.triggerMatch?.winnerTeamId || '');
    const snapshot = finalComplete ? {
      ...page.snapshot,
      teams: (page.snapshot.teams || [])
        .filter((team: any) => String(team.teamId) === winnerId)
        .map((team: any) => ({ ...team, winEventProbability: 1 })),
    } : page.snapshot;
    return {
      ...page,
      snapshot,
      resolved: finalComplete,
      title: finalComplete ? 'Final result' : page.title,
      current: index === pages.length - 1 && index > 0,
      subtitle: index === 0
        ? 'Forecast frozen before any tournament result was applied.'
        : finalComplete
          ? 'The tournament is complete. The forecast sequence and final standings are preserved below.'
          : page.snapshot?.triggerMatch?.isChampionshipGame && Number(page.snapshot?.triggerMatch?.gameId || 0) === 1
            ? 'Championship game 1 is complete. Both finalists remain, so the bracket reset advances to game 2.'
            : `${(page.snapshot?.teams || []).length} teams remain after ${page.results} completed results.`,
    };
  });
}

function BracketPredictionTimeline({ timeline }: { timeline: any[] }) {
  const [selectedTeamId, setSelectedTeamId] = useState('');
  if (!timeline.length) return null;
  const teamMap = new Map<string, string>();
  timeline.forEach(point => (point.teams || []).forEach((team: any) => {
    if (!teamMap.has(String(team.teamId))) teamMap.set(String(team.teamId), teamPlayers(team));
  }));
  const rankedIds = (timeline[0]?.teams || [])
    .slice()
    .sort((a: any, b: any) => Number(b.winEventProbability) - Number(a.winEventProbability))
    .map((team: any) => String(team.teamId));
  const chartData = timeline.map(point => ({
    label: point.label,
    triggerMatch: point.triggerMatch,
    ...Object.fromEntries((point.teams || []).map((team: any) => [
      String(team.teamId),
      Number(team.winEventProbability) * 100,
    ])),
  })); 
  const activeTeamId = rankedIds.includes(selectedTeamId) ? selectedTeamId : (rankedIds[0] || '');
  const selectedName = teamMap.get(activeTeamId) || `Team ${activeTeamId}`;
  const selectedPoints = chartData
    .map(point => Number((point as any)[activeTeamId]))
    .filter(Number.isFinite);
  const selectedStart = selectedPoints[0];
  const selectedLatest = selectedPoints[selectedPoints.length - 1];
  const selectedChange = Number.isFinite(selectedStart) && Number.isFinite(selectedLatest)
    ? selectedLatest - selectedStart
    : 0;
  const progression = chartData.reduce<any[]>((points, point, index) => {
    const probability = Number((point as any)[activeTeamId]);
    if (!Number.isFinite(probability)) return points;
    const previous = points[points.length - 1];
    const isFirst = index === 0;
    const isLast = index === chartData.length - 1;
    if (isFirst || isLast || !previous || Math.abs(probability - previous.probability) >= 0.1) {
      points.push({
        ...point,
        checkpoint: isFirst ? 'Pregame' : `Update ${points.length}`,
        probability,
        delta: previous ? probability - previous.probability : 0,
      });
    }
    return points;
  }, []);
  const recentChanges = progression
    .filter(point => point.triggerMatch && Math.abs(point.delta) >= 0.1)
    .slice(-5)
    .reverse();
  return (
    <div className="rounded-2xl border border-white/10 bg-black/25 p-4">
      <div className="text-xs font-black uppercase tracking-[.18em] text-amber-300">Tournament forecast progression</div>
      <div className="mt-1 text-sm leading-6 text-zinc-400">
        Meaningful changes to one team&apos;s championship outlook as bracket results affect its path.
      </div>
      <div className="mt-4">
        <label className="text-xs font-black uppercase tracking-wider text-zinc-500" htmlFor="timeline-team">Team shown</label>
        <select
          id="timeline-team"
          value={activeTeamId}
          onChange={event => setSelectedTeamId(event.target.value)}
          className="mt-2 min-h-12 w-full rounded-xl border border-white/15 bg-zinc-900 px-3 text-base font-bold text-white"
        >
          {rankedIds.map((teamId, index) => <option key={teamId} value={teamId}>#{index + 1} {teamMap.get(teamId) || `Team ${teamId}`}</option>)}
        </select>
        <div className="mt-3 grid grid-cols-3 gap-2">
          <TimelineStat label="Pregame" value={Number.isFinite(selectedStart) ? `${selectedStart.toFixed(1)}%` : '—'} />
          <TimelineStat label="Current" value={Number.isFinite(selectedLatest) ? `${selectedLatest.toFixed(1)}%` : '—'} />
          <TimelineStat label="Net change" value={`${selectedChange >= 0 ? '+' : ''}${selectedChange.toFixed(1)} pts`} />
        </div>
      </div>
      <div className="mt-4 h-[270px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={progression} margin={{ top: 8, right: 8, left: -18, bottom: 8 }}>
            <XAxis dataKey="checkpoint" tick={{ fill: '#a1a1aa', fontSize: 11 }} interval="preserveStartEnd"/>
            <YAxis domain={[0, 100]} tick={{ fill: '#a1a1aa', fontSize: 11 }} tickFormatter={value => `${value}%`}/>
            <Tooltip
              contentStyle={{ background: '#09090b', border: '1px solid #3f3f46', borderRadius: 12, fontSize: 14 }}
              formatter={(value: any) => [`${Number(value).toFixed(1)}%`, selectedName]}
              labelFormatter={(_, payload) => payload?.[0]?.payload?.label || 'Pregame'}
            />
            <Line type="monotone" dataKey="probability" stroke="#fbbf24" strokeWidth={4} dot={{ r: 4 }} connectNulls={false}/>
          </LineChart>
        </ResponsiveContainer>
      </div>
      {recentChanges.length > 0 && (
        <div className="mt-4 border-t border-white/10 pt-4">
          <div className="text-xs font-black uppercase tracking-wider text-zinc-500">What moved the forecast</div>
          <div className="mt-3 space-y-2">
            {recentChanges.map(point => {
              const match = point.triggerMatch;
              const winner = teamMap.get(String(match.winnerTeamId)) || `Team ${match.winnerTeamId}`;
              const loser = teamMap.get(String(match.loserTeamId)) || `Team ${match.loserTeamId}`;
              return <div key={`${match.matchId}:${point.probability}`} className="rounded-xl border border-white/10 bg-white/[.035] p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-bold text-white">Match {match.matchId}: {winner} defeated {loser}</div>
                  <div className={`shrink-0 font-black ${point.delta >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                    {point.delta >= 0 ? '+' : ''}{point.delta.toFixed(1)} pts
                  </div>
                </div>
                <div className="mt-1 text-sm text-zinc-500">Score {match.score} · forecast moved to {point.probability.toFixed(1)}%</div>
              </div>;
            })}
          </div>
        </div>
      )}
      <div className="mt-3 text-xs leading-5 text-zinc-600">
        {Math.max(0, timeline.length - 1)} results evaluated · {Math.max(0, progression.length - 1)} meaningful forecast changes shown
      </div>
    </div>
  );
}

function TimelineStat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-white/[.05] p-3 text-center">
    <div className="text-[10px] font-black uppercase tracking-wide text-zinc-500">{label}</div>
    <div className="mt-1 text-base font-black text-white">{value}</div>
  </div>;
}

function teamPlayers(team: any) {
  return (team.players || []).map((player: any) => player.playerName).join(' / ') || team.teamName || `Team ${team.teamId}`;
}

function formatTimestamp(value: string) {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function ExplanationCard({ icon, title, text, warning = false }: {
  icon: ReactNode;
  title: string;
  text: string;
  warning?: boolean;
}) {
  return <div className={`rounded-2xl border p-4 ${warning ? 'border-amber-300/25 bg-amber-300/[.05]' : 'border-white/10 bg-black/25'}`}>
    <div className={`flex items-center gap-2 ${warning ? 'text-amber-300' : 'text-sky-300'}`}>
      {icon}
      <div className="text-base font-black text-white">{title}</div>
    </div>
    <p className="mt-2 text-sm leading-6 text-zinc-400">{text}</p>
  </div>;
}

function ProbabilityStat({ label, value, tone = 'white' }: { label: string; value: string; tone?: 'white' | 'sky' | 'amber' }) {
  const color = tone === 'amber' ? 'text-amber-300' : tone === 'sky' ? 'text-sky-300' : 'text-white';
  return <div className="rounded-xl bg-white/[.04] p-3 text-center">
    <div className="text-[11px] font-black uppercase tracking-wide text-zinc-500">{label}</div>
    <div className={`mt-1 text-lg font-black ${color}`}>{value}</div>
  </div>;
}

function number(value: any) {
  return value == null ? 'Unavailable' : Number(value).toFixed(2);
}

function pct(value: any) {
  return value == null ? '—' : `${(Number(value) * 100).toFixed(1)}%`;
}

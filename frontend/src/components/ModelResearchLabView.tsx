import { ArrowRight, BrainCircuit, CheckCircle2, FlaskConical, Lightbulb, RefreshCw, ShieldCheck, Sparkles } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { fetchModelResearch } from '../lib/api';

function pct(value?: number | null) {
  return value == null ? '—' : `${(Number(value) * 100).toFixed(1)}%`;
}

function delta(value?: number | null) {
  if (value == null) return '—';
  const points = Number(value) * 100;
  return `${points >= 0 ? '+' : ''}${points.toFixed(2)} pts`;
}

const toneClasses: Record<string, string> = {
  POSITIVE: 'border-emerald-400/25 bg-emerald-400/[.08] text-emerald-300',
  CAUTION: 'border-amber-400/25 bg-amber-400/[.08] text-amber-200',
  INFO: 'border-sky-400/25 bg-sky-400/[.08] text-sky-300',
};

const statusClasses: Record<string, string> = {
  COMPLETE: 'bg-emerald-400/15 text-emerald-300',
  ACTIVE: 'bg-sky-400/15 text-sky-300',
  RUNNING: 'bg-violet-400/15 text-violet-200',
  WAITING: 'bg-zinc-700 text-zinc-200',
  FAILED: 'bg-red-400/15 text-red-300',
  NEXT: 'bg-violet-400/15 text-violet-300',
  NEXT_BUILD: 'bg-violet-400/15 text-violet-300',
  PARTIAL: 'bg-amber-400/15 text-amber-200',
  GATED: 'bg-zinc-700 text-zinc-200',
  CONTROL: 'bg-sky-400/15 text-sky-300',
  PROMISING: 'bg-emerald-400/15 text-emerald-300',
  VALIDATED_CANDIDATE: 'bg-emerald-300 text-black',
  MIXED: 'bg-amber-400/15 text-amber-200',
  BEHIND: 'bg-red-400/15 text-red-300',
};

export default function ModelResearchLabView() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [changes, setChanges] = useState<Record<string, number>>({});
  const previousActivity = useRef<any>(null);

  async function refresh() {
    setLoading(true);
    setError('');
    try {
      const next = await fetchModelResearch();
      const current = next?.activity || {};
      const previous = previousActivity.current;
      if (previous) {
        setChanges({
          games: Number(current?.ledger?.games || 0) - Number(previous?.ledger?.games || 0),
          rounds: Number(current?.ledger?.rounds || 0) - Number(previous?.ledger?.rounds || 0),
          matchups: Number(current?.analysis?.cutoffSafeMatchups || 0) - Number(previous?.analysis?.cutoffSafeMatchups || 0),
          evaluations: Number(current?.analysis?.modelMatchEvaluations || 0) - Number(previous?.analysis?.modelMatchEvaluations || 0),
          replays: Number(current?.analysis?.tournamentReplays || 0) - Number(previous?.analysis?.tournamentReplays || 0),
        });
      }
      previousActivity.current = current;
      setData(next);
    } catch (err: any) {
      setError(err?.message || 'Model research results could not be loaded.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 15000);
    return () => window.clearInterval(timer);
  }, []);

  if (loading && !data) {
    return <section className="mt-4 flex min-h-72 items-center justify-center rounded-[30px] border border-violet-300/20 bg-zinc-950">
      <RefreshCw className="animate-spin text-violet-300" size={34} />
    </section>;
  }

  const findings = data?.findings || [];
  const experiments = data?.experiments || [];
  const activity = data?.activity || {};
  const analysis = activity?.analysis || {};
  const discovery = activity?.discovery || {};
  const ledger = activity?.ledger || {};
  const queue = activity?.queue || {};
  const hourly = activity?.lastHour || {};
  const totalQueue = Number(queue.pending || 0) + Number(queue.processing || 0) + Number(queue.complete || 0) + Number(queue.failed || 0);
  const queueProgress = totalQueue ? (Number(queue.complete || 0) / totalQueue) * 100 : 0;
  const localEnvironment = ['localhost', '127.0.0.1'].includes(window.location.hostname);

  return <section className="mt-4 space-y-4 pb-12">
    <header className="relative overflow-hidden rounded-[32px] border border-violet-300/20 bg-zinc-950 p-5 md:p-8">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(168,85,247,.20),transparent_40%),radial-gradient(circle_at_bottom_left,rgba(14,165,233,.12),transparent_38%)]" />
      <div className="relative flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.24em] text-violet-300"><FlaskConical size={17} /> Model Research Lab</div>
          <h2 className="mt-3 max-w-4xl text-3xl font-black tracking-tight text-white md:text-5xl">Finding signal beyond PPR</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-zinc-400 md:text-base">{data?.mission}</p>
        </div>
        <button type="button" onClick={refresh} disabled={loading} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-2xl border border-white/15 bg-white/[.05] px-5 font-black text-white transition active:translate-y-1 disabled:opacity-50">
          <RefreshCw size={17} className={loading ? 'animate-spin' : ''} /> Refresh evidence
        </button>
      </div>
    </header>

    {error && <div className="rounded-2xl border border-red-400/30 bg-red-950/40 p-4 text-red-200">{error}</div>}

    <section className="overflow-hidden rounded-[30px] border border-sky-300/20 bg-zinc-950">
      <div className="flex flex-col gap-3 border-b border-white/10 p-5 md:flex-row md:items-center md:justify-between md:p-6">
        <div>
          <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.22em] text-sky-300"><BrainCircuit size={18} /> Research work in progress</div>
          <h3 className="mt-2 text-2xl font-black text-white">What the system is doing right now</h3>
          <p className="mt-1 text-sm text-zinc-500">Automatically refreshes every 15 seconds. Collection and model analysis are reported separately.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {localEnvironment && <span className="rounded-full bg-amber-400/15 px-3 py-1.5 text-[10px] font-black uppercase tracking-wider text-amber-200">Local database</span>}
          <span className={`rounded-full px-3 py-1.5 text-[10px] font-black uppercase tracking-wider ${activity.collectionStatus === 'WORKING' ? 'bg-emerald-400/15 text-emerald-300' : activity.collectionStatus === 'PAUSED' ? 'bg-amber-400/15 text-amber-200' : 'bg-sky-400/15 text-sky-300'}`}>{activity.collectionStatus || 'Unknown'}</span>
        </div>
      </div>
      {localEnvironment && Number(ledger.rounds || 0) < 100000 && <div className="border-b border-amber-300/15 bg-amber-300/[.06] px-5 py-3 text-sm leading-5 text-amber-100 md:px-6">
        This page is connected to the smaller local database, not the cloud production archive. Zero or low research counts here do not represent production totals.
      </div>}
      <div className="grid gap-px bg-white/10 sm:grid-cols-2 xl:grid-cols-5">
        <LiveMetric label="Games collected" value={Number(ledger.games || 0)} change={changes.games} detail={`${Number(hourly.gamesDownloaded || 0).toLocaleString()} added in the last hour`} tone="green" />
        <LiveMetric label="Player rounds" value={Number(ledger.rounds || 0)} change={changes.rounds} detail={`${Number(hourly.roundsAdded || 0).toLocaleString()} added in the last hour`} tone="blue" />
        <LiveMetric label="Cutoff-safe matches" value={Number(analysis.cutoffSafeMatchups || 0)} change={changes.matchups} detail={`${Number(analysis.resolvedMatchupsFound || 0).toLocaleString()} resolved matchups found`} tone="amber" />
        <LiveMetric label="Model-match evaluations" value={Number(analysis.modelMatchEvaluations || 0)} change={changes.evaluations} detail={`${Number(analysis.modelConfigurations || 0)} configurations scored`} tone="violet" />
        <LiveMetric label="Tournament replays" value={Number(analysis.tournamentReplays || 0)} change={changes.replays} detail={`${Number(analysis.tournamentReplaysRemaining || 0).toLocaleString()} remaining`} tone="zinc" />
      </div>
      <div className="grid gap-4 p-5 md:grid-cols-2 md:p-6">
        <div className="rounded-2xl border border-white/10 bg-white/[.025] p-4">
          <div className="flex items-center justify-between gap-3"><div className="text-xs font-black uppercase tracking-[.18em] text-zinc-400">Collection queue</div><div className="text-sm font-black text-white">{queueProgress.toFixed(1)}%</div></div>
          <div className="mt-3 h-3 overflow-hidden rounded-full bg-zinc-800"><div className="h-full rounded-full bg-gradient-to-r from-sky-400 to-emerald-400 transition-all duration-500" style={{ width: `${Math.min(100, queueProgress)}%` }} /></div>
          <div className="mt-3 grid grid-cols-4 gap-2 text-center"><QueueStat label="Pending" value={queue.pending} /><QueueStat label="Active" value={queue.processing} /><QueueStat label="Complete" value={queue.complete} /><QueueStat label="Failed" value={queue.failed} /></div>
          <div className="mt-3 text-xs text-zinc-500">Current: {activity.currentWork?.type ? `${activity.currentWork.type} ${activity.currentWork.key || ''}` : 'waiting for the next queued item'}</div>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/[.025] p-4">
          <div className="text-xs font-black uppercase tracking-[.18em] text-zinc-400">Analysis lifecycle</div>
          <div className="mt-3 grid grid-cols-2 gap-2"><QueueStat label="Development" value={analysis.developmentMatchups} /><QueueStat label="Validation" value={analysis.validationMatchups} /><QueueStat label="Untouched holdout" value={analysis.holdoutMatchups} /><QueueStat label="Forward frozen" value={analysis.forwardFrozenExamples} /></div>
          <div className="mt-3 text-xs leading-5 text-zinc-500">
            Backtest: <strong className="text-zinc-300">{activity.backtestRefresh?.status || 'unknown'}</strong>
            {activity.backtestRefresh?.newGamesSinceRun ? ` · ${Number(activity.backtestRefresh.newGamesSinceRun).toLocaleString()} new games await/reinforce refresh` : ''}
            {activity.backtestRefresh?.generatedAt ? ` · last analyzed ${new Date(activity.backtestRefresh.generatedAt).toLocaleString()}` : ' · not generated in this database'}
          </div>
        </div>
      </div>
    </section>

    <section className="overflow-hidden rounded-[30px] border border-violet-300/25 bg-zinc-950">
      <div className="flex flex-col gap-3 border-b border-white/10 p-5 md:flex-row md:items-center md:justify-between md:p-6">
        <div>
          <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.22em] text-violet-300"><BrainCircuit size={18} /> Automated pattern discovery</div>
          <h3 className="mt-2 text-2xl font-black text-white">Step 4 is running</h3>
          <p className="mt-1 text-sm leading-6 text-zinc-400">The engine generates patterns on development history, selects them on chronological validation, and only then opens the untouched holdout. Production predictions are never changed automatically.</p>
        </div>
        <Status value={discovery.status || 'WAITING'} />
      </div>
      <div className="grid gap-px bg-white/10 sm:grid-cols-2 lg:grid-cols-5">
        <DiscoveryMetric label="Examples scanned" value={discovery.examplesScanned} />
        <DiscoveryMetric label="Patterns generated" value={discovery.candidatesGenerated} />
        <DiscoveryMetric label="Validated" value={discovery.candidatesValidated} />
        <DiscoveryMetric label="Locked before holdout" value={discovery.candidatesLocked} />
        <DiscoveryMetric label="Holdout scored" value={discovery.candidatesHoldoutScored} />
      </div>
      <div className="grid gap-4 p-5 md:grid-cols-[1fr_2fr] md:p-6">
        <div className="rounded-2xl border border-white/10 bg-white/[.025] p-4">
          <div className="text-[10px] font-black uppercase tracking-[.18em] text-zinc-500">Current phase</div>
          <div className="mt-2 text-lg font-black text-violet-200">{String(discovery.phase || 'Waiting for first run').replaceAll('_', ' ')}</div>
          <div className="mt-2 text-sm text-zinc-500">{discovery.lastCandidate ? `Evaluating: ${discovery.lastCandidate}` : discovery.completedAt ? `Completed ${new Date(discovery.completedAt).toLocaleString()}` : 'The worker will publish progress here as it advances.'}</div>
          {discovery.lastError && <div className="mt-3 rounded-xl border border-red-400/25 bg-red-950/30 p-3 text-sm text-red-200">{discovery.lastError}</div>}
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/[.025] p-4">
          <div className="text-[10px] font-black uppercase tracking-[.18em] text-zinc-500">Leading discovered candidates</div>
          {(discovery.candidates || []).length ? <div className="mt-3 space-y-2">{(discovery.candidates || []).slice(0, 6).map((candidate: any, index: number) => <div key={candidate.candidate_key} className="grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-xl bg-black/25 p-3">
            <div className="font-black text-violet-300">#{index + 1}</div>
            <div><div className="font-black text-white">{candidate.name}</div><div className="text-xs text-zinc-500">{String(candidate.family || '').replaceAll('_', ' ')} · {Number(candidate.evaluated_matchups || 0).toLocaleString()} holdout matches</div></div>
            <div className="text-right"><div className={`font-black ${Number(candidate.accuracy_delta || 0) > 0 ? 'text-emerald-300' : 'text-zinc-400'}`}>{delta(candidate.accuracy_delta)}</div><div className="text-[10px] uppercase text-zinc-600">vs PPR</div></div>
          </div>)}</div> : <div className="mt-3 rounded-xl border border-dashed border-white/10 p-4 text-sm text-zinc-500">Candidates will appear after the first development and validation pass.</div>}
        </div>
      </div>
    </section>

    <section className="rounded-[30px] border border-amber-300/20 bg-zinc-950 p-4 md:p-6">
      <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.22em] text-amber-300"><Sparkles size={17} /> Major findings first</div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {findings.map((finding: any) => <article key={finding.title} className={`rounded-2xl border p-4 ${toneClasses[finding.tone] || toneClasses.INFO}`}>
          <div className="text-[10px] font-black uppercase tracking-[.18em] opacity-70">{finding.title}</div>
          <div className="mt-2 text-xl font-black leading-tight text-white">{finding.headline}</div>
          <p className="mt-2 text-sm leading-5 text-zinc-300">{finding.detail}</p>
        </article>)}
      </div>
    </section>

    <section className="grid gap-4 lg:grid-cols-2">
      {(data?.tracks || []).map((track: any, index: number) => <article key={track.name} className={`rounded-[28px] border p-5 md:p-6 ${index === 0 ? 'border-sky-300/20 bg-sky-400/[.045]' : 'border-violet-300/20 bg-violet-400/[.045]'}`}>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.2em] text-white">{index === 0 ? <Lightbulb className="text-sky-300" /> : <BrainCircuit className="text-violet-300" />} Learning path {index + 1}</div>
          <span className={`rounded-full px-3 py-1 text-[10px] font-black uppercase tracking-wider ${statusClasses[track.status] || statusClasses.GATED}`}>{String(track.status).replaceAll('_', ' ')}</span>
        </div>
        <h3 className="mt-4 text-2xl font-black text-white">{track.name}</h3>
        <p className="mt-2 text-sm leading-6 text-zinc-400">{track.description}</p>
        <div className="mt-4 rounded-xl border border-white/10 bg-black/20 p-3 text-sm font-bold text-zinc-200">{track.output}</div>
      </article>)}
    </section>

    <section className="overflow-hidden rounded-[30px] border border-white/10 bg-zinc-950">
      <div className="border-b border-white/10 p-5 md:p-6">
        <div className="text-xs font-black uppercase tracking-[.22em] text-emerald-300">Current experiment scoreboard</div>
        <h3 className="mt-2 text-2xl font-black text-white">Every challenger versus the PPR control</h3>
        <p className="mt-1 text-sm text-zinc-500">Promising means worth further testing. It does not mean production-ready.</p>
      </div>
      <div className="space-y-3 p-3 md:hidden">
        {experiments.map((row: any) => <ExperimentCard key={row.name} row={row} />)}
      </div>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full min-w-[900px] text-sm">
          <thead className="text-left text-[10px] font-black uppercase tracking-wider text-zinc-500"><tr><th className="p-4">Model</th><th>Status</th><th>Accuracy</th><th>vs PPR</th><th>Brier</th><th>Changed calls</th><th>Net correct</th><th>Confidence</th></tr></thead>
          <tbody>{experiments.map((row: any) => <tr key={row.name} className="border-t border-white/10">
            <td className="p-4 font-black text-white">{row.name}</td>
            <td><Status value={row.status} /></td>
            <td className="font-black text-emerald-300">{pct(row.accuracy)}</td><td>{row.role === 'CONTROL' ? 'Baseline' : delta(row.accuracyDelta)}</td>
            <td>{row.brierScore == null ? '—' : Number(row.brierScore).toFixed(3)}</td><td>{row.changedDecisions == null ? '—' : Number(row.changedDecisions).toLocaleString()}</td>
            <td>{row.netAdditionalCorrect == null ? '—' : `${Number(row.netAdditionalCorrect) >= 0 ? '+' : ''}${row.netAdditionalCorrect}`}</td>
            <td className={row.statisticallyClearAt95 ? 'font-black text-emerald-300' : 'text-amber-200'}>{row.role === 'CONTROL' ? 'Control' : row.statisticallyClearAt95 ? 'Clear at 95%' : row.pValue == null ? 'Not available' : `p ${Number(row.pValue).toFixed(3)}`}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>

    <section className="rounded-[30px] border border-white/10 bg-zinc-950 p-5 md:p-6">
      <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.22em] text-sky-300"><ShieldCheck size={18} /> Research pipeline</div>
      <div className="mt-5 grid gap-3 lg:grid-cols-2">
        {(data?.pipeline || []).map((stage: any) => <article key={stage.order} className="flex gap-4 rounded-2xl border border-white/10 bg-white/[.025] p-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/5 text-lg font-black text-sky-300">{stage.order}</div>
          <div><div className="flex flex-wrap items-center gap-2"><h4 className="font-black text-white">{stage.name}</h4><Status value={stage.status} /></div><p className="mt-1 text-sm leading-5 text-zinc-500">{stage.detail}</p></div>
        </article>)}
      </div>
    </section>

    <section className="rounded-[30px] border border-violet-300/20 bg-violet-400/[.045] p-5 md:p-6">
      <div className="text-xs font-black uppercase tracking-[.22em] text-violet-300">Next experiments</div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">{(data?.nextExperiments || []).map((item: string) => <div key={item} className="flex gap-3 rounded-2xl border border-white/10 bg-black/20 p-4 text-sm leading-6 text-zinc-300"><ArrowRight className="mt-1 shrink-0 text-violet-300" size={17} />{item}</div>)}</div>
    </section>
  </section>;
}

function Status({ value }: { value: string }) {
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-[9px] font-black uppercase tracking-wider ${statusClasses[value] || statusClasses.GATED}`}>{String(value || 'UNKNOWN').replaceAll('_', ' ')}</span>;
}

function DiscoveryMetric({ label, value }: { label: string; value?: number }) {
  return <div className="bg-zinc-950 p-4 md:p-5"><div className="text-[10px] font-black uppercase tracking-[.18em] text-zinc-500">{label}</div><div className="mt-2 text-3xl font-black text-white">{Number(value || 0).toLocaleString()}</div></div>;
}

function ExperimentCard({ row }: { row: any }) {
  return <article className="rounded-2xl border border-white/10 bg-white/[.025] p-4">
    <div className="flex items-start justify-between gap-3"><div className="font-black text-white">{row.name}</div><Status value={row.status} /></div>
    <div className="mt-4 grid grid-cols-2 gap-2">
      <Mini label="Accuracy" value={pct(row.accuracy)} /><Mini label="vs PPR" value={row.role === 'CONTROL' ? 'Baseline' : delta(row.accuracyDelta)} />
      <Mini label="Brier" value={row.brierScore == null ? '—' : Number(row.brierScore).toFixed(3)} /><Mini label="Changed calls" value={row.changedDecisions == null ? '—' : Number(row.changedDecisions).toLocaleString()} />
    </div>
    <div className="mt-3 flex items-center gap-2 text-xs text-zinc-500">{row.statisticallyClearAt95 ? <CheckCircle2 className="text-emerald-300" size={15} /> : <BrainCircuit className="text-amber-200" size={15} />}{row.role === 'CONTROL' ? 'Reference model' : row.statisticallyClearAt95 ? 'Statistically clear at 95%' : row.pValue == null ? 'Confidence not available' : `Not conclusive yet (p ${Number(row.pValue).toFixed(3)})`}</div>
  </article>;
}

function Mini({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-black/30 p-3"><div className="text-[9px] font-black uppercase tracking-wider text-zinc-500">{label}</div><div className="mt-1 text-lg font-black text-white">{value}</div></div>;
}

function LiveMetric({ label, value, change, detail, tone }: { label: string; value: number; change?: number; detail: string; tone: 'green'|'blue'|'amber'|'violet'|'zinc' }) {
  const colors = { green: 'text-emerald-300', blue: 'text-sky-300', amber: 'text-amber-300', violet: 'text-violet-300', zinc: 'text-zinc-100' };
  return <div className="bg-zinc-950 p-4 md:p-5"><div className="text-[10px] font-black uppercase tracking-[.18em] text-zinc-500">{label}</div><div className={`mt-2 text-3xl font-black ${colors[tone]}`}>{value.toLocaleString()}</div><div className="mt-1 min-h-5 text-xs text-zinc-500">{change ? <span className="mr-2 font-black text-emerald-300">+{change.toLocaleString()} live</span> : null}{detail}</div></div>;
}

function QueueStat({ label, value }: { label: string; value?: number }) {
  return <div className="rounded-xl bg-black/25 p-2"><div className="text-base font-black text-white">{Number(value || 0).toLocaleString()}</div><div className="text-[9px] font-black uppercase tracking-wider text-zinc-600">{label}</div></div>;
}

import { Award, ChevronDown, RefreshCw, Sparkles, Trophy } from 'lucide-react';
import { useEffect, useState } from 'react';
import { fetchTournamentReportCards, generateTournamentReportCards } from '../lib/api';

const categoryLabels: Record<string, string> = {
  performance: 'Performance', expectation: 'Vs Expectation', consistency: 'Consistency',
  clutch: 'Clutch', resilience: 'Resilience',
};

export default function TournamentReportCards({ eventId }: { eventId: string }) {
  const [data, setData] = useState<any>();
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    fetchTournamentReportCards(eventId)
      .then(setData)
      .catch(error => setError(error.message))
      .finally(() => setLoading(false));
  }, [eventId]);

  async function generate() {
    setGenerating(true);
    setError('');
    try { setData(await generateTournamentReportCards(eventId)); }
    catch (error: any) { setError(error.message || 'Report cards could not be generated.'); }
    finally { setGenerating(false); }
  }

  const ready = data?.status === 'COMPLETE' || data?.status === 'LIVE';
  return <section className="mt-4 overflow-hidden rounded-[28px] border border-violet-300/20 bg-zinc-950">
    <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 p-5">
      <div>
        <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.2em] text-violet-300"><Sparkles size={17}/> Tournament report cards</div>
        <h2 className="mt-2 text-2xl font-black text-white">Who played best—and who beat expectations?</h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-zinc-400">On-demand grading for every recorded game and the full tournament. Nothing runs until you select generate or recalculate.</p>
      </div>
      <button onClick={generate} disabled={generating} className="inline-flex min-h-12 items-center gap-2 rounded-xl border border-violet-300 bg-violet-300 px-5 font-black text-black active:translate-y-1 disabled:opacity-60">
        <RefreshCw className={generating ? 'animate-spin' : ''} size={18}/>{ready ? 'Recalculate report cards' : 'Generate report cards'}
      </button>
    </div>
    {error && <div className="m-5 rounded-xl border border-red-400/30 bg-red-950/30 p-4 text-red-200">{error}</div>}
    {data?.dataPreparationNote && <div className="mx-5 mt-5 rounded-xl border border-amber-300/25 bg-amber-300/[.08] p-4 text-sm leading-6 text-amber-100">{data.dataPreparationNote}</div>}
    {loading && <div className="p-8 text-center text-zinc-400">Checking for a saved report…</div>}
    {!loading && !ready && <div className="p-8 text-center text-zinc-400">No report has been generated for this event yet.</div>}
    {ready && <div className="space-y-5 p-5">
      <div className="grid gap-4 lg:grid-cols-2">
        <MvpCard title="Tournament MVP" icon={<Award size={22}/>} subject={data.playerMvp} player/>
        {data.teamMvp && <MvpCard title="MVP Team" icon={<Trophy size={22}/>} subject={data.teamMvp}/>} 
      </div>
      <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
        <div className="text-xs font-black uppercase tracking-[.18em] text-amber-300">Tournament superlatives</div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {(data.highlights || []).slice(0, 12).map((item: any, index: number) => <div key={`${item.title}:${index}`} className="rounded-xl bg-white/[.04] p-3">
            <div className="text-xs font-black uppercase tracking-wide text-zinc-500">{item.title}</div>
            <div className="mt-1 font-black text-white">{item.playerName}</div>
            {item.opponentName && <div className="mt-1 text-xs font-bold text-zinc-400"><span className="uppercase tracking-wider text-zinc-600">Opponent</span> {item.opponentName}</div>}
            <div className="mt-1 text-sm font-bold text-cyan-300">{item.value}</div>
            {item.matchId && <div className="mt-1 text-xs text-zinc-600">Match {item.matchId} · Game {item.gameId}</div>}
          </div>)}
        </div>
      </div>
      <div>
        <div className="mb-3 text-xs font-black uppercase tracking-[.18em] text-violet-300">Final player report cards</div>
        <div className="space-y-3">
          {(data.players || []).map((player: any) => <PlayerCard key={player.playerId} player={player}/>) }
        </div>
      </div>
      <div className="rounded-xl border border-white/10 bg-white/[.03] p-4 text-xs leading-5 text-zinc-500">
        Generated {formatTime(data.generatedAt)} · {data.status === 'LIVE' ? 'Live tournament snapshot' : 'Final tournament report'} · Final tournament grade is 75% performance grade, 15% tournament depth and 10% sustained evidence. The performance grade evaluates performance, expectation, consistency, clutch and resilience.
      </div>
    </div>}
  </section>;
}

function MvpCard({ title, icon, subject, player = false }: { title: string; icon: any; subject: any; player?: boolean }) {
  if (!subject) return null;
  const name = player ? subject.playerName : subject.teamName;
  return <div className="rounded-2xl border border-amber-300/25 bg-gradient-to-br from-amber-300/10 to-violet-300/[.06] p-5">
    <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.18em] text-amber-300">{icon}{title}</div>
    <div className="mt-3 text-2xl font-black text-white">{name}</div>
    <div className="mt-3 flex items-end gap-3"><div className="text-5xl font-black text-amber-300">{number(subject.overallScore, 1)}</div>{subject.grade && <div className="pb-1 text-2xl font-black text-violet-300">{subject.grade}</div>}</div>
    <div className="mt-1 text-xs font-bold uppercase tracking-wider text-zinc-500">Final tournament / MVP grade</div>
    {subject.performanceGrade != null && <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs font-bold text-zinc-400"><span>Performance {number(subject.performanceGrade, 1)}</span><span>Depth {number(subject.depthScore, 1)}</span><span>Sustained evidence {number(subject.sustainedEvidenceScore, 1)}</span></div>}
  </div>;
}

function PlayerCard({ player }: { player: any }) {
  return <details className="overflow-hidden rounded-2xl border border-white/10 bg-zinc-900">
    <summary className="flex cursor-pointer list-none items-center gap-3 p-4">
      <div className="w-9 text-xl font-black text-cyan-300">#{player.rank}</div>
      <div className="min-w-0 flex-1"><div className="truncate text-lg font-black text-white">{player.playerName}</div><div className="text-xs text-zinc-500">{player.games} games · {player.rounds} rounds · {number(player.ppr, 2)} PPR · {signed(player.pprVsExpected)} vs expected</div></div>
      <div className="text-right"><div className="text-2xl font-black text-amber-300">{number(player.overallScore, 1)}</div><div className="text-xs font-black text-violet-300">{player.grade}</div></div>
      <ChevronDown className="text-zinc-500" size={18}/>
    </summary>
    <div className="border-t border-white/10 p-4">
      <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Metric label="Performance grade" value={number(player.performanceGrade, 1)}/><Metric label="Tournament depth" value={number(player.depthScore, 1)}/><Metric label="Sustained evidence" value={number(player.sustainedEvidenceScore, 1)}/>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">{Object.entries(player.categoryScores || {}).map(([key, value]) => <Metric key={key} label={categoryLabels[key] || key} value={number(value, 1)}/>)}</div>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Metric label="DPR" value={signed(player.dpr)}/><Metric label="4-bagger rate" value={percent(player.fourBaggerRate)}/><Metric label="Clutch rounds" value={player.clutchRounds}/><Metric label="Large swings conceded" value={player.largeSwingsConceded}/>
      </div>
      <div className="mt-4 text-xs font-black uppercase tracking-[.16em] text-zinc-500">Game-by-game grades</div>
      <div className="mt-2 grid gap-2 md:grid-cols-2">{(player.matchReportCards || []).map((card: any) => <div key={`${card.matchId}:${card.gameId}`} className="rounded-xl bg-black/25 p-3">
        <div className="flex items-center justify-between"><div className="font-black text-white">Match {card.matchId} · Game {card.gameId}</div><div className="text-xl font-black text-amber-300">{number(card.overallScore, 1)}</div></div>
        <div className="mt-1 text-xs text-zinc-500">{number(card.ppr, 2)} PPR · {signed(card.dpr)} DPR · {signed(card.pprVsExpected)} vs expected · {card.fourBaggers} four-baggers</div>
        {card.throwingPerformanceGrade != null && <div className="mt-2 grid grid-cols-2 gap-2"><Metric label="Throwing quality" value={number(card.throwingPerformanceGrade, 1)}/><Metric label="Competitive impact" value={number(card.competitiveImpactGrade, 1)}/></div>}
        {card.observedPerformanceScore != null && <div className="mt-2 text-xs font-semibold text-zinc-400">Observed performance {number(card.observedPerformanceScore, 1)} · {card.sampleRounds ?? card.rounds} rounds · {percent(card.sampleConfidence)} evidence weight</div>}
      </div>)}</div>
    </div>
  </details>;
}

function Metric({ label, value }: { label: string; value: any }) { return <div className="rounded-xl bg-black/30 p-3"><div className="text-xl font-black text-white">{value}</div><div className="mt-1 text-[10px] font-black uppercase tracking-wider text-zinc-500">{label}</div></div>; }
function number(value: any, digits = 1) { const n = Number(value); return Number.isFinite(n) ? n.toFixed(digits) : '—'; }
function signed(value: any) { const n = Number(value); return Number.isFinite(n) ? `${n > 0 ? '+' : ''}${n.toFixed(2)}` : '—'; }
function percent(value: any) { const n = Number(value); return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : '—'; }
function formatTime(value: any) { const date = new Date(value); return Number.isNaN(date.getTime()) ? 'unknown time' : date.toLocaleString(); }

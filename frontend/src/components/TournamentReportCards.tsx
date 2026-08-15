import { Award, ChevronDown, RefreshCw, Sparkles, Trophy } from 'lucide-react';
import { useEffect, useState } from 'react';
import { fetchEvent, fetchTournamentReportCards, generateSingleGameReportCard, generateTournamentReportCards } from '../lib/api';
import { ShareMatchGradeButton, SharePlayerGradesButton, ShareTeamGradesButton } from './ShareSnapshotButton';

const categoryLabels: Record<string, string> = {
  performance: 'Performance', expectation: 'Vs Expectation', consistency: 'Consistency',
  clutch: 'Clutch', resilience: 'Resilience',
};

function recognizableTeamName(team: any, fallback: string) {
  const playerNames = (team?.players || [])
    .map((player: any) => player?.displayName || [player?.firstName, player?.lastName].filter(Boolean).join(' '))
    .filter(Boolean);
  const name = playerNames.join(' / ') || String(team?.name || '').trim();
  return name && !/^team\s*-?\d+$/i.test(name) ? name : fallback;
}

function gameOptionLabel(match: any, game: any) {
  const top = recognizableTeamName(match?.teams?.top, 'Team A');
  const bottom = recognizableTeamName(match?.teams?.bottom, 'Team B');
  const context = [
    match?.roundDescription || `Match ${match?.matchId}`,
    `Match ${match?.matchId}`,
    Number(game?.gameId || 1) > 1 ? `Game ${game.gameId}` : '',
    match?.courtId && String(match.courtId) !== '-1' ? `Court ${match.courtId}` : '',
  ].filter(Boolean).join(' · ');
  return `${top} vs ${bottom} — ${context}`;
}

export default function TournamentReportCards({ eventId }: { eventId: string }) {
  const [data, setData] = useState<any>();
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [eventDetails, setEventDetails] = useState<any>();
  const [gameOptions, setGameOptions] = useState<{ matchId: string; gameId: number; label: string; match: any; game: any }[]>([]);
  const [selectedGame, setSelectedGame] = useState('');
  const [gameGenerating, setGameGenerating] = useState(false);
  const [gameReport, setGameReport] = useState<any>();
  const [gameError, setGameError] = useState('');
  const [error, setError] = useState('');
  const [playerSort, setPlayerSort] = useState<'performance' | 'mvp'>('performance');
  const [queuedMessage, setQueuedMessage] = useState('');

  useEffect(() => {
    setLoading(true);
    fetchTournamentReportCards(eventId)
      .then(setData)
      .catch(error => setError(error.message))
      .finally(() => setLoading(false));
    fetchEvent(eventId, false).then(event => {
      setEventDetails(event);
      const options = event.matches.flatMap(match => (match.games || []).map(game => ({
        matchId: String(match.matchId),
        gameId: Number(game.gameId || 1),
        label: gameOptionLabel(match, game),
        match, game,
      })));
      setGameOptions(options);
      setSelectedGame(options.length ? `${options[0].matchId}:${options[0].gameId}` : '');
    }).catch(() => setGameOptions([]));
  }, [eventId]);

  async function generate(force = false) {
    if (force && !window.confirm('Force a new report version using the same game results? The current saved version will be preserved for audit.')) return;
    setGenerating(true);
    setError('');
    try {
      await generateTournamentReportCards(eventId, force);
      setQueuedMessage('Grading queued. You can leave this page; the saved report will appear here when it is ready.');
    }
    catch (error: any) { setError(error.message || 'Report cards could not be generated.'); }
    finally { setGenerating(false); }
  }

  useEffect(() => {
    if (!queuedMessage) return;
    const timer = window.setInterval(() => {
      fetchTournamentReportCards(eventId).then(result => {
        if (result?.status === 'COMPLETE' || result?.status === 'LIVE') {
          setData(result);
          setQueuedMessage('');
        }
      }).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [eventId, queuedMessage]);

  async function gradeOneGame() {
    const option = gameOptions.find(item => `${item.matchId}:${item.gameId}` === selectedGame);
    if (!option) return;
    setGameGenerating(true);
    setGameError('');
    try { setGameReport(await generateSingleGameReportCard(eventId, option.matchId, option.gameId)); }
    catch (error: any) { setGameError(error.message || 'This game could not be graded.'); }
    finally { setGameGenerating(false); }
  }

  const ready = data?.status === 'COMPLETE' || data?.status === 'LIVE';
  const updateAvailable = Boolean(data?.updateAvailable);
  const gradingUpdateAvailable = Boolean(data?.gradingUpdateAvailable);
  const showPrimaryAction = !ready || updateAvailable || gradingUpdateAvailable;
  const sortedPlayers = [...(data?.players || [])].sort((left: any, right: any) => {
    const leftScore = playerSort === 'mvp' ? Number(left.mvpScore ?? left.overallScore ?? 0) : Number(left.performanceGrade ?? left.overallScore ?? 0);
    const rightScore = playerSort === 'mvp' ? Number(right.mvpScore ?? right.overallScore ?? 0) : Number(right.performanceGrade ?? right.overallScore ?? 0);
    return rightScore - leftScore || String(left.playerName || '').localeCompare(String(right.playerName || ''));
  });
  const sortedTeams = [...(data?.teams || [])].sort((left: any, right: any) => {
    const leftScore = Number(left.teamGrade ?? left.mvpScore ?? left.overallScore ?? 0);
    const rightScore = Number(right.teamGrade ?? right.mvpScore ?? right.overallScore ?? 0);
    return rightScore - leftScore || String(left.teamName || '').localeCompare(String(right.teamName || ''));
  });
  const eventName = eventDetails?.name || eventDetails?.eventName || data?.event?.event_name || `ACL Event ${eventId}`;
  const selectedGameDetails = gameOptions.find(item => `${item.matchId}:${item.gameId}` === selectedGame);
  return <section className="mt-4 overflow-hidden rounded-[28px] border border-violet-300/20 bg-zinc-950">
    <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 p-5">
      <div>
        <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.2em] text-violet-300"><Sparkles size={17}/> Tournament report cards</div>
        <h2 className="mt-2 text-2xl font-black text-white">Who played best—and who beat expectations?</h2>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-zinc-400">On-demand grading for every recorded game and the full tournament. Nothing runs until you select generate or recalculate.</p>
      </div>
      <div className="flex flex-col items-end gap-2">
        {showPrimaryAction && <button onClick={() => generate(false)} disabled={generating} className="inline-flex min-h-12 items-center gap-2 rounded-xl border border-violet-300 bg-violet-300 px-5 font-black text-black active:translate-y-1 disabled:opacity-60">
          <RefreshCw className={generating ? 'animate-spin' : ''} size={18}/>{updateAvailable ? `Include ${data.newCompletedGameCount} new completed game${data.newCompletedGameCount === 1 ? '' : 's'}` : gradingUpdateAvailable ? 'Apply corrected grading model' : 'Generate report cards'}
        </button>}
        {ready && !updateAvailable && !gradingUpdateAvailable && <div className="text-sm font-bold text-emerald-300">Up to date · {data.incorporatedGameCount || data.matches?.length || 0} games incorporated</div>}
        {ready && <details className="text-right"><summary className="cursor-pointer text-xs font-bold text-zinc-500">Advanced</summary><button onClick={() => generate(true)} disabled={generating} className="mt-2 rounded-lg border border-white/15 px-3 py-2 text-xs font-black text-zinc-300 disabled:opacity-50">Force a new report version</button></details>}
      </div>
    </div>
    <div className="border-b border-white/10 bg-violet-300/[.035] p-5">
      <div className="text-xs font-black uppercase tracking-[.18em] text-cyan-300">Grade one game only</div>
      <p className="mt-1 text-sm leading-6 text-zinc-400">Calculates the selected game without grading or replacing the tournament as a whole.</p>
      <div className="mt-3 flex flex-col gap-3 sm:flex-row">
        <select value={selectedGame} onChange={event => setSelectedGame(event.target.value)} disabled={!gameOptions.length || gameGenerating} className="min-h-12 min-w-0 flex-1 rounded-xl border border-white/15 bg-zinc-900 px-4 font-bold text-white">
          {!gameOptions.length && <option value="">No games published yet</option>}
          {gameOptions.map(option => <option key={`${option.matchId}:${option.gameId}`} value={`${option.matchId}:${option.gameId}`}>{option.label}</option>)}
        </select>
        <button onClick={gradeOneGame} disabled={!selectedGame || gameGenerating} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-cyan-300 bg-cyan-300 px-5 font-black text-black active:translate-y-1 disabled:opacity-50">
          <RefreshCw className={gameGenerating ? 'animate-spin' : ''} size={18}/>{gameGenerating ? 'Grading selected game…' : 'Grade selected game'}
        </button>
      </div>
      {gameError && <div className="mt-3 rounded-xl border border-red-400/30 bg-red-950/30 p-4 text-red-200">{gameError}</div>}
      {gameReport?.status === 'COMPLETE' && <SingleGameReport report={gameReport} eventId={eventId} eventName={eventName} option={selectedGameDetails}/>}
    </div>
    {error && <div className="m-5 rounded-xl border border-red-400/30 bg-red-950/30 p-4 text-red-200">{error}</div>}
    {queuedMessage && <div className="m-5 rounded-xl border border-sky-300/30 bg-sky-950/30 p-4 font-bold text-sky-100">{queuedMessage}</div>}
    {data?.dataPreparationNote && <div className="mx-5 mt-5 rounded-xl border border-amber-300/25 bg-amber-300/[.08] p-4 text-sm leading-6 text-amber-100">{data.dataPreparationNote}</div>}
    {data?.status === 'COMPLETE' && <div className="mx-5 mt-5 rounded-xl border border-emerald-300/25 bg-emerald-300/[.07] p-4 text-sm leading-6 text-emerald-100"><span className="font-black">Final grades saved server-side.</span> Every phone and computer sees this same result. A new version is offered only when another completed game is available; forced reruns remain under Advanced.</div>}
    {loading && <div className="p-8 text-center text-zinc-400">Checking for a saved report…</div>}
    {!loading && !ready && <div className="p-8 text-center text-zinc-400">No report has been generated for this event yet.</div>}
    {ready && <div className="space-y-5 p-5">
      <div className="grid gap-4 lg:grid-cols-2">
        <MvpCard title="Tournament MVP" icon={<Award size={22}/>} subject={data.playerMvp} player/>
        {data.teamMvp && <MvpCard title="Top Graded Team" icon={<Trophy size={22}/>} subject={data.teamMvp}/>}
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
      {sortedTeams.length > 0 && <div>
        <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="text-xs font-black uppercase tracking-[.18em] text-amber-300">Final team report cards</div>
            <div className="mt-1 max-w-3xl text-xs font-semibold leading-5 text-zinc-500">Every team receives one Team Grade combining both players' performance, sustained evidence, and tournament advancement. Combined Player Grade remains visible inside each card to explain the performance component.</div>
          </div>
          <ShareTeamGradesButton input={{ eventId, eventName, generatedAt: data.generatedAt, teams: sortedTeams }}/>
        </div>
        <div className="space-y-3">
          {sortedTeams.map((team: any, index: number) => <TeamCard key={team.teamId || team.teamName} team={{...team, rank: index + 1}}/>)}
        </div>
      </div>}
      <div>
        <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="text-xs font-black uppercase tracking-[.18em] text-violet-300">Final player report cards</div>
            <div className="mt-1 text-xs font-semibold text-zinc-500">Ranked by {playerSort === 'performance' ? 'individual player grade' : 'tournament MVP score'}.</div>
          </div>
          <div className="grid grid-cols-2 gap-2 rounded-xl bg-black/30 p-1" role="group" aria-label="Sort player report cards">
            <button type="button" aria-pressed={playerSort === 'performance'} onClick={() => setPlayerSort('performance')} className={`min-h-11 rounded-lg border-2 px-4 text-sm font-black transition active:translate-y-0.5 ${playerSort === 'performance' ? 'border-violet-100 bg-violet-300 text-black shadow-[0_0_24px_rgba(196,181,253,.45)]' : 'border-white/10 text-zinc-300 hover:bg-white/[.06]'}`}>{playerSort === 'performance' ? '✓ ' : ''}Player Grade</button>
            <button type="button" aria-pressed={playerSort === 'mvp'} onClick={() => setPlayerSort('mvp')} className={`min-h-11 rounded-lg border-2 px-4 text-sm font-black transition active:translate-y-0.5 ${playerSort === 'mvp' ? 'border-amber-100 bg-amber-300 text-black shadow-[0_0_24px_rgba(252,211,77,.45)]' : 'border-white/10 text-zinc-300 hover:bg-white/[.06]'}`}>{playerSort === 'mvp' ? '✓ ' : ''}MVP Score</button>
          </div>
          <SharePlayerGradesButton input={{ eventId, eventName, generatedAt: data.generatedAt, players: data.players || [] }}/>
        </div>
        <div className="space-y-3">
          {sortedPlayers.map((player: any, index: number) => <PlayerCard key={player.playerId} player={{...player, rank: index + 1}} sortMode={playerSort}/>) }
        </div>
      </div>
      <div className="rounded-xl border border-white/10 bg-white/[.03] p-4 text-xs leading-5 text-zinc-500">
        Generated {formatTime(data.generatedAt)} · {data.status === 'LIVE' ? 'Live tournament snapshot' : 'Final tournament report'} · Individual Player Grade measures play only; individual MVP Score also considers tournament depth and sustained evidence. Teams receive one Team Grade because team performance and advancement describe the same competitive result.
      </div>
    </div>}
  </section>;
}

function TeamCard({ team }: { team: any }) {
  return <details className="overflow-hidden rounded-2xl border border-white/10 bg-zinc-900">
    <summary className="flex cursor-pointer list-none items-center gap-3 p-4">
      <div className="w-9 text-xl font-black text-cyan-300">#{team.rank}</div>
      <div className="min-w-0 flex-1">
        <div className="text-lg font-black text-white">{team.teamName}</div>
        <div className="mt-1 text-xs text-zinc-500">{(team.players || []).map((player: any) => `ACL #${player.playerId}`).join(' / ')}</div>
      </div>
      <div className="text-right">
        <div className="text-2xl font-black text-amber-300">{number(team.teamGrade ?? team.mvpScore ?? team.overallScore, 1)}</div>
        <div className="text-xs font-black text-amber-200">{team.grade || ''} Team Grade</div>
      </div>
      <ChevronDown className="text-zinc-500" size={18}/>
    </summary>
    <div className="border-t border-white/10 p-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Metric label="Team grade" value={`${number(team.teamGrade ?? team.mvpScore ?? team.overallScore, 1)} ${team.grade || ''}`}/>
        <Metric label="Combined player grade" value={number(team.combinedPlayerGrade ?? team.performanceGrade, 1)}/>
        <Metric label="Tournament depth" value={number(team.depthScore, 1)}/>
        <Metric label="Sustained evidence" value={number(team.sustainedEvidenceScore, 1)}/>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <Metric label="Combined vs expectation" value={number(team.expectationScore, 1)}/>
        <Metric label="Combined performance" value={number(team.performanceScore, 1)}/>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {(team.players || []).map((player: any) => <div key={player.playerId} className="rounded-lg border border-white/10 bg-black/25 px-3 py-2 text-sm font-bold text-zinc-200">{player.playerName} <span className="text-xs text-zinc-500">ACL #{player.playerId}</span></div>)}
      </div>
    </div>
  </details>;
}

function SingleGameReport({ report, eventId, eventName, option }: { report: any; eventId: string; eventName: string; option?: any }) {
  return <div className="mt-4 rounded-2xl border border-cyan-300/20 bg-black/30 p-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div><div className="text-xs font-black uppercase tracking-[.18em] text-cyan-300">Single-game report</div><div className="mt-1 text-lg font-black text-white">Match {report.matchId} · Game {report.gameId}</div></div>
      <div className="rounded-lg bg-cyan-300/10 px-3 py-2 text-xs font-black uppercase tracking-wider text-cyan-200">Tournament report unchanged</div>
      <ShareMatchGradeButton input={{ eventId, eventName, report, match: option?.match, game: option?.game, label: option?.label }}/>
    </div>
    <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {(report.players || []).map((player: any) => <div key={player.playerId} className="rounded-xl bg-white/[.05] p-3">
        <div className="flex items-start justify-between gap-2"><div><div className="font-black text-white">#{player.rank} {player.playerName}</div><div className="text-xs text-zinc-500">{player.rounds} rounds · {number(player.ppr, 2)} PPR</div></div><div className="text-2xl font-black text-amber-300">{number(player.overallScore, 1)}</div></div>
        <div className="mt-2 text-xs font-semibold text-zinc-400">Throwing {number(player.throwingPerformanceGrade, 1)} · Impact {number(player.competitiveImpactGrade, 1)} · {percent(player.sampleConfidence)} evidence</div>
      </div>)}
    </div>
  </div>;
}

function MvpCard({ title, icon, subject, player = false }: { title: string; icon: any; subject: any; player?: boolean }) {
  if (!subject) return null;
  const name = player ? subject.playerName : subject.teamName;
  const primaryScore = player ? subject.mvpScore ?? subject.overallScore : subject.teamGrade ?? subject.mvpScore ?? subject.overallScore;
  return <div className="rounded-2xl border border-amber-300/25 bg-gradient-to-br from-amber-300/10 to-violet-300/[.06] p-5">
    <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.18em] text-amber-300">{icon}{title}</div>
    <div className="mt-3 text-2xl font-black text-white">{name}</div>
    <div className="mt-3 flex items-end gap-3"><div className="text-5xl font-black text-amber-300">{number(primaryScore, 1)}</div></div>
    <div className="mt-1 text-xs font-bold uppercase tracking-wider text-zinc-500">{player ? 'MVP score' : `${subject.grade || ''} Team Grade`}</div>
    {subject.performanceGrade != null && <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs font-bold text-zinc-400"><span>{player ? 'Player grade' : 'Combined player grade'} {number(player ? subject.performanceGrade : subject.combinedPlayerGrade ?? subject.performanceGrade, 1)} {player ? subject.grade : ''}</span><span>Depth {number(subject.depthScore, 1)}</span><span>Sustained evidence {number(subject.sustainedEvidenceScore, 1)}</span></div>}
  </div>;
}

function PlayerCard({ player, sortMode }: { player: any; sortMode: 'performance' | 'mvp' }) {
  const showingMvp = sortMode === 'mvp';
  const playerGrade = player.performanceGrade ?? player.overallScore;
  const mvpScore = player.mvpScore ?? player.overallScore;
  return <details className="overflow-hidden rounded-2xl border border-white/10 bg-zinc-900">
    <summary className="flex cursor-pointer list-none items-center gap-3 p-4">
      <div className="w-9 text-xl font-black text-cyan-300">#{player.rank}</div>
      <div className="min-w-0 flex-1"><div className="truncate text-lg font-black text-white">{player.playerName}</div><div className="text-xs text-zinc-500">{player.games} games · {player.rounds} rounds · {number(player.ppr, 2)} PPR · {signed(player.pprVsExpected)} vs expected</div></div>
      <div className="text-right">
        <div className={`text-2xl font-black ${showingMvp ? 'text-amber-300' : 'text-violet-300'}`}>{number(showingMvp ? mvpScore : playerGrade, 1)}</div>
        <div className={`text-xs font-black ${showingMvp ? 'text-amber-200' : 'text-violet-200'}`}>{showingMvp ? 'MVP Score' : `${player.grade} Player Grade`}</div>
        <div className="mt-1 text-[10px] font-bold uppercase tracking-wider text-zinc-500">{showingMvp ? `Player Grade ${number(playerGrade, 1)} ${player.grade || ''}` : `MVP Score ${number(mvpScore, 1)}`}</div>
      </div>
      <ChevronDown className="text-zinc-500" size={18}/>
    </summary>
    <div className="border-t border-white/10 p-4">
      <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Metric label="Player performance grade" value={`${number(player.performanceGrade, 1)} ${player.performanceGradeLetter || player.grade || ''}`}/><Metric label="MVP score" value={number(player.mvpScore ?? player.overallScore, 1)}/><Metric label="Tournament depth" value={number(player.depthScore, 1)}/><Metric label="Sustained evidence" value={number(player.sustainedEvidenceScore, 1)}/>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">{Object.entries(player.categoryScores || {}).map(([key, value]) => <Metric key={key} label={categoryLabels[key] || key} value={number(value, 1)}/>)}</div>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Metric label="DPR" value={signed(player.dpr)}/><Metric label="4-bagger rate" value={percent(player.fourBaggerRate)}/><Metric label="Clutch rounds" value={player.clutchRounds}/><Metric label="Large swings conceded" value={player.largeSwingsConceded}/>
      </div>
      {player.expectationSource === 'NO_PRIOR_HISTORY_NEUTRAL' && <div className="mt-3 rounded-xl border border-amber-300/25 bg-amber-300/[.07] p-3 text-sm leading-6 text-amber-100">
        <span className="font-black">No prior history for player ID {player.playerId}.</span> Expectation was held neutral and this player received no above-expectation credit. {(player.possibleHistoricalAccounts || []).length > 0 && <span> Possible same-name historical account{player.possibleHistoricalAccounts.length === 1 ? '' : 's'}: {player.possibleHistoricalAccounts.map((account: any) => `${account.playerName} #${account.playerId} (${account.rounds} rounds, ${number(account.ppr, 2)} PPR)`).join('; ')}. These were not merged or used in grading.</span>}
      </div>}
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

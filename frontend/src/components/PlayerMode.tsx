import { Activity, ArrowLeftRight, Gauge, Target, UserRound } from 'lucide-react';
import type { Match, PlayerStat, RoundRow } from '../lib/api';

export function PlayerMode({
  match,
  players,
  rounds,
  playerId,
  winProbability,
}: {
  match: Match;
  players: PlayerStat[];
  rounds: RoundRow[];
  playerId: string;
  winProbability?: any;
}) {
  const game = match.activeGame || match.games?.[0];
  const topScore = Number(game?.score?.top ?? match.score.top ?? 0);
  const bottomScore = Number(game?.score?.bottom ?? match.score.bottom ?? 0);
  const me = players.find(player => String(player.id) === String(playerId));
  const myTeamId = String(me?.teamId || '');
  const topIsMine = myTeamId === String(match.teams.top.id);
  const myScore = topIsMine ? topScore : bottomScore;
  const opponentScore = topIsMine ? bottomScore : topScore;
  const myTeam = topIsMine ? match.teams.top : match.teams.bottom;
  const opponentTeam = topIsMine ? match.teams.bottom : match.teams.top;
  const teammate = players.find(player => String(player.teamId) === myTeamId && String(player.id) !== String(playerId));
  const latestRound = rounds.at(-1);
  const latestProbability = winProbability?.points?.at(-1);
  const myProbability = latestProbability
    ? (topIsMine ? Number(latestProbability.topWinProbability) : Number(latestProbability.bottomWinProbability)) * 100
    : undefined;
  const nextFirstThrowTeamId = String(latestRound?.gameState?.nextFirstThrowTeamId || latestRound?.scoringTeamId || '');
  const nextThrow = nextFirstThrowTeamId
    ? nextFirstThrowTeamId === myTeamId ? 'Your team throws first' : `${opponentTeam.name} throws first`
    : 'First throw not known yet';
  const margin = myScore - opponentScore;

  return (
    <section className="space-y-3 lg:hidden">
      <div className={`overflow-hidden rounded-[26px] border ${margin >= 0 ? 'border-emerald-300/30 bg-emerald-950/25' : 'border-red-300/30 bg-red-950/20'}`}>
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <div>
            <div className="text-xs font-black uppercase tracking-[.2em] text-amber-300">Player Mode</div>
            <div className="mt-1 text-sm font-bold text-zinc-300">{match.roundDescription || 'Bracket match'} · Court {court(match.courtId)}</div>
          </div>
          <span className={`rounded-lg px-3 py-1 text-xs font-black ${match.status === 'live' ? 'bg-emerald-400 text-black' : match.status === 'completed' ? 'bg-blue-400 text-black' : 'bg-amber-300 text-black'}`}>
            {match.status === 'live' ? 'LIVE' : match.status === 'completed' ? 'FINAL' : 'UP NEXT'}
          </span>
        </div>

        <div className="p-4 text-center">
          <div className="text-sm font-black text-sky-200">{myTeam.name}</div>
          <div className="mt-2 flex items-center justify-center gap-5">
            <div className="text-7xl font-black leading-none text-white">{myScore}</div>
            <div className="text-xl font-black text-zinc-600">–</div>
            <div className="text-7xl font-black leading-none text-zinc-400">{opponentScore}</div>
          </div>
          <div className={`mt-3 text-lg font-black ${margin > 0 ? 'text-emerald-300' : margin < 0 ? 'text-red-300' : 'text-amber-200'}`}>
            {margin > 0 ? `Leading by ${margin}` : margin < 0 ? `Trailing by ${Math.abs(margin)}` : 'Match tied'}
          </div>
          <div className="mt-1 text-sm font-bold text-zinc-500">vs {opponentTeam.name}</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <PlayerTile icon={<UserRound size={18}/>} label="You" value={me?.name || `Player ${playerId}`} detail={teammate ? `with ${teammate.name}` : 'Singles'} tone="sky" />
        <PlayerTile icon={<Target size={18}/>} label="Live PPR" value={number(me?.ppr)} detail={`${me?.rounds || rounds.length} rounds`} tone="amber" />
        <PlayerTile icon={<Gauge size={18}/>} label="Win chance" value={myProbability == null || !Number.isFinite(myProbability) ? '—' : `${myProbability.toFixed(1)}%`} detail={winProbability?.simulationCount ? `${Number(winProbability.simulationCount).toLocaleString()} simulations` : 'Calculating'} tone="emerald" />
        <PlayerTile icon={<Activity size={18}/>} label="Four baggers" value={String(Math.round(Number(me?.fourBaggers || 0)))} detail={`${number(me?.fourBaggerPct, 1)}% rate`} tone="violet" />
      </div>

      <div className="rounded-2xl border border-amber-300/25 bg-amber-300/[.07] p-4">
        <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.18em] text-amber-300"><ArrowLeftRight size={17}/> Next throw</div>
        <div className="mt-2 text-2xl font-black text-white">{nextThrow}</div>
        <div className="mt-2 text-sm leading-6 text-zinc-400">
          {latestRound
            ? `Round ${latestRound.round || rounds.length} complete${Number(latestRound.netPoints || 0) ? ` · ${Math.abs(Number(latestRound.netPoints))} net points scored` : ' · wash'}.`
            : 'Waiting for the first completed round.'}
        </div>
      </div>

      <div className="rounded-2xl border border-white/10 bg-zinc-950 p-4">
        <div className="text-xs font-black uppercase tracking-[.18em] text-zinc-500">Your current match line</div>
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Mini label="PPR" value={number(me?.ppr)} />
          <Mini label="DPR" value={signed(me?.dpr)} />
          <Mini label="Round win" value={`${number(me?.roundWinPct, 1)}%`} />
        </div>
      </div>
    </section>
  );
}

function PlayerTile({ icon, label, value, detail, tone }: { icon: React.ReactNode; label: string; value: string; detail: string; tone: 'sky' | 'amber' | 'emerald' | 'violet' }) {
  const colors = { sky: 'text-sky-300', amber: 'text-amber-300', emerald: 'text-emerald-300', violet: 'text-violet-300' };
  return <div className="rounded-2xl border border-white/10 bg-zinc-950 p-4">
    <div className={`flex items-center gap-2 text-xs font-black uppercase tracking-wider ${colors[tone]}`}>{icon}{label}</div>
    <div className="mt-3 truncate text-xl font-black text-white">{value}</div>
    <div className="mt-1 truncate text-xs font-bold text-zinc-500">{detail}</div>
  </div>;
}

function Mini({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-white/[.05] px-2 py-3"><div className="text-[10px] font-black uppercase tracking-wider text-zinc-500">{label}</div><div className="mt-1 text-xl font-black text-white">{value}</div></div>;
}

function number(value: unknown, digits = 2) {
  const result = Number(value);
  return Number.isFinite(result) ? result.toFixed(digits) : '—';
}

function signed(value: unknown) {
  const result = Number(value);
  return Number.isFinite(result) ? `${result > 0 ? '+' : ''}${result.toFixed(2)}` : '—';
}

function court(value?: string) {
  return !value || value === '-1' ? '?' : value;
}

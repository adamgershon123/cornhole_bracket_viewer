import { ChevronLeft, ChevronRight, Radio, RotateCcw } from 'lucide-react';
import { useMemo } from 'react';
import type { RoundRow } from '../lib/api';

type Props = {
  rounds: RoundRow[];
  topTeamId?: string;
  bottomTeamId?: string;
  topTeamName?: string;
  bottomTeamName?: string;
  selectedRound?: number | null;
  onSelectRound?: (round: number | null) => void;
};

type Snapshot = {
  round: RoundRow;
  topScore: number;
  bottomScore: number;
  topGross: number;
  bottomGross: number;
};

export function RoundWalkthrough({
  rounds,
  topTeamId,
  bottomTeamId,
  topTeamName = 'Team 1',
  bottomTeamName = 'Team 2',
  selectedRound = null,
  onSelectRound,
}: Props) {
  const snapshots = useMemo(() => buildSnapshots(rounds, topTeamId, bottomTeamId), [rounds, topTeamId, bottomTeamId]);
  const followingLive = selectedRound == null;
  const selectedIndex = followingLive
    ? snapshots.length - 1
    : snapshots.findIndex(snapshot => Number(snapshot.round.round) === Number(selectedRound));
  const cursor = Math.max(0, selectedIndex < 0 ? snapshots.length - 1 : selectedIndex);
  const current = snapshots[cursor];
  const previous = cursor > 0 ? snapshots[cursor - 1] : null;
  const isPregame = Number(current.round.round) === 0;
  const leader = current.topScore === current.bottomScore
    ? 'The match is tied'
    : current.topScore > current.bottomScore
      ? `${topTeamName} leads by ${current.topScore - current.bottomScore}`
      : `${bottomTeamName} leads by ${current.bottomScore - current.topScore}`;
  const roundWinner = current.topGross === current.bottomGross
    ? 'The round cancelled out'
    : current.topGross > current.bottomGross
      ? `${topTeamName} won the round by ${current.topGross - current.bottomGross}`
      : `${bottomTeamName} won the round by ${current.bottomGross - current.topGross}`;
  const state = current.round.gameState;
  const firstThrowTeam = state?.firstThrowTeamId == null
    ? 'Unknown'
    : String(state.firstThrowTeamId) === String(topTeamId) ? topTeamName : bottomTeamName;
  const firstThrowPlayer = playerName(rounds, state?.firstThrowPlayerId);

  function move(next: number) {
    const target = snapshots[Math.max(0, Math.min(next, snapshots.length - 1))];
    onSelectRound?.(Number(target.round.round));
  }

  return (
    <section className="glass overflow-hidden rounded-[28px]">
      <div className="border-b border-white/10 p-4 md:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-xs font-black uppercase tracking-[.22em] text-amber-300">Match walkthrough</div>
            <h2 className="mt-1 text-2xl font-black">
              {isPregame ? 'Round 0 · Pregame' : `Round ${current.round.round} of ${snapshots.length - 1}`}
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => move(cursor - 1)} disabled={cursor === 0} aria-label="Previous round" className="rounded-xl border border-white/10 bg-white/5 p-2.5 text-white disabled:opacity-30"><ChevronLeft /></button>
            <button type="button" onClick={() => move(cursor + 1)} disabled={cursor >= snapshots.length - 1} aria-label="Next round" className="rounded-xl border border-white/10 bg-white/5 p-2.5 text-white disabled:opacity-30"><ChevronRight /></button>
            <button type="button" onClick={() => onSelectRound?.(null)} className="flex items-center gap-2 rounded-xl bg-amber-300 px-3 py-2.5 text-xs font-black text-black">
              {followingLive ? <Radio size={15} /> : <RotateCcw size={15} />}
              {followingLive ? 'Latest' : 'Return to latest'}
            </button>
          </div>
        </div>
        <input className="mt-4 w-full accent-amber-300" type="range" min={0} max={snapshots.length - 1} value={cursor} onChange={event => move(Number(event.target.value))} aria-label="Select round" />
        <div className="mt-1 flex justify-between text-[10px] font-bold uppercase tracking-wider text-zinc-600">
          <span>Round 0 · Pregame</span><span>Latest round</span>
        </div>
      </div>

      <div className="grid gap-3 p-4 md:grid-cols-3 md:p-5">
        <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
          <div className="text-xs font-black uppercase tracking-widest text-zinc-500">Previous state</div>
          {previous ? <>
            <div className="mt-2 font-black text-white">{Number(previous.round.round) === 0 ? 'Pregame' : `Round ${previous.round.round}`}</div>
            <div className="mt-1 text-sm text-zinc-400">{Number(previous.round.round) === 0 ? 'No bags thrown.' : describeRound(previous, topTeamName, bottomTeamName)}</div>
            <div className="mt-2 text-sm font-bold text-zinc-300">Score: {previous.topScore}–{previous.bottomScore}</div>
          </> : <div className="mt-2 text-sm text-zinc-500">Pregame—no bags have been thrown.</div>}
        </div>

        <div className="rounded-2xl border border-amber-300/25 bg-amber-300/10 p-4">
          <div className="text-xs font-black uppercase tracking-widest text-amber-300">Selected state</div>
          {isPregame ? <>
            <div className="mt-2 text-3xl font-black text-white">0–0</div>
            <div className="mt-1 text-sm font-bold text-amber-100">Prematch prediction and Tale of the Tape</div>
            <div className="mt-2 text-xs text-zinc-400">Advance to Round 1 to see statistics after the first bags are thrown.</div>
          </> : <>
            <div className="mt-2 text-3xl font-black text-white">{current.topGross}–{current.bottomGross}</div>
            <div className="mt-1 text-sm font-bold text-amber-100">{roundWinner}</div>
            <div className="mt-2 text-xs text-zinc-400">{roundPlayerSummary(current.round)}</div>
            <div className="mt-3 border-t border-amber-200/10 pt-3 text-xs text-amber-100">
              <span className="font-black">First throw:</span> {firstThrowTeam}
              {firstThrowPlayer ? ` · ${firstThrowPlayer}` : ''}
              <span className="ml-2 text-amber-200/50">({friendlyStatus(state?.firstThrowPlayerStatus || state?.firstThrowTeamStatus)})</span>
            </div>
          </>}
        </div>

        <div className="rounded-2xl border border-sky-400/25 bg-sky-400/10 p-4">
          <div className="text-xs font-black uppercase tracking-widest text-sky-300">{isPregame ? 'Prematch state' : `State after round ${current.round.round}`}</div>
          <div className="mt-2 text-3xl font-black text-white">{current.topScore}–{current.bottomScore}</div>
          <div className="mt-1 text-sm font-bold text-sky-100">{isPregame ? 'Awaiting first bags' : leader}</div>
          <div className="mt-2 text-xs text-zinc-400">{snapshots.length - cursor - 1} later round{snapshots.length - cursor - 1 === 1 ? '' : 's'} available</div>
        </div>
      </div>
    </section>
  );
}

function buildSnapshots(rounds: RoundRow[], topTeamId?: string, bottomTeamId?: string): Snapshot[] {
  let topScore = 0;
  let bottomScore = 0;
  const played = [...rounds].sort((a, b) => Number(a.round) - Number(b.round)).map(round => {
    const topGross = grossForTeam(round, topTeamId);
    const bottomGross = grossForTeam(round, bottomTeamId);
    if (topGross > bottomGross) topScore += topGross - bottomGross;
    if (bottomGross > topGross) bottomScore += bottomGross - topGross;
    return { round, topScore, bottomScore, topGross, bottomGross };
  });
  return [{
    round: { round: 0, netPoints: 0, scoringTeamId: null, players: [] },
    topScore: 0, bottomScore: 0, topGross: 0, bottomGross: 0,
  }, ...played];
}

function grossForTeam(round: RoundRow, teamId?: string) {
  return (round.players || []).filter(player => String(player.teamId) === String(teamId)).reduce((sum, player) => sum + Number(player.grossPoints || 0), 0);
}

function describeRound(snapshot: Snapshot, topName: string, bottomName: string) {
  if (snapshot.topGross === snapshot.bottomGross) return `Cancelled at ${snapshot.topGross}–${snapshot.bottomGross}.`;
  const winner = snapshot.topGross > snapshot.bottomGross ? topName : bottomName;
  return `${winner} scored ${Math.abs(snapshot.topGross - snapshot.bottomGross)} net point${Math.abs(snapshot.topGross - snapshot.bottomGross) === 1 ? '' : 's'}.`;
}

function roundPlayerSummary(round: RoundRow) {
  return (round.players || []).map(player => `${player.name}: ${player.grossPoints}`).join(' · ');
}

function playerName(rounds: RoundRow[], playerId?: string | null) {
  if (!playerId) return '';
  return rounds.flatMap(round => round.players || []).find(player => String(player.playerId) === String(playerId))?.name || `Player ${playerId}`;
}

function friendlyStatus(status?: string) {
  if (!status || status === 'UNKNOWN') return 'unknown';
  if (status === 'MANUAL') return 'entered manually';
  if (status === 'ACL_REPORTED') return 'reported by ACL';
  if (status === 'INFERRED_FROM_SCORE') return 'inferred from scoring';
  if (status === 'INFERRED_FROM_ROTATION') return 'inferred from rotation';
  return status.toLowerCase().replaceAll('_', ' ');
}

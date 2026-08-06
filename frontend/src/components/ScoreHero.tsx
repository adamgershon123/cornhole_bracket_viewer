import type { Match, PlayerStat, RoundRow } from '../lib/api';
import type { SnapshotEventDetails } from '../lib/shareSnapshot';
import { ShareFinalResultButton } from './ShareSnapshotButton';

type Props = {
  match: Match;
  players?: PlayerStat[];
  rounds?: RoundRow[];
  event?: SnapshotEventDetails;
};

const TEAM_1 = {
  border: 'border-blue-400',
  text: 'text-blue-400',
  bg: 'bg-blue-400/10',
};

const TEAM_2 = {
  border: 'border-red-400',
  text: 'text-red-400',
  bg: 'bg-red-400/10',
};

export function ScoreHero({ match, players = [], rounds = [], event }: Props) {
  const game = match.activeGame || match.games?.[0];
  const topScore = game?.score?.top ?? match.score.top ?? 0;
  const bottomScore = game?.score?.bottom ?? match.score.bottom ?? 0;
  const topPlayers = players.filter(player => String(player.teamId) === String(match.teams.top.id));
  const bottomPlayers = players.filter(player => String(player.teamId) === String(match.teams.bottom.id));
  const topPositions = getThrowingPositions(rounds, match.teams.top.id, topPlayers);
  const bottomPositions = getThrowingPositions(rounds, match.teams.bottom.id, bottomPlayers);
  const highlights = getMatchHighlights(rounds, match.teams.top.id, match.teams.bottom.id);

  return (
    <section className="glass rounded-[28px] p-4 overflow-hidden">
      <div className="grid grid-cols-3 items-start gap-3">
        <div className="text-left">
          <div className="text-sm font-black uppercase tracking-widest text-zinc-400">
            Court {courtLabel(match.courtId)}
          </div>
        </div>

        <div className="text-center">
          <div className="text-sm font-black uppercase tracking-[0.18em] text-amber-300">
            {match.roundDescription || 'Bracket Round'}
          </div>
          <div className="mt-1 text-xs font-bold uppercase tracking-widest text-zinc-500">
            Round {game?.currentRound ?? match.currentRound ?? '-'}
          </div>
        </div>

        <div className="text-right">
          <span className={`inline-flex rounded-lg px-3 py-1 text-xs font-black ${statusClass(match.status)}`}>
            {statusLabel(match.status)}
          </span>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-[1fr_auto_1fr] items-start gap-3">
        <TeamScore
          name={match.teams.top.name}
          score={topScore}
          color={TEAM_1.text}
          align="left"
        />
        <div className="pt-10 text-center text-3xl font-black text-zinc-600">VS</div>
        <TeamScore
          name={match.teams.bottom.name}
          score={bottomScore}
          color={TEAM_2.text}
          align="right"
        />
      </div>

      <div className="mt-5 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <TeamPlayerPanel
          teamLabel="Team 1"
          players={topPlayers}
          rounds={rounds}
          positions={topPositions}
          color={TEAM_1}
        />
        <TeamPlayerPanel
          teamLabel="Team 2"
          players={bottomPlayers}
          rounds={rounds}
          positions={bottomPositions}
          color={TEAM_2}
        />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="rounded-2xl border border-white/10 bg-black/25 p-4 text-center">
          <div className="text-sm font-black uppercase tracking-widest text-zinc-400">
            Next Up
          </div>
          <div className="mt-3 text-sm uppercase tracking-widest text-zinc-500">Current state</div>
          <div className="mt-1 text-2xl font-black text-amber-300">
            {topScore === bottomScore ? 'Tied' : topScore > bottomScore ? match.teams.top.name : match.teams.bottom.name}
          </div>
          <div className="mt-2 text-sm font-bold text-zinc-400">
            {match.status === 'live' ? 'Match in progress' : statusLabel(match.status)}
          </div>
        </div>

        <div className="rounded-2xl border border-white/10 bg-black/25 p-4">
          <div className="text-center text-sm font-black uppercase tracking-widest text-zinc-400">
            Match Highlights
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center">
            <MiniHighlight label="Largest Lead" value={highlights.largestLead} />
            <MiniHighlight label="Lead Changes" value={highlights.leadChanges} />
            <MiniHighlight label="Ties" value={highlights.ties} />
          </div>
        </div>
      </div>
      {match.status === 'completed' && (
        <div className="mt-4 flex justify-center border-t border-white/10 pt-4">
          <ShareFinalResultButton input={{
            eventId: match.eventId,
            event,
            match: { courtId: match.courtId, roundDescription: match.roundDescription },
            topTeamName: match.teams.top.name,
            bottomTeamName: match.teams.bottom.name,
            topScore: Number(topScore || 0),
            bottomScore: Number(bottomScore || 0),
            roundCount: rounds.length,
            players: players.map(player => ({
              name: player.name,
              team: String(player.teamId) === String(match.teams.top.id) ? 'top' : 'bottom',
              ppr: player.ppr,
              dpr: player.dpr,
              fourBaggers: player.fourBaggers,
              fourBaggerPct: player.fourBaggerPct,
            })),
          }}/>
        </div>
      )}
    </section>
  );
}

function TeamScore({
  name,
  score,
  color,
  align,
}: {
  name: string;
  score: number | null;
  color: string;
  align: 'left' | 'right';
}) {
  return (
    <div className={align === 'right' ? 'text-right' : 'text-left'}>
      <div className="min-h-12 border-b border-current pb-2 text-xl font-black leading-tight">
        {name}
      </div>
      <div className={`mt-3 text-7xl font-black leading-none ${color}`}>
        {score ?? 0}
      </div>
    </div>
  );
}

function TeamPlayerPanel({
  teamLabel,
  players,
  rounds,
  positions,
  color,
}: {
  teamLabel: string;
  players: PlayerStat[];
  rounds: RoundRow[];
  positions: Map<string, number>;
  color: typeof TEAM_1;
}) {
  const visiblePlayers = players.length ? players : [{ id: teamLabel, name: 'No player stats' } as PlayerStat];

  return (
    <div className={`space-y-3 rounded-2xl border ${color.border} ${color.bg} p-3`}>
      {visiblePlayers.map((player, index) => {
        const cancellation = getCancellationTotals(player, rounds);
        return (
          <div key={player.id || player.name} className="rounded-xl border border-white/10 bg-black/35 p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-xl font-black">{player.name}</div>
                <div className="text-sm font-bold text-zinc-400">
                  P{positions.get(String(player.id)) || index + 1}
                </div>
              </div>
              <div className="text-right">
                <div className="text-xs font-bold uppercase tracking-widest text-zinc-400">Avg PPR</div>
                <div className={`text-3xl font-black leading-none ${color.text}`}>{fmt(player.ppr)}</div>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              <PlayerMetric label="Points Scored" value={fmt(cancellation.scored, 0)} tone="text-blue-400" />
              <PlayerMetric label="Points Conceded" value={fmt(cancellation.conceded, 0)} tone="text-red-400" />
              <PlayerMetric label="In / On / Off" value={`${num(player.bagsIn)} / ${num(player.bagsOn)} / ${num(player.bagsOff)}`} />
            </div>

            <div className="mt-4 h-px bg-white/15" />

            <div className="mt-4 grid grid-cols-2 gap-2 text-center">
              <PlayerMetric label="4 Baggers" value={num(player.fourBaggers)} tone={color.text} />
              <PlayerMetric label="4 Bagger %" value={`${fmt(player.fourBaggerPct, 0)}%`} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PlayerMetric({ label, value, tone = 'text-white' }: { label: string; value: string | number; tone?: string }) {
  return (
    <div>
      <div className="text-[11px] font-bold uppercase tracking-widest text-zinc-400">{label}</div>
      <div className={`mt-1 text-2xl font-black leading-none ${tone}`}>{value}</div>
    </div>
  );
}

function MiniHighlight({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-white/10 bg-zinc-950/70 px-2 py-3">
      <div className="text-xs font-bold uppercase tracking-widest text-zinc-400">{label}</div>
      <div className="mt-2 text-2xl font-black">{value}</div>
    </div>
  );
}

function getThrowingPositions(rounds: RoundRow[], teamId: string | number | undefined, players: PlayerStat[]) {
  const positions = new Map<string, number>();

  rounds.forEach(round => {
    (round.players || []).forEach(thrower => {
      const playerId = String(thrower.playerId ?? '');
      if (!playerId || String(thrower.teamId) !== String(teamId) || positions.has(playerId)) {
        return;
      }

      positions.set(playerId, positions.size + 1);
    });
  });

  players.forEach(player => {
    const playerId = String(player.id ?? '');
    if (playerId && !positions.has(playerId)) {
      positions.set(playerId, positions.size + 1);
    }
  });

  return positions;
}

function getCancellationTotals(player: PlayerStat, rounds: RoundRow[]) {
  const playerId = String(player.id ?? '');
  let scored = 0;
  let conceded = 0;

  rounds.forEach(round => {
    const throwers = round.players || [];
    const current = throwers.find(thrower => String(thrower.playerId) === playerId);
    const opponent = throwers.find(thrower => String(thrower.playerId) !== playerId);

    if (!current || !opponent) return;

    const diff = Number(current.grossPoints ?? 0) - Number(opponent.grossPoints ?? 0);
    if (diff > 0) scored += diff;
    if (diff < 0) conceded += Math.abs(diff);
  });

  return { scored, conceded };
}

function getMatchHighlights(rounds: RoundRow[], topTeamId?: string, bottomTeamId?: string) {
  let topScore = 0;
  let bottomScore = 0;
  let largestLead = 0;
  let leadChanges = 0;
  let ties = 0;
  let previousLeader = 'tie';

  rounds.forEach(round => {
    if (round.scoringTeamId && Number(round.netPoints) > 0) {
      if (String(round.scoringTeamId) === String(topTeamId)) topScore += Number(round.netPoints);
      if (String(round.scoringTeamId) === String(bottomTeamId)) bottomScore += Number(round.netPoints);
    }

    const diff = topScore - bottomScore;
    largestLead = Math.max(largestLead, Math.abs(diff));

    const leader = diff === 0 ? 'tie' : diff > 0 ? 'top' : 'bottom';
    if (leader === 'tie') {
      ties += 1;
    } else if (previousLeader !== 'tie' && leader !== previousLeader) {
      leadChanges += 1;
    }
    previousLeader = leader;
  });

  return { largestLead, leadChanges, ties };
}

function fmt(value: any, digits = 2) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : digits === 0 ? '0' : '0.00';
}

function num(value: any) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.round(n) : 0;
}

function courtLabel(court?: string) {
  return String(court || '?') === '-1' ? '?' : court || '?';
}

function statusLabel(status?: string) {
  if (status === 'live') return 'LIVE';
  if (status === 'completed') return 'FINAL';
  if (status === 'upcoming') return 'NEXT';
  return 'UNKNOWN';
}

function statusClass(status?: string) {
  if (status === 'live') return 'bg-blue-500 text-white';
  if (status === 'completed') return 'bg-blue-400 text-black';
  if (status === 'upcoming') return 'bg-yellow-300 text-black';
  return 'bg-zinc-600 text-white';
}

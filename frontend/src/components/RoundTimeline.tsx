import type { RoundRow } from '../lib/api';

type Props = {
  rounds: RoundRow[];
  topTeamName?: string;
  bottomTeamName?: string;
  topTeamId?: string;
  bottomTeamId?: string;
};

type ScoreRow = {
  key: string;
  playerId?: string;
  name: string;
  detail: string;
  team: 'top' | 'bottom';
  pair: 1 | 2;
  scores: Record<number, number | string>;
  total: number;
};

export function RoundTimeline({
  rounds,
  topTeamName,
  bottomTeamName,
  topTeamId,
  bottomTeamId,
}: Props) {
  const rows = buildScoreRows(rounds, topTeamId, bottomTeamId);
  const roundNumbers = rounds.map(round => Number(round.round)).filter(Number.isFinite);

  return (
    <section className="glass rounded-[28px] p-4 overflow-hidden">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-black uppercase tracking-wider">Score Per Round</h2>
        <div className="flex flex-wrap gap-3 text-xs font-bold uppercase tracking-widest text-zinc-400">
          <LegendDot color="bg-green-500" label="Odd rounds" />
          <LegendDot color="bg-orange-500" label="Even rounds" />
        </div>
      </div>

      <div className="mb-3 grid grid-cols-1 gap-2 text-sm font-bold text-zinc-400 sm:grid-cols-2">
        <div className="rounded-xl border border-blue-400/40 bg-blue-400/10 px-3 py-2">
          <span className="text-blue-400">Team 1</span> / {topTeamName || 'Team 1'}
        </div>
        <div className="rounded-xl border border-red-400/40 bg-red-400/10 px-3 py-2">
          <span className="text-red-400">Team 2</span> / {bottomTeamName || 'Team 2'}
        </div>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-white/10">
        <table className="min-w-max w-full border-collapse bg-zinc-950/70">
          <thead>
            <tr className="border-b border-white/10 text-left text-sm uppercase tracking-widest text-zinc-400">
              <th className="sticky left-0 z-10 min-w-[12rem] bg-zinc-950 px-3 py-3 font-black">
                Player
              </th>
              {roundNumbers.map(round => (
                <th key={round} className="min-w-[4.25rem] border-l border-white/10 px-3 py-3 text-center font-black">
                  {round}
                </th>
              ))}
              <th className="min-w-[5rem] border-l border-white/10 px-3 py-3 text-center font-black">
                Total
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.key} className="border-b border-white/10 last:border-b-0">
                <td className="sticky left-0 z-10 min-w-[12rem] bg-zinc-950 px-3 py-3">
                  <div className="text-lg font-black leading-tight">{row.name}</div>
                  <div className="text-sm font-bold text-zinc-400">{row.detail}</div>
                </td>
                {roundNumbers.map(round => {
                  const value = row.scores[round] ?? '';
                  const isOdd = round % 2 === 1;
                  return (
                    <td
                      key={round}
                      className="border-l border-white/10 px-3 py-3 text-center"
                    >
                      <span className={`text-3xl font-black ${isOdd ? 'text-green-500' : 'text-orange-400'}`}>
                        {value}
                      </span>
                    </td>
                  );
                })}
                <td className={`border-l border-white/10 px-3 py-3 text-center text-4xl font-black ${row.team === 'top' ? 'text-blue-400' : 'text-red-400'}`}>
                  {row.total}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3 text-xs font-bold text-zinc-500">
        <span>Swipe horizontally to see all rounds.</span>
        <span>{roundNumbers.length} rounds</span>
      </div>
    </section>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`h-3 w-3 rounded-full ${color}`} />
      {label}
    </span>
  );
}

function buildScoreRows(rounds: RoundRow[], topTeamId?: string, bottomTeamId?: string): ScoreRow[] {
  const rows = new Map<string, ScoreRow>();

  rounds.forEach(round => {
    const roundNo = Number(round.round);
    const players = round.players || [];

    players.forEach(player => {
      const team = String(player.teamId) === String(bottomTeamId) ? 'bottom' : 'top';
      const pair = roundNo % 2 === 1 ? 1 : 2;
      const key = String(player.playerId || `${team}-${player.name}`);
      const existing = rows.get(key);
      const detail = `${team === 'top' ? 'Team 1' : 'Team 2'} - P${pair}`;

      if (!existing) {
        rows.set(key, {
          key,
          playerId: player.playerId,
          name: player.name,
          detail,
          team,
          pair,
          scores: {},
          total: 0,
        });
      }

      const row = rows.get(key)!;
      const points = Number(player.grossPoints ?? 0);
      row.scores[roundNo] = Number.isFinite(points) ? points : '';
      if (Number.isFinite(points)) row.total += points;
    });
  });

  return [...rows.values()].sort((a, b) => {
    if (a.pair !== b.pair) return a.pair - b.pair;
    if (a.team !== b.team) return a.team === 'top' ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

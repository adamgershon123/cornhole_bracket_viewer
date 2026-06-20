import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
} from 'recharts';
import type { RoundRow } from '../lib/api';

export function MomentumChart({
  rounds,
  topTeamId,
  bottomTeamId,
}: {
  rounds: RoundRow[];
  topTeamId?: string;
  bottomTeamId?: string;
}) {
  let running = 0;

  const data = rounds.map((r) => {
    const signed =
      r.scoringTeamId === topTeamId
        ? r.netPoints
        : r.scoringTeamId === bottomTeamId
          ? -r.netPoints
          : 0;

    running += signed;

    return {
      round: r.round,
      momentum: running,
      net: r.netPoints,
    };
  });

  return (
    <section className="glass rounded-[28px] p-4 overflow-hidden">
      <h2 className="text-lg font-black mb-3">Momentum</h2>

      <div className="h-52 w-full overflow-hidden">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
          >
            <XAxis dataKey="round" tick={{ fontSize: 12 }} />
            <YAxis domain={[-12, 12]} hide />
            <Tooltip />
            <ReferenceLine y={0} strokeDasharray="3 3" />
            <Area
              type="monotone"
              dataKey="momentum"
              stroke="currentColor"
              fill="currentColor"
              fillOpacity={0.18}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
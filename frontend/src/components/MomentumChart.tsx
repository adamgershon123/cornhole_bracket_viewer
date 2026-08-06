import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { RoundRow } from '../lib/api';

type MomentumPoint = {
  round: number;
  momentum: number;
  net: number;
  leader: 'top' | 'bottom' | 'tie';
  leaderName: string;
  topPlayer?: RoundRow['players'][number];
  bottomPlayer?: RoundRow['players'][number];
  topScoreAfter: number;
  bottomScoreAfter: number;
  topMomentum: number | null;
  bottomMomentum: number | null;
};

function shortName(name?: string) {
  if (!name) return 'Player';
  return name;
}

function MomentumTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;

  const point = payload[0]?.payload as MomentumPoint;

  if (!point) return null;

  return (
    <div className="w-[min(340px,calc(100vw-32px))] rounded-2xl border border-white/10 bg-zinc-950/95 p-4 shadow-2xl">
      <div className="text-xs font-black uppercase tracking-[0.2em] text-zinc-500">
        Round {point.round}
      </div>

      <div className="mt-1 text-lg font-black text-white">
        {point.leader === 'tie' ? 'Match tied' : `${point.leaderName} leading`}
      </div>

      <div className="mt-3 space-y-2 text-sm">
        <RoundThrowRow
          label="Team 1"
          player={point.topPlayer}
          colorClass="text-blue-300"
        />
        <RoundThrowRow
          label="Team 2"
          player={point.bottomPlayer}
          colorClass="text-red-300"
        />
      </div>

      <div className="mt-3 rounded-xl bg-zinc-900 px-3 py-2 text-center text-sm font-black text-zinc-300">
        Match score after round: {point.topScoreAfter} - {point.bottomScoreAfter}
      </div>

      <div className="mt-2 text-xs text-zinc-500">
        Momentum value: {point.momentum > 0 ? '+' : ''}{point.momentum}
      </div>
    </div>
  );
}

function RoundThrowRow({
  label,
  player,
  colorClass,
}: {
  label: string;
  player?: RoundRow['players'][number];
  colorClass: string;
}) {
  return (
    <div className="rounded-xl bg-zinc-900 p-3">
      <div className={`text-xs font-black uppercase tracking-widest ${colorClass}`}>
        {label}
      </div>
      <div className="mt-1 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-base font-black text-white">
            {shortName(player?.name)}
          </div>
          <div className="text-xs text-zinc-500">
            Threw {player?.grossPoints ?? '-'} points
          </div>
        </div>
      </div>
    </div>
  );
}

export function MomentumChart({
  rounds,
  topTeamId,
  bottomTeamId,
  topTeamName = 'Team 1',
  bottomTeamName = 'Team 2',
}: {
  rounds: RoundRow[];
  topTeamId?: string;
  bottomTeamId?: string;
  topTeamName?: string;
  bottomTeamName?: string;
}) {
  let momentum = 0;
  let topScore = 0;
  let bottomScore = 0;

  const data: MomentumPoint[] = rounds.map((r) => {
    const topPlayer = r.players.find(player => player.teamId === topTeamId) || r.players[0];
    const bottomPlayer = r.players.find(player => player.teamId === bottomTeamId) || r.players[1];

    const topRoundPoints = Number(topPlayer?.grossPoints ?? 0);
    const bottomRoundPoints = Number(bottomPlayer?.grossPoints ?? 0);
    const roundNet = Math.abs(topRoundPoints - bottomRoundPoints);

    if (topRoundPoints > bottomRoundPoints) {
      topScore += roundNet;
    } else if (bottomRoundPoints > topRoundPoints) {
      bottomScore += roundNet;
    }

    momentum = topScore - bottomScore;

    const leader = momentum > 0 ? 'top' : momentum < 0 ? 'bottom' : 'tie';

    return {
      round: r.round,
      momentum,
      net: roundNet,
      leader,
      leaderName: leader === 'top' ? topTeamName : leader === 'bottom' ? bottomTeamName : 'Tied',
      topPlayer,
      bottomPlayer,
      topScoreAfter: topScore,
      bottomScoreAfter: bottomScore,
      topMomentum: momentum > 0 ? momentum : null,
      bottomMomentum: momentum < 0 ? momentum : null,
    };
  });

  const maxAbsMomentum = Math.max(6, ...data.map(point => Math.abs(point.momentum)));

  return (
    <section className="glass rounded-[28px] p-4 overflow-visible">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-black">Momentum</h2>
        <div className="flex flex-wrap gap-3 text-xs font-bold text-zinc-400">
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-blue-400" />Team 1 leads</span>
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-red-400" />Team 2 leads</span>
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-yellow-300" />Tied</span>
        </div>
      </div>

      <div className="h-56 w-full overflow-visible">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 12, right: 10, left: 0, bottom: 0 }}
          >
            <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
            <XAxis dataKey="round" tick={{ fontSize: 12 }} />
            <YAxis domain={[-maxAbsMomentum, maxAbsMomentum]} hide />
            <Tooltip
              content={<MomentumTooltip />}
              cursor={{ stroke: 'rgba(255,255,255,0.18)', strokeWidth: 18 }}
              allowEscapeViewBox={{ x: true, y: true }}
              wrapperStyle={{ zIndex: 40 }}
            />
            <ReferenceLine y={0} stroke="rgba(255,255,255,0.55)" strokeDasharray="3 3" />
            <Area
              type="monotone"
              dataKey="topMomentum"
              stroke="none"
              fill="#60a5fa"
              fillOpacity={0.28}
              connectNulls={false}
              dot={false}
              activeDot={false}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="bottomMomentum"
              stroke="none"
              fill="#fb7185"
              fillOpacity={0.28}
              connectNulls={false}
              dot={false}
              activeDot={false}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="momentum"
              stroke="rgba(255,255,255,0.92)"
              strokeWidth={2}
              fill="transparent"
              fillOpacity={0}
              dot={({ cx, cy, payload }: any) => {
                const fill = payload.leader === 'top' ? '#60a5fa' : payload.leader === 'bottom' ? '#fb7185' : '#fde047';
                return <circle cx={cx} cy={cy} r={4} fill={fill} stroke="#09090b" strokeWidth={2} />;
              }}
              activeDot={{ r: 7, stroke: '#fff', strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

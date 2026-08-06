import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

type Point = {
  round:number;
  topScore:number;
  bottomScore:number;
  topWinProbability:number;
  bottomWinProbability:number;
  probabilityChange:number|null;
  firstThrowTeamId?:string|null;
  firstThrowPlayerId?:string|null;
  status:string;
};

export function LiveWinProbabilityChart({
  model,
  topTeamName,
  bottomTeamName,
  selectedRound,
  onSelectRound,
}: {
  model?:any;
  topTeamName:string;
  bottomTeamName:string;
  selectedRound?:number|null;
  onSelectRound?:(round:number|null)=>void;
}) {
  if (!model?.points?.length) return null;
  const data = model.points.map((point:Point) => ({
    ...point,
    probability: Number(point.topWinProbability) * 100,
  }));
  const latest = data[data.length - 1];
  const displayed = selectedRound == null
    ? latest
    : data.find((point: Point) => Number(point.round) === Number(selectedRound)) || latest;
  return (
    <section className="glass overflow-hidden rounded-[28px] p-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-xs font-black uppercase tracking-[.22em] text-amber-300">Live Win Probability</div>
          <div className="mt-2 flex items-baseline gap-3">
            <span className="text-3xl font-black text-blue-300">{displayed.probability.toFixed(1)}%</span>
            <span className="text-sm font-bold text-zinc-400">{topTeamName}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-3xl font-black text-red-300">{(100 - displayed.probability).toFixed(1)}%</div>
          <div className="text-sm font-bold text-zinc-400">{bottomTeamName}</div>
        </div>
      </div>
      <div className="mt-4 h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 10, right: 8, left: -20, bottom: 0 }}
            onClick={(state:any) => {
              const round = state?.activePayload?.[0]?.payload?.round;
              if (round !== undefined) onSelectRound?.(round === data[data.length - 1].round ? null : Number(round));
            }}
          >
            <defs>
              <linearGradient id="winProbabilityFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#60a5fa" stopOpacity={.45} />
                <stop offset="100%" stopColor="#60a5fa" stopOpacity={.04} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
            <XAxis dataKey="round" tick={{ fontSize: 11 }} tickFormatter={value => value === 0 ? 'Pre' : `R${value}`} />
            <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fontSize: 11 }} />
            <ReferenceLine y={50} stroke="rgba(255,255,255,.4)" strokeDasharray="4 4" />
            {selectedRound != null && <ReferenceLine x={selectedRound} stroke="#fcd34d" strokeWidth={2} />}
            <Tooltip content={<ProbabilityTooltip topName={topTeamName} bottomName={bottomTeamName} />} />
            <Area type="monotone" dataKey="probability" stroke="#60a5fa" strokeWidth={3} fill="url(#winProbabilityFill)" isAnimationActive={false} activeDot={{ r: 6 }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap justify-between gap-2 text-[11px] text-zinc-500">
        <span>{model.simulationCount?.toLocaleString()} simulations per round state</span>
        <span>{model.modelVersion}</span>
      </div>
    </section>
  );
}

function ProbabilityTooltip({ active, payload, topName, bottomName }:any) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-2xl border border-white/10 bg-zinc-950/95 p-4 shadow-2xl">
      <div className="text-xs font-black uppercase tracking-widest text-zinc-500">{point.round === 0 ? 'Pregame' : `After round ${point.round}`}</div>
      <div className="mt-2 font-black text-blue-300">{topName}: {point.probability.toFixed(1)}%</div>
      <div className="font-black text-red-300">{bottomName}: {(100 - point.probability).toFixed(1)}%</div>
      {point.round > 0 && <div className="mt-2 text-xs text-zinc-400">
        Score: {point.topScore}–{point.bottomScore} · {topName} change since previous round: {point.probabilityChange >= 0 ? '+' : ''}{(point.probabilityChange * 100).toFixed(1)} pts
      </div>}
    </div>
  );
}

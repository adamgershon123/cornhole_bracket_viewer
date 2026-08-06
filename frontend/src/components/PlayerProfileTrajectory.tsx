import { ArrowDown, ArrowRight, ArrowUp, Gauge } from 'lucide-react';

type Props = {
  data?: any;
  selectedRound?: number | null;
  completed?: boolean;
};

function value(metric: any, key: 'before' | 'current' | 'delta') {
  const raw = metric?.[key];
  if (raw === null || raw === undefined) return '—';
  const suffix = metric.kind === 'percent' ? '%' : '';
  const sign = key === 'delta' && Number(raw) > 0 ? '+' : '';
  return `${sign}${Number(raw).toFixed(2)}${suffix}`;
}

function directionStyle(direction: string) {
  if (direction === 'UP') return 'text-emerald-300';
  if (direction === 'DOWN') return 'text-red-300';
  return 'text-zinc-400';
}

function DirectionIcon({ direction }: { direction: string }) {
  if (direction === 'UP') return <ArrowUp size={15} />;
  if (direction === 'DOWN') return <ArrowDown size={15} />;
  return <ArrowRight size={15} />;
}

export function PlayerProfileTrajectory({ data, selectedRound, completed = false }: Props) {
  if (!data || data.status === 'UNAVAILABLE') return null;
  const targetRound = selectedRound == null
    ? Math.max(0, ...(data.players || []).flatMap((player: any) => (player.snapshots || []).map((snapshot: any) => Number(snapshot.round))))
    : Number(selectedRound);

  return (
    <section className="glass overflow-hidden rounded-[28px]">
      <div className="border-b border-white/10 p-4 md:p-5">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-violet-400/10 p-2 text-violet-300"><Gauge size={20} /></div>
          <div>
            <div className="text-xs font-black uppercase tracking-[.22em] text-violet-300">Player profile trajectory</div>
            <h2 className="mt-1 text-2xl font-black">
              {targetRound === 0 ? 'Pregame baseline' : completed && selectedRound == null ? 'Final match impact' : `Profile impact through Round ${targetRound}`}
            </h2>
            <p className="mt-1 max-w-3xl text-xs leading-5 text-zinc-500">
              Internal season values calculated from ACL match rounds before this event, plus the selected rounds. Official ACL statistics are not overwritten.
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-4 p-4 xl:grid-cols-2 md:p-5">
        {(data.players || []).map((player: any) => {
          const snapshots = player.snapshots || [];
          const snapshot = snapshots.find((item: any) => Number(item.round) === targetRound)
            || snapshots.filter((item: any) => Number(item.round) <= targetRound).at(-1)
            || snapshots[0];
          return (
            <div key={player.playerId} className="rounded-2xl border border-white/10 bg-black/25 p-4">
              <div className="flex items-end justify-between gap-3">
                <div>
                  <a href={`/?view=profile&playerId=${player.playerId}`} className="text-lg font-black text-white hover:text-amber-200">
                    {player.name}
                  </a>
                  <div className="mt-1 text-xs text-zinc-500">
                    {player.baselineRounds} pre-event season rounds · {snapshot?.matchRounds || 0} match rounds included
                  </div>
                </div>
                <div className="text-right text-[10px] font-black uppercase tracking-widest text-zinc-600">Before → Current</div>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {(snapshot?.metrics || []).map((metric: any) => (
                  <div key={metric.key} className="rounded-xl border border-white/[.07] bg-white/[.03] p-3">
                    <div className="text-[10px] font-black uppercase tracking-wider text-zinc-500">{metric.label}</div>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <div className="text-sm font-bold text-zinc-400">{value(metric, 'before')} → <span className="text-white">{value(metric, 'current')}</span></div>
                      <div className={`flex items-center gap-1 text-xs font-black ${directionStyle(metric.direction)}`}>
                        <DirectionIcon direction={metric.direction} /> {value(metric, 'delta')}
                      </div>
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/5">
                        <div className="h-full rounded-full bg-violet-400" style={{ width: `${metric.impact?.score || 0}%` }} />
                      </div>
                      <span className="text-[10px] font-bold text-zinc-600">{metric.impact?.label || 'Unknown'} impact</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <div className="border-t border-white/10 px-4 py-3 text-xs text-zinc-600 md:px-5">
        Population-relative ratings such as clutch, swing, form percentile, and competition strength are recalculated after completed match data is indexed.
      </div>
    </section>
  );
}

import { Crown, RotateCcw, Trophy } from 'lucide-react';

export function ChampionshipDoubleDip({ profile }: { profile?: any }) {
  if (!profile || profile.status !== 'AVAILABLE') return null;
  return <section className="glass overflow-hidden rounded-[28px] border border-amber-300/20">
    <div className="border-b border-white/10 bg-amber-300/[.055] p-4 md:p-5">
      <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.22em] text-amber-300"><Trophy size={17}/> Championship double-dip history</div>
      <h2 className="mt-1 text-2xl font-black">The advantage—and the reset risk</h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-400">Role-specific history from completed double-elimination championships. Player ratings are stabilized toward the overall championship baseline when samples are small.</p>
    </div>
    <div className="grid gap-4 p-4 lg:grid-cols-2 md:p-5">
      <RoleCard role="KING_SEAT" data={profile.kingSeat} />
      <RoleCard role="CHALLENGER" data={profile.challenger} />
    </div>
  </section>;
}

function RoleCard({ role, data }: { role: 'KING_SEAT' | 'CHALLENGER'; data: any }) {
  const king = role === 'KING_SEAT';
  const metrics = king ? [
    ['Win in one game', 'winInOneRate'],
    ['Win after reset', 'winInTwoRate'],
    ['Get double-dipped', 'doubleDippedRate'],
  ] : [
    ['Lose game one', 'loseFirstRate'],
    ['Lose game two', 'loseSecondRate'],
    ['Complete double dip', 'completeDoubleDipRate'],
  ];
  return <article className={`overflow-hidden rounded-2xl border ${king ? 'border-amber-300/25 bg-amber-300/[.045]' : 'border-fuchsia-300/20 bg-fuchsia-300/[.035]'}`}>
    <div className="border-b border-white/10 p-4">
      <div className={`flex items-center gap-2 text-xs font-black uppercase tracking-[.18em] ${king ? 'text-amber-300' : 'text-fuchsia-300'}`}>
        {king ? <Crown size={16}/> : <RotateCcw size={16}/>} {king ? 'King seat' : 'Elimination-bracket challenger'}
      </div>
      <div className="mt-1 text-sm text-zinc-400">{king ? 'Enters the championship undefeated; one win secures the title.' : 'Must win twice; one loss ends the tournament.'}</div>
    </div>
    <div className="grid grid-cols-3 gap-2 p-3">
      {metrics.map(([label, key]) => <Metric key={key} label={label} value={data?.teamAverageRating?.[key]} />)}
    </div>
    <div className="px-4 pb-3 text-xs font-bold text-zinc-500">Team average rating · combined history {data?.combinedHistory?.appearances || 0} unique championship appearances</div>
    <div className="divide-y divide-white/10 border-t border-white/10">
      {(data?.players || []).map((player: any) => <div key={player.playerId} className="p-4">
        <div className="flex items-baseline justify-between gap-3">
          <a href={`/?view=profile&playerId=${player.playerId}`} className="font-black text-white hover:text-amber-300 hover:underline">{player.playerName}</a>
          <span className="text-xs font-bold text-zinc-500">{player.appearances} appearances · {Math.round((player.sampleConfidence || 0) * 100)}% sample confidence</span>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2">
          {metrics.map(([label, key]) => <PlayerMetric key={key} label={label} rating={player.rating?.[key]} raw={player.raw?.[key]} />)}
        </div>
      </div>)}
    </div>
  </article>;
}

function Metric({ label, value }: { label: string; value?: number | null }) {
  return <div className="rounded-xl border border-white/10 bg-black/25 p-3 text-center">
    <div className="text-[10px] font-black uppercase tracking-wider text-zinc-500">{label}</div>
    <div className="mt-1 text-xl font-black text-white">{percent(value)}</div>
  </div>;
}

function PlayerMetric({ label, rating, raw }: { label: string; rating?: number | null; raw?: number | null }) {
  return <div className="rounded-xl bg-black/20 p-2.5 text-center">
    <div className="text-[9px] font-black uppercase tracking-wider text-zinc-500">{label}</div>
    <div className="mt-1 text-lg font-black text-white">{percent(rating)}</div>
    <div className="mt-0.5 text-[10px] text-zinc-500">raw {percent(raw)}</div>
  </div>;
}

function percent(value?: number | null) {
  return value == null ? '—' : `${(Number(value) * 100).toFixed(1)}%`;
}

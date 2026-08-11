import { Search, Trophy } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { fetchPlayerAnalyticsLeaderboard } from '../lib/api';

const metrics:any = {
  currentFormRating: 'Current Form',
  consistencyRating: 'Consistency',
  clutchRating: 'Clutch',
  carryRating: 'Carry Performance',
  competitionStrengthRating: 'Strength of Competition',
  calculatedPpr: 'PPR',
  calculatedDpr: 'DPR',
  rounds: 'Rounds',
};

export default function PlayerAnalyticsLeaderboardView() {
  const [data, setData] = useState<any>({ players: [] });
  const [sort, setSort] = useState('currentFormRating');
  const [search, setSearch] = useState('');
  const [minimumRounds, setMinimumRounds] = useState(30);
  const [minimumClutch, setMinimumClutch] = useState(0);
  const [classification, setClassification] = useState<'ALL'|'PRO'|'NON_PRO'>('ALL');
  const [membership, setMembership] = useState('ALL');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    setLoading(true);
    fetchPlayerAnalyticsLeaderboard(sort, 500, classification, membership).then(setData).finally(() => setLoading(false));
  }, [sort, classification, membership]);
  const players = useMemo(() => (data.players || []).filter((row:any) => {
    const query = search.toLowerCase().trim();
    return (!query || String(row.playerName).toLowerCase().includes(query) || String(row.playerId).includes(query))
      && Number(row.rounds || 0) >= minimumRounds
      && Number(row.clutchOpportunities || 0) >= minimumClutch;
  }), [data, search, minimumRounds, minimumClutch]);
  return (
    <section className="mt-4 space-y-4">
      <div className="rounded-[30px] border border-white/10 bg-zinc-950 p-6">
        <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.24em] text-amber-300"><Trophy size={17}/> Player Analytics Leaderboard</div>
        <h2 className="mt-2 text-3xl font-black text-white">Compare predictive player profiles</h2>
        <p className="mt-2 text-sm text-zinc-500">Cheesebaggers-calculated rankings. ACL CPI is intentionally kept separate from these calculated metrics.</p>
        {data?.snapshot?.profile_count > 0 && (
          <p className="mt-3 text-xs font-bold text-emerald-300">
            {Number(data.snapshot.profile_count).toLocaleString()} saved profiles ready
            {' · '}
            {data.snapshot.stage === 'FULL_READY'
              ? 'all calculated ratings included'
              : 'core profiles ready while advanced ratings refresh'}
          </p>
        )}
      </div>
      <div className="grid gap-2 rounded-2xl border border-white/10 bg-zinc-950 p-4 md:grid-cols-[1fr_150px_150px_180px_140px_140px]">
        <label className="flex items-center gap-2 rounded-xl bg-white/5 px-3"><Search size={16}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search player or ID" className="w-full bg-transparent py-3 text-sm outline-none"/></label>
        <select value={classification} onChange={e=>setClassification(e.target.value as any)} className="rounded-xl bg-zinc-900 px-3 text-sm">
          <option value="ALL">All players</option>
          <option value="PRO">ACL Pros</option>
          <option value="NON_PRO">Non-pro</option>
        </select>
        <select value={membership} onChange={e=>setMembership(e.target.value)} className="rounded-xl bg-zinc-900 px-3 text-sm">
          <option value="ALL">All memberships</option>
          {(data.membershipOptions || []).map((name:string)=><option key={name} value={name.toUpperCase()}>{name}</option>)}
          <option value="UNKNOWN">Membership unknown</option>
        </select>
        <select value={sort} onChange={e=>{
          const nextSort = e.target.value;
          setSort(nextSort);
          if (nextSort === 'consistencyRating' && minimumRounds < 100) setMinimumRounds(100);
        }} className="rounded-xl bg-zinc-900 px-3 text-sm">{Object.entries(metrics).map(([key,label]:any)=><option key={key} value={key}>{label}</option>)}</select>
        <input type="number" min="0" value={minimumRounds} onChange={e=>setMinimumRounds(Number(e.target.value))} title="Minimum rounds" className="rounded-xl bg-zinc-900 px-3 text-sm" placeholder="Min rounds"/>
        <input type="number" min="0" value={minimumClutch} onChange={e=>setMinimumClutch(Number(e.target.value))} title="Minimum clutch opportunities" className="rounded-xl bg-zinc-900 px-3 text-sm" placeholder="Min clutch"/>
      </div>
      <div className="overflow-x-auto rounded-[26px] border border-white/10 bg-zinc-950">
        <table className="w-full min-w-[1100px]">
          <thead className="bg-white/[.04] text-left text-[10px] uppercase tracking-wider text-zinc-500"><tr><th className="p-3">Rank</th><th>Player</th><th>Form</th><th>Consistency</th><th>Clutch</th><th>Carry</th><th>Competition</th><th>PPR</th><th>DPR</th><th>Rounds</th><th>Sample confidence</th></tr></thead>
          <tbody>
            {players.map((row:any,index:number)=><tr key={row.playerId} className="border-t border-white/10 hover:bg-white/[.03]">
              <td className="p-3 font-black text-amber-300">{index+1}</td>
              <td><a href={`/?view=profile&playerId=${row.playerId}`} className="font-black text-white hover:text-amber-300">{row.playerName}</a><div className="flex flex-wrap items-center gap-2 text-[10px] text-zinc-600">Player {row.playerId}{row.isPro && <span className="rounded bg-amber-300/15 px-1.5 py-0.5 font-black text-amber-200">ACL PRO</span>}{row.membershipName && <span className="rounded bg-cyan-300/10 px-1.5 py-0.5 font-black text-cyan-200">{row.membershipName}</span>}</div></td>
              <Rating value={row.currentFormRating} label={row.currentFormLabel}/>
              <Rating value={row.consistencyRating} label={row.consistencyLabel}/>
              <Rating value={row.clutchRating} label={row.clutchLabel}/>
              <Rating value={row.carryRating} label={row.carryLabel}/>
              <Rating value={row.competitionStrengthRating} label={row.competitionStrengthLabel}/>
              <td className="font-bold">{num(row.calculatedPpr)}</td><td className="font-bold">{num(row.calculatedDpr)}</td><td>{row.rounds}</td><td>{pct(row.reliability)}</td>
            </tr>)}
          </tbody>
        </table>
        {!loading && !players.length && <div className="p-8 text-center text-zinc-500">No players match these filters.</div>}
        {loading && <div className="p-8 text-center text-zinc-500">Loading rankings…</div>}
      </div>
    </section>
  );
}
function Rating({value,label}:any){return <td><div className="font-black text-white">{value ?? '—'}</div><div className="text-[10px] text-zinc-600">{label || 'Not rated'}</div></td>}
function num(value:any){return value==null?'—':Number(value).toFixed(2)}
function pct(value:any){return value==null?'—':`${(Number(value)*100).toFixed(0)}%`}

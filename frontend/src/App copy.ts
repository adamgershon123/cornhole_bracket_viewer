import React, {useEffect, useMemo, useState} from 'react';
import { createRoot } from 'react-dom/client';
import { RefreshCw } from 'lucide-react';
import './index.css';
import { fetchEvent, type Match } from './lib/api';
import { ScoreHero } from './components/ScoreHero';
import { MetricPill } from './components/MetricPill';
import { PlayerBars } from './components/PlayerBars';
import { MomentumChart } from './components/MomentumChart';
import { RoundTimeline } from './components/RoundTimeline';

function useQueryParam(name:string, fallback:string){ return new URLSearchParams(location.search).get(name) || fallback }

function App(){
  const [eventId,setEventId]=useState(useQueryParam('event_id','248182'));
  const [data,setData]=useState<any>(null);
  const [selected,setSelected]=useState<string|undefined>();
  const [loading,setLoading]=useState(false);
  const [err,setErr]=useState<string|undefined>();
	async function load(stats = true) {
	  setLoading(true);
	  setErr(undefined);

	  try {
		const d = await fetchEvent(eventId, stats);
		setData(d);

		setSelected(current => {
		  if (current && d.matches?.some((m: Match) => m.matchId === current)) {
			return current;
		  }

		  return (d.matches?.find((m: Match) => m.status === 'live') || d.matches?.[0])?.matchId;
		});
	  } catch (e: any) {
		setErr(e.message);
	  } finally {
		setLoading(false);
	  }
	}
  useEffect(()=>{load(true); const id=setInterval(()=>load(true),30000); return ()=>clearInterval(id)},[eventId]);
  const match:Match|undefined=useMemo(()=>data?.matches?.find((m:Match)=>m.matchId===selected) || data?.matches?.[0],[data,selected]);
  const game=match?.activeGame || match?.games?.[0];
  const players=game?.players || [];
  const rounds=game?.rounds || [];
  return <main className="min-h-screen safe-x py-4 max-w-6xl mx-auto">
    <header className="flex items-center justify-between gap-3 sticky top-0 z-20 bg-black/75 backdrop-blur py-3">
      <div><div className="text-xs uppercase tracking-[.25em] text-amber-300">Cornhole Live</div><h1 className="text-xl font-black leading-tight truncate max-w-[240px] sm:max-w-none">{data?.event?.name || 'Live Scoreboard'}</h1></div>
      <button onClick={()=>load(true)} className="rounded-full border border-white/10 bg-zinc-900 p-3"> <RefreshCw className={loading?'animate-spin':''} size={18}/> </button>
    </header>
    <form onSubmit={(e)=>{e.preventDefault(); load(true)}} className="mt-2 flex gap-2"><input className="flex-1 rounded-2xl bg-zinc-900 border border-white/10 px-4 py-3" value={eventId} onChange={e=>setEventId(e.target.value)} placeholder="Event ID"/><button className="rounded-2xl bg-amber-400 text-black font-black px-5">Load</button></form>
    {err && <div className="mt-3 rounded-2xl bg-red-950 border border-red-500/40 p-3 text-sm">{err}</div>}
    {data && <nav className="mt-4 flex overflow-x-auto gap-2 pb-2">{data.matches.map((m:Match)=><button key={m.matchId} onClick={()=>setSelected(m.matchId)} className={`shrink-0 rounded-2xl px-4 py-3 border ${m.matchId===match?.matchId?'bg-white text-black border-white':'bg-zinc-900 border-white/10'}`}><div className="text-xs opacity-70">Court {m.courtId||'?'} · Match {m.matchId}</div><div className="font-black max-w-[210px] truncate">{m.teams.top.name} vs {m.teams.bottom.name}</div></button>)}</nav>}
    {match && <div className="mt-4 grid grid-cols-1 lg:grid-cols-[1.05fr_.95fr] gap-4">
      <div className="space-y-4"><ScoreHero match={match}/><div className="grid grid-cols-3 gap-2"><MetricPill label="Round" value={game?.currentRound || match.currentRound || '-'}/><MetricPill label="Top PPR" value={players[0]?.ppr?.toFixed(2)||'0.00'}/><MetricPill label="Rounds" value={rounds.length}/></div><PlayerBars players={players}/></div>
      <div className="space-y-4"><MomentumChart rounds={rounds} topTeamId={match.teams.top.id} bottomTeamId={match.teams.bottom.id}/><RoundTimeline rounds={rounds}/><section className="glass rounded-[28px] p-4"><h2 className="text-lg font-black mb-3">Match List Context</h2><div className="grid grid-cols-3 gap-2 text-center"><MetricPill label="Live" value={data.matches.filter((m:Match)=>m.status==='live').length}/><MetricPill label="Done" value={data.matches.filter((m:Match)=>m.status==='completed').length}/><MetricPill label="Upcoming" value={data.matches.filter((m:Match)=>m.status==='upcoming').length}/></div></section></div>
    </div>}
  </main>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);

import { LockKeyhole, Mail, Phone, RefreshCw, Search, ShieldCheck, UserRound } from 'lucide-react';
import { FormEvent, useEffect, useState } from 'react';
import { fetchPrivatePlayerDirectory, refreshPrivatePlayerDirectory } from '../lib/api';

const TOKEN_KEY = 'cheesebaggers.playerDirectoryAccess';
const PAGE_SIZE = 100;

export default function PlayerDirectoryView() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || '');
  const [tokenInput, setTokenInput] = useState('');
  const [data, setData] = useState<any>();
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [classification, setClassification] = useState('ALL');
  const [membership, setMembership] = useState('ALL');
  const [contact, setContact] = useState('ALL');
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    setError('');
    fetchPrivatePlayerDirectory(token, {
      search, classification, membership, contact, limit: PAGE_SIZE, offset,
    })
      .then(setData)
      .catch((reason:Error) => {
        setError(reason.message);
        if (/access|required|401|valid player directory/i.test(reason.message)) {
          sessionStorage.removeItem(TOKEN_KEY);
          setToken('');
        }
      })
      .finally(() => setLoading(false));
  }, [token, search, classification, membership, contact, offset]);

  function unlock(event:FormEvent) {
    event.preventDefault();
    const value = tokenInput.trim();
    if (!value) return;
    sessionStorage.setItem(TOKEN_KEY, value);
    setToken(value);
    setTokenInput('');
  }

  function applySearch(event:FormEvent) {
    event.preventDefault();
    setOffset(0);
    setSearch(searchInput.trim());
  }

  async function refreshIndex() {
    if (!token) return;
    setRefreshing(true);
    setError('');
    try {
      await refreshPrivatePlayerDirectory(token);
      const updated = await fetchPrivatePlayerDirectory(token, {
        search, classification, membership, contact, limit: PAGE_SIZE, offset,
      });
      setData(updated);
    } catch (reason:any) {
      setError(reason.message || String(reason));
    } finally {
      setRefreshing(false);
    }
  }

  if (!token) {
    return (
      <section className="mx-auto mt-5 max-w-xl rounded-[30px] border border-amber-300/25 bg-zinc-950 p-6 sm:p-8">
        <div className="grid h-14 w-14 place-items-center rounded-2xl bg-amber-300/10 text-amber-300"><LockKeyhole size={28}/></div>
        <div className="mt-5 text-xs font-black uppercase tracking-[.24em] text-amber-300">Private player directory</div>
        <h2 className="mt-2 text-3xl font-black text-white">Collected profiles and contacts</h2>
        <p className="mt-3 text-sm leading-6 text-zinc-400">
          Player contact information comes from captured ACL schedule and swap records. Enter the administrator access code to continue.
        </p>
        <form onSubmit={unlock} className="mt-6 space-y-3">
          <input
            type="password"
            autoComplete="current-password"
            value={tokenInput}
            onChange={event => setTokenInput(event.target.value)}
            placeholder="Directory access code"
            className="w-full rounded-2xl border border-white/15 bg-zinc-900 px-4 py-4 text-base text-white outline-none focus:border-amber-300"
          />
          <button type="submit" className="min-h-[54px] w-full rounded-2xl bg-amber-300 px-5 font-black text-black active:translate-y-1">Open directory</button>
        </form>
        {error && <div className="mt-4 rounded-2xl border border-red-400/25 bg-red-950/30 p-4 text-sm text-red-200">{error}</div>}
        <div className="mt-5 flex items-start gap-2 text-xs leading-5 text-zinc-500"><ShieldCheck className="mt-0.5 shrink-0" size={15}/>Contacts are excluded from public profiles, APIs, rankings, and share images.</div>
      </section>
    );
  }

  const players = data?.players || [];
  const coverage = data?.contactCoverage || {};
  const end = Math.min(offset + players.length, Number(data?.total || 0));
  return (
    <section className="mt-4 space-y-4">
      <div className="rounded-[30px] border border-white/10 bg-zinc-950 p-5 sm:p-7">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.24em] text-amber-300"><UserRound size={17}/> Private player directory</div>
            <h2 className="mt-2 text-3xl font-black text-white">Collected player profiles</h2>
            <p className="mt-2 text-sm leading-6 text-zinc-500">Analytics profiles joined to captured ACL player contact records.</p>
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={refreshIndex} disabled={refreshing} className="flex min-h-[48px] items-center gap-2 rounded-2xl border border-amber-300/40 bg-amber-300/10 px-4 font-black text-amber-200 disabled:opacity-50">
              <RefreshCw size={17} className={refreshing ? 'animate-spin' : ''}/>{refreshing ? 'Indexing…' : 'Index new captures'}
            </button>
            <button type="button" onClick={() => { sessionStorage.removeItem(TOKEN_KEY); setToken(''); setData(undefined); }} className="min-h-[48px] rounded-2xl border border-white/10 bg-zinc-900 px-4 text-sm font-bold text-zinc-300">Lock</button>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Summary label="Indexed contacts" value={coverage.players}/>
          <Summary label="With email" value={coverage.with_email}/>
          <Summary label="With phone" value={coverage.with_phone}/>
          <Summary label="Profiles shown" value={data?.total}/>
        </div>
      </div>

      <div className="rounded-[26px] border border-white/10 bg-zinc-950 p-4">
        <form onSubmit={applySearch} className="grid gap-2 lg:grid-cols-[1fr_150px_180px_160px_auto]">
          <label className="flex min-h-[50px] items-center gap-2 rounded-xl bg-white/5 px-3"><Search size={17}/><input value={searchInput} onChange={event=>setSearchInput(event.target.value)} placeholder="Search player name or ACL ID" className="w-full bg-transparent py-3 text-sm outline-none"/></label>
          <select value={classification} onChange={event=>{setClassification(event.target.value);setOffset(0)}} className="min-h-[50px] rounded-xl bg-zinc-900 px-3 text-sm">
            <option value="ALL">All players</option><option value="PRO">ACL Pros</option><option value="NON_PRO">Non-pro</option>
          </select>
          <select value={membership} onChange={event=>{setMembership(event.target.value);setOffset(0)}} className="min-h-[50px] rounded-xl bg-zinc-900 px-3 text-sm">
            <option value="ALL">All memberships</option>
            {(data?.membershipOptions || []).map((name:string)=><option key={name} value={name.toUpperCase()}>{name}</option>)}
            <option value="UNKNOWN">Membership unknown</option>
          </select>
          <select value={contact} onChange={event=>{setContact(event.target.value);setOffset(0)}} className="min-h-[50px] rounded-xl bg-zinc-900 px-3 text-sm">
            <option value="ALL">Any contact status</option><option value="BOTH">Email and phone</option><option value="EMAIL">Has email</option><option value="PHONE">Has phone</option><option value="MISSING">Contact missing</option>
          </select>
          <button type="submit" className="min-h-[50px] rounded-xl bg-amber-300 px-5 font-black text-black active:translate-y-1">Search</button>
        </form>
      </div>

      {error && <div className="rounded-2xl border border-red-400/25 bg-red-950/30 p-4 text-sm text-red-200">{error}</div>}
      {loading && <div className="rounded-[26px] border border-white/10 bg-zinc-950 p-10 text-center text-zinc-400">Loading private player directory…</div>}
      {!loading && (
        <div className="grid gap-3 lg:grid-cols-2">
          {players.map((player:any)=><PlayerCard key={player.playerId} player={player}/>) }
        </div>
      )}
      {!loading && !players.length && <div className="rounded-[26px] border border-dashed border-white/10 p-10 text-center text-zinc-500">No collected profiles match these filters.</div>}
      {data && (
        <div className="flex flex-col items-center justify-between gap-3 rounded-2xl border border-white/10 bg-zinc-950 p-4 sm:flex-row">
          <div className="text-sm text-zinc-400">Showing {data.total ? offset + 1 : 0}–{end} of {Number(data.total || 0).toLocaleString()}</div>
          <div className="flex gap-2">
            <button type="button" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-PAGE_SIZE))} className="min-h-[46px] rounded-xl border border-white/10 bg-zinc-900 px-5 font-bold disabled:opacity-30">Previous</button>
            <button type="button" disabled={end>=Number(data.total||0)} onClick={()=>setOffset(offset+PAGE_SIZE)} className="min-h-[46px] rounded-xl border border-white/10 bg-zinc-900 px-5 font-bold disabled:opacity-30">Next</button>
          </div>
        </div>
      )}
    </section>
  );
}

function PlayerCard({player}:{player:any}) {
  const [photoFailed,setPhotoFailed]=useState(false);
  const initials=String(player.playerName||'P').split(/\s+/).filter(Boolean).slice(0,2).map((part:string)=>part[0]).join('').toUpperCase();
  return <article className="rounded-[24px] border border-white/10 bg-zinc-950 p-4 sm:p-5">
    <div className="flex items-start gap-3">
      {player.profileImage&&!photoFailed?<img src={String(player.profileImage).trim()} onError={()=>setPhotoFailed(true)} className="h-16 w-16 shrink-0 rounded-full border border-white/15 object-cover"/>:<div className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-zinc-900 font-black text-amber-300">{initials}</div>}
      <div className="min-w-0 flex-1">
        <a href={`/?view=profile&playerId=${player.playerId}`} className="text-xl font-black leading-tight text-white hover:text-amber-300">{player.playerName}</a>
        <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] font-black uppercase tracking-wide text-zinc-500">
          <span>ACL {player.playerId}</span>{player.isPro&&<span className="rounded bg-amber-300/15 px-1.5 py-0.5 text-amber-200">PRO</span>}{player.membershipName&&<span className="rounded bg-sky-300/10 px-1.5 py-0.5 text-sky-200">{player.membershipName}</span>}
        </div>
        {(player.city||player.state)&&<div className="mt-1 text-xs text-zinc-500">{[player.city,player.state].filter(Boolean).join(', ')}</div>}
      </div>
      <div className="text-right"><div className="text-2xl font-black text-sky-300">{num(player.calculatedPpr)}</div><div className="text-[9px] font-black uppercase tracking-wider text-zinc-600">PPR</div></div>
    </div>
    <div className="mt-4 grid gap-2 sm:grid-cols-2">
      {player.email?<a href={`mailto:${player.email}`} className="flex min-h-[48px] items-center gap-2 overflow-hidden rounded-xl bg-white/[.05] px-3 text-sm font-bold text-sky-200"><Mail size={16} className="shrink-0"/><span className="truncate">{player.email}</span></a>:<Missing icon={<Mail size={16}/>} label="Email not captured"/>}
      {player.phone?<a href={`tel:${player.phone}`} className="flex min-h-[48px] items-center gap-2 rounded-xl bg-white/[.05] px-3 text-sm font-bold text-emerald-200"><Phone size={16}/>{player.phone}</a>:<Missing icon={<Phone size={16}/>} label="Phone not captured"/>}
    </div>
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-3 text-[10px] text-zinc-600">
      <span>{Number(player.rounds||0).toLocaleString()} rounds · Form {player.currentFormRating??'—'}</span>
      <span>{player.contactSource?`${sourceLabel(player.contactSource)}${player.contactSourceEventId?` · Event ${player.contactSourceEventId}`:''}`:'No captured contact source'}</span>
    </div>
  </article>;
}

function Missing({icon,label}:{icon:any;label:string}){return <div className="flex min-h-[48px] items-center gap-2 rounded-xl bg-white/[.025] px-3 text-sm text-zinc-600">{icon}{label}</div>}
function Summary({label,value}:{label:string;value:any}){return <div className="rounded-2xl bg-white/[.04] p-3"><div className="text-2xl font-black text-white">{Number(value||0).toLocaleString()}</div><div className="mt-1 text-[9px] font-black uppercase tracking-wider text-zinc-500">{label}</div></div>}
function num(value:any){return value==null?'—':Number(value).toFixed(2)}
function sourceLabel(value:string){return value==='swap_standings'?'Swap standings':value==='swap_up_next'?'Swap up-next':'Event schedule'}

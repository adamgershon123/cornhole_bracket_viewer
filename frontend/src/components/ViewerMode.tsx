import { Brackets, Check, ChevronRight, Eye, Flag, Share2, Trophy, Users } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { Match, PlayerStat, RoundRow, TournamentStatsPlayer, TournamentStatsResponse } from '../lib/api';
import { fetchBracketProbabilities, fetchTournamentStats } from '../lib/api';
import { SharePlayerStatusSnapshotButton } from './ShareSnapshotButton';

export function ViewerMode({
  match,
  matches,
  players,
  playerId,
  subjectTeamId,
  event,
  winProbability,
  standalone = false,
}: {
  match: Match;
  matches: Match[];
  players: PlayerStat[];
  playerId: string;
  subjectTeamId?: string;
  event?: any;
  winProbability?: any;
  standalone?: boolean;
}) {
  const [shareNotice, setShareNotice] = useState('');
  const [bracketProjection, setBracketProjection] = useState<any>();
  const [tournamentStats, setTournamentStats] = useState<TournamentStatsResponse | null>(null);
  const [tournamentStatsLoading, setTournamentStatsLoading] = useState(true);
  const [selectedTeamId, setSelectedTeamId] = useState(
    String(subjectTeamId || new URLSearchParams(window.location.search).get('teamId') || '')
  );
  useEffect(() => {
    if (subjectTeamId) setSelectedTeamId(String(subjectTeamId));
  }, [subjectTeamId]);
  useEffect(() => {
    let cancelled = false;
    fetchBracketProbabilities(String(match.eventId))
      .then(result => { if (!cancelled) setBracketProjection(result); })
      .catch(() => { if (!cancelled) setBracketProjection(null); });
    return () => { cancelled = true; };
  }, [match.eventId]);
  const requestedPlayer = players.find(player => String(player.id) === String(playerId));
  const requestedPlayerTeamId = String(requestedPlayer?.teamId || '');
  const myTeamId = (
    [match.teams.top.id, match.teams.bottom.id].some(id => String(id) === selectedTeamId)
      ? selectedTeamId
      : requestedPlayerTeamId
  ) || String(match.teams.top.id);
  const topIsMine = myTeamId === String(match.teams.top.id);
  const myTeam = topIsMine ? match.teams.top : match.teams.bottom;
  const opponent = topIsMine ? match.teams.bottom : match.teams.top;
  const displayedMatchStatus = placeholderTeam(opponent.name)
    ? 'waiting'
    : match.status;
  const game = match.activeGame || match.games?.[0];
  const myScore = Number(topIsMine ? game?.score?.top ?? match.score.top ?? 0 : game?.score?.bottom ?? match.score.bottom ?? 0);
  const opponentScore = Number(topIsMine ? game?.score?.bottom ?? match.score.bottom ?? 0 : game?.score?.top ?? match.score.top ?? 0);
  const appearances = matches.filter(item => teamAppears(item, myTeamId, myTeam.name) && !isByeMatch(item));
  useEffect(() => {
    let cancelled = false;
    const loadStats = () => fetchTournamentStats(
      String(match.eventId),
      {
        refresh: false,
        refreshLive: match.status === 'live',
        cachedOnly: false,
        teamId: myTeamId,
      },
    )
      .then(result => { if (!cancelled) setTournamentStats(result); })
      .catch(() => { if (!cancelled) setTournamentStats(null); })
      .finally(() => { if (!cancelled) setTournamentStatsLoading(false); });
    setTournamentStatsLoading(true);
    loadStats();
    const timer = match.status === 'live'
      ? window.setInterval(loadStats, 30_000)
      : undefined;
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [match.eventId, match.status, myTeamId]);
  const completed = appearances.filter(item => item.status === 'completed');
  const record = completed.reduce((total, item) => {
    const teamIsTop = sameTeam(item.teams.top, myTeamId, myTeam.name);
    const itemGame = item.activeGame || item.games?.[0];
    const mine = Number(teamIsTop ? itemGame?.score?.top ?? item.score.top : itemGame?.score?.bottom ?? item.score.bottom);
    const theirs = Number(teamIsTop ? itemGame?.score?.bottom ?? item.score.bottom : itemGame?.score?.top ?? item.score.top);
    if (mine > theirs) total.wins += 1;
    else if (mine < theirs) total.losses += 1;
    return total;
  }, { wins: 0, losses: 0 });
  const pendingAppearance = appearances.some(item => item.status !== 'completed');
  const eventComplete = matches.length > 0 && matches.every(item => item.status === 'completed');
  const latestAppearance = [...completed].sort((a, b) => stageOrder(b.roundDescription) - stageOrder(a.roundDescription) || Number(b.matchId || 0) - Number(a.matchId || 0))[0];
  const latestWasLoss = latestAppearance ? teamLost(latestAppearance, myTeamId, myTeam.name) : false;
  const hasEliminationBracket = matches.some(item => normalizedSide(item) === 'L');
  const eliminated = !pendingAppearance && (
    eventComplete
    || (latestWasLoss && (normalizedSide(latestAppearance) === 'L' || !hasEliminationBracket || record.losses >= 2))
  );
  const probabilityPoint = winProbability?.points?.at(-1);
  const probability = probabilityPoint
    ? (topIsMine ? Number(probabilityPoint.topWinProbability) : Number(probabilityPoint.bottomWinProbability)) * 100
    : undefined;
  const frozenMatchProbability = gameProjection(match, bracketProjection, myTeamId, myTeam.name);
  const displayedProbability = Number.isFinite(probability)
    ? probability
    : frozenMatchProbability;
  const path = championshipPath(match, matches, eliminated);
  const eventCompleted = matches.filter(item => item.status === 'completed').length;
  const eventTotal = matches.length;
  const standing = eliminated ? 'Eliminated' : record.losses === 0 ? 'Undefeated' : record.losses === 1 ? 'One loss' : `${record.losses} losses`;
  const projectedTeam = findProjectedTeam(bracketProjection?.pregameSnapshot?.teams || bracketProjection?.teams || [], playerId, myTeamId, myTeam.name);
  const teamPlayers = viewedTeamPlayers(
    projectedTeam,
    matches,
    myTeamId,
    myTeam.name,
    tournamentStats,
  );
  const showCurrentGameStats = displayedMatchStatus === 'live';
  const initialTournamentChance = projectedTeam?.winEventProbability == null ? undefined : Number(projectedTeam.winEventProbability) * 100;
  const futureGameChance = averageProjectedGameChance(bracketProjection, projectedTeam?.teamId || myTeamId);
  const gameHistory = [...appearances].sort((a, b) => Number(a.matchId || 0) - Number(b.matchId || 0));
  const opponentOutlook = upcomingOpponentOutlook(
    match,
    matches,
    bracketProjection,
    myTeamId,
    myTeam.name,
  );

  return (
    <section className={`space-y-3 ${standalone ? 'mx-auto w-full max-w-3xl py-3' : 'lg:hidden'}`}>
      <div className="overflow-hidden rounded-[26px] border border-sky-300/25 bg-gradient-to-br from-sky-950/50 via-zinc-950 to-zinc-950">
        <div className="flex items-start justify-between gap-3 border-b border-white/10 p-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.2em] text-sky-300"><Eye size={16}/> Viewer Mode</div>
            <h2 className="mt-2 text-2xl font-black text-white">{myTeam.name}</h2>
            <div className="mt-1 text-sm font-bold text-zinc-400">{event?.name || `Event ${match.eventId}`}</div>
          </div>
          <span className={`rounded-lg px-3 py-1 text-xs font-black ${displayedMatchStatus === 'live' ? 'bg-emerald-400 text-black' : displayedMatchStatus === 'completed' ? 'bg-blue-400 text-black' : 'bg-amber-300 text-black'}`}>
            {displayedMatchStatus === 'live' ? 'PLAYING' : displayedMatchStatus === 'completed' ? 'MATCH FINAL' : displayedMatchStatus === 'waiting' ? 'WAITING ON OPPONENT' : 'UP NEXT'}
          </span>
        </div>
        <div className="border-b border-white/10 p-3">
          <div className="mb-2 text-[10px] font-black uppercase tracking-[.18em] text-zinc-500">Status being viewed and shared</div>
          <div className="grid grid-cols-2 gap-2">
            {[match.teams.top, match.teams.bottom].map(team => {
              const active = String(team.id) === myTeamId;
              return (
                <button
                  key={team.id}
                  type="button"
                  aria-pressed={active}
                  onClick={() => {
                    setSelectedTeamId(String(team.id));
                    const url = new URL(window.location.href);
                    url.searchParams.set('teamId', String(team.id));
                    window.history.replaceState({}, '', url.toString());
                    setShareNotice(`Now viewing ${team.name}.`);
                  }}
                  className={`min-h-14 rounded-xl border px-3 py-2 text-left text-sm font-black transition active:scale-[.98] ${
                    active
                      ? 'border-sky-300 bg-sky-300 text-black shadow-[0_0_0_2px_rgba(125,211,252,.15)]'
                      : 'border-white/10 bg-white/[.04] text-zinc-300'
                  }`}
                >
                  <span className="block text-[9px] uppercase tracking-wider opacity-70">{active ? 'Viewing' : 'View team'}</span>
                  <span className="mt-1 block leading-tight">{team.name}</span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="p-4">
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
            <div>
              <div className="text-sm font-black leading-tight text-sky-200">{myTeam.name}</div>
              <div className="mt-2 text-6xl font-black text-white">{myScore}</div>
            </div>
            <div className="text-xl font-black text-zinc-600">–</div>
            <div className="text-right">
              <div className="text-sm font-black leading-tight text-zinc-400">{opponent.name}</div>
              <div className="mt-2 text-6xl font-black text-zinc-400">{opponentScore}</div>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-white/10 pt-3">
            <div className="text-sm font-black text-white">{match.roundDescription || 'Bracket match'} · Court {court(match.courtId)}</div>
            <div className="text-sm font-black text-amber-300">
              {displayedMatchStatus === 'completed'
                ? myScore > opponentScore ? 'Won this match' : myScore < opponentScore ? 'Lost this match' : 'Final result'
                : displayedMatchStatus === 'waiting' ? 'Awaiting opponent'
                : displayedProbability == null || !Number.isFinite(displayedProbability)
                ? 'Projection unavailable'
                : `${displayedProbability.toFixed(1)}% ${Number.isFinite(probability) ? 'live win chance' : 'pregame win chance'}`}
            </div>
          </div>
        </div>
      </div>

      {opponentOutlook && (
        <div className="overflow-hidden rounded-2xl border border-violet-300/25 bg-violet-300/[.05]">
          <div className="border-b border-violet-300/15 p-4">
            <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.18em] text-violet-300">
              <Brackets size={17}/> Upcoming opponent outlook
            </div>
            <div className="mt-2 text-2xl font-black text-white">{opponentOutlook.round}</div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs font-black">
              <span className="rounded-lg bg-white/10 px-3 py-2 text-zinc-200">Court {opponentOutlook.court}</span>
              <span className={`rounded-lg px-3 py-2 ${opponentOutlook.status === 'LIVE' ? 'bg-emerald-400 text-black' : opponentOutlook.status === 'FINAL' ? 'bg-blue-400 text-black' : 'bg-amber-300 text-black'}`}>
                {opponentOutlook.status}
              </span>
            </div>
            <div className="mt-2 text-sm leading-6 text-zinc-400">{opponentOutlook.explanation}</div>
          </div>
          <div className="space-y-2 p-3">
            {opponentOutlook.feederMatches.map((feeder: Match) => {
              const feederGame = feeder.activeGame || feeder.games?.[0];
              const topScore = Number(feederGame?.score?.top ?? feeder.score.top ?? 0);
              const bottomScore = Number(feederGame?.score?.bottom ?? feeder.score.bottom ?? 0);
              return (
                <div key={`feeder:${feeder.matchId}`} className="overflow-hidden rounded-xl border border-sky-300/25 bg-sky-950/20">
                  <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
                    <div>
                      <div className="text-[10px] font-black uppercase tracking-[.18em] text-sky-300">Waiting on this game</div>
                      <div className="mt-1 text-xs font-bold text-zinc-400">
                        {feeder.roundDescription || `Match ${feeder.matchId}`} · Court {courtValue(feeder.courtId)}
                      </div>
                    </div>
                    <span className={`rounded-lg px-2 py-1 text-xs font-black ${feeder.status === 'live' ? 'bg-emerald-400 text-black' : 'bg-amber-300 text-black'}`}>
                      {feeder.status === 'live' ? 'LIVE' : 'NOT STARTED'}
                    </span>
                  </div>
                  <div className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-3 p-4">
                    <div className="min-w-0 text-base font-black leading-tight text-white">{feeder.teams.top.name}</div>
                    <div className="text-3xl font-black text-sky-300">{topScore}</div>
                    <div className="min-w-0 text-base font-black leading-tight text-zinc-300">{feeder.teams.bottom.name}</div>
                    <div className="text-3xl font-black text-zinc-300">{bottomScore}</div>
                  </div>
                  <div className="border-t border-white/10 px-4 py-3 text-xs font-bold text-zinc-400">
                    {feeder.status === 'live'
                      ? `Round ${feeder.currentRound || feederGame?.currentRound || 'in progress'} · Score refreshes with tournament status`
                      : 'This game has not started yet. The winner or loser will determine the next opponent.'}
                  </div>
                </div>
              );
            })}
            {opponentOutlook.options.map((option: any) => (
              <div key={`${option.teamId}:${option.condition}`} className="rounded-xl border border-white/10 bg-black/30 p-4">
                <div className="text-xs font-black uppercase tracking-wider text-zinc-500">{option.condition}</div>
                <div className="mt-1 text-lg font-black text-white">{option.teamName}</div>
                <div className="mt-3 flex items-end justify-between gap-3">
                  <div className="text-sm text-zinc-400">{myTeam.name} chance to win that matchup</div>
                  <div className="shrink-0 text-2xl font-black text-amber-300">
                    {option.probability == null ? 'Unavailable' : `${option.probability.toFixed(1)}%`}
                  </div>
                </div>
                {option.source && <div className="mt-2 text-xs text-zinc-600">{option.source}</div>}
              </div>
            ))}
            {!opponentOutlook.options.length && (
              <div className="rounded-xl border border-dashed border-white/10 p-4 text-sm text-zinc-500">
                ACL has not published enough bracket routing information to identify the possible opponents yet.
              </div>
            )}
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-2">
        <StatusStat label="Games played" value={String(completed.length)} />
        <StatusStat label="Record" value={`${record.wins}–${record.losses}`} />
        <StatusStat label="Position" value={standing} />
      </div>

      <div className="rounded-2xl border border-sky-300/25 bg-sky-300/[.05] p-4">
        <div className="text-xs font-black uppercase tracking-[.18em] text-sky-300">Initial tournament projection</div>
        <div className="mt-2 text-4xl font-black text-white">
          {initialTournamentChance == null || !Number.isFinite(initialTournamentChance) ? 'Unavailable' : `${initialTournamentChance.toFixed(1)}%`}
        </div>
        <div className="mt-1 text-sm text-zinc-400">
          Pregame chance to win the event, frozen before tournament results changed the bracket.
        </div>
      </div>

      <ViewedTeamStatistics
        teamName={myTeam.name}
        teamPlayers={teamPlayers}
        livePlayers={players}
        liveRounds={game?.rounds || []}
        showCurrentGame={showCurrentGameStats}
        loading={tournamentStatsLoading}
        coverage={tournamentStats?.matchStats}
      />

      <div className="overflow-hidden rounded-2xl border border-amber-300/25 bg-amber-300/[.05]">
        <div className="border-b border-amber-300/15 p-4">
          <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.18em] text-amber-300"><Trophy size={17}/> Path to a championship</div>
          <div className="mt-2 text-3xl font-black text-white">
            {eliminated ? 'Tournament run complete' : `Up to ${path.gamesLeft} game${path.gamesLeft === 1 ? '' : 's'} left`}
          </div>
          <div className="mt-1 text-sm text-zinc-400">
            {eliminated
              ? 'This player has no remaining scheduled or possible tournament games.'
              : `Estimated from the remaining ${path.sideLabel.toLowerCase()} stages published by ACL.`}
          </div>
        </div>
        <div className="space-y-1 p-3">
          {path.steps.map((step, index) => (
            <div key={`${step}:${index}`} className="flex items-center gap-3 rounded-xl bg-black/25 p-3">
              <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg font-black ${path.gamesLeft === 0 ? 'bg-red-400/20 text-red-200' : index === 0 ? 'bg-sky-400 text-black' : index === path.steps.length - 1 ? 'bg-amber-300 text-black' : 'bg-white/10 text-white'}`}>
                {path.gamesLeft === 0 ? <Flag size={17}/> : index === path.steps.length - 1 ? <Trophy size={17}/> : index + 1}
              </div>
              <div className="min-w-0 flex-1 font-black text-white">{step}</div>
              {index < path.steps.length - 1 && <ChevronRight className="shrink-0 text-zinc-600" size={18}/>}
              {path.gamesLeft > 0 && <div className="shrink-0 text-right text-xs font-bold text-zinc-500">
                {futureGameChance == null ? 'Opponent TBD' : `${futureGameChance.toFixed(1)}% vs field`}
              </div>}
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-2xl border border-white/10 bg-zinc-950 p-4">
          <div className="flex items-center gap-2 text-xs font-black uppercase tracking-wider text-zinc-500"><Brackets size={16}/> Tournament</div>
          <div className="mt-2 text-2xl font-black text-white">{eventCompleted}/{eventTotal}</div>
          <div className="mt-1 text-xs font-bold text-zinc-500">matches complete</div>
        </div>
        <div className="rounded-2xl border border-white/10 bg-zinc-950 p-4">
          <div className="flex items-center gap-2 text-xs font-black uppercase tracking-wider text-zinc-500"><Flag size={16}/> Destination</div>
          <div className="mt-2 text-xl font-black text-amber-300">Championship</div>
          <div className="mt-1 text-xs font-bold text-zinc-500">{path.sideLabel}</div>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-white/10 bg-zinc-950">
        <div className="border-b border-white/10 p-4">
          <div className="text-xs font-black uppercase tracking-[.18em] text-sky-300">Player tournament history</div>
          <div className="mt-1 text-sm text-zinc-400">Every known game for this player in chronological order.</div>
        </div>
        <div className="divide-y divide-white/10">
          {gameHistory.map((item, index) => {
            const teamIsTop = sameTeam(item.teams.top, myTeamId, myTeam.name);
            const itemGame = item.activeGame || item.games?.[0];
            const mine = Number(teamIsTop ? itemGame?.score?.top ?? item.score.top : itemGame?.score?.bottom ?? item.score.bottom);
            const theirs = Number(teamIsTop ? itemGame?.score?.bottom ?? item.score.bottom : itemGame?.score?.top ?? item.score.top);
            const itemOpponent = teamIsTop ? item.teams.bottom.name : item.teams.top.name;
            const chance = gameProjection(item, bracketProjection, myTeamId, myTeam.name);
            return <div key={`${item.matchId}:${index}`} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-black uppercase tracking-wider text-zinc-500">Game {index + 1} · {item.roundDescription || 'Bracket match'}</div>
                  <div className="mt-1 text-lg font-black text-white">vs {itemOpponent}</div>
                </div>
                <span className={`rounded-lg px-2 py-1 text-xs font-black ${item.status === 'completed' ? mine > theirs ? 'bg-emerald-400/15 text-emerald-200' : 'bg-red-400/15 text-red-200' : item.status === 'live' ? 'bg-sky-400 text-black' : 'bg-amber-300 text-black'}`}>
                  {item.status === 'completed' ? mine > theirs ? 'WIN' : 'LOSS' : item.status === 'live' ? 'LIVE' : 'POSSIBLE'}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <Mini label="Score" value={item.status === 'completed' || item.status === 'live' ? `${mine}–${theirs}` : 'Not started'} />
                <Mini label="Projected win chance" value={chance == null ? 'Unavailable' : `${chance.toFixed(1)}%`} />
              </div>
            </div>;
          })}
          {!gameHistory.length && <div className="p-4 text-sm text-zinc-500">No player games are available in the cached bracket yet.</div>}
        </div>
      </div>

      <div className="grid gap-2">
      <button type="button" onClick={async () => {
        const url = `${window.location.origin}/status/${match.eventId}/team/${encodeURIComponent(myTeamId)}`;
        try {
          if (navigator.share) {
            await navigator.share({ title: `${myTeam.name} tournament status`, url });
            setShareNotice('Status link shared.');
          } else {
            await navigator.clipboard.writeText(url);
            setShareNotice('Status link copied.');
          }
        } catch (error: any) {
          if (error?.name !== 'AbortError') setShareNotice('Unable to share automatically. Copy the page address instead.');
        }
      }} className="flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl border border-violet-300/35 bg-violet-300/10 px-4 text-base font-black text-violet-100 transition active:translate-y-px active:bg-violet-300/20">
        <Share2 size={19}/> Share This Player Status
      </button>
      <SharePlayerStatusSnapshotButton input={{
        eventId: String(match.eventId),
        eventName: event?.name || `Event ${match.eventId}`,
        playerId,
        playerName: myTeam.name,
        teamName: myTeam.name,
        record: `${record.wins}–${record.losses}`,
        status: standing,
        gamesPlayed: completed.length,
        gamesLeft: path.gamesLeft,
        initialTournamentChance,
        currentOpponent: opponent.name,
        currentScore: `${myScore}–${opponentScore}`,
        currentWinChance: match.status === 'completed' ? undefined : displayedProbability,
        path: path.steps,
      }}/>
      </div>
      {shareNotice && <div className="flex items-center gap-2 rounded-xl border border-emerald-300/20 bg-emerald-300/10 px-3 py-2 text-sm font-bold text-emerald-100"><Check size={17}/>{shareNotice}</div>}
    </section>
  );
}

function findProjectedTeam(teams: any[], playerId: string, teamId: string, teamName: string) {
  return teams.find(team => String(team.teamId || '') === teamId)
    || teams.find(team => (team.players || []).some((player: any) => String(player.playerId ?? player.id ?? '') === String(playerId)))
    || teams.find(team => String(team.teamName || '') === teamName);
}

function gameProjection(match: Match, bracket: any, teamId: string, teamName: string) {
  const teamIsTop = sameTeam(match.teams.top, teamId, teamName);
  const game = match.activeGame || match.games?.[0];
  const pregamePoint = game?.liveWinProbability?.points?.find((point: any) => Number(point.round) === 0)
    || game?.liveWinProbability?.points?.[0];
  if (pregamePoint) return (teamIsTop ? Number(pregamePoint.topWinProbability) : Number(pregamePoint.bottomWinProbability)) * 100;
  const details = bracket?.pregameSnapshot?.coverage?.pairingDetails || bracket?.coverage?.pairingDetails || [];
  const pairing = details.find((item: any) => {
    const mine = teamIsTop ? match.teams.top.id : match.teams.bottom.id;
    const theirs = teamIsTop ? match.teams.bottom.id : match.teams.top.id;
    return [String(item.teamAId), String(item.teamBId)].includes(String(mine))
      && [String(item.teamAId), String(item.teamBId)].includes(String(theirs));
  });
  if (!pairing) return undefined;
  const mineIsA = String(pairing.teamAId) === String(teamIsTop ? match.teams.top.id : match.teams.bottom.id);
  const value = mineIsA ? pairing.teamAProbability : pairing.teamBProbability;
  return value == null ? undefined : Number(value) * 100;
}

function averageProjectedGameChance(bracket: any, teamId: string) {
  const details = bracket?.pregameSnapshot?.coverage?.pairingDetails || bracket?.coverage?.pairingDetails || [];
  const values = details.flatMap((pairing: any) => {
    if (String(pairing.teamAId) === String(teamId) && pairing.teamAProbability != null) return [Number(pairing.teamAProbability) * 100];
    if (String(pairing.teamBId) === String(teamId) && pairing.teamBProbability != null) return [Number(pairing.teamBProbability) * 100];
    return [];
  }).filter(Number.isFinite);
  return values.length ? values.reduce((sum: number, value: number) => sum + value, 0) / values.length : undefined;
}

function upcomingOpponentOutlook(
  current: Match,
  matches: Match[],
  bracket: any,
  teamId: string,
  teamName: string,
) {
  const structure = bracket?.liveBracketStructure;
  const edges = structure?.edges || {};
  if (structure?.status !== 'VALIDATED_TEMPLATE' || !Object.keys(edges).length) return undefined;

  const currentIsTop = sameTeam(current.teams.top, teamId, teamName);
  const currentOpponent = currentIsTop ? current.teams.bottom : current.teams.top;
  let destination = current;
  let viewedPosition = currentIsTop ? 'T' : 'B';

  if (!placeholderTeam(currentOpponent.name)) {
    const winnerEdge = edges[`${current.matchId}:W`];
    if (!winnerEdge) return undefined;
    destination = matches.find(match => String(match.matchId) === String(winnerEdge.matchId)) as Match;
    if (!destination) return undefined;
    viewedPosition = String(winnerEdge.position || '').toUpperCase().includes('T') ? 'T' : 'B';
  }

  const opponentPosition = viewedPosition === 'T' ? 'B' : 'T';
  const destinationOpponent = opponentPosition === 'T'
    ? destination.teams.top
    : destination.teams.bottom;
  const options: any[] = [];
  const feederMatches: Match[] = [];

  if (destinationOpponent?.id && !placeholderTeam(destinationOpponent.name)) {
    options.push({
      teamId: String(destinationOpponent.id),
      teamName: destinationOpponent.name,
      condition: 'Opponent confirmed',
      probability: projectedMatchupChance(bracket, teamId, String(destinationOpponent.id)),
      source: `Already placed into Match ${destination.matchId}.`,
    });
  } else {
    Object.entries(edges).forEach(([edgeKey, edgeValue]: [string, any]) => {
      const position = String(edgeValue?.position || '').toUpperCase().includes('T') ? 'T' : 'B';
      if (String(edgeValue?.matchId) !== String(destination.matchId) || position !== opponentPosition) return;
      const [sourceMatchId, outcome = 'W'] = edgeKey.split(':');
      const sourceMatch = matches.find(match => String(match.matchId) === String(sourceMatchId));
      if (!sourceMatch) return;
      const sourceTeams = [sourceMatch.teams.top, sourceMatch.teams.bottom].filter(team => (
        team?.id && !placeholderTeam(team.name)
      ));
      if (sourceMatch.status === 'completed') {
        const resolved = outcome === 'L'
          ? losingTeam(sourceMatch)
          : winningTeam(sourceMatch);
        if (resolved) {
          options.push({
            teamId: String(resolved.id),
            teamName: resolved.name,
            condition: outcome === 'L' ? 'Feeder-game loser advances here' : 'Feeder-game winner advances here',
            probability: projectedMatchupChance(bracket, teamId, String(resolved.id)),
            source: `Match ${sourceMatch.matchId} is final.`,
          });
        }
        return;
      }
      if (!feederMatches.some(item => String(item.matchId) === String(sourceMatch.matchId))) {
        feederMatches.push(sourceMatch);
      }
      sourceTeams.forEach(team => options.push({
        teamId: String(team.id),
        teamName: team.name,
        condition: outcome === 'L' ? `If ${team.name} loses` : `If ${team.name} wins`,
        probability: projectedMatchupChance(bracket, teamId, String(team.id)),
        source: `Feeder Match ${sourceMatch.matchId} · Court ${courtValue(sourceMatch.courtId)} · ${viewerStatus(sourceMatch)}`,
      }));
    });
  }

  return {
    matchId: destination.matchId,
    round: destination.roundDescription || `Match ${destination.matchId}`,
    court: courtValue(destination.courtId),
    status: placeholderTeam(destinationOpponent?.name)
      ? 'WAITING ON FEEDER'
      : viewerStatus(destination),
    explanation: placeholderTeam(destinationOpponent?.name)
      ? `The ${teamName} matchup is waiting for another bracket result. These are the possible opponents currently identified.`
      : `${destinationOpponent.name} is currently the published opponent.`,
    feederMatches,
    options: uniqueScenarioOptions(options),
  };
}

function projectedMatchupChance(bracket: any, teamId: string, opponentId: string) {
  const details = bracket?.pregameSnapshot?.coverage?.pairingDetails
    || bracket?.coverage?.pairingDetails
    || [];
  const pairing = details.find((item: any) => (
    [String(item.teamAId), String(item.teamBId)].includes(String(teamId))
    && [String(item.teamAId), String(item.teamBId)].includes(String(opponentId))
  ));
  if (!pairing) return undefined;
  if (String(pairing.teamAId) === String(teamId) && pairing.teamAProbability != null) {
    return Number(pairing.teamAProbability) * 100;
  }
  if (String(pairing.teamBId) === String(teamId) && pairing.teamBProbability != null) {
    return Number(pairing.teamBProbability) * 100;
  }
  return undefined;
}

function winningTeam(match: Match) {
  const top = Number(match.activeGame?.score?.top ?? match.games?.[0]?.score?.top ?? match.score.top);
  const bottom = Number(match.activeGame?.score?.bottom ?? match.games?.[0]?.score?.bottom ?? match.score.bottom);
  if (!Number.isFinite(top) || !Number.isFinite(bottom) || top === bottom) return undefined;
  return top > bottom ? match.teams.top : match.teams.bottom;
}

function losingTeam(match: Match) {
  const winner = winningTeam(match);
  if (!winner) return undefined;
  return String(winner.id) === String(match.teams.top.id) ? match.teams.bottom : match.teams.top;
}

function placeholderTeam(name?: string) {
  const value = String(name || '').trim().toLowerCase();
  return !value
    || value === 'tbd'
    || value === 'bye'
    || value === 'team -1'
    || value === '-1'
    || value.startsWith('bye user');
}

function viewerStatus(match: Match) {
  if (match.status === 'live') return 'LIVE';
  if (match.status === 'completed') return 'FINAL';
  return 'NOT STARTED';
}

function courtValue(value: unknown) {
  const court = String(value ?? '').trim();
  return !court || court === '-1' ? 'TBD' : court;
}

function uniqueScenarioOptions(options: any[]) {
  const seen = new Set<string>();
  return options.filter(option => {
    const key = `${option.teamId}:${option.condition}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function championshipPath(current: Match, matches: Match[], eliminated = false) {
  if (eliminated) {
    return {
      gamesLeft: 0,
      steps: ['Eliminated · no games remaining'],
      sideLabel: 'Tournament complete',
    };
  }
  const side = normalizedSide(current);
  const currentOrder = stageOrder(current.roundDescription);
  const later = [...new Set(matches
    .filter(item => normalizedSide(item) === side && stageOrder(item.roundDescription) > currentOrder)
    .map(item => item.roundDescription || 'Next bracket round'))]
    .sort((a, b) => stageOrder(a) - stageOrder(b));
  const finals = [...new Set(matches
    .filter(item => normalizedSide(item) === 'F')
    .map(item => item.roundDescription || 'Championship'))];
  const currentStep = current.status === 'completed' ? [] : [current.roundDescription || 'Current match'];
  const steps = [...currentStep, ...later, ...finals];
  if (!steps.length) steps.push('Championship');
  if (!steps.some(step => /final|champ/i.test(step))) steps.push('Championship');
  return {
    gamesLeft: Math.max(1, steps.length),
    steps: steps.slice(0, 6),
    sideLabel: side === 'L' ? 'Elimination bracket' : side === 'F' ? 'Championship round' : 'Winners bracket',
  };
}

function teamLost(match: Match, id: string, name: string) {
  const teamIsTop = sameTeam(match.teams.top, id, name);
  const game = match.activeGame || match.games?.[0];
  const mine = Number(teamIsTop ? game?.score?.top ?? match.score.top : game?.score?.bottom ?? match.score.bottom);
  const theirs = Number(teamIsTop ? game?.score?.bottom ?? match.score.bottom : game?.score?.top ?? match.score.top);
  return Number.isFinite(mine) && Number.isFinite(theirs) && mine < theirs;
}

function normalizedSide(match: Match) {
  const side = String(match.bracketSide || '').toUpperCase();
  if (/final|champ/i.test(match.roundDescription || '')) return 'F';
  if (['L', 'LB', 'LOSER', 'LOSERS'].includes(side)) return 'L';
  return 'W';
}

function stageOrder(label = '') {
  const number = Number(label.match(/(\d+)/)?.[1] || 0);
  if (/champ/i.test(label)) return 1000;
  if (/final/i.test(label)) return 900;
  if (/semi/i.test(label)) return 800;
  if (/qtr|quarter/i.test(label)) return 700;
  return number || 1;
}

function teamAppears(match: Match, id: string, name: string) {
  return sameTeam(match.teams.top, id, name) || sameTeam(match.teams.bottom, id, name);
}

function isByeMatch(match: Match) {
  return [match.teams?.top?.name, match.teams?.bottom?.name].some(name => {
    const value = String(name || '').trim().toLowerCase();
    return value === 'bye' || value.startsWith('bye user');
  });
}

function sameTeam(team: { id: string; name: string }, id: string, name: string) {
  return Boolean(id && String(team.id) === id) || Boolean(name && team.name === name);
}

type ViewedTeamPlayer = {
  id: string;
  name: string;
  tournament?: TournamentStatsPlayer;
};

function viewedTeamPlayers(
  projectedTeam: any,
  matches: Match[],
  teamId: string,
  teamName: string,
  tournamentStats: TournamentStatsResponse | null,
): ViewedTeamPlayer[] {
  const identities = new Map<string, string>();
  (projectedTeam?.players || []).forEach((player: any) => {
    const id = String(player.playerId ?? player.id ?? '');
    if (id) identities.set(id, player.playerName || player.name || `Player ${id}`);
  });
  matches.forEach(match => {
    (match.games || []).forEach(game => {
      (game.players || []).forEach(player => {
        if (String(player.teamId || '') === String(teamId)) {
          identities.set(String(player.id), player.name || `Player ${player.id}`);
        }
      });
    });
  });

  const raw = tournamentStats?.players;
  const statsEntries: [string, TournamentStatsPlayer][] = !raw
    ? []
    : Array.isArray(raw)
      ? raw.map((player, index) => [String((player as any).player_id ?? index), player])
      : Object.entries(raw);
  statsEntries.forEach(([id, stats]) => {
    if (identities.has(String(id))) return;
    const name = String(stats.name || '').trim();
    if (name && teamName.toLowerCase().includes(name.toLowerCase())) {
      identities.set(String(id), name);
    }
  });

  return [...identities.entries()].map(([id, name]) => ({
    id,
    name,
    tournament: statsEntries.find(([statsId]) => String(statsId) === id)?.[1]
      || statsEntries.find(([, stats]) => String(stats.name || '').toLowerCase() === name.toLowerCase())?.[1],
  })).slice(0, 2);
}

function ViewedTeamStatistics({
  teamName,
  teamPlayers,
  livePlayers,
  liveRounds,
  showCurrentGame,
  loading,
  coverage,
}: {
  teamName: string;
  teamPlayers: ViewedTeamPlayer[];
  livePlayers: PlayerStat[];
  liveRounds: RoundRow[];
  showCurrentGame: boolean;
  loading: boolean;
  coverage?: TournamentStatsResponse['matchStats'];
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-zinc-950 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.18em] text-violet-300">
            <Users size={17}/> Team statistics
          </div>
          <div className="mt-1 text-sm font-bold text-zinc-400">{teamName}</div>
        </div>
        <span className="rounded-lg bg-white/[.06] px-2 py-1 text-[10px] font-black uppercase tracking-wider text-zinc-400">
          {tournamentCoverageLabel(coverage, loading)}
        </span>
      </div>
      <div className="mt-3 space-y-3">
        {teamPlayers.map(player => {
          const live = livePlayers.find(item => String(item.id) === player.id);
          const tournament = player.tournament;
          const cancelledPoints = cancelledPointsForPlayer(player.id, live?.teamId, liveRounds);
          return (
            <div key={player.id} className="overflow-hidden rounded-xl border border-white/10 bg-white/[.025]">
              <div className="border-b border-white/10 px-3 py-3">
                <div className="text-lg font-black text-white">{player.name}</div>
                <div className="text-[10px] font-black uppercase tracking-wider text-zinc-600">ACL Player {player.id}</div>
              </div>
              {showCurrentGame && (
                <div className="border-b border-sky-300/15 bg-sky-300/[.04] p-3">
                  <div className="mb-2 text-[10px] font-black uppercase tracking-[.16em] text-sky-300">Current game</div>
                  <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                    <CompactMetric label="PPR" value={metric(live?.ppr)} />
                    <CompactMetric label="DPR" value={signed(live?.dpr)} />
                    <CompactMetric label="Net scored" value={whole(cancelledPoints.scored)} />
                    <CompactMetric label="Net conceded" value={whole(cancelledPoints.conceded)} />
                    <CompactMetric label="Round win" value={percent(live?.roundWinPct)} />
                    <CompactMetric label="Rounds" value={whole(live?.rounds)} />
                  </div>
                </div>
              )}
              <div className="p-3">
                <div className="mb-2 text-[10px] font-black uppercase tracking-[.16em] text-amber-300">
                  {tournamentCoverageLabel(coverage, loading)}
                </div>
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                  <CompactMetric label="PPR" value={metric(tournament?.ppr)} />
                  <CompactMetric label="Opp PPR" value={metric(tournament?.opp_ppr)} />
                  <CompactMetric label="+/- per rnd" value={signed(tournament?.point_diff)} />
                  <CompactMetric label="Round win" value={percent(tournament?.rounds_won_pct)} />
                  <CompactMetric label="Rounds" value={whole(tournament?.rounds)} />
                  <CompactMetric label="4 baggers" value={`${whole(tournament?.['4baggers'])} · ${percent(tournament?.['4bagger_pct'])}`} />
                </div>
                {!tournament && !loading && (
                  <div className="mt-2 text-xs text-zinc-600">No accumulated tournament stat rows have been published for this player yet.</div>
                )}
              </div>
            </div>
          );
        })}
        {loading && !teamPlayers.length && <div className="p-3 text-sm text-zinc-500">Loading both players’ tournament statistics…</div>}
        {!loading && !teamPlayers.length && <div className="p-3 text-sm text-zinc-500">The team roster has not been published with player identities yet.</div>}
        {!loading && coverage?.eligibleGames && Number(coverage.usableGames || 0) < coverage.eligibleGames && (
          <div className="rounded-xl border border-amber-300/20 bg-amber-300/[.06] p-3 text-xs leading-5 text-amber-100">
            ACL published complete player-round statistics for {coverage.usableGames || 0} of {coverage.eligibleGames} played games. The values above include only those games; incomplete games are not estimated.
          </div>
        )}
      </div>
    </div>
  );
}

function tournamentCoverageLabel(coverage: TournamentStatsResponse['matchStats'] | undefined, loading: boolean) {
  if (loading) return 'Loading tournament stats';
  if (coverage?.eligibleGames && Number(coverage.usableGames || 0) < coverage.eligibleGames) {
    return `Partial · ${coverage.usableGames || 0}/${coverage.eligibleGames} games`;
  }
  return 'Tournament totals';
}

function CompactMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-black/35 px-2 py-2 text-center">
      <div className="text-base font-black text-white">{value}</div>
      <div className="mt-0.5 text-[8px] font-black uppercase tracking-wider text-zinc-600">{label}</div>
    </div>
  );
}

function cancelledPointsForPlayer(
  playerId: string,
  teamId: string | undefined,
  rounds: RoundRow[],
) {
  return rounds.reduce((totals, round) => {
    const playerRound = (round.players || []).find(
      player => String(player.playerId) === String(playerId),
    );
    if (!playerRound) return totals;
    const resolvedTeamId = String(teamId || playerRound.teamId || '');
    const scoringTeamId = String(round.scoringTeamId || '');
    const netPoints = Math.max(0, Number(round.netPoints || 0));
    if (!scoringTeamId || !netPoints) return totals;
    if (scoringTeamId === resolvedTeamId) totals.scored += netPoints;
    else totals.conceded += netPoints;
    return totals;
  }, { scored: 0, conceded: 0 });
}

function StatusStat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-2xl border border-white/10 bg-zinc-950 px-2 py-3 text-center"><div className="text-[10px] font-black uppercase tracking-wider text-zinc-500">{label}</div><div className="mt-1 text-xl font-black text-white">{value}</div></div>;
}

function Mini({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-white/[.05] p-3"><div className="text-[10px] font-black uppercase tracking-wider text-zinc-500">{label}</div><div className="mt-1 text-xl font-black text-white">{value}</div></div>;
}

function metric(value: unknown, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : '—';
}

function signed(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number > 0 ? '+' : ''}${number.toFixed(2)}` : '—';
}

function percent(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(1)}%` : '—';
}

function whole(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? String(Math.round(number)) : '—';
}

function court(value?: string) {
  return !value || value === '-1' ? '?' : value;
}

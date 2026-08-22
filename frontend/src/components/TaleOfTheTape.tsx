import { ChevronDown, Scale, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import type { PlayerStat } from '../lib/api';
import type { SnapshotEventDetails } from '../lib/shareSnapshot';
import { ShareTaleOfTapeButton } from './ShareSnapshotButton';

type Props = {
  players: PlayerStat[];
  topTeamId?: string;
  bottomTeamId?: string;
  topTeamName?: string;
  bottomTeamName?: string;
  pregame?: boolean;
  pregameTopProbability?: number;
  pregameEvidence?: any;
  eventId?: string;
  event?: SnapshotEventDetails;
  match?: { courtId?: string; roundDescription?: string };
};

type Metric = {
  label: string;
  top: number;
  bottom: number;
  digits?: number;
  suffix?: string;
  higherWins?: boolean;
};

export function TaleOfTheTape({
  players,
  topTeamId,
  bottomTeamId,
  topTeamName = 'Team 1',
  bottomTeamName = 'Team 2',
  pregame = false,
  pregameTopProbability = 0.5,
  pregameEvidence,
  eventId = '',
  event,
  match,
}: Props) {
  const [showReasoning, setShowReasoning] = useState(false);
  const topPlayers = players.filter(player => String(player.teamId) === String(topTeamId));
  const bottomPlayers = players.filter(player => String(player.teamId) === String(bottomTeamId));
  const top = aggregate(topPlayers, pregame);
  const bottom = aggregate(bottomPlayers, pregame);
  const topFavored = pregameTopProbability >= 0.5;
  const favoriteProbability = topFavored ? pregameTopProbability : 1 - pregameTopProbability;
  const projectedTopScore = Number(pregameEvidence?.projectedScore?.sideAScore);
  const projectedBottomScore = Number(pregameEvidence?.projectedScore?.sideBScore);
  const projectedScore = Number.isFinite(projectedTopScore) && Number.isFinite(projectedBottomScore)
    ? `${projectedTopScore}–${projectedBottomScore}`
    : 'Unavailable';
  const reasoning = buildProjectionReasoning(pregameEvidence, topTeamName, bottomTeamName, pregameTopProbability);
  const metrics: Metric[] = [
    { label: 'PPR', top: top.ppr, bottom: bottom.ppr, digits: 2 },
    { label: 'DPR', top: top.dpr, bottom: bottom.dpr, digits: 2 },
    { label: 'Round win rate', top: top.roundWinPct, bottom: bottom.roundWinPct, digits: 1, suffix: '%' },
    { label: 'Four-bagger rate', top: top.fourBaggerPct, bottom: bottom.fourBaggerPct, digits: 1, suffix: '%' },
    { label: 'Bags in', top: top.bagsInPct, bottom: bottom.bagsInPct, digits: 1, suffix: '%' },
  ];

  if (!players.length) {
    return (
      <section className="glass rounded-[28px] p-5">
        <h2 className="text-xl font-black uppercase tracking-wider">Tale of the Tape</h2>
        <p className="mt-2 text-sm text-zinc-500">Player statistics will appear when ACL publishes match data.</p>
      </section>
    );
  }

  return (
    <section className="glass overflow-hidden rounded-[28px]">
      <div className="border-b border-white/10 p-4 md:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[.22em] text-amber-300">
              <Scale size={16} /> Tale of the Tape
            </div>
            <h2 className="mt-1 text-2xl font-black">{pregame ? 'Prematch projection' : 'Side-by-side matchup'}</h2>
          </div>
          <div className="flex flex-col items-stretch gap-2 sm:items-end">
            <div className="flex items-center gap-2 rounded-full border border-sky-400/20 bg-sky-400/10 px-3 py-1.5 text-[11px] font-bold text-sky-200">
              <ShieldCheck size={14} /> ACL match-stat feed
            </div>
            {pregame && <ShareTaleOfTapeButton input={{
              eventId,
              event,
              match,
              topTeamName,
              bottomTeamName,
              topProbability: pregameTopProbability,
              evidence: pregameEvidence,
              reasoning,
            }}/>}
          </div>
        </div>
        <p className="mt-2 max-w-3xl text-xs leading-5 text-zinc-500">
          {pregame
            ? 'Round 0 uses the prediction engine and available season baselines. No in-match performance is included.'
            : 'These values describe performance in this match through the selected round. They are not official CPI.'}
        </p>
      </div>

      {pregame && <div className="grid gap-3 border-b border-white/10 bg-amber-300/[.06] p-4 text-center sm:grid-cols-3">
        <SummaryCard label="Projected winner" value={topFavored ? topTeamName : bottomTeamName} />
        <SummaryCard label="Win probability" value={`${(favoriteProbability * 100).toFixed(1)}%`} />
        <SummaryCard label="Projected score" value={projectedScore} />
      </div>}

      {pregame && (
        <div className="border-b border-white/10 p-4">
          <button type="button" aria-expanded={showReasoning} onClick={() => setShowReasoning(value => !value)}
            className="flex min-h-14 w-full items-center justify-between rounded-xl border border-amber-300/30 bg-amber-300/[.07] px-4 text-left text-base font-black text-amber-100 transition hover:bg-amber-300/[.13] active:translate-y-px active:bg-amber-300/20">
            <span>Why did the model make this projection?</span>
            <ChevronDown className={`shrink-0 transition-transform ${showReasoning ? 'rotate-180' : ''}`} />
          </button>
          {showReasoning && <div className="mt-3 space-y-2">
            {reasoning.map((reason, index) => <div key={`${reason.title}:${index}`} className="grid grid-cols-[2.25rem_1fr] gap-3 rounded-xl border border-white/10 bg-black/25 p-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-300/10 font-black text-amber-300">{index + 1}</div>
              <div><div className="font-black text-white">{reason.title}</div><div className="mt-1 text-sm leading-6 text-zinc-400">{reason.detail}</div></div>
            </div>)}
          </div>}
        </div>
      )}

      <div className="grid grid-cols-[1fr_auto_1fr] items-stretch border-b border-white/10">
        <TeamHeader name={topTeamName} players={topPlayers} tone="blue" />
        <div className="flex items-center px-3 text-xs font-black uppercase tracking-widest text-zinc-600">vs</div>
        <TeamHeader name={bottomTeamName} players={bottomPlayers} tone="red" />
      </div>

      {pregame && pregameEvidence ? <PregameEvidence evidence={pregameEvidence} topTeamName={topTeamName} bottomTeamName={bottomTeamName} /> : <>
      <div className="divide-y divide-white/10">
        {metrics.map(metric => {
          const higherWins = metric.higherWins !== false;
          const topLeads = higherWins ? metric.top > metric.bottom : metric.top < metric.bottom;
          const bottomLeads = higherWins ? metric.bottom > metric.top : metric.bottom < metric.top;
          const maximum = Math.max(Math.abs(metric.top), Math.abs(metric.bottom), 1);
          return (
            <div key={metric.label} className="grid grid-cols-[1fr_7rem_1fr] items-center gap-3 px-4 py-3 md:px-5">
              <MetricSide value={metric.top} max={maximum} digits={metric.digits} suffix={metric.suffix} leads={topLeads} side="top" />
              <div className="text-center text-[11px] font-black uppercase tracking-wider text-zinc-500">{metric.label}</div>
              <MetricSide value={metric.bottom} max={maximum} digits={metric.digits} suffix={metric.suffix} leads={bottomLeads} side="bottom" />
            </div>
          );
        })}
      </div>

      <div className="grid gap-2 border-t border-white/10 p-4 sm:grid-cols-3">
        <Summary label="Rounds recorded" top={top.rounds} bottom={bottom.rounds} />
        <Summary label="Total points" top={top.points} bottom={bottom.points} />
        <Summary label="Four baggers" top={top.fourBaggers} bottom={bottom.fourBaggers} />
      </div>
      </>}
    </section>
  );
}

function PregameEvidence({ evidence, topTeamName, bottomTeamName }: { evidence: any; topTeamName: string; bottomTeamName: string }) {
  const topPlayers = evidence?.top?.players || [];
  const bottomPlayers = evidence?.bottom?.players || [];
  const inactiveRatings = Object.entries(evidence?.profileRatingWeights || {})
    .filter(([, policy]: any) => Number(policy?.gamePredictionWeight || 0) === 0);
  return <>
    <div className="grid gap-4 border-b border-white/10 p-4 lg:grid-cols-2">
      <PlayerEvidenceColumn players={topPlayers} tone="blue" />
      <PlayerEvidenceColumn players={bottomPlayers} tone="red" />
    </div>
    <div className="grid gap-3 border-b border-white/10 bg-white/[.02] p-4 md:grid-cols-4">
      <EvidenceSummary label="Team projection PPR" value={`${formatMaybe(evidence?.top?.aggregate?.predictivePpr)} — ${formatMaybe(evidence?.bottom?.aggregate?.predictivePpr)}`} />
      <EvidenceSummary label="PPR difference" value={signed(evidence?.top?.aggregate?.predictivePpr, evidence?.bottom?.aggregate?.predictivePpr)} />
      <EvidenceSummary label="Evidence tier" value={evidence?.evidenceTier || 'Unavailable'} />
      <EvidenceSummary label="Confidence adjustment" value={`${Math.round(finite(evidence?.shrinkageFactor) * 100)}%`} />
    </div>
    <ChallengerComparison evidence={evidence} topTeamName={topTeamName} bottomTeamName={bottomTeamName} />
    <div className="p-4">
      <div className="text-xs font-black uppercase tracking-[.18em] text-zinc-500">Profile ratings shown elsewhere but not weighted in this projection</div>
      <div className="mt-3 flex flex-wrap gap-2">
        {inactiveRatings.map(([key, policy]: any) => <span key={key} title={policy.evidence} className="rounded-lg border border-white/10 bg-white/[.035] px-3 py-2 text-xs font-bold text-zinc-400">
          {titleCase(key)} · 0% weight
        </span>)}
      </div>
      <div className="mt-3 text-xs leading-5 text-zinc-500">
        Model {evidence?.modelVersion || 'unknown'} · Feature set {evidence?.featureVersion || 'unknown'} · Data cutoff {formatDate(evidence?.dataCutoffAt)}.
        The displayed probability uses PPR, scoring ceiling, floor avoidance, point differential, and their validated nonlinear effects. PPR-only continues as the background control.
      </div>
    </div>
  </>;
}

function ChallengerComparison({ evidence, topTeamName, bottomTeamName }: { evidence: any; topTeamName: string; bottomTeamName: string }) {
  const challenger = evidence?.challenger;
  if (!challenger) return null;
  if (challenger.status !== 'PREDICTED') {
    return <div className="border-b border-white/10 bg-sky-400/[.035] p-4">
      <div className="text-xs font-black uppercase tracking-[.18em] text-sky-300">Advanced challenger unavailable</div>
      <p className="mt-2 text-sm text-zinc-400">{challenger.reason}</p>
    </div>;
  }
  const baseline = finite(evidence?.control?.sideAProbability);
  const advanced = finite(challenger.sideAProbability);
  const adjustment = (advanced - baseline) * 100;
  const topFavored = advanced >= 0.5;
  const validation = challenger.validation || {};
  return <div className="border-b border-sky-300/20 bg-sky-400/[.045] p-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div className="text-xs font-black uppercase tracking-[.18em] text-sky-300">Advanced model · prospective validation</div>
        <div className="mt-1 text-lg font-black text-white">PPR + scoring ceiling + floor avoidance + point differential</div>
      </div>
      <div className="rounded-lg border border-sky-300/20 bg-sky-300/10 px-3 py-2 text-xs font-black text-sky-200">Primary experimental prediction</div>
    </div>
    <div className="mt-4 grid gap-3 sm:grid-cols-4">
      <EvidenceSummary label="PPR control · top" value={`${(baseline * 100).toFixed(1)}%`} />
      <EvidenceSummary label="Displayed advanced · top" value={`${(advanced * 100).toFixed(1)}%`} />
      <EvidenceSummary label="Advanced favorite" value={topFavored ? topTeamName : bottomTeamName} />
      <EvidenceSummary label="Adjustment to top" value={`${adjustment >= 0 ? '+' : ''}${adjustment.toFixed(1)} pts`} />
    </div>
    <div className="mt-4 grid gap-2 sm:grid-cols-3">
      {Object.entries(challenger.featureContributions || {}).map(([key, value]: any) =>
        <MiniStat key={key} label={`${titleCase(key)} contribution`} value={`${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(3)} log-odds`} />
      )}
    </div>
    <div className="mt-3 text-xs leading-5 text-zinc-500">
      Rolling-origin validation: {validation.testMatchups || 0} test matchups · Accuracy {validation.challengerAccuracy == null ? '—' : `${(validation.challengerAccuracy * 100).toFixed(1)}%`} versus {validation.pprOnlyAccuracy == null ? '—' : `${(validation.pprOnlyAccuracy * 100).toFixed(1)}%`} PPR-only · Brier {validation.challengerBrier} versus {validation.pprOnlyBrier}.
    </div>
  </div>;
}

function PlayerEvidenceColumn({ players, tone }: { players: any[]; tone: 'blue' | 'red' }) {
  return <div className="space-y-3">
    {players.map(player => {
      const aclPpr = player?.aclSnapshots?.ppr;
      const internal = player?.predictivePprSource === 'INTERNAL_CALCULATED_PPR';
      return <div key={player.playerId} className={`rounded-2xl border p-4 ${tone === 'blue' ? 'border-blue-400/20 bg-blue-400/[.05]' : 'border-red-400/20 bg-red-400/[.05]'}`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <a href={`/?view=profile&playerId=${player.playerId}`} className="text-lg font-black text-white hover:text-amber-300 hover:underline">{player.displayName || `Player ${player.playerId}`}</a>
            <div className="mt-1 text-xs font-bold uppercase tracking-wider text-zinc-500">ACL player ID {player.playerId}</div>
          </div>
          <div className="text-right">
            <div className={`text-3xl font-black ${tone === 'blue' ? 'text-blue-300' : 'text-red-300'}`}>{formatMaybe(player.predictivePpr)}</div>
            <div className="text-xs font-black uppercase tracking-wider text-zinc-500">Projection PPR</div>
          </div>
        </div>
        <div className="mt-3 rounded-xl border border-white/10 bg-black/25 p-3 text-sm">
          <div className="font-black text-zinc-200">{internal ? 'Internal calculated PPR' : 'ACL-provided PPR assistance'}</div>
          <div className="mt-1 text-zinc-500">Sample confidence: {Math.round(finite(player.predictivePprSampleConfidence) * 100)}%</div>
          {!internal && aclPpr && <div className="mt-1 text-sky-300">Snapshot retrieved {formatDate(aclPpr.retrievedAt)} · {aclPpr.sourceEndpoint}</div>}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
          <MiniStat label="Internal PPR" value={formatMaybe(player.calculatedPpr)} />
          <MiniStat label="ACL PPR" value={aclPpr?.value == null ? 'Unavailable' : formatMaybe(aclPpr.value)} />
          <MiniStat label="DPR" value={formatMaybe(player.calculatedDpr)} />
          <MiniStat label="Opponent PPR" value={formatMaybe(player.calculatedOpponentPpr)} />
          <MiniStat label="Round win rate" value={percentMaybe(player.roundWinRate)} />
          <MiniStat label="Four-bagger rate" value={percentMaybe(player.fourBaggerRate)} />
          <MiniStat label="Bags in" value={percentMaybe(player.bagsInRate)} />
          <MiniStat label="Events / games" value={`${player.events || 0} / ${player.games || 0}`} />
          <MiniStat label="Rounds" value={String(player.rounds || 0)} />
        </div>
        <div className="mt-3 text-xs text-zinc-500">Latest included event: {player.lastEventDate || 'No internal events before cutoff'}</div>
      </div>;
    })}
  </div>;
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-black/25 p-3">
    <div className="text-[10px] font-black uppercase tracking-wider text-zinc-600">{label}</div>
    <div className="mt-1 font-black text-zinc-200">{value}</div>
  </div>;
}

function EvidenceSummary({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-white/10 bg-black/25 p-3 text-center">
    <div className="text-[10px] font-black uppercase tracking-wider text-zinc-500">{label}</div>
    <div className="mt-1 text-lg font-black text-white">{value}</div>
  </div>;
}

function TeamHeader({ name, players, tone }: { name: string; players: PlayerStat[]; tone: 'blue' | 'red' }) {
  return (
    <div className={`p-4 text-center md:p-5 ${tone === 'blue' ? 'bg-blue-400/5' : 'bg-red-400/5'}`}>
      <div className={`text-lg font-black ${tone === 'blue' ? 'text-blue-300' : 'text-red-300'}`}>{name}</div>
      <div className="mt-1 text-xs text-zinc-500">
        {players.length ? players.map((player, index) => (
          <span key={player.id}>
            {index > 0 && ' · '}
            <a href={`/?view=profile&playerId=${player.id}`} className="hover:text-amber-300 hover:underline">{player.name}</a>
          </span>
        )) : 'Players unavailable'}
      </div>
    </div>
  );
}

function MetricSide({
  value,
  max,
  digits = 0,
  suffix = '',
  leads,
  side,
}: {
  value: number;
  max: number;
  digits?: number;
  suffix?: string;
  leads: boolean;
  side: 'top' | 'bottom';
}) {
  const width = `${Math.max(4, Math.min(100, Math.abs(value) / max * 100))}%`;
  return (
    <div className={side === 'bottom' ? 'text-right' : ''}>
      <div className={`text-xl font-black ${leads ? 'text-amber-300' : 'text-zinc-200'}`}>
        {finite(value).toFixed(digits)}{suffix}
      </div>
      <div className={`mt-1 flex h-1.5 overflow-hidden rounded-full bg-white/5 ${side === 'bottom' ? 'justify-end' : ''}`}>
        <div className={side === 'top' ? 'bg-blue-400' : 'bg-red-400'} style={{ width }} />
      </div>
    </div>
  );
}

function Summary({ label, top, bottom }: { label: string; top: number; bottom: number }) {
  return (
    <div className="rounded-xl bg-white/[.04] px-3 py-2 text-center">
      <div className="text-[10px] font-black uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="mt-1 font-black"><span className="text-blue-300">{finite(top).toFixed(0)}</span><span className="px-2 text-zinc-600">—</span><span className="text-red-300">{finite(bottom).toFixed(0)}</span></div>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return <div className="rounded-2xl border border-amber-300/15 bg-black/25 p-3">
    <div className="text-xs font-black uppercase tracking-wider text-zinc-500">{label}</div>
    <div className="mt-1 text-xl font-black text-amber-200">{value}</div>
  </div>;
}

function aggregate(players: PlayerStat[], pregame = false) {
  const rounds = players.reduce((sum, player) => sum + finite(player.rounds), 0);
  const weighted = (key: keyof PlayerStat) => rounds
    ? players.reduce((sum, player) => sum + finite(player[key]) * finite(player.rounds), 0) / rounds
    : 0;
  const average = (key: keyof PlayerStat) => players.length
    ? players.reduce((sum, player) => sum + finite(player[key]), 0) / players.length
    : 0;
  return {
    rounds,
    points: players.reduce((sum, player) => sum + finite(player.points), 0),
    fourBaggers: players.reduce((sum, player) => sum + finite(player.fourBaggers), 0),
    ppr: pregame ? average('seasonPpr') : weighted('ppr'),
    dpr: pregame ? average('seasonDpr') : weighted('dpr'),
    roundWinPct: pregame ? average('seasonRoundWinPct') : weighted('roundWinPct'),
    fourBaggerPct: pregame ? average('seasonFourBagPct') : weighted('fourBaggerPct'),
    bagsInPct: pregame ? average('seasonBagsInPct') : weighted('bagsInPct'),
  };
}

function finite(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function formatMaybe(value: unknown) {
  return value == null || !Number.isFinite(Number(value)) ? 'Unavailable' : Number(value).toFixed(2);
}

function percentMaybe(value: unknown) {
  return value == null || !Number.isFinite(Number(value)) ? 'Unavailable' : `${(Number(value) * 100).toFixed(1)}%`;
}

function signed(top: unknown, bottom: unknown) {
  if (top == null || bottom == null) return 'Unavailable';
  const difference = Number(top) - Number(bottom);
  return `${difference >= 0 ? '+' : ''}${difference.toFixed(2)}`;
}

function titleCase(value: string) {
  return value.replace(/([A-Z])/g, ' $1').replace(/^./, character => character.toUpperCase());
}

function formatDate(value: unknown) {
  if (!value) return 'Unavailable';
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function buildProjectionReasoning(evidence: any, topName: string, bottomName: string, topProbability: number) {
  const topRaw = evidence?.top?.aggregate?.predictivePpr;
  const bottomRaw = evidence?.bottom?.aggregate?.predictivePpr;
  const hasPprEvidence = topRaw != null && bottomRaw != null
    && Number.isFinite(Number(topRaw)) && Number.isFinite(Number(bottomRaw));
  const topPpr = hasPprEvidence ? Number(topRaw) : 0;
  const bottomPpr = hasPprEvidence ? Number(bottomRaw) : 0;
  const difference = topPpr - bottomPpr;
  const favorite = topProbability >= 0.5 ? topName : bottomName;
  const reasons = [{
    title: 'Expected scoring baseline',
    detail: hasPprEvidence
      ? `${topName} projects at ${topPpr.toFixed(2)} PPR versus ${bottomName} at ${bottomPpr.toFixed(2)}. The ${Math.abs(difference).toFixed(2)} PPR difference favors ${difference >= 0 ? topName : bottomName}.`
      : 'Archived scoring baselines were unavailable to this saved projection. No 0.00 PPR values should be interpreted as actual player performance.',
  }];
  const control = Number(evidence?.control?.sideAProbability);
  const advanced = Number(evidence?.challenger?.sideAProbability);
  if (Number.isFinite(control) && Number.isFinite(advanced)) {
    reasons.push({
      title: 'Experimental challenger comparison',
      detail: `The active PPR control gives ${topName} ${(control * 100).toFixed(1)}%. The shadow scoring-distribution challenger gives ${(advanced * 100).toFixed(1)}%; it is shown for evaluation but does not replace the public forecast until it passes the promotion gate.`,
    });
  }
  const contributions = Object.entries(evidence?.challenger?.featureContributions || {})
    .map(([key, value]) => ({ key, value: Number(value) }))
    .filter(item => Number.isFinite(item.value))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  if (contributions.length) {
    reasons.push({
      title: 'Largest model drivers',
      detail: `${contributions.slice(0, 3).map(item => `${titleCase(item.key)} ${item.value >= 0 ? '+' : ''}${item.value.toFixed(3)}`).join('; ')}. Positive values favor ${topName}; negative values favor ${bottomName}.`,
    });
  }
  reasons.push({
    title: 'Evidence and uncertainty',
    detail: `${evidence?.evidenceTier || 'Unknown evidence tier'} with a ${Math.round(finite(evidence?.shrinkageFactor) * 100)}% confidence adjustment. The model selects ${favorite}; incomplete samples and match variance remain uncertainty.`,
  });
  return reasons;
}

import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { RoundRow } from '../lib/api';

type Player = {
  id?: string;
  name: string;

  playerimage?: string;
  playerImage?: string;
  imageUrl?: string;
  profileImage?: string;

  ppr?: number;
  dpr?: number;
  points?: number;
  opponentPoints?: number;
  bagsIn?: number;
  bagsOn?: number;
  bagsOff?: number;
  roundWinPct?: number;
  roundLossPct?: number;
  roundTiePct?: number;
  fourBaggerPct?: number;
  bagsInPct?: number;

  seasonPpr?: number;
  seasonDpr?: number;
  seasonYear?: string;
  seasonBucketId?: number;
  pprVsSeason?: number;
  pprTrend?: 'up' | 'down' | 'even' | 'unknown';
};

function fmt(value: any, digits = 2) {
  if (value === null || value === undefined || value === '') return '-';
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : String(value);
}

function pct(value: any) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : 0;
}

function trendClass(value?: number | null) {
  if (value === undefined || value === null) return 'text-zinc-400';
  if (value > 0) return 'text-green-400';
  if (value < 0) return 'text-red-400';
  return 'text-zinc-400';
}

function trendIcon(value?: number | null) {
  if (value === undefined || value === null) return '-';
  if (value > 0) return '+';
  if (value < 0) return '-';
  return '-';
}

export function PlayerBars({ players, rounds = [] }: { players: Player[]; rounds?: RoundRow[] }) {
  const [advancedOpen, setAdvancedOpen] = useState(false);

  if (!players?.length) {
    return (
      <section className="glass rounded-[28px] p-4">
        <h2 className="text-lg font-black mb-3">Players</h2>
        <div className="text-base text-zinc-400">
          No player stats available yet.
        </div>
      </section>
    );
  }

  return (
    <section className="glass rounded-[28px] p-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-xl font-black">Player Statistics</h2>
        <button
          type="button"
          onClick={() => setAdvancedOpen(open => !open)}
          className="flex items-center gap-2 rounded-xl border border-white/10 bg-zinc-900 px-3 py-2 text-sm font-black text-zinc-300"
        >
          <ChevronDown
            size={16}
            className={`transition-transform ${advancedOpen ? '' : '-rotate-90'}`}
          />
          Advanced
        </button>
      </div>

      <div className="space-y-4">
        {players.map((player) => {
          const diff = player.pprVsSeason;

          const absDiff =
            diff === null || diff === undefined
              ? '-'
              : Math.abs(Number(diff)).toFixed(2);

          const imageUrl =
            player.playerimage ||
            player.playerImage ||
            player.imageUrl ||
            player.profileImage;

          const cancellation = getCancellationTotals(player, rounds);

          return (
            <div
              key={player.id || player.name}
              className="rounded-2xl bg-zinc-950/70 border border-white/10 p-5"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-4 min-w-0">
                  {imageUrl && (
                    <img
                      src={imageUrl}
                      alt={player.name}
                      className="h-16 w-16 shrink-0 rounded-full object-cover border border-white/10 bg-zinc-800"
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                      }}
                    />
                  )}

                  <div className="min-w-0">
                    <div className="font-black text-2xl leading-tight truncate">
                      {player.name}
                    </div>

                    <div className="text-sm text-zinc-400">
                      {player.seasonYear
                        ? `vs ${player.seasonYear} season`
                        : 'Season comparison'}
                    </div>
                  </div>
                </div>

                <div className="text-right shrink-0">
                  <div className="text-sm text-zinc-400">Game PPR</div>
                  <div className="text-4xl font-black leading-none">
                    {fmt(player.ppr)}
                  </div>
                </div>
              </div>

              <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-3 text-center">
                <StatBox
                  label="Points Scored"
                  value={fmt(cancellation.scored, 0)}
                  valueClass="text-green-400"
                />
                <StatBox
                  label="Points Conceded"
                  value={fmt(cancellation.conceded, 0)}
                  valueClass="text-red-400"
                />
              </div>

              <OutcomeBar
                win={player.roundWinPct}
                tie={player.roundTiePct}
                loss={player.roundLossPct}
              />

              <BagPlacementBar player={player} />

              {advancedOpen && (
                <div className="mt-5 rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="mb-3 text-sm uppercase tracking-widest text-zinc-500">
                    Advanced
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-center">
                    <StatBox label="Season PPR" value={fmt(player.seasonPpr)} />
                    <StatBox
                      label="Vs Season"
                      value={`${trendIcon(diff)} ${absDiff}`}
                      valueClass={trendClass(diff)}
                    />
                    <StatBox label="DPR" value={fmt(player.dpr)} />
                  </div>

                  <div className="mt-4 rounded-xl bg-zinc-900 px-4 py-3 flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm uppercase tracking-widest text-zinc-500">Four bagger rate</div>
                      <div className="text-xs text-zinc-500">Share of rounds with all four bags in</div>
                    </div>
                    <div className="text-2xl font-black">{fmt(player.fourBaggerPct, 1)}%</div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function getCancellationTotals(player: Player, rounds: RoundRow[]) {
  const playerId = String(player.id ?? '');
  let scored = 0;
  let conceded = 0;

  rounds.forEach(round => {
    const throwers = round.players || [];

    if (throwers.length < 2) return;

    const current = throwers.find(thrower => String(thrower.playerId) === playerId);

    if (!current) return;

    const opponent = throwers.find(thrower => String(thrower.playerId) !== playerId);

    if (!opponent) return;

    const currentPoints = Number(current.grossPoints ?? 0);
    const opponentPoints = Number(opponent.grossPoints ?? 0);
    const net = Math.abs(currentPoints - opponentPoints);

    if (net === 0) return;

    if (currentPoints > opponentPoints) {
      scored += net;
    } else {
      conceded += net;
    }
  });

  return { scored, conceded };
}

function StatBox({
  label,
  value,
  valueClass = 'text-white',
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="rounded-xl bg-zinc-900 p-4">
      <div className="text-sm uppercase tracking-widest text-zinc-500">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-black ${valueClass}`}>
        {value}
      </div>
    </div>
  );
}

function OutcomeBar({ win, tie, loss }: { win?: number; tie?: number; loss?: number }) {
  const rawSegments = [
    { label: 'Win', short: 'W', value: pct(win), className: 'bg-green-500 text-black' },
    { label: 'Tie', short: 'T', value: pct(tie), className: 'bg-yellow-300 text-black' },
    { label: 'Loss', short: 'L', value: pct(loss), className: 'bg-red-500 text-white' },
  ];

  return (
    <StackedPercentBar
      title="Round Outcomes"
      subtitle="Win / Tie / Loss"
      segments={rawSegments}
    />
  );
}

function BagPlacementBar({ player }: { player: Player }) {
  const bagsIn = Number(player.bagsIn ?? 0);
  const bagsOn = Number(player.bagsOn ?? 0);
  const bagsOff = Number(player.bagsOff ?? 0);

  const rawSegments = [
    { label: 'In', short: 'In', value: bagsIn, className: 'bg-green-500 text-black' },
    { label: 'On', short: 'On', value: bagsOn, className: 'bg-yellow-300 text-black' },
    { label: 'Off', short: 'Off', value: bagsOff, className: 'bg-red-500 text-white' },
  ];

  return (
    <StackedPercentBar
      title="Bag Placement"
      subtitle="In / On / Off"
      segments={rawSegments}
      showCounts
    />
  );
}

function StackedPercentBar({
  title,
  subtitle,
  segments,
  showCounts = false,
}: {
  title: string;
  subtitle: string;
  segments: { label: string; short: string; value: number; className: string }[];
  showCounts?: boolean;
}) {
  const total = segments.reduce((sum, segment) => sum + pct(segment.value), 0);
  const normalized = total > 0
    ? segments.map(segment => ({ ...segment, width: (pct(segment.value) / total) * 100 }))
    : segments.map(segment => ({ ...segment, width: 0 }));

  return (
    <div className="mt-5">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="text-sm uppercase tracking-widest text-zinc-500">
          {title}
        </div>
        <div className="text-sm font-bold text-zinc-400">
          {subtitle}
        </div>
      </div>

      <div className="flex h-12 w-full overflow-hidden rounded-xl border border-white/10 bg-zinc-900">
        {total > 0 ? (
          normalized.map(segment => (
            <div
              key={segment.label}
              className={`flex min-w-0 items-center justify-center text-base font-black ${segment.className}`}
              style={{ width: `${segment.width}%` }}
              title={`${segment.label}: ${showCounts ? `${segment.value} / ` : ''}${fmt(segment.width, 1)}%`}
            >
              {segment.width >= 13
                ? `${segment.short} ${showCounts ? `${segment.value} ` : ''}${fmt(segment.width, 1)}%`
                : ''}
            </div>
          ))
        ) : (
          <div className="flex w-full items-center justify-center text-base font-black text-zinc-500">
            No data
          </div>
        )}
      </div>

      <div className="mt-2 grid grid-cols-3 gap-2 text-center text-base font-black">
        {normalized.map(segment => (
          <div key={segment.label} className={segment.className.includes('green') ? 'text-green-400' : segment.className.includes('yellow') ? 'text-yellow-300' : 'text-red-400'}>
            {segment.label} {showCounts ? `${segment.value} / ` : ''}{fmt(segment.width, 1)}%
          </div>
        ))}
      </div>
    </div>
  );
}

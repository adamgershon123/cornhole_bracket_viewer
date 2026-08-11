import { useMemo, useState } from 'react';
import type { TournamentStatsResponse, TournamentStatsPlayer } from '../lib/api';
import TournamentReportCards from './TournamentReportCards';

type Row = TournamentStatsPlayer & { id: string };
type SortDirection = 'asc' | 'desc';

const columns = [
  { key: 'matchRecord', label: 'W/L Record' },
  { key: 'finishPlace', label: 'Finish' },
  { key: 'rounds', label: 'Rnds Thrown' },
  { key: 'scored', label: 'Scored Pts' },
  { key: 'scoredPerRound', label: 'Scored Pts/Rnd' },
  { key: 'pointDiff', label: '+/- (PR)' },
  { key: 'ppr', label: 'PPR' },
  { key: 'oppPpr', label: 'Opp PPR' },
  { key: 'fourBaggers', label: '4B#' },
  { key: 'fourBaggerPct', label: '4B%' },
  { key: 'roundWinPct', label: 'RW%' },
  { key: 'roundLossPct', label: 'RL%' },
  { key: 'roundTiePct', label: 'RT%' },
  { key: 'bagsInPct', label: 'Bags In%' },
  { key: 'bagsOnPct', label: 'On%' },
  { key: 'bagsOffPct', label: 'Off%' },
];

function num(value: any, digits = 1) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return n.toFixed(digits);
}

function integer(value: any) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return String(Math.round(n));
}

function signed(value: any) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}`;
}

function ordinal(value: any) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  if (n % 10 === 1) return `${n}st`;
  if (n % 10 === 2) return `${n}nd`;
  if (n % 10 === 3) return `${n}rd`;
  return `${n}th`;
}

function playersToRows(payload: TournamentStatsResponse | null): Row[] {
  const raw = payload?.players;

  if (!raw) return [];

  const entries = Array.isArray(raw)
    ? raw.map((player, index) => [String(index), player] as const)
    : Object.entries(raw);

  return entries.map(([id, player]) => ({ id, ...player }));
}

function rawValueFor(row: Row, key: string) {
  switch (key) {
    case 'name': return row.name || row.id;
    case 'matchRecord': return Number(row.match_wins || 0) - Number(row.match_losses || 0);
    case 'finishPlace': return Number(row.finish_place || 9999);
    case 'rounds': return Number(row.rounds || 0);
    case 'scored': return Number(row.sum_positive_round_net_points || 0);
    case 'scoredPerRound': return Number(row.scored_pts_per_round || 0);
    case 'ppr': return Number(row.ppr || 0);
    case 'pointDiff': return Number(row.point_diff || 0);
    case 'oppPpr': return Number(row.opp_ppr || 0);
    case 'fourBaggers': return Number(row['4baggers'] || 0);
    case 'fourBaggerPct': return Number(row['4bagger_pct'] || 0);
    case 'roundWinPct': return Number(row.rounds_won_pct || 0);
    case 'roundLossPct': return Number(row.rounds_lost_pct || 0);
    case 'roundTiePct': return Number(row.rounds_tied_pct || 0);
    case 'bagsInPct': return Number(row.bagsin_pct || 0);
    case 'bagsOnPct': return Number(row.bagson_pct || 0);
    case 'bagsOffPct': return Number(row.bagsoff_pct || 0);
    default: return '';
  }
}

function valueFor(row: Row, key: string) {
  switch (key) {
    case 'name': return row.name || row.id;
    case 'matchRecord': return row.match_record || `${row.match_wins ?? 0}-${row.match_losses ?? 0}`;
    case 'finishPlace': return row.finish_place ? ordinal(row.finish_place) : '-';
    case 'rounds': return integer(row.rounds);
    case 'scored': return integer(row.sum_positive_round_net_points);
    case 'scoredPerRound': return num(row.scored_pts_per_round, 2);
    case 'ppr': return num(row.ppr, 2);
    case 'pointDiff': return signed(row.point_diff);
    case 'oppPpr': return num(row.opp_ppr, 2);
    case 'fourBaggers': return integer(row['4baggers']);
    case 'fourBaggerPct': return `${num(row['4bagger_pct'], 1)}%`;
    case 'roundWinPct': return `${num(row.rounds_won_pct, 1)}%`;
    case 'roundLossPct': return `${num(row.rounds_lost_pct, 1)}%`;
    case 'roundTiePct': return `${num(row.rounds_tied_pct, 1)}%`;
    case 'bagsInPct': return `${num(row.bagsin_pct, 1)}%`;
    case 'bagsOnPct': return `${num(row.bagson_pct, 1)}%`;
    case 'bagsOffPct': return `${num(row.bagsoff_pct, 1)}%`;
    default: return '-';
  }
}

function deltaTone(value: any) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 'text-zinc-100';
  if (n > 0) return 'text-green-300';
  if (n < 0) return 'text-red-300';
  return 'text-zinc-100';
}

function MiniMetric({ label, value }: { label: string; value: any }) {
  return (
    <div className="rounded-xl bg-zinc-950 px-2.5 py-2">
      <div className="text-sm font-black leading-tight text-zinc-100 sm:text-base">{value}</div>
      <div className="mt-0.5 text-[11px] uppercase tracking-wider text-zinc-500">{label}</div>
    </div>
  );
}

function PrimaryMetric({ label, value, tone, emphasized = false }: { label: string; value: any; tone: string; emphasized?: boolean }) {
  return (
    <div className="rounded-xl bg-zinc-950 px-3 py-2.5">
      <div className={`${emphasized ? 'text-[1.7rem]' : 'text-2xl'} font-black leading-none ${tone}`}>{value}</div>
      <div className="mt-1 text-[11px] uppercase tracking-wider text-zinc-500">{label}</div>
    </div>
  );
}

export default function TournamentStatsView({
  eventId,
  statsData,
  loading,
}: {
  eventId: string;
  statsData: TournamentStatsResponse | null;
  loading?: boolean;
}) {
  const [sortKey, setSortKey] = useState('ppr');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const baseRows = useMemo(() => playersToRows(statsData), [statsData]);
  const rows = useMemo(() => {
    return [...baseRows].sort((a, b) => {
      const aValue = rawValueFor(a, sortKey);
      const bValue = rawValueFor(b, sortKey);

      if (typeof aValue === 'string' || typeof bValue === 'string') {
        const result = String(aValue).localeCompare(String(bValue), undefined, { sensitivity: 'base' });
        return sortDirection === 'asc' ? result : -result;
      }

      const result = Number(aValue) - Number(bValue);
      return sortDirection === 'asc' ? result : -result;
    });
  }, [baseRows, sortKey, sortDirection]);

  return (<>
    <section className="glass rounded-[28px] p-4 mt-4">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-black">Tournament Statistics</h2>
          <div className="text-sm text-zinc-400">
            Player totals across all played match stats.
            {statsData?.matchStats?.targets ? ` ${statsData.matchStats.targets} games scanned.` : ''}
          </div>
        </div>
        <div className="rounded-xl bg-zinc-900 px-3 py-2 text-sm font-black text-zinc-300">
          {loading ? 'Loading' : `${rows.length} players`}
        </div>
      </div>

      {!loading && rows.length === 0 && (
        <div className="rounded-2xl border border-white/10 bg-zinc-950 p-4 text-zinc-400">
          No tournament statistics available yet.
        </div>
      )}

      {rows.length > 0 && (
        <div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-xs font-black uppercase tracking-widest text-zinc-500">
              Sorted by {columns.find(column => column.key === sortKey)?.label || 'PPR'} {sortDirection === 'asc' ? 'ascending' : 'descending'}
            </div>
            <div className="flex items-center gap-2">
              <select
                value={sortKey}
                onChange={event => {
                  setSortKey(event.target.value);
                  setSortDirection('desc');
                }}
                className="rounded-xl border border-white/10 bg-zinc-900 px-3 py-2 text-sm"
              >
                {columns.map(column => (
                  <option key={column.key} value={column.key}>{column.label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setSortDirection(direction => direction === 'asc' ? 'desc' : 'asc')}
                className="rounded-xl border border-white/10 bg-zinc-900 px-3 py-2 text-sm font-black text-zinc-200"
              >
                {sortDirection === 'asc' ? 'Asc' : 'Desc'}
              </button>
            </div>
          </div>

          <div className="space-y-2">
            {rows.map((row, index) => (
              <div key={row.id} className="rounded-2xl border border-white/10 bg-zinc-900 p-3.5">
                <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(360px,480px)]">
                  <div className="min-w-0">
                    <div className="truncate text-base font-black leading-tight sm:text-lg">#{index + 1} {row.name || row.id}</div>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3 xl:grid-cols-6">
                      {row.finish_place && <MiniMetric label="Finish" value={ordinal(row.finish_place)} />}
                      <MiniMetric label="Rounds" value={integer(row.rounds)} />
                      <MiniMetric label="Scored Pts" value={integer(row.sum_positive_round_net_points)} />
                      <MiniMetric label="Scored/Rnd" value={num(row.scored_pts_per_round, 2)} />
                      <MiniMetric label="Opp PPR" value={num(row.opp_ppr, 2)} />
                      <MiniMetric label="RW%" value={`${num(row.rounds_won_pct, 1)}%`} />
                      <MiniMetric label="Bags In%" value={`${num(row.bagsin_pct, 1)}%`} />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <PrimaryMetric label="W/L Record" value={row.match_record || `${row.match_wins ?? 0}-${row.match_losses ?? 0}`} tone="text-zinc-100" />
                    <PrimaryMetric label="PPR" value={num(row.ppr, 2)} tone="text-amber-300" />
                    <PrimaryMetric label="4B# / 4B%" value={`${integer(row['4baggers'])} / ${num(row['4bagger_pct'], 1)}%`} tone="text-zinc-100" emphasized />
                    <PrimaryMetric label="+/-" value={signed(row.point_diff)} tone={deltaTone(row.point_diff)} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
    <TournamentReportCards eventId={eventId}/>
  </>);
}

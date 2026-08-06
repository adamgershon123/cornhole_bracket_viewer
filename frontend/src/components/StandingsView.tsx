import React, { useEffect, useMemo, useState } from 'react';

type Props = {
  standingsData: any;
};

type TabKey = 'overview' | 'events' | 'games' | 'partners' | 'timeline' | 'data';
type EventSortKey = 'date' | 'place' | 'location' | 'points';
type PartnerSortKey = 'partner' | 'events' | 'rounds' | 'ppr' | 'dpr' | 'fourBaggerPct' | 'lastDate';

type ColumnDef = {
  key: string;
  label: string;
  group?: string;
  grains?: string[];
};

type SortState = {
  key: string;
  direction: 'asc' | 'desc';
};

class EventBreakoutBoundary extends React.Component<
  { children: React.ReactNode; resetKey?: string | null },
  { error?: Error }
> {
  state: { error?: Error } = {};

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidUpdate(previous: { resetKey?: string | null }) {
    if (previous.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: undefined });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="mt-3 rounded-xl border border-red-400/30 bg-red-950/30 p-3 text-sm text-red-100">
          This event breakout hit a display error instead of loading cleanly: {this.state.error.message}
        </div>
      );
    }

    return this.props.children;
  }
}

const OPPONENT_ROLLUP_COLUMNS: ColumnDef[] = [
  { key: 'opponent_name', label: 'Opponent', group: 'Opponent' },
  { key: 'games', label: 'Games', group: 'Volume' },
  { key: 'overallRecord', label: 'Overall Record', group: 'Overall' },
  { key: 'overallWinPct', label: 'Overall W/L %', group: 'Overall' },
  { key: 'singlesRecord', label: 'Singles Record', group: 'Singles' },
  { key: 'singlesWinPct', label: 'Singles W/L %', group: 'Singles' },
  { key: 'doublesRecord', label: 'Doubles Record', group: 'Doubles' },
  { key: 'doublesWinPct', label: 'Doubles W/L %', group: 'Doubles' },
  { key: 'rounds', label: 'Rounds', group: 'Volume' },
  { key: 'avgPpr', label: 'Avg PPR', group: 'Scoring' },
  { key: 'highPpr', label: 'High PPR', group: 'Scoring' },
  { key: 'lowPpr', label: 'Low PPR', group: 'Scoring' },
  { key: 'avgOppPpr', label: 'Avg Opp PPR', group: 'Opponent' },
  { key: 'avgDpr', label: 'Avg DPR', group: 'Scoring' },
  { key: 'totalDiff', label: 'Total +/-', group: 'Scoring' },
  { key: 'fourBaggerPct', label: '4B%', group: 'Bags' },
  { key: 'firstDate', label: 'First', group: 'Event' },
  { key: 'lastDate', label: 'Last', group: 'Event' },
];

const ROUNDERS_SCHEDULE_COLUMNS: ColumnDef[] = [
  { key: 'scheduleGame', label: 'Game #', group: 'Schedule' },
  { key: 'partner_name', label: 'Partner', group: 'Schedule' },
  { key: 'opponent_name', label: 'Opponent', group: 'Schedule' },
  { key: 'court_id', label: 'Court', group: 'Game' },
  { key: 'gameResult', label: 'Doubles Result', group: 'Doubles' },
  { key: 'gameScore', label: 'Game Score', group: 'Game' },
  { key: 'directResult', label: 'Head-to-Head Result', group: 'Head-to-Head' },
  { key: 'directRecord', label: 'Head-to-Head Rounds', group: 'Head-to-Head' },
  { key: 'rounds', label: 'Rounds', group: 'Volume' },
  { key: 'ppr', label: 'PPR', group: 'Scoring' },
  { key: 'dpr', label: 'DPR', group: 'Scoring' },
  { key: 'rollingPpr', label: 'X-Game Avg PPR', group: 'Rolling' },
  { key: 'rollingDpr', label: 'X-Game Avg DPR', group: 'Rolling' },
  { key: 'fourBaggerPct', label: '4B%', group: 'Bags' },
];

const EVENT_COURT_ROLLUP_COLUMNS: ColumnDef[] = [
  { key: 'court_id', label: 'Court', group: 'Court' },
  { key: 'games', label: 'Games', group: 'Volume' },
  { key: 'rounds', label: 'Rounds', group: 'Volume' },
  { key: 'points', label: 'Points', group: 'Scoring' },
  { key: 'ppr', label: 'PPR', group: 'Scoring' },
  { key: 'opp_ppr', label: 'Opp PPR', group: 'Opponent' },
  { key: 'dpr', label: 'DPR', group: 'Scoring' },
  { key: 'four_baggers', label: '4B#', group: 'Bags' },
  { key: 'fourBaggerPct', label: '4B%', group: 'Bags' },
  { key: 'gameRecord', label: 'Doubles Record', group: 'Doubles' },
  { key: 'directRecord', label: 'Head-to-Head Record', group: 'Head-to-Head' },
  { key: 'vsEventPpr', label: 'PPR vs Event', group: 'Comparison' },
  { key: 'vsEventDpr', label: 'DPR vs Event', group: 'Comparison' },
];

const SWAP_STANDINGS_COLUMNS: ColumnDef[] = [
  { key: 'rank', label: 'Rank', group: 'Standing' },
  { key: 'player_name', label: 'Player', group: 'Player' },
  { key: 'wins', label: 'Wins', group: 'Record' },
  { key: 'losses', label: 'Losses', group: 'Record' },
  { key: 'differential_points', label: '+/-', group: 'Points' },
  { key: 'total_points', label: 'Total Pts', group: 'Points' },
  { key: 'player_ppr', label: 'PPR', group: 'Stats' },
  { key: 'player_cpi', label: 'CPI', group: 'Stats' },
  { key: 'finish_points', label: 'Finish Pts', group: 'Standing' },
  { key: 'checked_in', label: 'Checked In', group: 'Player' },
];

const SWAP_UP_NEXT_COLUMNS: ColumnDef[] = [
  { key: 'rank', label: 'Rank', group: 'Standing' },
  { key: 'player_name', label: 'Player', group: 'Player' },
  { key: 'wins', label: 'Wins', group: 'Record' },
  { key: 'losses', label: 'Losses', group: 'Record' },
  { key: 'differential_points', label: '+/-', group: 'Points' },
  { key: 'total_points', label: 'Total Pts', group: 'Points' },
  { key: 'player_ppr', label: 'PPR', group: 'Stats' },
  { key: 'player_cpi', label: 'CPI', group: 'Stats' },
  { key: 'checked_in', label: 'Checked In', group: 'Player' },
];

const DEFAULT_METRIC_CATALOG: ColumnDef[] = [
  { key: 'name', label: 'Player', group: 'Identity', grains: ['summary'] },
  { key: 'events_played', label: 'Events Played', group: 'Volume', grains: ['summary'] },
  { key: 'matches_played', label: 'Matches Played', group: 'Volume', grains: ['summary'] },
  { key: 'games_played', label: 'Games Played', group: 'Volume', grains: ['summary'] },
  { key: 'rounds_thrown', label: 'Rounds Thrown', group: 'Volume', grains: ['summary'] },
  { key: 'points', label: 'Points', group: 'Scoring', grains: ['summary', 'events'] },
  { key: 'scored_points', label: 'Scored Points', group: 'Scoring', grains: ['summary'] },
  { key: 'scored_pts_per_round', label: 'Scored Pts/Rnd', group: 'Scoring', grains: ['summary'] },
  { key: 'ppr', label: 'PPR', group: 'Scoring', grains: ['summary', 'games', 'partners', 'timeline'] },
  { key: 'opp_ppr', label: 'Opp PPR', group: 'Opponent', grains: ['summary', 'games'] },
  { key: 'dpr', label: 'DPR / +/-', group: 'Scoring', grains: ['summary', 'games', 'partners', 'timeline'] },
  { key: 'points_conceded', label: 'Points Conceded', group: 'Opponent', grains: ['summary'] },
  { key: 'pcpr', label: 'PCPR', group: 'Opponent', grains: ['summary'] },
  { key: 'four_baggers', label: '4B#', group: 'Bags', grains: ['summary'] },
  { key: 'four_bagger_pct', label: '4B%', group: 'Bags', grains: ['summary'] },
  { key: 'fourBaggerPct', label: '4B%', group: 'Bags', grains: ['games', 'partners', 'timeline'] },
  { key: 'round_win_pct', label: 'RW%', group: 'Rounds', grains: ['summary', 'games'] },
  { key: 'round_loss_pct', label: 'RL%', group: 'Rounds', grains: ['summary', 'games'] },
  { key: 'round_tie_pct', label: 'RT%', group: 'Rounds', grains: ['summary', 'games'] },
  { key: 'bags_in_pct', label: 'Bags In%', group: 'Bags', grains: ['summary'] },
  { key: 'bags_on_pct', label: 'Bags On%', group: 'Bags', grains: ['summary'] },
  { key: 'bags_off_pct', label: 'Bags Off%', group: 'Bags', grains: ['summary'] },
  { key: 'bagsInPct', label: 'Bags In%', group: 'Bags', grains: ['games', 'partners', 'timeline'] },
  { key: 'bagsOnPct', label: 'Bags On%', group: 'Bags', grains: ['games', 'partners', 'timeline'] },
  { key: 'bagsOffPct', label: 'Bags Off%', group: 'Bags', grains: ['games', 'partners', 'timeline'] },
  { key: 'winPct', label: 'Win %', group: 'Results', grains: ['summary'] },
  { key: 'averageFinish', label: 'Average Finish', group: 'Results', grains: ['summary'] },
  { key: 'bestFinish', label: 'Best Finish', group: 'Results', grains: ['summary'] },
  { key: 'partners_used', label: 'Partners Used', group: 'Partners', grains: ['summary'] },
  { key: 'event_date', label: 'Date', group: 'Event', grains: ['events', 'games'] },
  { key: 'event_name', label: 'Event', group: 'Event', grains: ['events', 'games'] },
  { key: 'location_name', label: 'Location', group: 'Event', grains: ['events', 'games'] },
  { key: 'place', label: 'Place', group: 'Results', grains: ['events'] },
  { key: 'wins', label: 'Wins', group: 'Results', grains: ['events'] },
  { key: 'losses', label: 'Losses', group: 'Results', grains: ['events'] },
  { key: 'player_ppr', label: 'Event PPR', group: 'Scoring', grains: ['events'] },
  { key: 'partner_name', label: 'Partner', group: 'Partners', grains: ['partners'] },
  { key: 'first_date', label: 'First', group: 'Partners', grains: ['partners'] },
  { key: 'last_date', label: 'Last', group: 'Partners', grains: ['partners'] },
  { key: 'opponent_name', label: 'Opponent', group: 'Opponent', grains: ['games'] },
  { key: 'court_id', label: 'Court', group: 'Game', grains: ['games'] },
  { key: 'match_id', label: 'Match', group: 'Game', grains: ['games'] },
  { key: 'game_id', label: 'Game', group: 'Game', grains: ['games'] },
  { key: 'gameResult', label: 'Doubles Result', group: 'Doubles', grains: ['games'] },
  { key: 'gameScore', label: 'Game Score', group: 'Game', grains: ['games'] },
  { key: 'directResult', label: 'Head-to-Head Result', group: 'Head-to-Head', grains: ['games'] },
  { key: 'directRecord', label: 'Head-to-Head Rounds', group: 'Head-to-Head', grains: ['games'] },
  { key: 'rounds', label: 'Rounds', group: 'Volume', grains: ['games', 'partners', 'timeline'] },
  { key: 'gross_points', label: 'Points', group: 'Scoring', grains: ['games', 'partners', 'timeline'] },
  { key: 'net_points', label: '+/-', group: 'Scoring', grains: ['games', 'partners', 'timeline'] },
  { key: 'bags_in', label: 'Bags In', group: 'Bags', grains: ['games', 'partners', 'timeline'] },
  { key: 'bags_on', label: 'Bags On', group: 'Bags', grains: ['games', 'partners', 'timeline'] },
  { key: 'bags_off', label: 'Bags Off', group: 'Bags', grains: ['games', 'partners', 'timeline'] },
  { key: 'date', label: 'Date', group: 'Timeline', grains: ['timeline'] },
  { key: 'rollingPpr', label: 'Rolling PPR', group: 'Timeline', grains: ['timeline'] },
  { key: 'rollingDpr', label: 'Rolling DPR', group: 'Timeline', grains: ['timeline'] },
  { key: 'rollingFourBaggerPct', label: 'Rolling 4B%', group: 'Timeline', grains: ['timeline'] },
];

function ordinal(n: number) {
  if (!n) return '-';
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  if (n % 10 === 1) return `${n}st`;
  if (n % 10 === 2) return `${n}nd`;
  if (n % 10 === 3) return `${n}rd`;
  return `${n}th`;
}

function num(value: any, digits = 0) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return n.toFixed(digits);
}

function roundNumber(value: number, digits = 2) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function formatValue(value: any, key: string) {
  if (value === null || value === undefined || value === '') return '-';
  if (key === 'place') return ordinal(Number(value));
  if (['result', 'record', 'gameResult', 'gameScore', 'directResult', 'directRecord', 'overallRecord', 'singlesRecord', 'doublesRecord'].includes(key)) return String(value);
  if (key.toLowerCase().includes('pct') || key.toLowerCase().includes('ppr') || key === 'dpr' || key === 'pcpr' || key === 'scored_pts_per_round') {
    return num(value, 2);
  }
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : num(value, 2);
  return String(value);
}

function columnLabel(column: ColumnDef) {
  const overrides: Record<string, string> = {
    gameResult: 'Doubles Result',
    directResult: 'Head-to-Head Result',
    directRecord: 'Head-to-Head Rounds',
  };
  return overrides[column.key] || column.label;
}

function compareValues(a: any, b: any, key: string) {
  const av = a?.[key];
  const bv = b?.[key];
  const an = Number(av);
  const bn = Number(bv);

  if (Number.isFinite(an) && Number.isFinite(bn)) return an - bn;
  return String(av ?? '').localeCompare(String(bv ?? ''));
}

function isSwapRoundersEvent(event: any) {
  const name = String(event?.event_name || event?.eventName || '').toLowerCase();
  return Boolean(
    event?.blind_draw ||
    name.includes('swap') ||
    name.includes('rounder') ||
    (event?.match_type === 'D' && event?.bracket_type === 'P')
  );
}

function recordFromRows(rows: any[], resultKey: string) {
  const wins = rows.filter(row => row[resultKey] === 'W').length;
  const losses = rows.filter(row => row[resultKey] === 'L').length;
  const ties = rows.filter(row => row[resultKey] === 'T').length;
  const count = wins + losses + ties;

  return {
    wins,
    losses,
    ties,
    count,
    record: count ? `${wins}-${losses}-${ties}` : '-',
    winPct: count ? roundNumber(100 * wins / count, 2) : null,
  };
}

function isSinglesGame(game: any) {
  const matchType = String(game.match_type || game.matchType || '').toUpperCase();
  return matchType === 'S' || (!game.partner_id && matchType !== 'D');
}

function isDoublesGame(game: any) {
  return !isSinglesGame(game);
}

function rollingScheduleRows(games: any[]) {
  let grossTotal = 0;
  let diffTotal = 0;
  let roundsTotal = 0;

  return [...games]
    .sort((a, b) => {
      const matchDiff = Number(a.match_id || 0) - Number(b.match_id || 0);
      if (matchDiff) return matchDiff;
      return Number(a.game_id || 0) - Number(b.game_id || 0);
    })
    .map((game, index) => {
      const rounds = Number(game.rounds || 0);
      grossTotal += Number(game.gross_points || 0);
      diffTotal += Number(game.net_points || 0);
      roundsTotal += rounds;

      return {
        ...game,
        scheduleGame: index + 1,
        rollingGameCount: index + 1,
        rollingPpr: roundsTotal ? roundNumber(grossTotal / roundsTotal, 2) : null,
        rollingDpr: roundsTotal ? roundNumber(diffTotal / roundsTotal, 2) : null,
      };
    });
}

function resultRecord(rows: any[], key: string) {
  const wins = rows.filter(row => row[key] === 'W').length;
  const losses = rows.filter(row => row[key] === 'L').length;
  const ties = rows.filter(row => row[key] === 'T').length;
  const total = wins + losses + ties;
  return {
    wins,
    losses,
    ties,
    total,
    record: total ? `${wins}-${losses}-${ties}` : '-',
    winPct: total ? roundNumber(100 * wins / total, 2) : null,
  };
}

function summarizeGameRows(rows: any[], label = 'Overall', baseline?: any) {
  const games = rows.length;
  const rounds = rows.reduce((sum, row) => sum + Number(row.rounds || 0), 0);
  const points = rows.reduce((sum, row) => sum + Number(row.gross_points || 0), 0);
  const net = rows.reduce((sum, row) => sum + Number(row.net_points || 0), 0);
  const opponentPoints = rows.reduce((sum, row) => {
    const raw = Number(row.opponent_points);
    if (Number.isFinite(raw)) return sum + raw;
    const oppPpr = Number(row.opp_ppr);
    return sum + (Number.isFinite(oppPpr) ? oppPpr * Number(row.rounds || 0) : 0);
  }, 0);
  const fourBaggers = rows.reduce((sum, row) => sum + Number(row.four_baggers || 0), 0);
  const bagsIn = rows.reduce((sum, row) => sum + Number(row.bags_in || 0), 0);
  const bagsOn = rows.reduce((sum, row) => sum + Number(row.bags_on || 0), 0);
  const bagsOff = rows.reduce((sum, row) => sum + Number(row.bags_off || 0), 0);
  const bagsThrown = bagsIn + bagsOn + bagsOff;
  const gameRecord = resultRecord(rows, 'gameResult');
  const directRecord = resultRecord(rows, 'directResult');
  const ppr = rounds ? roundNumber(points / rounds, 2) : null;
  const dpr = rounds ? roundNumber(net / rounds, 2) : null;

  return {
    label,
    court_id: label,
    games,
    rounds,
    points,
    net_points: net,
    ppr,
    opp_ppr: rounds ? roundNumber(opponentPoints / rounds, 2) : null,
    dpr,
    four_baggers: fourBaggers,
    fourBaggerPct: rounds ? roundNumber(100 * fourBaggers / rounds, 2) : null,
    gameRecord: gameRecord.record,
    gameWinPct: gameRecord.winPct,
    directRecord: directRecord.record,
    directWinPct: directRecord.winPct,
    bagsInPct: bagsThrown ? roundNumber(100 * bagsIn / bagsThrown, 2) : null,
    bagsOnPct: bagsThrown ? roundNumber(100 * bagsOn / bagsThrown, 2) : null,
    bagsOffPct: bagsThrown ? roundNumber(100 * bagsOff / bagsThrown, 2) : null,
    vsEventPpr: baseline?.ppr != null && ppr !== null ? roundNumber(Number(ppr) - Number(baseline.ppr), 2) : null,
    vsEventDpr: baseline?.dpr != null && dpr !== null ? roundNumber(Number(dpr) - Number(baseline.dpr), 2) : null,
  };
}

function groupGamesByCourt(rows: any[], baseline: any) {
  const groups = rows.reduce<Record<string, any[]>>((acc, row) => {
    const court = String(row.court_id || 'Unknown');
    acc[court] = acc[court] || [];
    acc[court].push(row);
    return acc;
  }, {});

  return Object.entries(groups)
    .map(([court, courtRows]) => summarizeGameRows(courtRows, court, baseline))
    .sort((a, b) => compareCourtLabels(a.court_id, b.court_id));
}

function compareCourtLabels(left: any, right: any) {
  const leftText = String(left ?? 'Unknown');
  const rightText = String(right ?? 'Unknown');
  const leftNumber = Number(leftText);
  const rightNumber = Number(rightText);

  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber) && leftNumber !== rightNumber) {
    return leftNumber - rightNumber;
  }

  return leftText.localeCompare(rightText);
}

function getPlayerName(player: any) {
  return player?.name || player?.display_name || player?.playerName || `Player ${player?.player_id || player?.playerId || ''}`.trim();
}

function asArray(value: any): any[] {
  if (Array.isArray(value)) return value;
  if (!value) return [];
  if (Array.isArray(value.rows)) return value.rows;
  if (Array.isArray(value.data)) return value.data;
  return [];
}

function normalizePlatformRows(individual: any) {
  const player = individual?.player || {};
  const playerId = player.player_id || player.playerId;
  const playerName = getPlayerName(player);

  return asArray(individual?.eventResults).map((event: any) => ({
    id: `${playerId}-${event.event_id}-${event.team_id || ''}`,
    playerId,
    playerName,
    eventId: event.event_id,
    eventName: event.event_name,
    event_id: event.event_id,
    event_name: event.event_name,
    date: event.event_date,
    event_date: event.event_date,
    locationId: event.location_id,
    locationName: event.location_name || 'Unknown location',
    location_id: event.location_id,
    location_name: event.location_name || 'Unknown location',
    place: Number(event.place || 0),
    points: Number(event.points || 0),
    teamName: event.team_name,
    team_name: event.team_name,
    wins: event.wins,
    losses: event.losses,
    playerPPR: event.player_ppr,
    player_ppr: event.player_ppr,
    match_type: event.match_type,
    bracket_type: event.bracket_type,
    blind_draw: event.blind_draw,
    partners: asArray(event.partners),
    swapStandings: asArray(event.swapStandings),
    swapUpNext: asArray(event.swapUpNext),
    partnersText: asArray(event.partners).map((partner: any) => partner.name).filter(Boolean).join(', '),
  }));
}

function normalizeLegacyRows(standings: any[]) {
  return standings.flatMap((player: any, playerIndex: number) => (
    asArray(player.eventResults).map((event: any) => ({
      id: `${player.playerId}-${event.eventId}-${event.teamId || playerIndex}`,
      playerId: player.playerId,
      playerName: player.name,
      eventId: event.eventId,
      eventName: event.eventName,
      event_id: event.eventId,
      event_name: event.eventName,
      date: event.date,
      event_date: event.date,
      locationId: event.locationId,
      locationName: event.locationName || 'Unknown location',
      location_id: event.locationId,
      location_name: event.locationName || 'Unknown location',
      place: Number(event.place || 0),
      points: Number(event.points || 0),
      teamName: event.teamName,
      team_name: event.teamName,
      wins: event.wins,
      losses: event.losses,
      playerPPR: event.playerPPR,
      player_ppr: event.playerPPR,
      match_type: event.matchType,
      bracket_type: event.bracketType,
      blind_draw: event.blindDraw,
      partners: asArray(event.partners),
      swapStandings: asArray(event.swapStandings),
      swapUpNext: asArray(event.swapUpNext),
      partnersText: asArray(event.partners).map((partner: any) => partner.name).filter(Boolean).join(', '),
    }))
  ));
}

function metricPoints(rows: any[], key: string) {
  const values = rows.map(row => Number(row[key])).filter(Number.isFinite);
  if (values.length === 0) return '';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return rows.map((row, index) => {
    const x = rows.length === 1 ? 50 : (index / (rows.length - 1)) * 100;
    const raw = Number(row[key]);
    const y = Number.isFinite(raw) ? 92 - ((raw - min) / span) * 74 : 92;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(' ');
}

function SeasonSparkline({ rows }: { rows: any[] }) {
  const ppr = metricPoints(rows, 'ppr');
  const rollingPpr = metricPoints(rows, 'rollingPpr');
  const dpr = metricPoints(rows, 'dpr');
  const rollingDpr = metricPoints(rows, 'rollingDpr');

  if (rows.length === 0) {
    return (
      <div className="rounded-2xl border border-white/10 bg-zinc-950 p-4 text-zinc-400">
        No round-level daily trend data has been saved yet.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-zinc-950 p-3">
      <svg viewBox="0 0 100 100" className="h-56 w-full" preserveAspectRatio="none" role="img">
        <line x1="0" y1="92" x2="100" y2="92" stroke="rgba(255,255,255,.16)" strokeWidth="1" />
        <line x1="0" y1="55" x2="100" y2="55" stroke="rgba(255,255,255,.08)" strokeWidth="1" />
        <line x1="0" y1="18" x2="100" y2="18" stroke="rgba(255,255,255,.08)" strokeWidth="1" />
        {ppr && <polyline points={ppr} fill="none" stroke="#fbbf24" strokeWidth="2.4" vectorEffect="non-scaling-stroke" />}
        {rollingPpr && <polyline points={rollingPpr} fill="none" stroke="#fef3c7" strokeWidth="1.8" vectorEffect="non-scaling-stroke" />}
        {dpr && <polyline points={dpr} fill="none" stroke="#38bdf8" strokeWidth="2.2" vectorEffect="non-scaling-stroke" />}
        {rollingDpr && <polyline points={rollingDpr} fill="none" stroke="#bae6fd" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />}
      </svg>
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-zinc-300">
        <span><span className="text-amber-300">PPR</span> day</span>
        <span><span className="text-amber-100">PPR</span> rolling</span>
        <span><span className="text-sky-300">DPR</span> day</span>
        <span><span className="text-sky-100">DPR</span> rolling</span>
      </div>
    </div>
  );
}

function MetricPicker({
  columns,
  selected,
  onChange,
}: {
  columns: ColumnDef[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const selectedSet = new Set(selected);
  const groups = columns.reduce<Record<string, ColumnDef[]>>((acc, column) => {
    const group = column.group || 'Stats';
    acc[group] = acc[group] || [];
    acc[group].push(column);
    return acc;
  }, {});

  function toggle(key: string) {
    if (selectedSet.has(key)) {
      onChange(selected.filter(item => item !== key));
    } else {
      onChange([...selected, key]);
    }
  }

  return (
    <details className="rounded-2xl border border-white/10 bg-zinc-950 p-3">
      <summary className="cursor-pointer text-sm font-black text-zinc-200">
        Choose Stats ({selected.length})
      </summary>
      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {Object.entries(groups).map(([group, groupColumns]) => (
          <div key={group}>
            <div className="mb-2 text-xs uppercase tracking-[.18em] text-zinc-500">{group}</div>
            <div className="space-y-1">
              {groupColumns.map(column => (
                <label key={column.key} className="flex items-center gap-2 rounded-lg px-2 py-1 text-sm text-zinc-200 hover:bg-white/5">
                  <input
                    type="checkbox"
                    checked={selectedSet.has(column.key)}
                    onChange={() => toggle(column.key)}
                    className="accent-amber-400"
                  />
                  <span>{columnLabel(column)}</span>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

function ResultChip({ label, value, detail }: { label: string; value: any; detail: string }) {
  return (
    <div className="rounded-xl bg-zinc-900 px-3 py-2">
      <div className="text-lg font-black leading-none text-zinc-100">{value || '-'}</div>
      <div className="mt-1 text-[11px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="mt-0.5 text-xs text-zinc-400">{detail}</div>
    </div>
  );
}

function EventGameSummary({ title, summary, showComparison = false }: { title: string; summary: any; showComparison?: boolean }) {
  const safeSummary = summary || summarizeGameRows([]);
  const chips = [
    { label: 'Games', value: safeSummary.games },
    { label: 'Rounds', value: safeSummary.rounds },
    { label: 'Points', value: safeSummary.points },
    { label: 'PPR', value: num(safeSummary.ppr, 2), tone: 'text-amber-300' },
    { label: 'DPR', value: num(safeSummary.dpr, 2), tone: Number(safeSummary.dpr) >= 0 ? 'text-green-300' : 'text-red-300' },
    { label: 'Opp PPR', value: num(safeSummary.opp_ppr, 2) },
    { label: '4B# / 4B%', value: `${safeSummary.four_baggers || 0} / ${num(safeSummary.fourBaggerPct, 2)}` },
    { label: 'Doubles', value: safeSummary.gameRecord },
    { label: 'Head-to-Head', value: safeSummary.directRecord },
  ];

  if (showComparison) {
    chips.push(
      { label: 'PPR vs Event', value: signed(safeSummary.vsEventPpr), tone: Number(safeSummary.vsEventPpr) >= 0 ? 'text-green-300' : 'text-red-300' },
      { label: 'DPR vs Event', value: signed(safeSummary.vsEventDpr), tone: Number(safeSummary.vsEventDpr) >= 0 ? 'text-green-300' : 'text-red-300' },
    );
  }

  return (
    <div className="mt-3 rounded-2xl border border-white/10 bg-zinc-900/70 p-3">
      <div className="mb-2 text-xs font-black uppercase tracking-[.18em] text-amber-300">{title}</div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-6">
        {chips.map(chip => (
          <div key={chip.label} className="rounded-xl bg-zinc-950 px-3 py-2">
            <div className={`text-lg font-black leading-none ${chip.tone || 'text-zinc-100'}`}>{chip.value ?? '-'}</div>
            <div className="mt-1 text-[11px] uppercase tracking-wider text-zinc-500">{chip.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function signed(value: any) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}`;
}

function SortableMetricTable({
  rows,
  columns,
  selected,
  sort,
  onSort,
  empty,
  rowKey,
  selectedRowKey,
  onRowClick,
}: {
  rows: any[];
  columns: ColumnDef[];
  selected: string[];
  sort: SortState;
  onSort: (next: SortState) => void;
  empty: string;
  rowKey?: (row: any, index: number) => string;
  selectedRowKey?: string | null;
  onRowClick?: (row: any) => void;
}) {
  const selectedColumns = selected
    .map(key => columns.find(column => column.key === key))
    .filter(Boolean) as ColumnDef[];
  const sortedRows = useMemo(() => (
    [...rows].sort((a, b) => {
      const result = compareValues(a, b, sort.key);
      return sort.direction === 'asc' ? result : -result;
    })
  ), [rows, sort.key, sort.direction]);

  function chooseSort(key: string) {
    onSort({
      key,
      direction: sort.key === key && sort.direction === 'desc' ? 'asc' : 'desc',
    });
  }

  if (rows.length === 0) {
    return <div className="mt-3 rounded-2xl border border-white/10 bg-zinc-950 p-4 text-zinc-400">{empty}</div>;
  }

  return (
    <div className="mt-3 overflow-x-auto rounded-2xl border border-white/10">
      <table className="w-full min-w-[980px] border-collapse bg-zinc-950/80 text-sm">
        <thead className="bg-zinc-900 text-xs uppercase tracking-widest text-zinc-400">
          <tr>
            {selectedColumns.map(column => (
              <th key={column.key} className="p-0 text-left">
                <button
                  type="button"
                  onClick={() => chooseSort(column.key)}
                  className={`w-full px-3 py-3 text-left font-black ${sort.key === column.key ? 'text-amber-300' : 'text-zinc-400'}`}
                >
                  {columnLabel(column)}{sort.key === column.key ? (sort.direction === 'asc' ? ' ↑' : ' ↓') : ''}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row, index) => {
            const key = rowKey ? rowKey(row, index) : (row.id || `${row.event_id || ''}:${row.match_id || ''}:${row.game_id || ''}:${index}`);
            const isSelected = selectedRowKey === key;

            return (
              <tr
                key={key}
                onClick={() => onRowClick?.(row)}
                className={`border-t border-white/5 odd:bg-white/[0.025] ${onRowClick ? 'cursor-pointer hover:bg-amber-400/10' : ''} ${isSelected ? 'bg-amber-400/10 text-amber-100' : ''}`}
              >
                {selectedColumns.map(column => (
                  <td key={column.key} className="whitespace-nowrap px-3 py-3">
                    {formatValue(row[column.key], column.key)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function StandingsView({ standingsData }: Props) {
  const [activeTab, setActiveTab] = useState<TabKey>('overview');
  const [eventSortKey, setEventSortKey] = useState<EventSortKey>('date');
  const [eventSortDirection, setEventSortDirection] = useState<'asc' | 'desc'>('desc');
  const [locationFilter, setLocationFilter] = useState('ALL');
  const [placeFilter, setPlaceFilter] = useState('ALL');
  const [eventSearch, setEventSearch] = useState('');
  const [gameSearch, setGameSearch] = useState('');
  const [gameLocationFilter, setGameLocationFilter] = useState('ALL');
  const [eventCourtFilter, setEventCourtFilter] = useState('ALL');
  const [eventCourtGrouping, setEventCourtGrouping] = useState(false);
  const [partnerSearch, setPartnerSearch] = useState('');
  const [partnerSortKey, setPartnerSortKey] = useState<PartnerSortKey>('events');
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedPartnerId, setSelectedPartnerId] = useState<string | null>(null);
  const [openPartnerEvents, setOpenPartnerEvents] = useState<Record<string, boolean>>({});
  const [selectedOpponentId, setSelectedOpponentId] = useState<string | null>(null);
  const [summaryColumns, setSummaryColumns] = useState(['name', 'events_played', 'matches_played', 'games_played', 'rounds_thrown', 'ppr', 'dpr', 'opp_ppr', 'four_bagger_pct', 'round_win_pct']);
  const [eventColumns, setEventColumns] = useState(['event_date', 'place', 'location_name', 'points', 'event_name', 'team_name', 'partnersText', 'wins', 'losses', 'player_ppr']);
  const [roundersColumns, setRoundersColumns] = useState(['scheduleGame', 'partner_name', 'opponent_name', 'court_id', 'gameResult', 'gameScore', 'directResult', 'directRecord', 'rounds', 'ppr', 'dpr', 'rollingPpr', 'rollingDpr']);
  const [eventCourtColumns, setEventCourtColumns] = useState(['court_id', 'games', 'rounds', 'points', 'ppr', 'dpr', 'four_baggers', 'fourBaggerPct', 'gameRecord', 'directRecord', 'vsEventPpr', 'vsEventDpr']);
  const [swapStandingColumns, setSwapStandingColumns] = useState(['rank', 'player_name', 'wins', 'losses', 'differential_points', 'total_points', 'player_ppr', 'finish_points']);
  const [swapUpNextColumns, setSwapUpNextColumns] = useState(['rank', 'player_name', 'wins', 'losses', 'differential_points', 'total_points', 'player_ppr']);
  const [gameColumns, setGameColumns] = useState(['event_date', 'event_name', 'opponent_name', 'court_id', 'match_id', 'game_id', 'gameResult', 'gameScore', 'directResult', 'directRecord', 'rounds', 'gross_points', 'ppr', 'opp_ppr', 'dpr', 'fourBaggerPct']);
  const [opponentRollupColumns, setOpponentRollupColumns] = useState(['opponent_name', 'games', 'overallRecord', 'overallWinPct', 'singlesRecord', 'singlesWinPct', 'doublesRecord', 'doublesWinPct', 'rounds', 'avgPpr', 'highPpr', 'lowPpr', 'avgOppPpr', 'avgDpr', 'totalDiff', 'fourBaggerPct']);
  const [partnerColumns, setPartnerColumns] = useState(['partner_name', 'events', 'matches', 'rounds', 'ppr', 'dpr', 'fourBaggerPct', 'first_date', 'last_date']);
  const [timelineColumns, setTimelineColumns] = useState(['date', 'events', 'matches', 'rounds', 'ppr', 'rollingPpr', 'dpr', 'rollingDpr', 'fourBaggerPct', 'rollingFourBaggerPct']);
  const [summarySort, setSummarySort] = useState<SortState>({ key: 'ppr', direction: 'desc' });
  const [eventMetricSort, setEventMetricSort] = useState<SortState>({ key: 'event_date', direction: 'desc' });
  const [roundersSort, setRoundersSort] = useState<SortState>({ key: 'scheduleGame', direction: 'asc' });
  const [eventCourtSort, setEventCourtSort] = useState<SortState>({ key: 'court_id', direction: 'asc' });
  const [swapStandingSort, setSwapStandingSort] = useState<SortState>({ key: 'rank', direction: 'asc' });
  const [swapUpNextSort, setSwapUpNextSort] = useState<SortState>({ key: 'rank', direction: 'asc' });
  const [gameSort, setGameSort] = useState<SortState>({ key: 'event_date', direction: 'desc' });
  const [opponentRollupSort, setOpponentRollupSort] = useState<SortState>({ key: 'games', direction: 'desc' });
  const [partnerMetricSort, setPartnerMetricSort] = useState<SortState>({ key: 'events', direction: 'desc' });
  const [timelineSort, setTimelineSort] = useState<SortState>({ key: 'date', direction: 'asc' });

  const individual = standingsData?.individual || standingsData?.individuals?.[0];
  const legacyStandings = standingsData?.standings || [];
  const season = standingsData?.season || standingsData?.manifest || {};
  const seasonDefinition = season.seasonDefinition || {};
  const coverage = standingsData?.manifest?.coverage || {};
  const notifications = standingsData?.notifications || standingsData?.manifest?.notifications || [];
  const player = individual?.player || standingsData?.leaderboard?.[0] || legacyStandings[0];
  const playerName = getPlayerName(player);
  const rows = useMemo(
    () => individual ? normalizePlatformRows(individual) : normalizeLegacyRows(legacyStandings),
    [individual, legacyStandings]
  );
  const partners = asArray(individual?.partners);
  const games = asArray(individual?.games);
  const timeline = asArray(individual?.timeline);
  const summary = individual?.summary || {};
  const metricCatalog: ColumnDef[] = individual?.metricCatalog?.length ? individual.metricCatalog : DEFAULT_METRIC_CATALOG;
  const locations = useMemo(() => (
    Array.from(new Set(rows.map(row => row.locationName).filter(Boolean))).sort()
  ), [rows]);
  const gameLocations = useMemo(() => (
    Array.from(new Set(games.map((game: any) => game.location_name).filter(Boolean))).sort()
  ), [games]);
  const columnsFor = (grain: string, extras: ColumnDef[] = []) => {
    const seen = new Set<string>();
    return [...metricCatalog.filter(column => (column.grains || []).includes(grain)), ...extras]
      .filter(column => {
        if (seen.has(column.key)) return false;
        seen.add(column.key);
        return true;
      });
  };
  const summaryColumnDefs = columnsFor('summary');
  const eventColumnDefs = columnsFor('events', [
    { key: 'team_name', label: 'Team', group: 'Event' },
    { key: 'partnersText', label: 'Partners', group: 'Partners' },
  ]);
  const gameColumnDefs = columnsFor('games', [
    { key: 'round_desc', label: 'Round', group: 'Game' },
  ]);
  const partnerColumnDefs = columnsFor('partners', [
    { key: 'events', label: 'Events', group: 'Volume' },
    { key: 'matches', label: 'Matches', group: 'Volume' },
  ]);
  const timelineColumnDefs = columnsFor('timeline', [
    { key: 'events', label: 'Events', group: 'Volume' },
    { key: 'matches', label: 'Matches', group: 'Volume' },
  ]);

  const filteredEvents = useMemo(() => {
    const needle = eventSearch.trim().toLowerCase();

    return rows
      .filter(row => locationFilter === 'ALL' || row.locationName === locationFilter)
      .filter(row => placeFilter === 'ALL' || String(row.place) === placeFilter)
      .filter(row => {
        if (!needle) return true;
        return [
          row.eventName,
          row.locationName,
          row.teamName,
          String(row.eventId),
          ...asArray(row.partners).map((partner: any) => partner.name),
        ].some(value => String(value || '').toLowerCase().includes(needle));
      })
      .sort((a, b) => {
        let result = 0;
        if (eventSortKey === 'date') result = String(a.date || '').localeCompare(String(b.date || ''));
        if (eventSortKey === 'place') result = a.place - b.place;
        if (eventSortKey === 'location') result = a.locationName.localeCompare(b.locationName);
        if (eventSortKey === 'points') result = a.points - b.points;
        return eventSortDirection === 'asc' ? result : -result;
      });
  }, [rows, locationFilter, placeFilter, eventSearch, eventSortKey, eventSortDirection]);
  const selectedEvent = useMemo(() => (
    rows.find(row => String(row.event_id) === String(selectedEventId)) || null
  ), [rows, selectedEventId]);
  const selectedEventGames = useMemo(() => {
    if (!selectedEventId) return [];
    return rollingScheduleRows(asArray(games).filter((game: any) => String(game.event_id) === String(selectedEventId)));
  }, [games, selectedEventId]);
  const selectedEventCourtOptions = useMemo(() => (
    Array.from(new Set(selectedEventGames.map((game: any) => String(game.court_id || 'Unknown')))).sort(compareCourtLabels)
  ), [selectedEventGames]);
  const selectedEventVisibleGames = useMemo(() => (
    asArray(selectedEventGames).filter((game: any) => eventCourtFilter === 'ALL' || String(game.court_id || 'Unknown') === eventCourtFilter)
  ), [selectedEventGames, eventCourtFilter]);
  const selectedEventOverall = useMemo(() => summarizeGameRows(selectedEventGames), [selectedEventGames]);
  const selectedEventVisibleOverall = useMemo(() => summarizeGameRows(selectedEventVisibleGames, eventCourtFilter === 'ALL' ? 'Overall' : `Court ${eventCourtFilter}`, selectedEventOverall), [selectedEventVisibleGames, eventCourtFilter, selectedEventOverall]);
  const selectedEventCourtRollups = useMemo(() => groupGamesByCourt(selectedEventGames, selectedEventOverall), [selectedEventGames, selectedEventOverall]);

  useEffect(() => {
    setEventCourtFilter('ALL');
    setEventCourtGrouping(false);
  }, [selectedEventId]);

  const filteredPartners = useMemo(() => {
    const needle = partnerSearch.trim().toLowerCase();
    return [...partners]
      .filter((partner: any) => !needle || String(partner.partner_name || '').toLowerCase().includes(needle))
      .sort((a: any, b: any) => {
        if (partnerSortKey === 'partner') return String(a.partner_name || '').localeCompare(String(b.partner_name || ''));
        if (partnerSortKey === 'lastDate') return String(b.last_date || '').localeCompare(String(a.last_date || ''));
        return Number(b[partnerSortKey] || 0) - Number(a[partnerSortKey] || 0);
      });
  }, [partners, partnerSearch, partnerSortKey]);
  const selectedPartner = useMemo(() => (
    partners.find((partner: any) => String(partner.partner_id) === String(selectedPartnerId)) || null
  ), [partners, selectedPartnerId]);
  const selectedPartnerEvents = useMemo(() => {
    if (!selectedPartnerId) return [];
    return rows
      .filter(row => asArray(row.partners).some((partner: any) => String(partner.player_id) === String(selectedPartnerId)))
      .sort((a, b) => String(b.event_date || '').localeCompare(String(a.event_date || '')));
  }, [rows, selectedPartnerId]);
  const selectedPartnerGames = useMemo(() => {
    if (!selectedPartnerId) return [];
    return games.filter((game: any) => String(game.partner_id) === String(selectedPartnerId));
  }, [games, selectedPartnerId]);

  const filteredGames = useMemo(() => {
    const needle = gameSearch.trim().toLowerCase();

    return games
      .filter((game: any) => gameLocationFilter === 'ALL' || game.location_name === gameLocationFilter)
      .filter((game: any) => {
        if (!needle) return true;
        return [
          game.event_name,
          game.location_name,
          game.opponent_name,
          game.court_id,
          game.match_id,
          String(game.event_id),
        ].some(value => String(value || '').toLowerCase().includes(needle));
      });
  }, [games, gameSearch, gameLocationFilter]);
  const opponentRollups = useMemo(() => {
    const grouped = new Map<string, any[]>();
    filteredGames.forEach((game: any) => {
      const key = String(game.opponent_player_id || game.opponent_name || 'Unknown');
      grouped.set(key, [...(grouped.get(key) || []), game]);
    });

    return Array.from(grouped.values()).map(group => {
      const first = group[0] || {};
      const gamesPlayed = group.length;
      const overall = recordFromRows(group, 'directResult');
      const singlesRows = group.filter(isSinglesGame);
      const doublesRows = group.filter(isDoublesGame);
      const singles = recordFromRows(singlesRows, 'directResult');
      const doubles = recordFromRows(doublesRows, 'directResult');
      const rounds = group.reduce((sum, game) => sum + Number(game.rounds || 0), 0);
      const gross = group.reduce((sum, game) => sum + Number(game.gross_points || 0), 0);
      const opponent = group.reduce((sum, game) => sum + Number(game.opponent_points || 0), 0);
      const diff = group.reduce((sum, game) => sum + Number(game.net_points || 0), 0);
      const fourBaggers = group.reduce((sum, game) => sum + Number(game.four_baggers || 0), 0);
      const pprs = group.map(game => Number(game.ppr)).filter(Number.isFinite);
      const dates = group.map(game => String(game.event_date || '')).filter(Boolean).sort();

      return {
        opponent_id: first.opponent_player_id,
        opponent_name: first.opponent_name || 'Unknown opponent',
        games: gamesPlayed,
        overallWins: overall.wins,
        overallLosses: overall.losses,
        overallTies: overall.ties,
        overallRecord: overall.record,
        overallWinPct: overall.winPct,
        singlesWins: singles.wins,
        singlesLosses: singles.losses,
        singlesTies: singles.ties,
        singlesRecord: singles.record,
        singlesWinPct: singles.winPct,
        doublesWins: doubles.wins,
        doublesLosses: doubles.losses,
        doublesTies: doubles.ties,
        doublesRecord: doubles.record,
        doublesWinPct: doubles.winPct,
        gameRecord: doubles.record,
        gameWinPct: doubles.winPct,
        directRecord: overall.record,
        directWinPct: overall.winPct,
        overallSummary: `${gamesPlayed} games / ${diff > 0 ? '+' : ''}${diff}`,
        rounds,
        avgPpr: rounds ? roundNumber(gross / rounds, 2) : null,
        highPpr: pprs.length ? roundNumber(Math.max(...pprs), 2) : null,
        lowPpr: pprs.length ? roundNumber(Math.min(...pprs), 2) : null,
        avgOppPpr: rounds ? roundNumber(opponent / rounds, 2) : null,
        avgDpr: rounds ? roundNumber(diff / rounds, 2) : null,
        totalDiff: diff,
        fourBaggerPct: rounds ? roundNumber(100 * fourBaggers / rounds, 2) : null,
        firstDate: dates[0],
        lastDate: dates[dates.length - 1],
      };
    });
  }, [filteredGames]);

  if (!standingsData) {
    return (
      <section className="glass rounded-[28px] p-4">
        <div className="text-zinc-400">No season stats loaded yet.</div>
      </section>
    );
  }

  const totalPoints = player?.points ?? player?.totalPoints ?? rows.reduce((sum, row) => sum + row.points, 0);
  const cards = [
    { label: 'Events', value: summary.eventsPlayed || rows.length },
    { label: 'Rounds', value: player?.rounds_thrown || coverage.playerRoundsSaved || 0 },
    { label: 'PPR', value: num(player?.ppr, 2) },
    { label: 'DPR', value: num(player?.dpr, 2) },
    { label: '4B%', value: num(player?.four_bagger_pct, 2) },
    { label: 'Partners', value: summary.partners || partners.length },
  ];

  function chooseEventSort(nextKey: EventSortKey) {
    if (nextKey === eventSortKey) {
      setEventSortDirection(direction => direction === 'asc' ? 'desc' : 'asc');
      return;
    }
    setEventSortKey(nextKey);
    setEventSortDirection(nextKey === 'place' || nextKey === 'location' ? 'asc' : 'desc');
  }

  const selectedPartnerColumns = partnerColumns
    .map(key => partnerColumnDefs.find(column => column.key === key))
    .filter(Boolean) as ColumnDef[];
  const selectedOpponentRollupColumns = opponentRollupColumns
    .map(key => OPPONENT_ROLLUP_COLUMNS.find(column => column.key === key))
    .filter(Boolean) as ColumnDef[];
  const sortedOpponentRollups = useMemo(() => (
    [...opponentRollups].sort((a: any, b: any) => {
      const result = compareValues(a, b, opponentRollupSort.key);
      return opponentRollupSort.direction === 'asc' ? result : -result;
    })
  ), [opponentRollups, opponentRollupSort.key, opponentRollupSort.direction]);
  const selectedOpponent = useMemo(() => (
    opponentRollups.find((opponent: any) => String(opponent.opponent_id || opponent.opponent_name) === String(selectedOpponentId)) || null
  ), [opponentRollups, selectedOpponentId]);
  const selectedOpponentGames = useMemo(() => {
    if (!selectedOpponentId) return [];
    return filteredGames.filter((game: any) => String(game.opponent_player_id || game.opponent_name) === String(selectedOpponentId));
  }, [filteredGames, selectedOpponentId]);
  const sortedPartnerRows = useMemo(() => (
    [...filteredPartners].sort((a: any, b: any) => {
      const result = compareValues(a, b, partnerMetricSort.key);
      return partnerMetricSort.direction === 'asc' ? result : -result;
    })
  ), [filteredPartners, partnerMetricSort.key, partnerMetricSort.direction]);

  function chooseOpponentRollupSort(key: string) {
    setOpponentRollupSort({
      key,
      direction: opponentRollupSort.key === key && opponentRollupSort.direction === 'desc' ? 'asc' : 'desc',
    });
  }

  function choosePartnerMetricSort(key: string) {
    setPartnerMetricSort({
      key,
      direction: partnerMetricSort.key === key && partnerMetricSort.direction === 'desc' ? 'asc' : 'desc',
    });
  }

  function togglePartnerEvent(eventId: any) {
    const key = String(eventId);
    setOpenPartnerEvents(current => ({ ...current, [key]: !current[key] }));
  }

  return (
    <section className="space-y-4">
      <section className="glass rounded-[28px] p-4">
        <div className="text-xs uppercase tracking-[.2em] text-amber-300">Individual Season</div>
        <div className="mt-2 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 className="text-2xl font-black">{playerName}</h2>
            <div className="mt-1 text-sm text-zinc-400">
              {season.startDate} - {season.endDate}
              {seasonDefinition.label ? ` / ${seasonDefinition.label}` : ''}
            </div>
          </div>
          <div className="rounded-2xl bg-zinc-950 px-4 py-3 md:text-right">
            <div className="text-xs text-amber-300">Season Points</div>
            <div className="text-2xl font-black">{num(totalPoints, 0)}</div>
            <div className="text-sm text-zinc-400">Best finish {ordinal(summary.bestFinish || player?.bestFinish)}</div>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-6">
          {cards.map(card => (
            <div key={card.label} className="rounded-2xl bg-zinc-900 p-3">
              <div className="text-2xl font-black">{card.value}</div>
              <div className="text-xs text-zinc-400">{card.label}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {[
          ['overview', 'Overview'],
          ['events', 'Events'],
          ['games', 'Games'],
          ['partners', 'Partners'],
          ['timeline', 'Timeline'],
          ['data', 'Data'],
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveTab(key as TabKey)}
            className={`shrink-0 rounded-xl px-4 py-2 text-sm font-black ${
              activeTab === key ? 'bg-amber-400 text-black' : 'bg-zinc-900 text-zinc-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && (
        <section className="glass rounded-[28px] p-4">
          <h3 className="text-lg font-black">Season Summary</h3>
          <div className="mt-3">
            <MetricPicker columns={summaryColumnDefs} selected={summaryColumns} onChange={setSummaryColumns} />
            <SortableMetricTable
              rows={[{ ...player, name: playerName }]}
              columns={summaryColumnDefs}
              selected={summaryColumns}
              sort={summarySort}
              onSort={setSummarySort}
              empty="No summary stats have been saved yet."
            />
          </div>
          {notifications.length > 0 && (
            <div className="mt-3 rounded-2xl border border-amber-400/30 bg-amber-950/30 p-3 text-sm text-amber-100">
              {notifications.length} coverage warning{notifications.length === 1 ? '' : 's'} while gathering this season.
            </div>
          )}
          {seasonDefinition.method && (
            <div className="mt-3 rounded-2xl border border-white/10 bg-zinc-950 p-3 text-sm text-zinc-300">
              Season detected from bucket {seasonDefinition.bucketId} across {seasonDefinition.eventCount || 0} player events.
            </div>
          )}
        </section>
      )}

      {activeTab === 'events' && (
        <section className="glass rounded-[28px] p-4">
          <div className="mb-3">
            <h3 className="text-lg font-black">Event Finishes</h3>
            <div className="text-sm text-zinc-400">Search, filter, and sort the player's historical season results.</div>
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-5">
            <input
              value={eventSearch}
              onChange={event => setEventSearch(event.target.value)}
              className="rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-sm md:col-span-2"
              placeholder="Search event, location, team, partner"
            />
            <select value={locationFilter} onChange={event => setLocationFilter(event.target.value)} className="rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-sm">
              <option value="ALL">All locations</option>
              {locations.map(location => <option key={location} value={location}>{location}</option>)}
            </select>
            <select value={placeFilter} onChange={event => setPlaceFilter(event.target.value)} className="rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-sm">
              <option value="ALL">All places</option>
              {Array.from(new Set(rows.map(row => row.place).filter(Boolean))).sort((a, b) => a - b).map(place => (
                <option key={place} value={String(place)}>{ordinal(place)}</option>
              ))}
            </select>
            <select
              value={`${eventSortKey}:${eventSortDirection}`}
              onChange={event => {
                const [nextKey, nextDirection] = event.target.value.split(':') as [EventSortKey, 'asc' | 'desc'];
                setEventSortKey(nextKey);
                setEventSortDirection(nextDirection);
              }}
              className="rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-sm"
            >
              <option value="date:desc">Newest first</option>
              <option value="date:asc">Oldest first</option>
              <option value="place:asc">Best place</option>
              <option value="place:desc">Worst place</option>
              <option value="location:asc">Location A-Z</option>
              <option value="points:desc">Most points</option>
            </select>
          </div>
          <div className="mt-3">
            <MetricPicker columns={eventColumnDefs} selected={eventColumns} onChange={setEventColumns} />
            <SortableMetricTable
              rows={filteredEvents}
              columns={eventColumnDefs}
              selected={eventColumns}
              sort={eventMetricSort}
              onSort={setEventMetricSort}
              empty="No event finishes match the current filters."
              rowKey={(row) => String(row.event_id)}
              selectedRowKey={selectedEventId}
              onRowClick={(row) => setSelectedEventId(selectedEventId === String(row.event_id) ? null : String(row.event_id))}
            />
          </div>
          {selectedEvent && (
            <div className="mt-4 rounded-2xl border border-amber-400/25 bg-zinc-950 p-3">
              <div className="flex flex-col gap-1 md:flex-row md:items-end md:justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[.18em] text-amber-300">
                    {isSwapRoundersEvent(selectedEvent) ? 'Rounders Schedule' : 'Event Games'}
                  </div>
                  <h4 className="text-lg font-black">{selectedEvent.event_name || `Event ${selectedEvent.event_id}`}</h4>
                  <div className="text-sm text-zinc-400">
                    {selectedEvent.event_date} / {selectedEvent.location_name}
                  </div>
                </div>
                <div className="text-sm text-zinc-400">
                  {selectedEventGames.length} saved games
                </div>
              </div>

              <EventBreakoutBoundary resetKey={selectedEventId}>
              {selectedEventGames.length === 0 && (asArray(selectedEvent.swapUpNext).length > 0 || asArray(selectedEvent.swapStandings).length > 0) ? (
                <div className="mt-3">
                  <div className="mb-3 rounded-xl border border-white/10 bg-zinc-900 p-3 text-sm text-zinc-300">
                    Swap live lists are available from ACL. Full game schedule rows are not available yet from bracket data.
                  </div>
                  {asArray(selectedEvent.swapUpNext).length > 0 && (
                    <div className="mb-5">
                      <h5 className="mb-2 text-sm font-black uppercase tracking-[.18em] text-zinc-500">Up Next Players</h5>
                      <MetricPicker columns={SWAP_UP_NEXT_COLUMNS} selected={swapUpNextColumns} onChange={setSwapUpNextColumns} />
                      <SortableMetricTable
                        rows={asArray(selectedEvent.swapUpNext)}
                        columns={SWAP_UP_NEXT_COLUMNS}
                        selected={swapUpNextColumns}
                        sort={swapUpNextSort}
                        onSort={setSwapUpNextSort}
                        empty="No up-next players have been saved for this event."
                      />
                    </div>
                  )}
                  {asArray(selectedEvent.swapStandings).length > 0 && (
                    <div>
                      <h5 className="mb-2 text-sm font-black uppercase tracking-[.18em] text-zinc-500">Swap Standings</h5>
                      <MetricPicker columns={SWAP_STANDINGS_COLUMNS} selected={swapStandingColumns} onChange={setSwapStandingColumns} />
                      <SortableMetricTable
                        rows={asArray(selectedEvent.swapStandings)}
                        columns={SWAP_STANDINGS_COLUMNS}
                        selected={swapStandingColumns}
                        sort={swapStandingSort}
                        onSort={setSwapStandingSort}
                        empty="No swap standings have been saved for this event."
                      />
                    </div>
                  )}
                </div>
              ) : selectedEventGames.length === 0 ? (
                <div className="mt-3 rounded-xl border border-white/10 bg-zinc-900 p-3 text-sm text-zinc-300">
                  No game schedule, swap standings, or round-level stats are saved for this event yet. The swap standings endpoint can be checked on the next season stats refresh.
                </div>
              ) : (
                <div className="mt-3">
                  <div className="mb-3 grid grid-cols-1 gap-2 md:grid-cols-[1fr_auto]">
                    <select
                      value={eventCourtFilter}
                      onChange={event => setEventCourtFilter(event.target.value)}
                      className="rounded-xl border border-white/10 bg-zinc-900 px-3 py-2 text-sm"
                    >
                      <option value="ALL">All courts</option>
                      {selectedEventCourtOptions.map(court => (
                        <option key={court} value={court}>Court {court}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => setEventCourtGrouping(value => !value)}
                      className={`rounded-xl border px-3 py-2 text-sm font-black transition ${
                        eventCourtGrouping
                          ? 'border-amber-300 bg-amber-400 text-black'
                          : 'border-white/10 bg-zinc-900 text-zinc-200 hover:border-white/25'
                      }`}
                      aria-pressed={eventCourtGrouping}
                    >
                      {eventCourtGrouping ? 'Court comparison on' : 'Group by court'}
                    </button>
                  </div>
                  <MetricPicker columns={ROUNDERS_SCHEDULE_COLUMNS} selected={roundersColumns} onChange={setRoundersColumns} />
                  <SortableMetricTable
                    rows={selectedEventVisibleGames}
                    columns={ROUNDERS_SCHEDULE_COLUMNS}
                    selected={roundersColumns}
                    sort={roundersSort}
                    onSort={setRoundersSort}
                    empty="No saved schedule games for this event."
                  />
                  <EventGameSummary
                    title={eventCourtFilter === 'ALL' ? 'Overall Stats' : `Court ${eventCourtFilter} Stats`}
                    summary={selectedEventVisibleOverall}
                    showComparison={eventCourtFilter !== 'ALL'}
                  />
                  {eventCourtGrouping && (
                    <div className="mt-4">
                      <div className="mb-2 flex flex-col gap-1 md:flex-row md:items-end md:justify-between">
                        <div>
                          <h5 className="text-sm font-black uppercase tracking-[.18em] text-zinc-500">Court Comparison</h5>
                          <div className="text-sm text-zinc-400">Each court is compared against this event's overall performance.</div>
                        </div>
                        <div className="text-xs text-zinc-500">
                          Event overall: PPR {num(selectedEventOverall.ppr, 2)} / DPR {num(selectedEventOverall.dpr, 2)}
                        </div>
                      </div>
                      <MetricPicker columns={EVENT_COURT_ROLLUP_COLUMNS} selected={eventCourtColumns} onChange={setEventCourtColumns} />
                      <SortableMetricTable
                        rows={selectedEventCourtRollups}
                        columns={EVENT_COURT_ROLLUP_COLUMNS}
                        selected={eventCourtColumns}
                        sort={eventCourtSort}
                        onSort={setEventCourtSort}
                        empty="No court comparison rows are available for this event."
                      />
                    </div>
                  )}
                </div>
              )}
              </EventBreakoutBoundary>
            </div>
          )}
        </section>
      )}

      {activeTab === 'games' && (
        <section className="glass rounded-[28px] p-4">
          <div className="mb-3">
            <h3 className="text-lg font-black">Game Stats</h3>
            <div className="text-sm text-zinc-400">Search by opponent, event, location, court, or match and sort by any selected stat.</div>
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
            <input
              value={gameSearch}
              onChange={event => setGameSearch(event.target.value)}
              className="rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-sm md:col-span-2"
              placeholder="Search opponent, event, location, court, match"
            />
            <select value={gameLocationFilter} onChange={event => setGameLocationFilter(event.target.value)} className="rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-sm">
              <option value="ALL">All locations</option>
              {gameLocations.map(location => <option key={location} value={location}>{location}</option>)}
            </select>
          </div>
          <div className="mt-3">
            <h4 className="mb-2 text-sm font-black uppercase tracking-[.18em] text-zinc-500">Opponent Rollup</h4>
            <MetricPicker columns={OPPONENT_ROLLUP_COLUMNS} selected={opponentRollupColumns} onChange={setOpponentRollupColumns} />
            {sortedOpponentRollups.length === 0 ? (
              <div className="mt-3 rounded-2xl border border-white/10 bg-zinc-950 p-4 text-zinc-400">
                No opponent summary rows match the current filters.
              </div>
            ) : (
              <div className="mt-3 overflow-x-auto rounded-2xl border border-white/10">
                <table className="w-full min-w-[980px] border-collapse bg-zinc-950/80 text-sm">
                  <thead className="bg-zinc-900 text-xs uppercase tracking-widest text-zinc-400">
                    <tr>
                      {selectedOpponentRollupColumns.map(column => (
                        <th key={column.key} className="p-0 text-left">
                          <button
                            type="button"
                            onClick={() => chooseOpponentRollupSort(column.key)}
                            className={`w-full px-3 py-3 text-left font-black ${opponentRollupSort.key === column.key ? 'text-amber-300' : 'text-zinc-400'}`}
                          >
                            {columnLabel(column)}{opponentRollupSort.key === column.key ? (opponentRollupSort.direction === 'asc' ? ' ↑' : ' ↓') : ''}
                          </button>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sortedOpponentRollups.map((opponent: any) => {
                      const opponentKey = String(opponent.opponent_id || opponent.opponent_name);
                      const isSelected = selectedOpponentId === opponentKey;

                      return (
                        <tr
                          key={opponentKey}
                          onClick={() => setSelectedOpponentId(isSelected ? null : opponentKey)}
                          className={`cursor-pointer border-t border-white/5 odd:bg-white/[0.025] hover:bg-amber-400/10 ${isSelected ? 'bg-amber-400/10 text-amber-100' : ''}`}
                        >
                          {selectedOpponentRollupColumns.map(column => (
                            <td key={column.key} className="whitespace-nowrap px-3 py-3">
                              {formatValue(opponent[column.key], column.key)}
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {selectedOpponent && (
              <div className="mt-4 rounded-2xl border border-amber-400/25 bg-zinc-950 p-3">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="text-xs uppercase tracking-[.18em] text-amber-300">Opponent Games</div>
                    <h4 className="text-lg font-black">{selectedOpponent.opponent_name}</h4>
                  </div>
                  <div className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
                    <ResultChip label="Overall" value={selectedOpponent.overallRecord} detail={`${formatValue(selectedOpponent.overallWinPct, 'overallWinPct')}%`} />
                    <ResultChip label="Singles" value={selectedOpponent.singlesRecord} detail={`${formatValue(selectedOpponent.singlesWinPct, 'singlesWinPct')}%`} />
                    <ResultChip label="Doubles" value={selectedOpponent.doublesRecord} detail={`${formatValue(selectedOpponent.doublesWinPct, 'doublesWinPct')}%`} />
                  </div>
                </div>
                <SortableMetricTable
                  rows={selectedOpponentGames}
                  columns={gameColumnDefs}
                  selected={gameColumns}
                  sort={gameSort}
                  onSort={setGameSort}
                  empty="No saved games for this opponent match the current filters."
                />
              </div>
            )}
          </div>
          <div className="mt-5">
            <h4 className="mb-2 text-sm font-black uppercase tracking-[.18em] text-zinc-500">Game Detail</h4>
            <MetricPicker columns={gameColumnDefs} selected={gameColumns} onChange={setGameColumns} />
            <SortableMetricTable
              rows={filteredGames}
              columns={gameColumnDefs}
              selected={gameColumns}
              sort={gameSort}
              onSort={setGameSort}
              empty="No game-level round stats match the current filters."
            />
          </div>
        </section>
      )}

      {activeTab === 'partners' && (
        <section className="glass rounded-[28px] p-4">
          <div className="mb-3">
            <h3 className="text-lg font-black">Partner Stats</h3>
            <div className="text-sm text-zinc-400">Current and historical partner performance from saved round-level data.</div>
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
            <input value={partnerSearch} onChange={event => setPartnerSearch(event.target.value)} className="rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-sm md:col-span-2" placeholder="Search partner" />
            <select value={partnerSortKey} onChange={event => setPartnerSortKey(event.target.value as PartnerSortKey)} className="rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-sm">
              <option value="events">Most events</option>
              <option value="rounds">Most rounds</option>
              <option value="ppr">Best PPR</option>
              <option value="dpr">Best DPR</option>
              <option value="fourBaggerPct">Best 4B%</option>
              <option value="lastDate">Most recent</option>
              <option value="partner">Partner A-Z</option>
            </select>
          </div>
          <div className="mt-3">
            <MetricPicker columns={partnerColumnDefs} selected={partnerColumns} onChange={setPartnerColumns} />
            {sortedPartnerRows.length === 0 ? (
              <div className="mt-3 rounded-2xl border border-white/10 bg-zinc-950 p-4 text-zinc-400">
                No partner round stats have been saved yet.
              </div>
            ) : (
              <div className="mt-3 overflow-x-auto rounded-2xl border border-white/10">
                <table className="w-full min-w-[980px] border-collapse bg-zinc-950/80 text-sm">
                  <thead className="bg-zinc-900 text-xs uppercase tracking-widest text-zinc-400">
                    <tr>
                      {selectedPartnerColumns.map(column => (
                        <th key={column.key} className="p-0 text-left">
                          <button
                            type="button"
                            onClick={() => choosePartnerMetricSort(column.key)}
                            className={`w-full px-3 py-3 text-left font-black ${partnerMetricSort.key === column.key ? 'text-amber-300' : 'text-zinc-400'}`}
                          >
                            {columnLabel(column)}{partnerMetricSort.key === column.key ? (partnerMetricSort.direction === 'asc' ? ' ↑' : ' ↓') : ''}
                          </button>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sortedPartnerRows.map((partner: any) => {
                      const isSelected = String(selectedPartnerId) === String(partner.partner_id);
                      return (
                        <tr
                          key={partner.partner_id}
                          onClick={() => {
                            setSelectedPartnerId(isSelected ? null : String(partner.partner_id));
                            setOpenPartnerEvents({});
                          }}
                          className={`cursor-pointer border-t border-white/5 odd:bg-white/[0.025] hover:bg-amber-400/10 ${isSelected ? 'bg-amber-400/10 text-amber-100' : ''}`}
                        >
                          {selectedPartnerColumns.map(column => (
                            <td key={column.key} className="whitespace-nowrap px-3 py-3">
                              {formatValue(partner[column.key], column.key)}
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          {selectedPartner && (
            <div className="mt-4 rounded-2xl border border-amber-400/25 bg-zinc-950 p-3">
              <div className="flex flex-col gap-1 md:flex-row md:items-end md:justify-between">
                <div>
                  <div className="text-xs uppercase tracking-[.18em] text-amber-300">Partner Drilldown</div>
                  <h4 className="text-lg font-black">{selectedPartner.partner_name}</h4>
                </div>
                <div className="text-sm text-zinc-400">
                  {selectedPartnerEvents.length} events / {selectedPartnerGames.length} games with saved round detail
                </div>
              </div>
              <div className="mt-3 space-y-2">
                {selectedPartnerEvents.map(event => {
                  const eventGames = selectedPartnerGames.filter((game: any) => String(game.event_id) === String(event.event_id));
                  const isOpen = Boolean(openPartnerEvents[String(event.event_id)]);

                  return (
                    <div key={`${event.event_id}-${event.team_id || ''}`} className="rounded-xl border border-white/10 bg-zinc-900">
                      <button
                        type="button"
                        onClick={() => togglePartnerEvent(event.event_id)}
                        className="flex w-full flex-col gap-1 px-3 py-2 text-left md:flex-row md:items-center md:justify-between"
                      >
                        <span>
                          <span className="font-black text-white">{event.event_name || `Event ${event.event_id}`}</span>
                          <span className="ml-2 text-sm text-zinc-400">{event.event_date} / {event.location_name}</span>
                        </span>
                        <span className="text-sm text-zinc-300">
                          {ordinal(event.place)} / {num(event.points, 0)} pts / {eventGames.length} games
                        </span>
                      </button>
                      {isOpen && (
                        <div className="border-t border-white/10 p-3">
                          <SortableMetricTable
                            rows={eventGames}
                            columns={gameColumnDefs}
                            selected={gameColumns}
                            sort={gameSort}
                            onSort={setGameSort}
                            empty="No saved game rows for this event and partner yet."
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>
      )}

      {activeTab === 'timeline' && (
        <section className="glass rounded-[28px] p-4">
          <div className="mb-3">
            <h3 className="text-lg font-black">Timeline</h3>
            <div className="text-sm text-zinc-400">Daily performance with rolling averages as of each day.</div>
          </div>
          <SeasonSparkline rows={timeline} />
          <div className="mt-3">
            <MetricPicker columns={timelineColumnDefs} selected={timelineColumns} onChange={setTimelineColumns} />
            <SortableMetricTable
              rows={timeline}
              columns={timelineColumnDefs}
              selected={timelineColumns}
              sort={timelineSort}
              onSort={setTimelineSort}
              empty="No daily timeline stats have been saved yet."
            />
          </div>
        </section>
      )}

      {activeTab === 'data' && (
        <section className="glass rounded-[28px] p-4">
          <h3 className="text-lg font-black">Data Gathered</h3>
          <div className="mt-2 grid gap-2 text-sm text-zinc-300 md:grid-cols-2">
            <div className="rounded-2xl bg-zinc-900 p-3">
              Player event indexes, event details, standings finishes, points, wins/losses, team names, partner names, dates, and locations.
            </div>
            <div className="rounded-2xl bg-zinc-900 p-3">
              Brackets, matches, games, courts, teams, team members, and round-level player rows when public match stats are available.
            </div>
            <div className="rounded-2xl bg-zinc-900 p-3">
              Coverage: {coverage.eventsInRange || 0} events, {coverage.eventsSkippedCached || 0} completed events reused, {coverage.bracketsChecked || 0} brackets checked, {coverage.bracketsFailed || 0} bracket failures.
            </div>
            <div className="rounded-2xl bg-zinc-900 p-3">
              Game stats checked: {coverage.matchStatsChecked || 0}. Saved game stats reused: {coverage.matchStatsSkippedCached || 0}. Round rows saved: {coverage.playerRoundsSaved || 0}. Auth blocked: {coverage.matchStatsAuthBlocked || 0}. Failed match stats: {coverage.matchStatsFailed || 0}.
            </div>
          </div>
        </section>
      )}
    </section>
  );
}

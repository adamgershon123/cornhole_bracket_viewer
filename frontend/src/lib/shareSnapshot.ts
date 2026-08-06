export type BracketSnapshotTeam = {
  teamName?: string;
  players?: Array<{ playerName?: string }>;
  reachSemifinalProbability?: number;
  reachFinalProbability?: number;
  winEventProbability?: number;
};

export type BracketSnapshotData = {
  simulationCount?: number;
  teams?: BracketSnapshotTeam[];
  coverage?: {
    modelCoverageRate?: number;
    equalProbabilityFallbackPairings?: number;
  };
  structure?: {
    mode?: string;
    templateKey?: string;
  };
};

export type SnapshotEventDetails = {
  eventId?: string | number;
  name?: string;
  date?: string;
  time?: string;
  matchType?: string;
  bracketType?: string;
  blindDraw?: boolean | number;
  formatLabel?: string;
  location?: {
    name?: string;
    city?: string;
    state?: string;
  };
};

export type TaleOfTapeSnapshotInput = {
  eventId: string;
  event?: SnapshotEventDetails;
  match?: {
    courtId?: string;
    roundDescription?: string;
  };
  topTeamName: string;
  bottomTeamName: string;
  topProbability: number;
  evidence?: any;
  reasoning?: Array<{ title: string; detail: string }>;
};

export type FinalResultSnapshotInput = {
  eventId: string;
  event?: SnapshotEventDetails;
  match?: { courtId?: string; roundDescription?: string };
  topTeamName: string;
  bottomTeamName: string;
  topScore: number;
  bottomScore: number;
  roundCount: number;
  players: Array<{ name: string; team: 'top' | 'bottom'; ppr?: number; dpr?: number; fourBaggers?: number; fourBaggerPct?: number }>;
};

export type PlayerStatusSnapshotInput = {
  eventId: string;
  eventName: string;
  playerId: string;
  playerName: string;
  teamName: string;
  record: string;
  status: string;
  gamesPlayed: number;
  gamesLeft: number;
  initialTournamentChance?: number;
  currentOpponent: string;
  currentScore: string;
  currentWinChance?: number;
  path: string[];
};

const WIDTH = 1080;
const HEIGHT = 1350;

export async function createBracketSnapshot(data: BracketSnapshotData, eventId: string, event?: SnapshotEventDetails) {
  const canvas = document.createElement('canvas');
  const teams = [...(data.teams || [])].sort((a, b) => Number(b.winEventProbability || 0) - Number(a.winEventProbability || 0));
  const snapshotHeight = Math.max(HEIGHT, 890 + teams.length * 78);
  canvas.width = WIDTH;
  canvas.height = snapshotHeight;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('This browser cannot create an image.');

  const gradient = ctx.createLinearGradient(0, 0, WIDTH, snapshotHeight);
  gradient.addColorStop(0, '#07101d');
  gradient.addColorStop(0.56, '#09090b');
  gradient.addColorStop(1, '#151006');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, WIDTH, snapshotHeight);

  ctx.strokeStyle = '#3f3210';
  ctx.lineWidth = 2;
  roundedRect(ctx, 42, 42, WIDTH - 84, snapshotHeight - 84, 34);
  ctx.stroke();

  text(ctx, 'CHEESEBAGGERS ANALYTICS', 72, 96, 22, 800, '#facc15', 'left', 5);
  text(ctx, 'BRACKET PATH', 72, 164, 54, 900, '#ffffff');
  text(ctx, 'PROBABILITIES', 72, 220, 54, 900, '#ffffff');
  text(ctx, `ACL EVENT ${event?.eventId || eventId}`, WIDTH - 72, 104, 22, 700, '#94a3b8', 'right');
  text(ctx, `${Number(data.simulationCount || 0).toLocaleString()} SIMULATIONS`, WIDTH - 72, 143, 22, 800, '#e2e8f0', 'right');

  roundedFill(ctx, 70, 254, WIDTH - 140, 146, 24, '#0d1118', '#26303d');
  text(ctx, 'EVENT', 98, 289, 17, 900, '#7dd3fc', 'left', 3);
  const eventLines = wrap(ctx, event?.name || `ACL Event ${eventId}`, 31, 830, 2);
  eventLines.forEach((line, index) => text(ctx, line, 98, 330 + index * 35, 31, 900, '#ffffff'));
  const eventMeta = eventMetadata(event);
  text(ctx, truncate(eventMeta, 82), 98, 385, 17, 700, '#a1a1aa');

  const leader = teams[0];
  const leaderName = teamPlayers(leader);
  const leaderChance = percent(leader?.winEventProbability);
  roundedFill(ctx, 70, 424, WIDTH - 140, 184, 28, '#171407', '#55440e');
  text(ctx, 'MOST LIKELY CHAMPION', 100, 463, 19, 800, '#facc15', 'left', 3);
  const leaderLines = wrap(ctx, leaderName || 'Unavailable', 58, 860, 2);
  leaderLines.forEach((line, index) => text(ctx, line, 100, 522 + index * 49, 42, 900, '#ffffff'));
  text(ctx, leaderChance, WIDTH - 100, 570, 58, 900, '#facc15', 'right');

  text(ctx, 'PROJECTED TO WIN EVENT', WIDTH - 100, 600, 17, 800, '#a1a1aa', 'right', 2);
  text(ctx, 'TOP CONTENDERS', 72, 652, 22, 900, '#7dd3fc', 'left', 3);

  let y = 674;
  teams.forEach((team, index) => {
    roundedFill(ctx, 70, y, WIDTH - 140, 72, 16, index === 0 ? '#171407' : '#111318', index === 0 ? '#493a0d' : '#262a32');
    text(ctx, `${index + 1}`, 98, y + 45, 24, 900, index === 0 ? '#facc15' : '#64748b');
    const names = truncate(teamPlayers(team), 44);
    text(ctx, names, 148, y + 31, 22, 850, '#ffffff');
    text(ctx, `SEMIS ${percent(team.reachSemifinalProbability)}   •   FINAL ${percent(team.reachFinalProbability)}`, 148, y + 57, 14, 700, '#94a3b8');
    text(ctx, percent(team.winEventProbability), WIDTH - 98, y + 46, 27, 900, index === 0 ? '#facc15' : '#7dd3fc', 'right');
    y += 78;
  });

  const coverage = percent(data.coverage?.modelCoverageRate);
  const fallback = Number(data.coverage?.equalProbabilityFallbackPairings || 0);
  const structure = data.structure?.mode === 'VALIDATED_ACL_BRACKET_TEMPLATE'
    ? `Validated ACL ${data.structure?.templateKey || 'bracket'} path`
    : 'Approximated single-elimination path';
  const footerY = y + 26;
  roundedFill(ctx, 70, footerY, WIDTH - 140, 88, 20, '#0d1118', '#26303d');
  text(ctx, `${coverage} MATCHUP COVERAGE`, 96, footerY + 38, 19, 900, '#ffffff');
  text(ctx, `${fallback} EVEN FALLBACK${fallback === 1 ? '' : 'S'}  •  ${structure}`, 96, footerY + 68, 16, 650, '#94a3b8');
  text(ctx, 'live.cheesebaggers.com', WIDTH - 72, snapshotHeight - 40, 18, 800, '#facc15', 'right');

  return await canvasBlob(canvas);
}

export async function createTaleOfTapeSnapshot(input: TaleOfTapeSnapshotInput) {
  const canvas = document.createElement('canvas');
  const taleHeight = input.reasoning?.length ? 1650 : HEIGHT;
  canvas.width = WIDTH;
  canvas.height = taleHeight;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('This browser cannot create an image.');

  const gradient = ctx.createLinearGradient(0, 0, WIDTH, taleHeight);
  gradient.addColorStop(0, '#07101d');
  gradient.addColorStop(0.52, '#09090b');
  gradient.addColorStop(1, '#18090c');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, WIDTH, taleHeight);
  ctx.strokeStyle = '#3f3210';
  ctx.lineWidth = 2;
  roundedRect(ctx, 42, 42, WIDTH - 84, taleHeight - 84, 34);
  ctx.stroke();

  text(ctx, 'CHEESEBAGGERS ANALYTICS', 72, 94, 20, 800, '#facc15', 'left', 5);
  text(ctx, 'TALE OF THE TAPE', 72, 156, 50, 900, '#ffffff');
  text(ctx, 'PREMATCH PREDICTION', WIDTH - 72, 96, 19, 800, '#94a3b8', 'right');

  roundedFill(ctx, 70, 190, WIDTH - 140, 128, 22, '#0d1118', '#26303d');
  const eventLines = wrap(ctx, input.event?.name || `ACL Event ${input.eventId}`, 28, 850, 2);
  eventLines.forEach((line, index) => text(ctx, line, 96, 230 + index * 32, 28, 900, '#ffffff'));
  const matchDetail = [
    eventMetadata(input.event),
    input.match?.roundDescription,
    input.match?.courtId ? `Court ${input.match.courtId}` : '',
    `Event ${input.event?.eventId || input.eventId}`,
  ].filter(Boolean).join('  •  ');
  text(ctx, truncate(matchDetail, 96), 96, 298, 15, 700, '#a1a1aa');

  const topProbability = Math.max(0.01, Math.min(0.99, Number(input.topProbability || 0.5)));
  const topFavored = topProbability >= 0.5;
  const favoriteProbability = topFavored ? topProbability : 1 - topProbability;
  const loserScore = Math.max(0, Math.min(20, Math.round(21 * (1 - favoriteProbability) / favoriteProbability)));
  const projectedScore = topFavored ? `21–${loserScore}` : `${loserScore}–21`;
  const winner = topFavored ? input.topTeamName : input.bottomTeamName;

  text(ctx, truncate(input.topTeamName, 32), 76, 372, 22, 900, '#60a5fa');
  text(ctx, truncate(input.bottomTeamName, 32), WIDTH - 76, 372, 22, 900, '#fb7185', 'right');
  text(ctx, 'VS', WIDTH / 2, 370, 18, 900, '#71717a', 'center');
  roundedFill(ctx, 70, 402, WIDTH - 140, 128, 24, '#171407', '#55440e');
  text(ctx, 'PROJECTED WINNER', 98, 438, 16, 900, '#facc15', 'left', 3);
  text(ctx, truncate(winner, 48), 98, 486, 35, 900, '#ffffff');
  text(ctx, `${(favoriteProbability * 100).toFixed(1)}%`, WIDTH - 98, 470, 50, 900, '#facc15', 'right');
  text(ctx, `PROJECTED SCORE  ${projectedScore}`, WIDTH - 98, 508, 18, 800, '#d4d4d8', 'right');

  const topPlayers = input.evidence?.top?.players || [];
  const bottomPlayers = input.evidence?.bottom?.players || [];
  text(ctx, 'PLAYER PROFILE EVIDENCE', 72, 580, 20, 900, '#7dd3fc', 'left', 3);
  drawEvidenceColumn(ctx, topPlayers, 70, 610, 462, '#60a5fa');
  drawEvidenceColumn(ctx, bottomPlayers, 548, 610, 462, '#fb7185');

  const topAggregate = input.evidence?.top?.aggregate || {};
  const bottomAggregate = input.evidence?.bottom?.aggregate || {};
  roundedFill(ctx, 70, 1082, WIDTH - 140, 118, 20, '#0d1118', '#26303d');
  text(ctx, 'TEAM PROJECTION', 96, 1117, 16, 900, '#a1a1aa', 'left', 2);
  text(ctx, `${formatNumber(topAggregate.predictivePpr)} PPR`, 96, 1160, 31, 900, '#60a5fa');
  text(ctx, `${formatNumber(bottomAggregate.predictivePpr)} PPR`, WIDTH - 96, 1160, 31, 900, '#fb7185', 'right');
  text(ctx, `${input.evidence?.evidenceTier || 'Evidence unavailable'}  •  ${Math.round(Number(input.evidence?.shrinkageFactor || 0) * 100)}% confidence adjustment`, WIDTH / 2, 1189, 15, 700, '#94a3b8', 'center');

  if (input.reasoning?.length) {
    text(ctx, 'WHY THIS PROJECTION', 72, 1248, 20, 900, '#facc15', 'left', 3);
    input.reasoning.slice(0, 4).forEach((reason, index) => {
      const reasonY = 1272 + index * 68;
      text(ctx, `${index + 1}`, 78, reasonY + 28, 20, 900, '#facc15');
      text(ctx, truncate(reason.title, 34), 116, reasonY + 20, 18, 900, '#ffffff');
      text(ctx, truncate(reason.detail, 91), 116, reasonY + 45, 14, 650, '#a1a1aa');
    });
  }
  const footerBase = taleHeight - 100;
  text(ctx, `MODEL ${input.evidence?.modelVersion || 'UNKNOWN'}  •  DATA CUTOFF ${shortDate(input.evidence?.dataCutoffAt)}`, 72, footerBase, 15, 750, '#94a3b8');
  text(ctx, 'Calculated player values are labeled; official CPI is not inferred.', 72, footerBase + 31, 14, 650, '#71717a');
  text(ctx, 'live.cheesebaggers.com', WIDTH - 72, taleHeight - 40, 18, 800, '#facc15', 'right');
  return await canvasBlob(canvas);
}

export async function createFinalResultSnapshot(input: FinalResultSnapshotInput) {
  const canvas = document.createElement('canvas');
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('This browser cannot create an image.');
  const gradient = ctx.createLinearGradient(0, 0, WIDTH, HEIGHT);
  gradient.addColorStop(0, '#07101d');
  gradient.addColorStop(0.55, '#09090b');
  gradient.addColorStop(1, '#18090c');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, WIDTH, HEIGHT);
  ctx.strokeStyle = '#3f3210';
  ctx.lineWidth = 2;
  roundedRect(ctx, 42, 42, WIDTH - 84, HEIGHT - 84, 34);
  ctx.stroke();
  text(ctx, 'CHEESEBAGGERS ANALYTICS', 72, 96, 21, 800, '#facc15', 'left', 5);
  text(ctx, 'FINAL GAME RESULT', 72, 158, 50, 900, '#ffffff');
  roundedFill(ctx, 70, 190, WIDTH - 140, 134, 22, '#0d1118', '#26303d');
  wrap(ctx, input.event?.name || `ACL Event ${input.eventId}`, 29, 850, 2)
    .forEach((line, index) => text(ctx, line, 96, 232 + index * 33, 29, 900, '#ffffff'));
  const detail = [eventMetadata(input.event), input.match?.roundDescription, input.match?.courtId ? `Court ${input.match.courtId}` : ''].filter(Boolean).join('  •  ');
  text(ctx, truncate(detail, 96), 96, 304, 15, 700, '#a1a1aa');
  const winner = input.topScore > input.bottomScore ? input.topTeamName : input.bottomTeamName;
  roundedFill(ctx, 70, 352, WIDTH - 140, 218, 28, '#171407', '#55440e');
  text(ctx, 'WINNER', 100, 394, 18, 900, '#facc15', 'left', 3);
  wrap(ctx, winner, 42, 650, 2).forEach((line, index) => text(ctx, line, 100, 442 + index * 42, 36, 900, '#ffffff'));
  text(ctx, `${input.topScore}  –  ${input.bottomScore}`, WIDTH - 100, 486, 62, 900, '#facc15', 'right');
  text(ctx, `${input.roundCount} ROUNDS PLAYED`, WIDTH - 100, 528, 17, 800, '#a1a1aa', 'right');
  text(ctx, truncate(input.topTeamName, 34), 76, 630, 24, 900, '#60a5fa');
  text(ctx, truncate(input.bottomTeamName, 34), WIDTH - 76, 630, 24, 900, '#fb7185', 'right');
  const drawPlayers = (team: 'top' | 'bottom', x: number, tone: string) => {
    input.players.filter(player => player.team === team).slice(0, 2).forEach((player, index) => {
      const y = 664 + index * 222;
      roundedFill(ctx, x, y, 462, 204, 20, '#101318', `${tone}55`);
      text(ctx, truncate(player.name, 28), x + 22, y + 42, 25, 900, '#ffffff');
      text(ctx, formatNumber(player.ppr), x + 440, y + 45, 36, 900, tone, 'right');
      text(ctx, 'PPR', x + 440, y + 67, 12, 800, '#71717a', 'right');
      [['DPR', formatNumber(player.dpr)], ['4-BAGGERS', String(player.fourBaggers || 0)], ['4-BAG %', `${Number(player.fourBaggerPct || 0).toFixed(1)}%`]]
        .forEach(([label, value], metricIndex) => {
          const metricX = x + 22 + metricIndex * 142;
          text(ctx, label, metricX, y + 114, 12, 800, '#71717a');
          text(ctx, value, metricX, y + 151, 23, 900, '#e4e4e7');
        });
    });
  };
  drawPlayers('top', 70, '#60a5fa');
  drawPlayers('bottom', 548, '#fb7185');
  text(ctx, 'Official final score with ACL match-stat performance.', 72, 1252, 15, 650, '#94a3b8');
  text(ctx, 'live.cheesebaggers.com', WIDTH - 72, 1310, 18, 800, '#facc15', 'right');
  return await canvasBlob(canvas);
}

export async function createPlayerStatusSnapshot(input: PlayerStatusSnapshotInput) {
  const canvas = document.createElement('canvas');
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('This browser cannot create an image.');
  const gradient = ctx.createLinearGradient(0, 0, WIDTH, HEIGHT);
  gradient.addColorStop(0, '#071525');
  gradient.addColorStop(0.55, '#09090b');
  gradient.addColorStop(1, '#160f03');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, WIDTH, HEIGHT);
  ctx.strokeStyle = '#334155';
  ctx.lineWidth = 2;
  roundedRect(ctx, 42, 42, WIDTH - 84, HEIGHT - 84, 34);
  ctx.stroke();
  text(ctx, 'CHEESEBAGGERS LIVE', 72, 96, 21, 850, '#7dd3fc', 'left', 5);
  text(ctx, 'PLAYER TOURNAMENT STATUS', 72, 154, 42, 900, '#ffffff');
  roundedFill(ctx, 70, 188, WIDTH - 140, 134, 22, '#0d1118', '#26303d');
  wrap(ctx, input.eventName, 29, 850, 2).forEach((line, index) => text(ctx, line, 96, 230 + index * 33, 29, 900, '#ffffff'));
  text(ctx, `EVENT ${input.eventId}  •  PLAYER ${input.playerId}`, 96, 302, 15, 750, '#94a3b8');
  text(ctx, input.playerName, 72, 382, 48, 900, '#ffffff');
  text(ctx, truncate(input.teamName, 62), 72, 421, 19, 750, '#7dd3fc');
  roundedFill(ctx, 70, 458, WIDTH - 140, 166, 26, '#101318', '#26303d');
  const stats = [
    ['RECORD', input.record],
    ['GAMES PLAYED', String(input.gamesPlayed)],
    ['STATUS', input.status],
  ];
  stats.forEach(([label, value], index) => {
    const x = 98 + index * 300;
    text(ctx, label, x, 500, 14, 850, '#71717a', 'left', 2);
    text(ctx, truncate(value, 18), x, 557, 34, 900, index === 2 && /eliminated/i.test(value) ? '#fb7185' : '#ffffff');
  });
  roundedFill(ctx, 70, 650, WIDTH - 140, 186, 26, '#171407', '#55440e');
  text(ctx, 'CURRENT / LATEST MATCH', 98, 691, 16, 900, '#facc15', 'left', 3);
  text(ctx, truncate(`vs ${input.currentOpponent}`, 46), 98, 742, 31, 900, '#ffffff');
  text(ctx, input.currentScore, WIDTH - 98, 750, 51, 900, '#facc15', 'right');
  const chance = input.currentWinChance == null ? 'FINAL' : `${input.currentWinChance.toFixed(1)}% CURRENT WIN CHANCE`;
  text(ctx, chance, 98, 797, 17, 800, '#a1a1aa');
  text(ctx, 'TOURNAMENT OUTLOOK', 72, 891, 20, 900, '#7dd3fc', 'left', 3);
  roundedFill(ctx, 70, 916, WIDTH - 140, 128, 22, '#0d1118', '#26303d');
  text(ctx, 'INITIAL TITLE CHANCE', 98, 957, 15, 850, '#71717a');
  text(ctx, input.initialTournamentChance == null ? 'Unavailable' : `${input.initialTournamentChance.toFixed(1)}%`, 98, 1005, 34, 900, '#7dd3fc');
  text(ctx, 'POTENTIAL GAMES LEFT', 560, 957, 15, 850, '#71717a');
  text(ctx, String(input.gamesLeft), 560, 1005, 34, 900, input.gamesLeft ? '#facc15' : '#fb7185');
  text(ctx, 'PATH', 72, 1094, 18, 900, '#facc15', 'left', 3);
  const pathText = input.path.length ? input.path.join('  →  ') : 'No games remaining';
  wrap(ctx, pathText, 21, 900, 3).forEach((line, index) => text(ctx, line, 72, 1136 + index * 30, 20, 750, '#e4e4e7'));
  text(ctx, `live.cheesebaggers.com/status/${input.eventId}/${input.playerId}`, 72, 1307, 17, 800, '#7dd3fc');
  return await canvasBlob(canvas);
}

export async function shareImage(blob: Blob, filename: string, title: string) {
  const file = new File([blob], filename, { type: 'image/png' });
  if (navigator.share && (!navigator.canShare || navigator.canShare({ files: [file] }))) {
    await navigator.share({ title, files: [file] });
    return 'shared' as const;
  }
  throw new Error('Native image sharing is not available on this device.');
}

export async function copyImage(blob: Blob) {
  if (!navigator.clipboard?.write || typeof ClipboardItem === 'undefined') {
    throw new Error('Image copying is not supported by this browser.');
  }
  await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
}

export function downloadImage(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function teamPlayers(team?: BracketSnapshotTeam) {
  const players = (team?.players || []).map(player => player.playerName).filter(Boolean).join(' / ');
  return players || team?.teamName || '';
}

function percent(value?: number) {
  return value == null ? '—' : `${(Number(value) * 100).toFixed(1)}%`;
}

function truncate(value: string, max: number) {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function eventMetadata(event?: SnapshotEventDetails) {
  const location = [event?.location?.name, event?.location?.city, event?.location?.state].filter(Boolean).join(', ');
  const format = [
    event?.formatLabel,
    event?.blindDraw ? 'Blind Draw' : '',
    event?.matchType === 'S' ? 'Singles' : event?.matchType === 'D' ? 'Doubles' : '',
  ].filter(Boolean).filter((value, index, all) => all.indexOf(value) === index).join(' • ');
  const when = [event?.date, event?.time].filter(Boolean).join(' at ');
  return [when, location, format].filter(Boolean).join('  •  ') || 'Event details unavailable';
}

function drawEvidenceColumn(ctx: CanvasRenderingContext2D, players: any[], x: number, y: number, width: number, tone: string) {
  const visiblePlayers = players.slice(0, 2);
  visiblePlayers.forEach((player, index) => {
    const cardY = y + index * 226;
    roundedFill(ctx, x, cardY, width, 210, 20, '#101318', `${tone}55`);
    text(ctx, truncate(player.displayName || `Player ${player.playerId}`, 28), x + 22, cardY + 39, 25, 900, '#ffffff');
    text(ctx, `ACL ID ${player.playerId || '—'}`, x + 22, cardY + 67, 13, 750, '#71717a');
    text(ctx, formatNumber(player.predictivePpr), x + width - 22, cardY + 47, 38, 900, tone, 'right');
    text(ctx, 'PROJECTED PPR', x + width - 22, cardY + 70, 12, 800, '#71717a', 'right');
    const metrics = [
      ['DPR', formatNumber(player.calculatedDpr)],
      ['ROUND WIN', formatPercent(player.roundWinRate)],
      ['4-BAG', formatPercent(player.fourBaggerRate)],
      ['BAGS IN', formatPercent(player.bagsInRate)],
      ['ROUNDS', String(player.rounds || 0)],
      ['SAMPLE', `${Math.round(Number(player.predictivePprSampleConfidence || 0) * 100)}%`],
    ];
    metrics.forEach(([label, value], metricIndex) => {
      const column = metricIndex % 3;
      const row = Math.floor(metricIndex / 3);
      const metricX = x + 22 + column * 143;
      const metricY = cardY + 112 + row * 55;
      text(ctx, label, metricX, metricY, 11, 800, '#71717a');
      text(ctx, value, metricX, metricY + 25, 20, 900, '#e4e4e7');
    });
  });
  if (!visiblePlayers.length) {
    roundedFill(ctx, x, y, width, 436, 20, '#101318', `${tone}55`);
    text(ctx, 'Player evidence unavailable', x + width / 2, y + 220, 23, 800, '#71717a', 'center');
  }
}

function formatNumber(value: any) {
  return value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(2);
}

function formatPercent(value: any) {
  return value == null || !Number.isFinite(Number(value)) ? '—' : `${(Number(value) * 100).toFixed(1)}%`;
}

function shortDate(value: any) {
  if (!value) return 'UNAVAILABLE';
  const parsed = new Date(String(value));
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleDateString();
}

function text(
  ctx: CanvasRenderingContext2D,
  value: string,
  x: number,
  y: number,
  size: number,
  weight: number,
  color: string,
  align: CanvasTextAlign = 'left',
  letterSpacing = 0,
) {
  ctx.font = `${weight} ${size}px Arial, sans-serif`;
  ctx.fillStyle = color;
  ctx.textAlign = align;
  if (!letterSpacing) {
    ctx.fillText(value, x, y);
    return;
  }
  const chars = [...value];
  const width = ctx.measureText(value).width + letterSpacing * (chars.length - 1);
  let cursor = align === 'right' ? x - width : align === 'center' ? x - width / 2 : x;
  chars.forEach(char => {
    ctx.fillText(char, cursor, y);
    cursor += ctx.measureText(char).width + letterSpacing;
  });
}

function wrap(ctx: CanvasRenderingContext2D, value: string, size: number, maxWidth: number, maxLines: number) {
  ctx.font = `900 ${size}px Arial, sans-serif`;
  const words = value.split(/\s+/);
  const lines: string[] = [];
  let current = '';
  words.forEach(word => {
    const candidate = current ? `${current} ${word}` : word;
    if (ctx.measureText(candidate).width <= maxWidth || !current) current = candidate;
    else {
      lines.push(current);
      current = word;
    }
  });
  if (current) lines.push(current);
  return lines.slice(0, maxLines);
}

function roundedFill(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number, fill: string, stroke: string) {
  roundedRect(ctx, x, y, width, height, radius);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 2;
  ctx.stroke();
}

function roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  ctx.beginPath();
  ctx.roundRect(x, y, width, height, radius);
}

function canvasBlob(canvas: HTMLCanvasElement) {
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('The snapshot could not be created.')), 'image/png');
  });
}

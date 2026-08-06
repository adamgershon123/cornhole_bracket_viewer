type Props = {
  match: any;
  onClick: () => void;
};

function statusLabel(status?: string) {
  if (status === 'live') return 'LIVE';
  if (status === 'completed') return 'FINAL';
  if (status === 'upcoming') return 'NEXT';
  return 'UNKNOWN';
}

function statusClass(status?: string) {
  if (status === 'live') return 'bg-green-400 text-black';
  if (status === 'completed') return 'bg-blue-400 text-black';
  if (status === 'upcoming') return 'bg-yellow-300 text-black';
  return 'bg-zinc-600 text-white';
}

function roundLabel(match: any) {
  return (
    match.roundDescription ||
    match.rounddesc ||
    match.bracketRoundDescription ||
    (match.round ? `Bracket Round ${match.round}` : 'Bracket Round ?')
  );
}

function getGameScore(match: any, side: 'top' | 'bottom') {
  const game = match?.activeGame || match?.games?.[0];
  return game?.score?.[side] ?? match?.score?.[side] ?? null;
}

function displayScore(score: unknown) {
  return typeof score === 'number' && Number.isFinite(score) ? String(score) : '';
}

export function TournamentMatchCard({ match, onClick }: Props) {
  const top = match?.teams?.top;
  const bottom = match?.teams?.bottom;
  const topScore = getGameScore(match, 'top') ?? top?.score ?? match?.scoreTop;
  const bottomScore = getGameScore(match, 'bottom') ?? bottom?.score ?? match?.scoreBottom;

  return (
    <button
      type="button"
      onClick={onClick}
      className="block w-full rounded-2xl border border-white/10 bg-zinc-900 p-4 text-left shadow-lg active:scale-[0.99]"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="min-w-0 text-sm font-bold text-zinc-400">
          <span>Court {match.courtId || '?'}</span>
          <span className="mx-2 text-zinc-600">•</span>
          <span>{roundLabel(match)}</span>
        </div>

        <div className={`shrink-0 rounded-full px-3 py-1 text-xs font-black ${statusClass(match.status)}`}>
          {statusLabel(match.status)}
        </div>
      </div>

      <TeamRow
        name={top?.name || 'TBD'}
        score={displayScore(topScore)}
      />

      <div className="my-2 h-px bg-white/10" />

      <TeamRow
        name={bottom?.name || 'TBD'}
        score={displayScore(bottomScore)}
      />
    </button>
  );
}

function TeamRow({
  name,
  score,
}: {
  name: string;
  score: number | string;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-4">
      <div className="min-w-0 text-[clamp(1.15rem,5vw,1.65rem)] font-black leading-tight">
        {name}
      </div>

      <div className="min-w-[2.5rem] text-right text-[clamp(2rem,10vw,3.25rem)] font-black leading-none tabular-nums text-white">
        {score}
      </div>
    </div>
  );
}
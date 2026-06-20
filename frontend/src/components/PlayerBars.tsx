type Player = {
  id?: string;
  name: string;

  playerimage?: string;
  playerImage?: string;
  imageUrl?: string;
  profileImage?: string;

  ppr?: number;
  dpr?: number;
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

function trendClass(value?: number | null) {
  if (value === undefined || value === null) return 'text-zinc-400';
  if (value > 0) return 'text-green-400';
  if (value < 0) return 'text-red-400';
  return 'text-zinc-400';
}

function trendIcon(value?: number | null) {
  if (value === undefined || value === null) return '–';
  if (value > 0) return '▲';
  if (value < 0) return '▼';
  return '–';
}

export function PlayerBars({ players }: { players: Player[] }) {
  console.log('PLAYER DATA', players);

  if (!players?.length) {
    return (
      <section className="glass rounded-[28px] p-4">
        <h2 className="text-lg font-black mb-3">Players</h2>
        <div className="text-sm text-zinc-400">
          No player stats available yet.
        </div>
      </section>
    );
  }

  return (
    <section className="glass rounded-[28px] p-4">
      <h2 className="text-lg font-black mb-3">Player Performance</h2>

      <div className="space-y-3">
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

          return (
            <div
              key={player.id || player.name}
              className="rounded-2xl bg-zinc-950/70 border border-white/10 p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  {imageUrl && (
                    <img
                      src={imageUrl}
                      alt={player.name}
                      className="h-14 w-14 shrink-0 rounded-full object-cover border border-white/10 bg-zinc-800"
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                      }}
                    />
                  )}

                  <div className="min-w-0">
                    <div className="font-black text-lg leading-tight truncate">
                      {player.name}
                    </div>

                    <div className="text-xs text-zinc-400">
                      {player.seasonYear
                        ? `vs ${player.seasonYear} season`
                        : 'Season comparison'}
                    </div>
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-xs text-zinc-400">Game PPR</div>
                  <div className="text-2xl font-black">
                    {fmt(player.ppr)}
                  </div>
                </div>
              </div>

              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-xl bg-zinc-900 p-2">
                  <div className="text-[10px] uppercase tracking-wide text-zinc-500">
                    Season PPR
                  </div>
                  <div className="font-black">
                    {fmt(player.seasonPpr)}
                  </div>
                </div>

                <div className="rounded-xl bg-zinc-900 p-2">
                  <div className="text-[10px] uppercase tracking-wide text-zinc-500">
                    vs Season
                  </div>

                  <div className={`font-black ${trendClass(diff)}`}>
                    {trendIcon(diff)} {absDiff}
                  </div>
                </div>

                <div className="rounded-xl bg-zinc-900 p-2">
                  <div className="text-[10px] uppercase tracking-wide text-zinc-500">
                    DPR
                  </div>

                  <div className="font-black">
                    {fmt(player.dpr)}
                  </div>
                </div>
              </div>

              <div className="mt-3 grid grid-cols-4 gap-2 text-center text-xs">
                <div>
                  <div className="text-zinc-500">Win</div>
                  <div className="font-bold text-green-400">
                    {fmt(player.roundWinPct, 1)}%
                  </div>
                </div>

                <div>
                  <div className="text-zinc-500">Tie</div>
                  <div className="font-bold text-yellow-300">
                    {fmt(player.roundTiePct, 1)}%
                  </div>
                </div>

                <div>
                  <div className="text-zinc-500">Loss</div>
                  <div className="font-bold text-red-400">
                    {fmt(player.roundLossPct, 1)}%
                  </div>
                </div>

                <div>
                  <div className="text-zinc-500">4B</div>
                  <div className="font-bold">
                    {fmt(player.fourBaggerPct, 1)}%
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
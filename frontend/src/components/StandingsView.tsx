type Props = {
  standingsData: any;
};

function ordinal(n: number) {
  if (!n) return '-';
  if (n === 1) return '1st';
  if (n === 2) return '2nd';
  if (n === 3) return '3rd';
  return `${n}th`;
}

export default function StandingsView({ standingsData }: Props) {
  if (!standingsData) {
    return (
      <section className="glass rounded-[28px] p-4">
        <div className="text-zinc-400">No standings loaded yet.</div>
      </section>
    );
  }

  const standings = standingsData.standings || [];
  const season = standingsData.season || {};

  return (
    <section className="space-y-4">
      <section className="glass rounded-[28px] p-4">
        <div className="text-xs uppercase tracking-[.2em] text-amber-300">
          Season Standings
        </div>

        <h2 className="mt-1 text-2xl font-black">
          {season.locationName || 'Location'}
        </h2>

        <div className="mt-2 text-sm text-zinc-400">
          {season.startDate} → {season.endDate}
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="rounded-2xl bg-zinc-900 p-3">
            <div className="text-2xl font-black">
              {season.includedEventCount || 0}
            </div>
            <div className="text-xs text-zinc-400">Events</div>
          </div>

          <div className="rounded-2xl bg-zinc-900 p-3">
            <div className="text-2xl font-black">
              {standings.length}
            </div>
            <div className="text-xs text-zinc-400">Players</div>
          </div>
        </div>
      </section>

      {standings.length === 0 && (
        <section className="glass rounded-[28px] p-4">
          <div className="text-zinc-400">
            No standings found for this date range.
          </div>
        </section>
      )}

      {standings.map((player: any, index: number) => (
        <section
          key={player.playerId}
          className="glass rounded-[28px] p-4"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-sm text-amber-300 font-black">
                #{index + 1}
              </div>

              <div className="mt-1 text-[clamp(22px,6vw,34px)] leading-tight font-black">
                {player.name}
              </div>

              <div className="mt-2 text-sm text-zinc-400">
                {player.eventsPlayed} events · Best finish {ordinal(player.bestFinish)}
              </div>
            </div>

            <div className="text-right shrink-0">
              <div className="text-[clamp(30px,8vw,44px)] leading-none font-black">
                {player.totalPoints}
              </div>
              <div className="text-xs text-zinc-400">points</div>
            </div>
          </div>

          <div className="mt-4 flex gap-2 flex-wrap">
            {(player.placements || []).map((place: number, i: number) => (
              <div
                key={i}
                className="rounded-full bg-zinc-900 px-3 py-2 text-sm font-black"
              >
                {ordinal(place)}
              </div>
            ))}
          </div>
        </section>
      ))}
    </section>
  );
}
type Props = {
  standingsData: any
}

export default function StandingsView({ standingsData }: Props) {
  const standings = standingsData?.standings || []

  return (
    <div className="space-y-4">

      <section className="glass rounded-[28px] p-4">
        <h1 className="text-2xl font-black">
          {standingsData?.season?.locationName}
        </h1>

        <div className="text-sm opacity-70">
          {standingsData?.season?.startDate}
          {" → "}
          {standingsData?.season?.endDate}
        </div>

        <div className="mt-2">
          {standingsData?.season?.includedEventCount} Events • {standings.length} Players
        </div>
      </section>

      {standings.map((player: any, idx: number) => (
        <div
          key={player.playerId}
          className="glass rounded-[28px] p-4"
        >
          <div className="flex justify-between items-center">
            <div>
              <div className="text-xs opacity-60">
                Rank #{idx + 1}
              </div>

              <div className="text-xl font-black">
                {player.name}
              </div>
            </div>

            <div className="text-right">
              <div className="text-3xl font-black">
                {player.totalPoints}
              </div>

              <div className="text-xs opacity-60">
                Points
              </div>
            </div>
          </div>

          <div className="mt-3 flex gap-2 flex-wrap">

            <span className="px-3 py-1 rounded-full bg-zinc-800">
              {player.eventsPlayed} Events
            </span>

            <span className="px-3 py-1 rounded-full bg-zinc-800">
              Best Finish: {player.bestFinish}
            </span>

          </div>

          <div className="mt-4 flex gap-2">
            {player.placements.map((p: number, i: number) => (
              <div
                key={i}
                className="w-10 h-10 rounded-full bg-zinc-800 flex items-center justify-center font-bold"
              >
                {p}
              </div>
            ))}
          </div>

        </div>
      ))}
    </div>
  )
}
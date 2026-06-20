import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

type MatchStatus = "LIVE" | "COMPLETE" | "NOT_STARTED";

export default function TournamentPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();

  const [eventData, setEventData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  async function loadTournament() {
    if (!eventId) return;

    setLoading(true);

    try {
      const data = await fetchEvent(eventId, true);
		setEventData(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTournament();

    const timer = window.setInterval(loadTournament, 30000);
    return () => window.clearInterval(timer);
  }, [eventId]);

  const matches = useMemo(() => {
    return eventData?.matches ?? eventData?.data?.matches ?? [];
  }, [eventData]);

  const liveMatches = matches.filter((m: any) => getMatchStatus(m) === "LIVE");
  const completedMatches = matches.filter((m: any) => getMatchStatus(m) === "COMPLETE");
  const onDeckMatches = matches.filter((m: any) => getMatchStatus(m) === "NOT_STARTED");

  if (loading && !eventData) {
    return <div className="min-h-screen bg-slate-950 text-white p-4">Loading tournament...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white pb-24">
      <div className="p-4 space-y-4">
        <EventHeader eventData={eventData} />

        <EventStats
          live={liveMatches.length}
          onDeck={onDeckMatches.length}
          completed={completedMatches.length}
          totalTeams={eventData?.teamCount ?? eventData?.teams?.length ?? "—"}
        />

        <ViewTabs />

        <MyTeamCard
          matches={matches}
          eventId={eventId!}
          onOpenMatch={(matchId) => navigate(`/game/${eventId}/${matchId}`)}
        />

        <MatchSection
          title="LIVE NOW"
          matches={liveMatches}
          eventId={eventId!}
          onOpenMatch={(matchId) => navigate(`/game/${eventId}/${matchId}`)}
        />

        <MatchSection
          title="ON DECK"
          matches={onDeckMatches}
          eventId={eventId!}
          onOpenMatch={(matchId) => navigate(`/game/${eventId}/${matchId}`)}
        />
      </div>
    </div>
  );
}

function getMatchStatus(match: any): MatchStatus {
  const status = String(match.status ?? match.matchStatus ?? "").toUpperCase();

  if (status.includes("COMPLETE") || match.isComplete || match.completed) {
    return "COMPLETE";
  }

  const score1 = Number(match.score1 ?? match.team1Score ?? match.homeScore ?? 0);
  const score2 = Number(match.score2 ?? match.team2Score ?? match.awayScore ?? 0);

  if (
    status.includes("LIVE") ||
    status.includes("ACTIVE") ||
    score1 > 0 ||
    score2 > 0
  ) {
    return "LIVE";
  }

  return "NOT_STARTED";
}

function getMatchId(match: any) {
  return match.matchId ?? match.id ?? match.matchNumber ?? match.gameId;
}

function getCourt(match: any) {
  return match.court ?? match.courtNumber ?? match.courtName ?? "TBD";
}

function getTeam1Name(match: any) {
  return (
    match.team1Name ??
    match.homeTeamName ??
    match.team1?.name ??
    match.teams?.[0]?.name ??
    "TBD"
  );
}

function getTeam2Name(match: any) {
  return (
    match.team2Name ??
    match.awayTeamName ??
    match.team2?.name ??
    match.teams?.[1]?.name ??
    "TBD"
  );
}

function getScore1(match: any) {
  return Number(match.score1 ?? match.team1Score ?? match.homeScore ?? 0);
}

function getScore2(match: any) {
  return Number(match.score2 ?? match.team2Score ?? match.awayScore ?? 0);
}

function EventHeader({ eventData }: { eventData: any }) {
  return (
    <div>
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-bold">
            {eventData?.eventName ?? eventData?.name ?? "Tournament"}
          </h1>
          <div className="text-sm text-slate-300">
            {eventData?.divisionName ?? eventData?.bracketType ?? "Open Doubles"}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {eventData?.date ?? eventData?.eventDate ?? ""}{" "}
            {eventData?.location ? `• ${eventData.location}` : ""}
          </div>
        </div>

        <div className="text-yellow-400 text-2xl">★</div>
      </div>
    </div>
  );
}

function EventStats({
  live,
  onDeck,
  completed,
  totalTeams,
}: {
  live: number;
  onDeck: number;
  completed: number;
  totalTeams: number | string;
}) {
  return (
    <div className="grid grid-cols-4 gap-2">
      <StatCard value={live} label="LIVE" color="text-green-400" />
      <StatCard value={onDeck} label="ON DECK" color="text-yellow-400" />
      <StatCard value={completed} label="COMPLETED" color="text-blue-300" />
      <StatCard value={totalTeams} label="TOTAL TEAMS" color="text-white" />
    </div>
  );
}

function StatCard({ value, label, color }: { value: any; label: string; color: string }) {
  return (
    <div className="rounded-lg bg-slate-900 border border-slate-800 p-3 text-center">
      <div className={`text-xl font-bold ${color}`}>{value}</div>
      <div className="text-[10px] text-slate-400 mt-1">{label}</div>
    </div>
  );
}

function ViewTabs() {
  return (
    <div className="grid grid-cols-4 rounded-lg bg-slate-900 border border-slate-800 overflow-hidden">
      <button className="py-3 text-sm font-semibold text-green-400 border-b-2 border-green-400">
        Snapshot
      </button>
      <button className="py-3 text-sm text-slate-300">Bracket</button>
      <button className="py-3 text-sm text-slate-300">Matches</button>
      <button className="py-3 text-sm text-slate-300">Players</button>
    </div>
  );
}

function MatchSection({
  title,
  matches,
  onOpenMatch,
}: {
  title: string;
  matches: any[];
  eventId: string;
  onOpenMatch: (matchId: string | number) => void;
}) {
  if (!matches.length) return null;

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-300">{title}</h2>
        <button className="text-xs text-blue-300">View All</button>
      </div>

<div className="space-y-2">
  {matches.map((match) => (
    <MatchCard
      key={getMatchId(match)}
      match={match}
      onClick={() => onOpenMatch(getMatchId(match))}
    />
  ))}
</div>
    </section>
  );
}

function MatchCard({ match, onClick }: { match: any; onClick: () => void }) {
  const status = getMatchStatus(match);
  const matchId = getMatchId(match);

  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-lg bg-slate-900 border border-slate-800 p-3"
    >
      <div className="flex items-center gap-2 text-xs text-slate-400 mb-2">
        <StatusPill status={status} />
        <span>M{matchId}</span>
        <span>•</span>
        <span>Court {getCourt(match)}</span>
        <span>•</span>
        <span>{match.roundName ?? match.bracketSide ?? "Bracket"}</span>
      </div>

      <div className="grid grid-cols-[1fr_auto] gap-3 items-center">
        <div className={status === "LIVE" ? "text-green-400 font-semibold" : "text-white"}>
          {getTeam1Name(match)}
        </div>
        <div className="text-xl font-bold">{getScore1(match) || ""}</div>

        <div className="text-white">{getTeam2Name(match)}</div>
        <div className="text-xl font-bold">{getScore2(match) || ""}</div>
      </div>
    </button>
  );
}

function StatusPill({ status }: { status: MatchStatus }) {
  if (status === "LIVE") {
    return <span className="text-red-400 font-bold">● LIVE</span>;
  }

  if (status === "COMPLETE") {
    return <span className="text-green-400 font-bold">✓ COMPLETE</span>;
  }

  return <span className="text-yellow-400 font-bold">● ON DECK</span>;
}

function MyTeamCard({
  matches,
  onOpenMatch,
}: {
  matches: any[];
  eventId: string;
  onOpenMatch: (matchId: string | number) => void;
}) {
  const favoritePlayerId =
    localStorage.getItem("defaultPlayerId") ??
    localStorage.getItem("favoritePlayerId") ??
    "142125";

  const myMatch = matches.find((match) =>
    JSON.stringify(match).includes(String(favoritePlayerId))
  );

  if (!myMatch) {
    return (
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-300">MY TEAM</h2>
        </div>

        <div className="rounded-lg bg-slate-900 border border-slate-800 p-4 text-sm text-slate-300">
          No active match found for your selected player.
        </div>
      </section>
    );
  }

  const status = getMatchStatus(myMatch);

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-300">MY TEAM</h2>
        <button className="text-xs text-blue-300">Edit</button>
      </div>

      <div className="rounded-xl bg-slate-900 border border-slate-800 overflow-hidden">
        <div className="p-4 border-b border-slate-800">
          <div className="flex justify-between gap-3">
            <div>
              <div className="font-bold text-white">{getTeam1Name(myMatch)}</div>
              <div className="text-sm text-slate-300">
                Status: <span className="text-green-400 font-bold">{status}</span>
              </div>
              <div className="text-xs text-slate-400">
                {myMatch.bracketSide ?? "Bracket"} • Match {getMatchId(myMatch)}
              </div>
            </div>

            <div className="text-yellow-400 text-xl">★</div>
          </div>
        </div>

        <div className="p-4 space-y-3">
          <div className="flex justify-between text-xs text-slate-300">
            <StatusPill status={status} />
            <span>Court {getCourt(myMatch)}</span>
          </div>

          <div className="grid grid-cols-[1fr_auto] gap-3 items-center">
            <div className="text-green-400 font-bold">{getTeam1Name(myMatch)}</div>
            <div className="text-2xl font-bold text-green-400">{getScore1(myMatch)}</div>

            <div>{getTeam2Name(myMatch)}</div>
            <div className="text-2xl font-bold">{getScore2(myMatch)}</div>
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-950/60 p-3 space-y-3">
            <div className="font-bold text-sm">🏆 Path to Finals: Calculating</div>

            <div>
              <div className="text-green-400 text-xs font-bold mb-1">IF WIN:</div>
              <div className="text-sm">→ Winner destination TBD</div>
              <div className="text-sm">→ Next opponent TBD</div>
            </div>

            <div>
              <div className="text-red-400 text-xs font-bold mb-1">IF LOSE:</div>
              <div className="text-sm">↓ Loser destination TBD</div>
              <div className="text-sm">↓ Next opponent TBD</div>
            </div>
          </div>

          <button
            onClick={() => onOpenMatch(getMatchId(myMatch))}
            className="w-full rounded-lg border border-green-500 py-3 text-green-400 font-semibold"
          >
            View Match Analytics ›
          </button>
        </div>
      </div>
    </section>
  );
}


import type { RoundRow } from '../lib/api';

type Props = {
  rounds: RoundRow[];
  topTeamName?: string;
  bottomTeamName?: string;
  topTeamId?: string;
  bottomTeamId?: string;
};

const TEAM_1_CARD = 'border-blue-400/90 bg-blue-400/10';
const TEAM_2_CARD = 'border-red-400/90 bg-red-400/10';
const WASH_CARD = 'border-yellow-300/90 bg-yellow-300/10';

const TEAM_1_TEXT = 'text-blue-400';
const TEAM_2_TEXT = 'text-red-400';
const WASH_TEXT = 'text-yellow-300';

const THROWER_PAIR_A_TEXT = 'text-green-400';
const THROWER_PAIR_B_TEXT = 'text-orange-400';

export function RoundTimeline({
  rounds,
  topTeamName,
  bottomTeamName,
  topTeamId,
  bottomTeamId,
}: Props) {
  const team1Name = topTeamName || 'Team 1';
  const team2Name = bottomTeamName || 'Team 2';

  const playerPairs = getPlayerPairsFromRounds(rounds);

  const pairA = {
    team1: playerPairs.pairA.team1 || 'Team 1 Player A',
    team2: playerPairs.pairA.team2 || 'Team 2 Player A',
  };

  const pairB = {
    team1: playerPairs.pairB.team1 || 'Team 1 Player B',
    team2: playerPairs.pairB.team2 || 'Team 2 Player B',
  };

  return (
    <section className="glass rounded-[28px] p-4 overflow-hidden">
      <h2 className="text-lg font-black mb-4">Round by Round</h2>

      <div className="mb-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="rounded-2xl border border-blue-400/80 bg-blue-400/10 p-4">
          <div className="text-xs font-black uppercase tracking-[0.25em] text-blue-400">
            Team 1
          </div>
          <div className="mt-1 text-xl font-black leading-tight text-white">
            {team1Name}
          </div>
        </div>

        <div className="rounded-2xl border border-red-400/80 bg-red-400/10 p-4">
          <div className="text-xs font-black uppercase tracking-[0.25em] text-red-400">
            Team 2
          </div>
          <div className="mt-1 text-xl font-black leading-tight text-white">
            {team2Name}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-[minmax(90px,0.8fr)_minmax(0,3fr)_minmax(90px,0.8fr)] gap-3 items-start">
		<ThrowerPanel
		  title="Odd Rounds"
		  color="green"
		  team1Player={pairA.team1}
		  team2Player={pairA.team2}
		/>

        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2">
          {rounds.map((r) => {
            const isWash = !r.netPoints || Number(r.netPoints) === 0;

            const winningTeam = isWash
              ? 'wash'
              : r.scoringTeamId === topTeamId
                ? 'team1'
                : r.scoringTeamId === bottomTeamId
                  ? 'team2'
                  : inferWinningTeamFromScores(r);

            const roundCardClass =
              winningTeam === 'team1'
                ? TEAM_1_CARD
                : winningTeam === 'team2'
                  ? TEAM_2_CARD
                  : WASH_CARD;

            const pointsTextClass =
              winningTeam === 'team1'
                ? TEAM_1_TEXT
                : winningTeam === 'team2'
                  ? TEAM_2_TEXT
                  : WASH_TEXT;

            const throwerPair = getThrowerPair(r);
            const scoreClass =
              throwerPair === 'A' ? THROWER_PAIR_A_TEXT : THROWER_PAIR_B_TEXT;

            const scores = getRoundScores(r);

            return (
              <div
                key={r.round}
                className={`rounded-2xl border ${roundCardClass} px-2 py-3 text-center min-w-0`}
              >
                <div className="text-xs font-bold text-zinc-400">
                  R{r.round}
                </div>

                <div
                  className={`mt-1 font-black leading-none ${pointsTextClass} ${
                    isWash ? 'text-[3rem]' : 'text-[3.25rem]'
                  }`}
                >
                  {isWash ? (
                    <span className="inline-block scale-x-75">W</span>
                  ) : (
                    r.netPoints
                  )}
                </div>

                <div className="my-2 h-px bg-white/15" />

                <div className={`text-[1.75rem] font-black leading-none ${scoreClass}`}>
                  {scores.top}
                </div>

                <div className="text-[0.9rem] font-black leading-none text-zinc-500">
                  –
                </div>

                <div className={`text-[1.75rem] font-black leading-none ${scoreClass}`}>
                  {scores.bottom}
                </div>
              </div>
            );
          })}
        </div>

        <ThrowerPanel
		  title="Even Rounds"
		  color="orange"
		  team1Player={pairB.team1}
		  team2Player={pairB.team2}
		/>
      </div>

      <div className="mt-4 text-xs font-bold text-zinc-500">
	  Border color = round winner. Yellow = wash. Green scores = odd rounds. Orange scores = even rounds.
	</div>
    </section>
  );
}

function ThrowerPanel({
  title,
  color,
  team1Player,
  team2Player,
}: {
  title: string;
  color: 'green' | 'orange';
  team1Player: string;
  team2Player: string;
}) {
  const border =
    color === 'green'
      ? 'border-green-400/80 bg-green-400/10'
      : 'border-orange-400/80 bg-orange-400/10';

  const text =
    color === 'green'
      ? 'text-green-400'
      : 'text-orange-400';

  return (
    <div className={`sticky top-3 rounded-2xl border ${border} p-3`}>
      <div className={`text-xs font-black uppercase tracking-[0.2em] ${text}`}>
        {title}
      </div>

      <div className="mt-3 space-y-3">
        <div>
          <div className="text-[10px] font-black uppercase tracking-widest text-blue-400">
            Team 1
          </div>
          <div className="text-sm font-black leading-tight text-white">
            {team1Player}
          </div>
        </div>

        <div>
          <div className="text-[10px] font-black uppercase tracking-widest text-red-400">
            Team 2
          </div>
          <div className="text-sm font-black leading-tight text-white">
            {team2Player}
          </div>
        </div>
      </div>
    </div>
  );
}

function getRoundScores(round: any) {
  const players = round.players || [];

  return {
    top: players[0]?.grossPoints ?? '-',
    bottom: players[1]?.grossPoints ?? '-',
  };
}

function getThrowerPair(round: any): 'A' | 'B' {
  return Number(round.round || 1) % 2 === 1 ? 'A' : 'B';
}

function inferWinningTeamFromScores(round: any): 'team1' | 'team2' | 'wash' {
  const scores = getRoundScores(round);
  const top = Number(scores.top);
  const bottom = Number(scores.bottom);

  if (!Number.isFinite(top) || !Number.isFinite(bottom)) return 'wash';
  if (top === bottom) return 'wash';

  return top > bottom ? 'team1' : 'team2';
}

function getPlayerPairsFromRounds(rounds: RoundRow[]) {
  const pairA = { team1: '', team2: '' };
  const pairB = { team1: '', team2: '' };

  rounds.forEach((round: any) => {
    const pair = getThrowerPair(round);
    const players = round.players || [];

    const team1Player =
      players[0]?.name ||
      players[0]?.playerName ||
      players[0]?.shortName ||
      '';

    const team2Player =
      players[1]?.name ||
      players[1]?.playerName ||
      players[1]?.shortName ||
      '';

    if (pair === 'A') {
      if (!pairA.team1 && team1Player) pairA.team1 = team1Player;
      if (!pairA.team2 && team2Player) pairA.team2 = team2Player;
    }

    if (pair === 'B') {
      if (!pairB.team1 && team1Player) pairB.team1 = team1Player;
      if (!pairB.team2 && team2Player) pairB.team2 = team2Player;
    }
  });

  return { pairA, pairB };
}
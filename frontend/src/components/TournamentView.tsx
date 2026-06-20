import { Match } from '../lib/api';
import { TournamentMatchCard } from './TournamentMatchCard';

type Props = {
  data: any;
  matches: (Match & any)[];
  onOpenMatch: (matchId: string) => void;
};

export function TournamentView({ data, matches, onOpenMatch }: Props) {
  const live = matches.filter(m => m.status === 'live');
  const completed = matches.filter(m => m.status === 'completed');
  const upcoming = matches.filter(m => m.status === 'upcoming');

  return (
    <section className="mt-4 space-y-5">
      <section className="rounded-[32px] border border-white/10 bg-zinc-950 p-5 shadow-xl">
        <div className="text-xs uppercase tracking-[0.24em] text-amber-300">
          Tournament
        </div>

        <h2 className="mt-1 text-[clamp(1.6rem,5vw,3rem)] font-black leading-none">
          {data?.event?.name || 'Current Event'}
        </h2>

        <div className="mt-3 text-base text-zinc-300">
          {data?.event?.date || 'Date TBD'} · {data?.event?.venue || data?.event?.location?.name || 'Venue TBD'}
        </div>

        <div className="mt-5 grid grid-cols-3 gap-3">
          <SummaryStat label="Live" value={live.length} tone="text-green-400" />
          <SummaryStat label="Done" value={completed.length} tone="text-blue-300" />
          <SummaryStat label="Next" value={upcoming.length} tone="text-yellow-300" />
        </div>
      </section>

      {live.length > 0 && (
        <MatchSection title="Live Matches" matches={live} onOpenMatch={onOpenMatch} />
      )}

      {upcoming.length > 0 && (
        <MatchSection title="Upcoming Matches" matches={upcoming} onOpenMatch={onOpenMatch} />
      )}

      {completed.length > 0 && (
        <MatchSection title="Completed Matches" matches={completed} onOpenMatch={onOpenMatch} />
      )}
    </section>
  );
}

function SummaryStat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-zinc-900 p-4 text-center">
      <div className={`text-[clamp(2rem,9vw,4rem)] font-black leading-none ${tone}`}>
        {value}
      </div>
      <div className="mt-1 text-xs font-bold uppercase tracking-widest text-zinc-400">
        {label}
      </div>
    </div>
  );
}

function MatchSection({ title, matches, onOpenMatch }: any) {
  return (
    <section>
      <h3 className="mb-3 px-1 text-xl font-black">{title}</h3>

      <div className="space-y-3">
        {matches.map((match: any) => {
          const matchId = match.id || match.matchId;

          return (
            <TournamentMatchCard
              key={matchId}
              match={match}
              onClick={() => onOpenMatch(matchId)}
            />
          );
        })}
      </div>
    </section>
  );
}
import { Activity, Database, ShieldCheck, Target } from 'lucide-react';
import { useEffect, useState } from 'react';
import { fetchPredictivePlayerProfile } from '../lib/api';

const percent = (value:any) => value == null ? '—' : `${(Number(value) * 100).toFixed(1)}%`;
const number = (value:any) => value == null ? '—' : Number(value).toFixed(2);

export default function PredictivePlayerProfileView({ playerId }: { playerId:string }) {
  const [data, setData] = useState<any>();
  const [error, setError] = useState('');
  const [photoFailed, setPhotoFailed] = useState(false);
  useEffect(() => {
    setError('');
    fetchPredictivePlayerProfile(playerId).then(setData).catch(error => setError(error.message));
  }, [playerId]);
  if (error) return <div className="mt-4 rounded-2xl border border-red-400/30 bg-red-950/30 p-5 text-red-200">{error}</div>;
  if (!data) return <div className="mt-4 rounded-2xl border border-white/10 bg-zinc-950 p-8 text-zinc-400">Loading predictive profile…</div>;
  const player = data.player || {};
  const cpi = data.officialAcl?.cpi;
  const aclPpr = data.officialAcl?.ppr;
  const calculated = data.calculated || {};
  const rolling = data.rollingPpr || {};
  const rollingWindows = rolling.windows || {};
  const expected = rolling.expectedPerformance || {};
  const photo = String(player.profile_image || '').trim();
  const initials = String(player.display_name || `Player ${playerId}`).split(/\s+/).filter(Boolean).slice(0, 2).map((value:string) => value[0]).join('').toUpperCase();
  return (
    <section className="mt-4 space-y-4">
      <div className="rounded-[24px] border border-white/10 bg-zinc-950 p-4 sm:rounded-[30px] sm:p-6">
        <div className="flex items-center gap-3 sm:gap-5">
          {photo && !photoFailed
            ? <img src={photo} alt={`${player.display_name || `Player ${playerId}`} profile`} onError={() => setPhotoFailed(true)} className="h-16 w-16 shrink-0 rounded-full border-2 border-amber-300/60 bg-zinc-900 object-cover shadow-[0_0_30px_rgba(252,211,77,.12)] sm:h-24 sm:w-24" />
            : <div className="grid h-16 w-16 shrink-0 place-items-center rounded-full border-2 border-white/15 bg-zinc-900 text-lg font-black text-amber-300 sm:h-24 sm:w-24 sm:text-2xl">{initials}</div>}
          <div className="min-w-0">
            <div className="text-xs font-black uppercase tracking-[.24em] text-amber-300">Predictive Player Profile</div>
            <h2 className="mt-1 text-2xl font-black leading-tight text-white sm:mt-2 sm:text-4xl">{player.display_name || `Player ${playerId}`}</h2>
            <div className="mt-1 break-words text-xs leading-5 text-zinc-500 sm:mt-2 sm:text-sm">Player {playerId} · Model cutoff {data.dataCutoffAt}</div>
          </div>
        </div>
        <div className="mt-3 text-xs font-bold text-zinc-500">
          Saved profile {data.snapshot?.generatedAt
            ? `from ${new Date(data.snapshot.generatedAt).toLocaleString()}`
            : 'loaded'}
          {data.snapshot?.refreshingAdvancedRatings && (
            <span className="ml-2 text-sky-300">
              · Advanced ratings are refreshing in the background
            </span>
          )}
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel icon={<ShieldCheck />} title="Official ACL values">
          <ProfileMetric label="CPI" value={cpi ? number(cpi.value) : 'Unavailable'} detail={source(cpi)} />
          <ProfileMetric label="ACL PPR" value={aclPpr ? number(aclPpr.value) : 'Unavailable'} detail={source(aclPpr)} />
        </Panel>
        <Panel icon={<Activity />} title="Calculated performance">
          <div className="grid grid-cols-2 gap-2">
            <ProfileMetric label="PPR" value={number(calculated.calculatedPpr)} />
            <ProfileMetric label="DPR" value={number(calculated.calculatedDpr)} />
            <ProfileMetric label="Opponent PPR" value={number(calculated.calculatedOpponentPpr)} />
            <ProfileMetric label="Round win rate" value={percent(calculated.roundWinRate)} />
            <ProfileMetric label="Four-bagger rate" value={percent(calculated.fourBaggerRate)} />
            <ProfileMetric label="Bags in" value={percent(calculated.bagsInRate)} />
          </div>
        </Panel>
      </div>
      <Panel icon={<Target />} title="Expected Performance & Rolling PPR">
        <div className="grid gap-3 lg:grid-cols-[220px_1fr]">
          <div className="rounded-2xl border border-sky-300/20 bg-sky-300/10 p-5 text-center">
            <div className="text-[10px] font-black uppercase tracking-[.18em] text-sky-200">Expected PPR</div>
            <div className="mt-2 text-5xl font-black text-sky-300">{number(expected.expectedPpr)}</div>
            <div className="mt-2 text-xs text-zinc-400">Validated season baseline</div>
            <div className="mt-1 text-[10px] text-zinc-500">Internal projection, not official ACL PPR</div>
          </div>
          <div className="grid grid-cols-1 gap-2 min-[430px]:grid-cols-2 md:grid-cols-5">
            <RollingMetric label="Season" value={rollingWindows.season} />
            <RollingMetric label="90 days" value={rollingWindows.last90Days} />
            <RollingMetric label="30 days" value={rollingWindows.last30Days} />
            <RollingMetric label="7 days" value={rollingWindows.last7Days} />
            <RollingMetric label="Last 100 rounds" value={rollingWindows.last100Rounds} />
          </div>
        </div>
        <div className="mt-3 rounded-xl bg-white/[.04] p-3 text-xs leading-5 text-zinc-400">
          Expected PPR currently uses season PPR from {rollingWindows.season?.rounds ?? 0} recorded rounds.
          In chronological testing it forecast future game PPR better than the 90-day, 30-day, seven-day, last-100-round, and population-shrunk candidates.
        </div>
      </Panel>
      <SectionHeading
        eyebrow="Player ratings"
        title="How this player performs"
        detail="Descriptive ratings calculated from the player's recorded match history."
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel icon={<Activity />} title="Current Form">
          <RatingHero value={data.ratings?.currentFormRating} label={data.ratings?.currentFormLabel} />
          <div className="mt-3 grid grid-cols-3 gap-2">
            <ProfileMetric label="Recent PPR" value={number(data.ratings?.recentPpr)} />
            <ProfileMetric label="Baseline PPR" value={number(data.ratings?.baselinePpr)} />
            <ProfileMetric label="Sample confidence" value={percent(data.ratings?.formReliability)} />
          </div>
          <p className="mt-3 text-xs text-zinc-500">Last 100 available rounds within 365 days, compared with the longer baseline using PPR, DPR and round-win movement. This window performed best in chronological validation.</p>
        </Panel>
        <Panel icon={<Database />} title="Consistency">
          <RatingHero value={data.ratings?.consistencyRating} label={data.ratings?.consistencyLabel} />
          <div className="mt-3 grid grid-cols-2 gap-2">
            <ProfileMetric label="Round variation" value={number(data.ratings?.roundPprStdDev)} />
            <ProfileMetric label="Sample confidence" value={percent(data.ratings?.consistencyReliability)} />
          </div>
          <p className="mt-3 text-xs text-zinc-500">League-relative stability of round scoring. Lower variation ranks higher; sample reliability is retained.</p>
        </Panel>
      </div>
      <Panel icon={<Target />} title="Clutch Rating">
        <div className="grid gap-3 sm:grid-cols-[180px_1fr]">
          <div className="rounded-2xl border border-amber-300/20 bg-amber-300/10 p-5 text-center">
            <div className="text-5xl font-black text-amber-300">{data.clutch?.clutchRating ?? '—'}</div>
            <div className="mt-1 font-black text-white">{data.clutch?.label}</div>
            {data.clutch?.percentile != null && <div className="mt-1 text-xs text-zinc-500">{data.clutch.percentile}th percentile</div>}
          </div>
          <div className="grid grid-cols-1 gap-2 min-[430px]:grid-cols-2 md:grid-cols-4">
            <ProfileMetric label="Opportunities" value={data.clutch?.opportunities ?? 0} />
            <ProfileMetric label="Adjusted net/rnd" value={number(data.clutch?.adjustedNetPerRound)} />
            <ProfileMetric label="Vs baseline" value={number(data.clutch?.performanceVsBaseline)} />
            <ProfileMetric label="Sample confidence" value={percent(data.clutch?.reliability)} />
          </div>
        </div>
        <p className="mt-3 text-xs text-zinc-500">Cheesebaggers calculated rating for rounds beginning at 15+ with a margin of five or fewer. First-throw adjusted and shrunk for sample reliability; not an official ACL statistic.</p>
      </Panel>
      <Panel icon={<Activity />} title="Carry Performance">
        <div className="grid gap-3 sm:grid-cols-[180px_1fr]">
          <div className="rounded-2xl border border-violet-300/20 bg-violet-300/10 p-5 text-center">
            <div className="text-5xl font-black text-violet-300">{data.carryPerformance?.carryRating ?? '—'}</div>
            <div className="mt-1 font-black text-white">{data.carryPerformance?.label}</div>
            {data.carryPerformance?.percentile != null && <div className="mt-1 text-xs text-zinc-500">{data.carryPerformance.percentile}th percentile</div>}
            {data.carryPerformance?.ratedPlayers != null && <div className="mt-1 text-[10px] text-zinc-600">Among {data.carryPerformance.ratedPlayers} qualified players</div>}
          </div>
          <div className="grid grid-cols-1 gap-2 min-[430px]:grid-cols-2 md:grid-cols-5">
            <ProfileMetric label="Carry games" value={data.carryPerformance?.opportunities ?? 0} />
            <ProfileMetric label="PPR vs expected" value={number(data.carryPerformance?.weightedOutperformance)} />
            <ProfileMetric label="Deficits covered" value={percent(data.carryPerformance?.deficitCoverageRate)} />
            <ProfileMetric label="Average burden" value={number(data.carryPerformance?.averageCarryBurden)} />
            <ProfileMetric label="Sample confidence" value={percent(data.carryPerformance?.reliability)} />
          </div>
        </div>
        <p className="mt-3 text-xs leading-5 text-zinc-500">
          Rewards games where pregame history identified this player as the stronger partner and the player exceeded Expected PPR or covered the partner deficit.
          A carry opportunity requires at least a 0.50 Expected PPR partner gap. This is a Cheesebaggers rating, not an ACL statistic.
        </p>
      </Panel>
      <Panel icon={<ShieldCheck />} title="Strength of Competition">
        <div className="grid gap-3 sm:grid-cols-[180px_1fr]">
          <div className="rounded-2xl border border-emerald-300/20 bg-emerald-300/10 p-5 text-center">
            <div className="text-5xl font-black text-emerald-300">{data.strengthOfCompetition?.strengthOfCompetitionRating ?? '—'}</div>
            <div className="mt-1 font-black text-white">{data.strengthOfCompetition?.label}</div>
            {data.strengthOfCompetition?.percentile != null && <div className="mt-1 text-xs text-zinc-500">{data.strengthOfCompetition.percentile}th percentile</div>}
            {data.strengthOfCompetition?.ratedPlayers != null && <div className="mt-1 text-[10px] text-zinc-600">Among {data.strengthOfCompetition.ratedPlayers} qualified players</div>}
          </div>
          <div className="grid grid-cols-1 gap-2 min-[430px]:grid-cols-2 md:grid-cols-5">
            <ProfileMetric label="Opponent Expected PPR" value={number(data.strengthOfCompetition?.averageOpponentExpectedPpr)} />
            <ProfileMetric label="Games measured" value={data.strengthOfCompetition?.games ?? 0} />
            <ProfileMetric label="Above-average opponents" value={percent(data.strengthOfCompetition?.aboveAverageOpponentRate)} />
            <ProfileMetric label="Strong opponents" value={percent(data.strengthOfCompetition?.strongOpponentRate)} />
            <ProfileMetric label="Sample confidence" value={percent(data.strengthOfCompetition?.sampleConfidence)} />
          </div>
        </div>
        <p className="mt-3 text-xs leading-5 text-zinc-500">
          Measures the opponents this player actually faced using each opponent's Expected PPR as it existed before that game.
          Later results are never used to make earlier opponents look stronger or weaker.
        </p>
      </Panel>
      <Panel icon={<Target />} title="Opponent-Adjusted Performance">
        <div className="grid gap-3 sm:grid-cols-[180px_1fr]">
          <div className="rounded-2xl border border-orange-300/20 bg-orange-300/10 p-5 text-center">
            <div className="text-5xl font-black text-orange-300">{data.opponentAdjustedPerformance?.opponentAdjustedRating ?? '—'}</div>
            <div className="mt-1 font-black text-white">{data.opponentAdjustedPerformance?.label}</div>
            {data.opponentAdjustedPerformance?.percentile != null && <div className="mt-1 text-xs text-zinc-500">{data.opponentAdjustedPerformance.percentile}th percentile</div>}
          </div>
          <div className="grid grid-cols-1 gap-2 min-[430px]:grid-cols-2 md:grid-cols-5">
            <ProfileMetric label="Overall PPR vs expected" value={number(data.opponentAdjustedPerformance?.overallPprVsExpected)} />
            <ProfileMetric label="Strong-field PPR vs expected" value={number(data.opponentAdjustedPerformance?.strongOpponentPprVsExpected)} />
            <ProfileMetric label="Strong-field games" value={data.opponentAdjustedPerformance?.strongOpponentGames ?? 0} />
            <ProfileMetric label="Elite-field games" value={data.opponentAdjustedPerformance?.eliteOpponentGames ?? 0} />
            <ProfileMetric label="Sample confidence" value={percent(data.opponentAdjustedPerformance?.strongOpponentSampleConfidence)} />
          </div>
        </div>
        <p className="mt-3 text-xs leading-5 text-zinc-500">
          Measures actual game PPR above or below the player's pregame Expected PPR, with opponent strength reconstructed as of that game.
          This separates facing difficult competition from actually outperforming against it.
        </p>
      </Panel>
      <Panel icon={<Activity />} title="Large Swings & Swing Surprise">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-2xl border border-cyan-300/20 bg-cyan-300/10 p-5 text-center">
            <div className="text-[10px] font-black uppercase tracking-[.18em] text-cyan-200">Large Swing Avoidance</div>
            <div className="mt-2 text-5xl font-black text-cyan-300">{data.swingPerformance?.largeSwingAvoidanceRating ?? '—'}</div>
            <div className="mt-1 font-black text-white">{data.swingPerformance?.avoidanceLabel}</div>
          </div>
          <div className="rounded-2xl border border-fuchsia-300/20 bg-fuchsia-300/10 p-5 text-center">
            <div className="text-[10px] font-black uppercase tracking-[.18em] text-fuchsia-200">Large Swing Resilience</div>
            <div className="mt-2 text-5xl font-black text-fuchsia-300">{data.swingPerformance?.largeSwingResilienceRating ?? '—'}</div>
            <div className="mt-1 font-black text-white">{data.swingPerformance?.resilienceLabel}</div>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 min-[430px]:grid-cols-2 md:grid-cols-5">
          <ProfileMetric label="5+ swings conceded" value={data.swingPerformance?.largeSwings ?? 0} />
          <ProfileMetric label="7+ severe swings" value={data.swingPerformance?.severeSwings ?? 0} />
          <ProfileMetric label="Round exposure" value={percent(data.swingPerformance?.largeSwingRate)} detail="Share of recorded rounds conceding 5+ net points" />
          <ProfileMetric label="Swing surprise" value={number(data.swingPerformance?.averageSwingSurprise)} detail="Standard deviations worse than expected" />
          <ProfileMetric label="Sample confidence" value={percent(data.swingPerformance?.sampleConfidence)} />
          <ProfileMetric label="Avg deficit per large swing" value={number(data.swingPerformance?.averageConcession)} detail="Only rounds already classified as 5+ swings" />
          <ProfileMetric label="Surprise points" value={number(data.swingPerformance?.averageSurprisePoints)} detail="Above this player's expected concession" />
          <ProfileMetric
            label="Games with a large swing"
            value={percent(data.swingPerformance?.largeSwingGameRate)}
            detail={data.swingPerformance?.games == null
              ? 'Game-level calculation unavailable; refresh this profile'
              : `${data.swingPerformance.gamesWithLargeSwing} of ${data.swingPerformance.games} recorded games`}
          />
          <ProfileMetric label="Large swings per game" value={number(data.swingPerformance?.largeSwingsPerGame)} />
          <ProfileMetric label="First-round share" value={percent(data.swingPerformance?.firstRoundSwingRate)} />
          <ProfileMetric label="Next-round recovery" value={number(data.swingPerformance?.recoveryNetVsExpected)} detail="Net points versus personal baseline" />
          <ProfileMetric label="Positive recovery rate" value={percent(data.swingPerformance?.recoveryRate)} />
        </div>
        <div className="mt-4 rounded-2xl border border-white/10 bg-white/[.025] p-4">
          <div className="text-[10px] font-black uppercase tracking-[.18em] text-zinc-400">What happens after the swing</div>
          <div className="mt-3 grid grid-cols-1 gap-2 min-[430px]:grid-cols-2 md:grid-cols-4">
            <ProfileMetric
              label="Partner response"
              value={number(data.swingPerformance?.partnerResponseVsExpected)}
              detail={`Net points versus partner baseline · ${data.swingPerformance?.partnerResponseOpportunities ?? 0} opportunities`}
            />
            <ProfileMetric
              label="Positive partner response"
              value={percent(data.swingPerformance?.partnerPositiveResponseRate)}
              detail="Partner scores on the immediately following round"
            />
            <ProfileMetric
              label="Opponent follow-through"
              value={percent(data.swingPerformance?.opponentFollowThroughRate)}
              detail="Opponent scores again on the immediately following round"
            />
            <ProfileMetric
              label="Opponent give-back"
              value={percent(data.swingPerformance?.opponentGivebackRate)}
              detail="Opponent immediately concedes points back"
            />
            <ProfileMetric
              label="Comeback win rate"
              value={percent(data.swingPerformance?.comebackWinRateAfterSwing)}
              detail={`Player's team still wins · ${data.swingPerformance?.swingOutcomeOpportunities ?? 0} swing outcomes`}
            />
            <ProfileMetric
              label="Opponent conversion"
              value={percent(data.swingPerformance?.opponentConversionRate)}
              detail="Opponent converts the swing into an eventual game win"
            />
            <ProfileMetric
              label="Average opening round"
              value={number(data.swingPerformance?.averageOpeningRoundNet)}
              detail={`Net points · ${data.swingPerformance?.openingRoundOpportunities ?? 0} recorded opening throws`}
            />
            <ProfileMetric
              label="Opening-round win rate"
              value={percent(data.swingPerformance?.openingRoundWinRate)}
              detail="Share of opening rounds won"
            />
          </div>
        </div>
        <p className="mt-3 text-xs leading-5 text-zinc-500">
          A large swing is a round conceding at least five net points; seven or more is reported as severe.
          Swing Surprise compares the damage with this player's pre-event performance and normal round-to-round volatility, so the same raw deficit can carry different meaning for different skill levels.
          Avoidance and resilience are Cheesebaggers ratings and currently have zero prediction weight.
        </p>
      </Panel>
      <SectionHeading
        eyebrow="Model usage"
        title="How predictions use these ratings"
        detail="Validation evidence and current game/bracket weight are kept separate from the player-facing ratings."
      />
      <Panel icon={<Database />} title="Rating & Prediction Policy">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="text-left text-[10px] font-black uppercase tracking-wider text-zinc-500">
              <tr><th className="pb-2">Profile rating</th><th>Rating</th><th>Sample confidence</th><th>Game weight</th><th>Bracket weight</th><th>Predictive status</th></tr>
            </thead>
            <tbody>
              {(data.ratingCatalog || []).map((row:any) => (
                <tr key={row.key} className="border-t border-white/10">
                  <td className="py-3"><div className="font-black text-white">{row.name}</div><div className="text-[10px] text-zinc-600">{row.label}</div></td>
                  <td className="font-black text-amber-300">{row.rating ?? '—'}</td>
                  <td>{percent(row.sampleConfidence)}</td>
                  <td className={row.gamePredictionWeight ? 'font-black text-emerald-300' : 'text-zinc-500'}>{Number(row.gamePredictionWeight || 0).toFixed(2)}</td>
                  <td className={row.bracketPredictionWeight ? 'font-black text-emerald-300' : 'text-zinc-500'}>{Number(row.bracketPredictionWeight || 0).toFixed(2)}</td>
                  <td><div className="font-bold text-zinc-300">{String(row.predictiveStatus || '').replaceAll('_', ' ')}</div><div className="max-w-sm text-[10px] leading-4 text-zinc-600">{row.evidence}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-3 rounded-xl border border-amber-300/15 bg-amber-300/5 p-3 text-xs leading-5 text-zinc-400">
          Active game model: <span className="font-black text-white">{data.predictionWeighting?.gamePrediction?.modelVersion}</span> using calculated PPR difference.
          Bracket prediction status: <span className="font-black text-white">{String(data.predictionWeighting?.bracketPrediction?.status || '').replaceAll('_', ' ')}</span>.
        </div>
      </Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel icon={<Database />} title="Model evidence">
          <div className="grid grid-cols-3 gap-2">
            <ProfileMetric label="Events" value={data.sample.events ?? 0} />
            <ProfileMetric label="Games" value={data.sample.games ?? 0} />
            <ProfileMetric label="Rounds" value={data.sample.rounds ?? 0} />
          </div>
          <div className="mt-3 text-xs text-zinc-500">Last event: {data.sample.lastEventDate || 'Unknown'} · Coverage {percent(data.coverage?.coverageRatio)}</div>
        </Panel>
        <Panel icon={<Target />} title="Prediction history">
          {(data.recentPredictions || []).length === 0 && <div className="text-sm text-zinc-500">No locked predictions involving this player.</div>}
          {(data.recentPredictions || []).map((row:any) => (
            <a key={row.prediction_id} href={`/?event_id=${row.event_id}`} className="mb-2 flex items-center justify-between rounded-xl bg-white/[.04] p-3">
              <span className="text-sm font-bold text-white">Event {row.event_id} · Match {row.match_id}</span>
              <span className="font-black text-amber-300">{percent(row.playerWinProbability)}</span>
            </a>
          ))}
        </Panel>
      </div>
    </section>
  );
}

function Panel({ icon, title, children }:any) {
  return <div className="rounded-[22px] border border-white/10 bg-zinc-950 p-4 sm:rounded-[26px] sm:p-5"><div className="flex items-center gap-2 text-amber-300">{icon}<h3 className="text-lg font-black text-white">{title}</h3></div><div className="mt-4">{children}</div></div>;
}
function SectionHeading({ eyebrow, title, detail }:any) {
  return <div className="px-1 pt-3">
    <div className="text-[10px] font-black uppercase tracking-[.24em] text-amber-300">{eyebrow}</div>
    <h3 className="mt-1 text-2xl font-black text-white">{title}</h3>
    <p className="mt-1 text-sm text-zinc-500">{detail}</p>
  </div>;
}
function ProfileMetric({ label, value, detail }:any) {
  return <div className="rounded-xl bg-white/[.04] p-3.5 sm:p-3"><div className="text-xs font-black uppercase tracking-wide text-zinc-400">{label}</div><div className="mt-1 text-2xl font-black text-white sm:text-xl">{value}</div>{detail && <div className="mt-1 text-xs leading-5 text-zinc-400">{detail}</div>}</div>;
}
function source(observation:any) {
  if (!observation) return '';
  return `${observation.sourceEndpoint} · effective ${observation.effectiveAt || observation.retrievedAt || 'unknown'}`;
}
function RollingMetric({ label, value }:any) {
  const strengthTone = value?.sampleLabel === 'STRONG'
    ? 'text-emerald-300'
    : value?.sampleLabel === 'MODERATE'
      ? 'text-sky-300'
      : 'text-amber-300';
  return <div className="rounded-xl bg-white/[.04] p-3">
    <div className="text-[10px] font-black uppercase tracking-wider text-zinc-500">{label}</div>
    <div className="mt-1 text-2xl font-black text-white">{number(value?.ppr)}</div>
    <div className="mt-1 text-[10px] text-zinc-500">{value?.rounds ?? 0} rounds · {value?.games ?? 0} games</div>
    <div className={`mt-2 text-[10px] font-black ${strengthTone}`}>{value?.sampleLabel || 'VERY_LIMITED'}</div>
  </div>;
}
function RatingHero({ value, label }:any) {
  return <div className="rounded-2xl bg-white/[.04] p-4 text-center"><div className="text-4xl font-black text-amber-300">{value ?? '—'}</div><div className="mt-1 font-black text-white">{label || 'Insufficient sample'}</div></div>;
}

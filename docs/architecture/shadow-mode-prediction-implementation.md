# Shadow-mode prediction implementation

## Current state

`fitted-ppr-logistic-v1` is registered as the monitored candidate using the
frozen parameters selected before rolling-origin validation. It is not exposed
as an official or user-facing pick.

## Pregame workflow

For each known matchup, the platform:

1. Requires the prediction record to be created before the scheduled start.
2. Rebuilds Stage A features using the record time as the data cutoff.
3. Applies the existing model-readiness and identity/history integrity checks.
4. Scores the frozen fitted-PPR model or records an abstention.
5. Stores one immutable shadow run for each event, match, and model version.

Repeated processing is idempotent: it returns the existing shadow run rather
than creating multiple predictions for the same matchup.

## Safeguards

- The frozen model was fitted on 288 eligible development examples and requires
  at least 100.
- Matchups failing Stage A readiness abstain.
- Probabilities are capped at 85% for either side because extreme-probability
  calibration evidence is sparse.
- Outcomes cannot be attached before the scheduled match start.
- Prediction inputs, cutoff, feature hash, model version, and probabilities are
  retained for audit.
- CPI remains ACL-only and is not calculated or inferred.

## Monitoring

The shadow report exposes:

- total runs;
- predicted and abstained runs;
- coverage;
- resolved predictions;
- accuracy;
- log loss;
- Brier score;
- abstentions grouped by reason; and
- the rolling-origin reference values for comparison.

Historical reference:

| Metric | Reference |
|---|---:|
| Accuracy | 63.14% |
| Coverage | 68.97% |
| Log loss | 0.649378 |
| Brier score | 0.228110 |

## Promotion status

Not approved for user-facing promotion. Promotion requires a meaningful number
of genuinely pregame shadow predictions and performance consistent with the
historical reference, along with no evidence of cutoff leakage or systematic
format-specific failure.

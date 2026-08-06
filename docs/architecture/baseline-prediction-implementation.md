# Baseline Prediction and Immutable Registry

Implementation date: 2026-07-25  
Feature version: `stage-a-v1`

## Purpose

The baseline layer answers the first modeling question: can a transparent calculation beat
an uninformed 50/50 forecast when evaluated chronologically?

These are benchmark models, not yet validated production models.

## Model definitions

### `equal-v1`

Assigns 50% probability to each identified side. This is the control benchmark every other
model must beat.

### `ppr-difference-v1`

Uses the Stage A calculated-PPR difference:

```text
raw P(side A wins) = sigmoid((side A PPR - side B PPR) / 1.5)
```

The scale `1.5` is a fixed, documented heuristic. It has not been fitted or calibrated.
Chronological evaluation must determine whether it is useful and whether the scale should
ever be replaced by a trained parameter.

## Evidence tiers and shrinkage

The matchup tier is the weakest player tier on either side.

| Tier | Scoring behavior |
|---|---|
| A | Raw benchmark probability; requires strong history, trustworthy coverage, and eligible ACL snapshots |
| B | Raw benchmark probability; substantial match history |
| C | Probability is pulled toward 50/50 according to the least-experienced player's rounds |
| `NO_PREDICTION` | Abstain; probabilities remain null |

Tier C shrinkage:

```text
factor = min(minimum player rounds / 100, 1)
final probability = 0.5 + (raw probability - 0.5) * factor
```

This is deliberately conservative. The shrinkage rule is versioned benchmark behavior and
must be evaluated rather than assumed optimal.

## Abstention

The PPR benchmark abstains when:

- either side has no player identity;
- any participant lacks eligible prior match history;
- the matchup fails temporal integrity/model-readiness checks; or
- calculated PPR difference is unavailable.

An abstention is stored with null probabilities and `NO_PREDICTION`; it is not silently
converted to 50/50. The separate `equal-v1` control remains available for evaluation.

## Immutable storage

### `model_definitions`

Stores versioned model type, feature version, parameters, description, and creation time.
Existing versions are never updated by prediction creation.

### `prediction_records`

Every prediction request appends a new record containing:

- model and feature versions;
- data cutoff;
- optional event/match identity;
- side player IDs;
- evidence tier and predicted/abstained status;
- raw and final probabilities;
- shrinkage factor;
- canonical feature hash;
- complete modeling-safe feature JSON; and
- creation time.

Repeated identical requests create separate audit records with the same feature hash. No
upsert or overwrite path exists.

## Safety properties

- Side probabilities sum to one.
- Reversing sides reverses PPR-model probabilities.
- Tier C predictions move toward, never away from, 50/50.
- Missing history causes abstention.
- Prediction features use the established strict prior-event-date cutoff.
- Raw personal data is not included in the feature record.

## Real-data smoke test

A non-persisted test for player `142125` versus player `197976`, using the July 25 cutoff,
produced:

- evidence tier B;
- side A probability `0.624603`;
- side B probability `0.375397`; and
- shrinkage factor `1.0`.

This confirms execution against the local dataset. It does **not** establish that 62.46% is
accurate or calibrated.

## Tests

The combined backend suite contains 26 passing tests. Baseline-specific tests cover:

- the 50/50 control;
- side-reversal symmetry;
- Tier C shrinkage;
- unshrunk Tier B scoring;
- missing-history abstention; and
- append-only prediction persistence.

## Next slice

Build a chronological evaluator that reconstructs pre-event features and outcomes, then
reports:

- number of eligible and abstained predictions;
- log loss;
- Brier score;
- accuracy;
- calibration by probability band;
- results by evidence tier and raw event format; and
- direct comparison of `equal-v1` and `ppr-difference-v1`.

No benchmark should be called predictive until it beats the control out of time with
acceptable calibration.

The first full chronological evaluation is complete. See
[`chronological-evaluation-2026-07-25.md`](./chronological-evaluation-2026-07-25.md).

# Untouched Chronological Holdout Evaluation

Evaluation date: 2026-07-25  
Evaluation version: `holdout-v1`  
Feature version: `stage-a-v1`

## Split

Events were divided by whole event date:

- development: 495 reconstructable matchups before 2026-04-16;
- holdout: 255 matchups on or after 2026-04-16;
- model-ready development matchups: 288; and
- model-ready holdout matchups: 175.

No event date appears in both periods. All fitted parameters and Elo tuning used development
outcomes only. Holdout outcomes remained untouched until final scoring.

## Decision

`fitted-ppr-logistic-v1` is the leading candidate for the next validation phase.

It:

- had the best holdout log loss;
- had the best holdout Brier score;
- improved over 50/50 with positive event-clustered 95% intervals on both metrics;
- used only one interpretable input: prior calculated-PPR difference; and
- outperformed the larger seven-feature model.

It is a candidate, not yet an approved production model. One chronological split is not
enough to establish stability across time and formats.

## Holdout results

| Model | Holdout predictions | Coverage | Log loss | Brier | Accuracy |
|---|---:|---:|---:|---:|---:|
| `equal-v1` | 255 | 100% | 0.693147 | 0.250000 | 0.500000 |
| `fixed-ppr-difference-v1` | 175 | 68.63% | 0.663891 | 0.235573 | 0.657143 |
| `fitted-ppr-logistic-v1` | 175 | 68.63% | **0.643939** | **0.224959** | 0.645714 |
| `regularized-stage-a-logistic-v1` | 175 | 68.63% | 0.646030 | 0.225143 | 0.628571 |
| `elo-v1` | 255 | 100% | 0.670737 | 0.238656 | 0.600000 |

Accuracy is not the primary selection metric. A model can classify slightly fewer winners
correctly while assigning better-calibrated probabilities and therefore achieving lower log
loss and Brier score.

## Event-clustered uncertainty

The bootstrap resampled whole events rather than individual games, reducing false precision
from correlated matches within the same event.

### Improvement versus 50/50

| Model | Log-loss improvement 95% | Brier improvement 95% | Event clusters |
|---|---|---|---:|
| Fixed PPR | 0.015457 to 0.042873 | 0.007600 to 0.021120 | 55 |
| Fitted PPR | **0.016420 to 0.079958** | **0.010096 to 0.039191** | 55 |
| Seven-feature logistic | -0.003099 to 0.090127 | 0.002758 to 0.043842 | 55 |
| Elo | -0.008709 to 0.053583 | -0.003645 to 0.026261 | 70 |

An interval crossing zero means improvement was not established at this uncertainty level.
The fitted and fixed PPR models were the only candidates with positive intervals for both
primary metrics.

## Fitted PPR model

The model was fitted on 288 development examples using:

```text
P(side A wins) =
    sigmoid(
        -0.050044
        + 0.671268 × ((PPR difference - 0.043210) / 0.852172)
    )
```

The standardization values and coefficient are part of the model version and must be stored
unchanged if this candidate is registered.

The model remains interpretable: higher prior calculated PPR relative to the opponent
increases win probability.

## Seven-feature model finding

The regularized Stage A logistic model used PPR, DPR, bag-in rate, four-bagger rate, round
win rate, relative sample size, and partnership history.

It did not improve meaningfully over the one-parameter PPR model:

- log loss was slightly worse (`0.646030` versus `0.643939`);
- Brier score was slightly worse (`0.225143` versus `0.224959`);
- its log-loss improvement interval crossed zero; and
- it produced more extreme small-sample probabilities.

The added complexity is not justified by this holdout. Do not promote it.

## Elo finding

Development tuning selected `K=40`. Elo covered all 255 holdout matchups and beat 50/50 on
point estimates, but both event-clustered improvement intervals crossed zero.

Elo remains valuable as:

- a full-coverage fallback;
- a cold-start comparison;
- an ensemble candidate after more data; and
- a continuously updated player-strength signal.

It is not the leading probability model on current evidence.

## Calibration

The fitted PPR model is improved but not perfectly calibrated. Several probability bands
remain small, and the 40–50% band observed a side-A win rate above 60%. These bands can also
reflect home/side assignment effects or temporal/format composition.

Do not apply post-hoc calibration using the holdout outcomes. That would consume the
untouched test set.

## Safety defect found during evaluation

The first implementation allowed the fitted logistic model to score some matchups where one
participant lacked history, even though the benchmark correctly abstained. Eligibility was
corrected so every fitted feature model uses the same all-participant `modelReady` rule.
A regression test protects this behavior.

## Required next step

Run rolling-origin validation using multiple chronological folds:

1. Fit the PPR coefficient/intercept on each earlier window.
2. Test on the immediately following event-date block.
3. Report parameter stability, coverage, Tier B/C results, format results, and
   event-clustered uncertainty.
4. Compare fitted PPR, fixed PPR, and Elo in every fold.
5. Register `fitted-ppr-logistic-v1` only if improvement is consistent rather than driven by
   the April-forward holdout.

The untouched holdout must remain archived as evaluation evidence and must not be reused to
tune the candidate.

# Chronological Baseline Evaluation

Evaluation date: 2026-07-25  
Evaluation version: `chronological-v1`  
Feature version: `stage-a-v1`  
History window: prior 365 days

## Decision

The calculated-PPR benchmark contains useful predictive signal and beats the 50/50 control
on the common historical sample. It is not yet ready to present as a calibrated production
probability.

Reasons to continue:

- lower log loss than 50/50;
- lower Brier score than 50/50;
- directional accuracy above chance; and
- improvement in both Tier B and Tier C samples.

Reasons not to ship the probability unchanged:

- it abstained on 38.3% of reconstructable matchups;
- only 79 predictions were Tier B;
- calibration bands show material under-confidence/misalignment;
- most format-specific evidence comes from raw format `D:D`; and
- the heuristic logistic scale and Tier C shrinkage have not been fitted.

## Historical population

The evaluator reconstructed 750 completed, non-tied games with:

- event date;
- final home/away score; and
- identifiable recorded players on both sides.

Every target used features from events strictly before the target event date. Matches from
the target date were excluded, preventing same-event and same-round leakage.

## Overall results

| Model | Predictions | Coverage | Log loss | Brier score | Accuracy |
|---|---:|---:|---:|---:|---:|
| `equal-v1` | 750 | 100% | 0.693147 | 0.250000 | 0.500000 |
| `ppr-difference-v1` | 463 | 61.73% | 0.666990 | 0.237184 | 0.637149 |

Accuracy assigns half credit to an exact 50/50 forecast. Log loss and Brier score are the
primary metrics.

## Fair common-sample comparison

On the same 463 games where the PPR benchmark could predict:

| Model | Log loss | Brier score |
|---|---:|---:|
| `equal-v1` | 0.693147 | 0.250000 |
| `ppr-difference-v1` | 0.666990 | 0.237184 |
| Improvement | 0.026157 | 0.012816 |

Positive improvement means the PPR benchmark performed better.

This establishes signal in prior calculated PPR. It does not prove the current probability
transformation is optimal or stable out of sample.

## Evidence-tier results

| Tier | Predictions | Log loss | Brier score | Accuracy |
|---|---:|---:|---:|---:|
| B | 79 | 0.626530 | 0.217952 | 0.645570 |
| C | 384 | 0.675314 | 0.241141 | 0.635417 |

Tier B performs materially better than Tier C on probability-sensitive metrics. This
supports retaining the evidence-tier distinction and conservative sparse-history behavior.

## Raw-format results

| Format | Predictions | Log loss | Brier score | Accuracy |
|---|---:|---:|---:|---:|
| `D:D` | 376 | 0.670493 | 0.238792 | 0.627660 |
| `S:D` | 82 | 0.647961 | 0.228346 | 0.695122 |
| `D:S` | 4 | 0.706456 | 0.256644 | 0.500000 |
| `S:S` | 1 | 0.752123 | 0.279455 | 0.000000 |

The last two samples are far too small for conclusions. Format codes remain raw until their
meanings are formally mapped.

## Coverage and abstention

The PPR model produced 463 predictions and abstained on 287 games because at least one side
lacked eligible prior history or the calculated-PPR feature.

The 61.73% coverage rate applies only to the 750 games whose outcomes and sides could be
reconstructed. It is not 61.73% of every ACL game.

## Calibration finding

The probability bands are directionally ordered but not well aligned:

- predictions near 47% corresponded to an observed side-A win rate near 39%;
- predictions near 53% corresponded to an observed win rate near 63%;
- the 60–70% band observed roughly 86%, but contained only 14 games.

The model is often too close to 50/50—under-confident—while some lower bands also have small
samples. The fixed `1.5` logistic scale and Tier C shrinkage should be treated as benchmark
parameters, not production calibration.

## What this proves

- Prior calculated PPR has predictive value in this dataset.
- The cutoff-aware feature path can produce legitimate historical forecasts.
- Sparse-history shrinkage preserves useful Tier C signal while keeping probabilities near
  50/50.
- Evidence tiers correspond to meaningful differences in probability performance.

## What this does not prove

- That the benchmark generalizes to future seasons, regions, or all formats.
- That the result is independent of player/event selection effects.
- That 63.7% directional accuracy will persist.
- That the displayed probabilities are calibrated.
- That unavailable or non-reconstructable games would show the same performance.
- That CPI would improve the model.

## Required next step

Build an out-of-time calibration/training slice:

1. Divide events into chronological development and holdout periods.
2. Fit only a small number of interpretable parameters on the development period.
3. Evaluate untouched holdout events.
4. Compare:
   - 50/50;
   - fixed PPR benchmark;
   - fitted PPR logistic calibration;
   - a simple Elo-style rating; and
   - a small regularized logistic model using Stage A features.
5. Report confidence intervals or bootstrap uncertainty.
6. Preserve Tier B/C and format-stratified results.

Until the untouched holdout confirms improvement and calibration, label
`ppr-difference-v1` as an internal benchmark rather than a production prediction model.

The untouched holdout is complete. See
[`holdout-evaluation-2026-07-25.md`](./holdout-evaluation-2026-07-25.md).

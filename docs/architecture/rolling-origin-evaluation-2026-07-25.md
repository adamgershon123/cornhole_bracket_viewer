# Rolling-origin evaluation — 2026-07-25

## Decision

`fitted-ppr-logistic-v1` remains the leading production candidate, but it should
initially be released as a monitored candidate rather than treated as a final
model. Across mature rolling-origin windows it maintained a meaningful aggregate
advantage over a 50/50 forecast, although individual small windows remained
volatile.

## Method

- 750 reconstructable historical matchups.
- Expanding development window, followed by five whole event-date test windows.
- No event date is split between development and test data.
- Features are rebuilt using only facts available before each event.
- Model parameters are fitted independently in every fold.
- Primary decision view begins after 50 development event dates, providing 94
  eligible examples for the first fitted model.

## Mature-history results

| Measure | Result |
|---|---:|
| Test windows | 22 |
| Predictions | 369 |
| Prediction coverage | 68.97% |
| Accuracy | 63.14% |
| Log loss | 0.649378 |
| Brier score | 0.228110 |
| Log-loss improvement vs 50/50 | 0.043769 |
| Brier improvement vs 50/50 | 0.021890 |
| Event-clustered 95% log-loss improvement interval | 0.016054 to 0.071069 |
| Event-clustered 95% Brier improvement interval | 0.009237 to 0.034627 |
| Windows beating 50/50 log loss | 16 of 22 |
| Mean fold accuracy | 62.14% |

The earlier-start sensitivity run used 29 windows and 454 predictions. It
produced 62.56% accuracy, 65.14% coverage, and 0.659368 log loss. Its first
models had as few as nine eligible development examples, explaining much of the
additional volatility.

## Interpretation

- The previous single holdout's 64.6% accuracy was not an isolated result.
- Both primary aggregate improvement intervals remain above zero when resampling
  whole events.
- A realistic current planning estimate is approximately 63% accuracy at 69%
  coverage once the model has sufficient history.
- Aggregate calibration is useful, but very small folds range widely and should
  not drive promotion decisions independently.
- Extreme probabilities are too sparsely represented to justify strong
  confidence labels.

## Required release safeguards

1. Preserve abstention whenever the Stage A matchup is not model-ready.
2. Require a minimum fitted-history threshold before using the model.
3. Cap or label high-confidence outputs until more extreme-probability evidence
   exists.
4. Monitor rolling log loss, Brier score, accuracy, coverage, and calibration by
   event format.
5. Keep CPI ACL-only and keep ACL PPR separate from internally calculated PPR.

## Next implementation step

Register the fitted PPR model as a versioned candidate, add the minimum-history
and confidence safeguards to its scoring path, and run it in shadow mode so
predictions can be compared with outcomes without affecting user-facing picks.

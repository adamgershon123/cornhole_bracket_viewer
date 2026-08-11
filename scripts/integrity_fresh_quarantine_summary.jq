[
  .games[]
  | select(.status == "WOULD_QUARANTINE")
  | {
      eventId,
      matchId,
      gameId,
      codes: (.checks.errors | map(.code) | unique)
    }
]
| group_by(.codes | join(","))
| map({codes: .[0].codes, count: length, examples: .[0:5]})

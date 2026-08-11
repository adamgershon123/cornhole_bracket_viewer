{
  integrityVersion,
  mode,
  filesDiscovered,
  archivePayloadsDiscovered,
  sourcesDiscovered,
  eligibleFinalGames,
  partialGames,
  alreadyCurrent,
  validated,
  quarantined,
  remaining,
  statusCounts: (
    [.games[].status]
    | group_by(.)
    | map({status: .[0], count: length})
    | sort_by(-.count)
  ),
  unreadableErrors: (
    [.games[] | select(.status == "UNREADABLE") | .error]
    | group_by(.)
    | map({error: .[0], count: length})
    | sort_by(-.count)
    | .[:10]
  ),
  issueCodes: (
    [.games[].checks.errors[]?.code]
    | group_by(.)
    | map({code: .[0], count: length})
    | sort_by(-.count)
  ),
  quarantineExamples: (
    [.games[]
      | select(.status == "WOULD_QUARANTINE")
      | {eventId, matchId, gameId, source, codes: [.checks.errors[].code]}]
    | .[:20]
  )
}

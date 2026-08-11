[.[] | select(.event.match_type != "S")]
| group_by(.codes | join(","))
| map({codes: .[0].codes, count: length, examples: .[0:8]})

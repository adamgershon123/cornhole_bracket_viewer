# Cheesebaggers Feature Backlog

## Bag tracking and player bag collection

**Status:** Planned

### Goal

Let a player quickly record which bags they used in a particular game, retain those bags in their personal collection for one-tap reuse, and build useful bag-performance history without interrupting live play.

### Core workflow

1. Associate the selection with a specific `event_id`, `match_id`, `game_id`, player, and—when relevant—side or throwing position.
2. Prompt the player after a game begins or completes when no bag selection has been recorded.
3. Offer the player's recently used and saved bags first as large, selectable tags.
4. Let the player choose a bag from the shared catalog by **brand**, then **series/model**.
5. Allow a missing bag to be added with minimal information and make it immediately reusable.
6. Save the selection once and show clear confirmation. Permit later correction with an audit trail.

### Reminder behavior

- Use a visible but dismissible reminder card; do not obstruct live scores or current-match controls.
- Remind again at sensible transitions, such as game completion or the next game, rather than repeatedly during a round.
- Provide **Select bags**, **Same as last game**, **Remind me later**, and **Not sure** actions.
- Stop reminders for that game after a selection or an explicit **Not sure** response.
- Track reminder state per player and game so refreshing or changing devices does not restart the nag cycle.
- Make reminders and their frequency configurable when account preferences are introduced.

### Bag catalog

Maintain a normalized shared catalog that supports:

- manufacturer/brand;
- series/model;
- optional speed rating for each side;
- optional color/design and production variant;
- active/discontinued status;
- aliases and spelling normalization;
- catalog provenance and last verification date.

Catalog search should tolerate partial names and aliases. A player-submitted entry should be usable immediately but marked unverified until it is merged with or promoted into the shared catalog.

### Personal collection

- A saved bag becomes a reusable tag in the player's collection.
- Sort choices by most recently used, most frequently used, then alphabetical.
- Support favorites and optional nicknames for a player's particular set.
- Allow removal from the personal collection without deleting historical game associations or the shared catalog entry.
- Support **Same as last game** and multi-game assignment for consecutive games using the same set.

### Suggested data model

- `bag_catalog`: canonical brand/series metadata.
- `bag_catalog_aliases`: alternative names mapped to canonical bags.
- `player_bag_collection`: player favorites, nicknames, recency, and usage counts.
- `game_bag_usage`: player-to-game association, selection source, timestamps, and confidence/state.
- `bag_usage_audit`: corrections and prior values so historical analytics remain explainable.
- `bag_prompt_state`: reminder status per player/game/device or future account.

The game association must use stable ACL identifiers and must not be inferred solely from event names or timestamps.

### Interface requirements

- Mobile-first, thumb-friendly controls.
- Recent bag tags appear before catalog search.
- Brand and series selection should normally take two taps.
- Clearly distinguish a catalog bag, a player nickname, and an unverified custom entry.
- Expose bag selection in player mode, game summaries, report cards, and share cards when the player permits it.
- Do not hold up score refreshes, grading, or prediction requests while bag information is being entered or saved.

### Analytics enabled later

- PPR, DPR, round-win rate, four-bagger rate, and grade by bag series.
- Performance versus the player's baseline with the same and different bags.
- Venue, court, format, partner, opponent, and time-window splits.
- Sample-confidence labels so small bag samples are never presented as conclusive.
- Bag-change detection between games and performance before/after a change.

Bag choice should remain descriptive until cutoff-safe validation shows incremental predictive value beyond existing player and event features.

### Privacy and sharing

- Bag usage can be public, private, or excluded from share cards when account preferences exist.
- A player's selection is player-supplied data, not an official ACL statistic, and must be labeled accordingly.

### Acceptance criteria for the first release

- A player can identify bags for a game in no more than two taps when the bags are already saved.
- A new catalog selection can normally be completed in four taps or fewer.
- The selection persists across devices once account identity exists; until then it follows the shared simulated-default-player state.
- Refreshing the page does not lose the selection or re-display a dismissed reminder immediately.
- Historical game associations survive catalog cleanup, personal-collection removal, and spelling/alias merges.


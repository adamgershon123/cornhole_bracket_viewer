# ACL Player Profile Endpoint Review

Endpoint:

```text
GET /api/auth/v1/players/{player_id}?dw=false&nd=true&dwt=true
```

Review status: **Successful and unauthenticated responses captured; authentication mechanism
still undocumented**

Alternative public-source collection strategy:
[`../player-stats-without-authenticated-profile.md`](../player-stats-without-authenticated-profile.md).

## Authentication results

| Test | Result |
|---|---|
| Player `142125`, Fanzone headers, no credentials | HTTP `403 Forbidden` |
| Unauthenticated response | `{"status":"ERROR","success":false,"message":"NOT Authorized - No session found."}` |
| User-supplied response from an authenticated context | HTTP/application success: `"status":"OK"`, `"message":"Player Successfully found"` |
| Current backend behavior | Sends no session or authorization credentials, so a network refresh cannot succeed under the observed access behavior. |

The `/api/auth/v1` path is genuinely session-protected in the observed test. The successful
response proves that a valid authenticated context can access it, but we have not yet
documented the authorized login/session flow or whether Cheesebaggers should use it.

## Successful response structure

| Response variable | Observed contents |
|---|---|
| `status` | `"OK"` |
| `message` | `"Player Successfully found"` |
| `data[]` | One player/account/profile record |
| `playerMembershipInfo[]` | Two combined membership records |
| `playerMembershipDetails[]` | One player-membership record |
| `directorMembershipDetails[]` | One director-membership record |
| `nearestDirector[]` | Fifteen nearby director records |
| `nearestNonClubDirector[]` | Four nearby non-club director records |

## Player/account result: `data[]`

### Analytics-relevant or potentially relevant

| Variable | Sanitized sample | Likely meaning |
|---|---:|---|
| `userID` | `142125` | ACL account/user identifier |
| `playerID` | `142125` | ACL player identifier |
| `skillLevel` | `"C"` | ACL skill-level code |
| `skillLevelDesc` | `"Competitive"` | Skill-level label |
| `status` | `"A"` | Account/player status code |
| `playerType` | `"ADULT"` | Player category |
| `playerPPRPlayerInfo` | `7.4153` | Higher-precision PPR-like value; definition/scope unconfirmed |
| `playerPPR` | `7.39` | ACL-reported PPR; definition/window unconfirmed |
| `playerCPI` | `6.35` | ACL-reported CPI |
| `cPITimeStamp` | `"2026-07-22 13:29:30"` | CPI observation/update time; timezone absent |
| `conferenceID` | `1` | ACL conference identifier |
| `conferenceName` | `"SouthEast Conference"` | Conference label |
| `playerMembershipCount` | `1` | Player membership count |
| `playerMembershipID` | `4` | Player membership identifier |
| `playerMembershipName` | `"PLATINUM"` | Player membership label |
| `directorMembershipCount` | `1` | Director membership count |
| `directorrMembershipID` | `14` | Director membership ID; source contains apparent spelling error |
| `directorMembershipName` | `"Club DIRECTOR"` | Director membership label |
| `playerDiscounts` | `true` | Player-discount eligibility |

### Identity and presentation

| Variable | Sanitized sample | Likely meaning |
|---|---|---|
| `firstName`, `lastName`, `nickName` | `[REDACTED_PLAYER_NAME]` | Player identity/display name |
| `profileImage` | `[REDACTED_PROFILE_IMAGE]` | Player image URL |
| `gender`, `playerGender` | `[REDACTED_PERSONAL_DATA: gender]` | Gender fields |
| `ageGroup` | `null` | Age-group classification |
| `state` | `"FL"` | Player state |
| `city` | `[REDACTED_PERSONAL_DATA: city]` | Player city |
| `countryCodeID` | `"US"` | Country code |
| `playerCurrency` | `"USD"` | Account currency |

### Sensitive account/contact data — exclude by default

| Variable/group | Visible marker | Why flagged |
|---|---|---|
| `email` | `[REDACTED_EMAIL]` | Personal contact data |
| `phoneNo` | `[REDACTED_PHONE]` | Personal contact data |
| `dobYear`, `dobMonth`, `dobDay` | `[REDACTED_DATE_OF_BIRTH]` | Reconstructable full birth date |
| `playerLat`, `playerLng` | `[REDACTED_PRECISE_LOCATION]` | Precise personal location |
| `lastLogin` | `[REDACTED_PERSONAL_DATA: account activity]` | Account activity |
| `paymentMethod`, `paypalEmail` | `[REDACTED_PERSONAL_DATA: payment metadata]` | Payment-account metadata |
| `paymentAddress`, `paymentCity`, `paymentState`, `paymentZip` | `[REDACTED_ADDRESS]` | Payment address |
| `w9Verified`, `w9Type`, `w9DeliveryMethod` | `[REDACTED_PERSONAL_DATA: tax metadata]` | Tax-form metadata |
| `resetPasscode` | `[REDACTED_TOKEN]` if populated | Credential-recovery field; null in supplied response |
| `digitalWalletTotal` | `[REDACTED_FINANCIAL_BALANCE]` | Account balance |
| `conferenceDirectorEmail` | `[REDACTED_EMAIL]` | Third-party contact data |
| `playerNotes` | `[REDACTED_PERSONAL_DATA: account notes]` if populated | Potentially sensitive free text |

### Other account/role fields observed

`adminType`, `leagueAdmin`, `leagueAdminType`, `collegeName`, `conferenceLocked`,
`codeOfConduct`, `directorAgreement`, `playerServiceBackground`, `selectedDirectorID`,
selected-director name fields, conference logo/file fields, and conference-director
identity fields were also returned.

## Membership results

Both player and director membership structures repeat player/director identity and contact
data. Observed business fields include:

| Variable group | Examples/meaning |
|---|---|
| Membership identity | `playerMembershipID`, `playerMembershipName`, `playerMembershipDesc`, `playerMembershipType`, `playerMembershipSubType` |
| Season/bucket | `bucketID: 11`, `bucketDesc: "2025 - 2026"` |
| Lifecycle | Purchase timestamp/date, start date, expiry/end date, and status |
| Price/points | Membership price and points sold; financial retention requires review |
| Standing eligibility | `eventsResultsIncludedInStandings` |
| Feature permissions | Event discounts, text messaging, tour features, player-information access, membership processing, bracket restriction |
| Associated director | Director ID, identity, state, and email; contact fields require redaction |

## Nearby-director results

The endpoint returned nearby club, regional, and state directors. Each record can contain:

| Variable | Likely meaning |
|---|---|
| `directorPlayerID`, `directorID` | Director/player identifiers |
| `directorSubType`, `directorType` | Director role code and label |
| Name and state fields | Director identity/location |
| `fldPlayerLocationLat`, `fldPlayerLocationLng` | Precise third-party coordinates — redact/exclude |
| `distance` | Distance from requested player; likely miles but unconfirmed |
| `rn` | Result/rank sequence |

This data has no current prediction-engine requirement and should not be ingested by default.

## CPI and PPR observations

| Statistic | Value | Source context | Timestamp/window |
|---|---:|---|---|
| CPI | `6.35` | Authenticated player/account profile | `cPITimeStamp: "2026-07-22 13:29:30"` |
| PPR | `7.39` | Authenticated player/account profile | Window not stated |
| PPR-like precision value | `7.4153` | `playerPPRPlayerInfo` in player/account profile | Definition/window not stated |

These values must be stored with the endpoint and capture time. `playerPPR` and
`playerPPRPlayerInfo` must not be treated as interchangeable until ACL definitions are
known.

## Required decisions

1. Document the authorized session/login mechanism and ACL permission to use it.
2. Decide whether player profile access is needed or whether public endpoints provide the
   required CPI/PPR fields.
3. Use a strict field allowlist for normalized analytics data.
4. Decide whether raw authenticated payloads may be retained at all; if so, use encrypted,
   access-restricted storage with a retention/deletion policy.
5. Exclude contact, birth date, precise location, payment, W-9, wallet, reset-passcode,
   account-note, and nearby-director data from analytics by default.
6. Determine the definition and window of `playerPPR` and `playerPPRPlayerInfo`.
7. Determine whether CPI is scoped by season, membership, event type, or another context.

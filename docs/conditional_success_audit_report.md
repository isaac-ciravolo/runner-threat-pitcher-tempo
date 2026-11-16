# Conditional-success denominator audit

Executed 2026-11-16 under conditional_success_audit_protocol.md. Published run: a1c78511e1f340b2a34ae464ddad479a. All three input checksums match chronology-v2 provenance.

| Season | Windows | Recorded attempts | Existing success bucket | Existing unsuccessful bucket | History-eligible attempts |
|---|---:|---:|---:|---:|---:|
| 2022 | 137,732 | 1,797 | 1,554 | 243 | 1,796 |
| 2023 | 138,862 | 2,377 | 2,081 | 296 | 2,377 |
| 2024 | 136,487 | 2,462 | 2,161 | 301 | 2,462 |

No attempt window has multiple or unresolved classified records. One 2022 window, W-662498-68-pre, changes runner and is excluded from success history attribution. All recorded attempts have the existing terminal-window flag; this denotes absence of a following pitch within that opportunity, not necessarily the end of a plate appearance or inning. It must not be interpreted as a game-ending event.

The audit checks internal accounting only. The existing historical success definition explicitly includes advance, error_advance and advance_then_out; it has not yet been shown equivalent to official stolen-base credit or safe occupancy at closure. A separate model remains deferred pending event/movement review and target specification. The keyed local review file contains all 6,636 attempts and their source/action provenance; none is marked manually verified.

Code audit: disjoint exhaustive dispositions, nonnegative integer counts, eligibility reconciliation, immutable paired publication, input checksums and environment provenance. Tests exercise attribution exclusions, ambiguity, multiple actions and invalid counts/eligibility. All 67 repository tests passed. No old labels, histories or fitted results were modified. No 2025 feeds were opened.

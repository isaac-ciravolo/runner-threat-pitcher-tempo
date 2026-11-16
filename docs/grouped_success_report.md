# G3 conditional-outcome source review

The final audit run `519acf33bb724d989d802ac010b71a7e` accounts for all 8,141 recorded-attempt windows and 8,141 attempt records. It excludes 168 windows from opening-runner history attribution (42 in 2022, 69 in 2023, 57 in 2024); none have multiple or unresolved coarse attempt records. This leaves 7,973 attribution-eligible records. These exclusions remain visible rather than silently assigning a substitute runner's outcome.

Reviewing the complete outcome crosswalk exposed eight caught-stealing credits inside the coarse `recorded_success` category. The first audit's exception filter omitted that distinction; the amended filter retains these alongside five SB-credit paths with an out. Preserve the initial run `5e36d9cc2398413184df2b5c279e82a9` and its narrower five-case list for audit history.

All 13 final exceptions were inspected in the checksum-verified source movements and fielding credits:

- Eight CS-credit paths advance from first to second on a fielding error: games 662830/PA5, 663102/PA20, 663295/PA2, 716375/PA45, 717601/PA69, 744988/PA11, 746810/PA25 and 747005/PA34. Six contain dropped-ball error credit, one a fielding-error credit and one a throwing-error credit. Advancement is not synonymous with SB credit.
- Five SB-credit paths then end with an out: games 661511/PA38, 716728/PA41, 746014/PA58, 746247/PA65 and 746471/PA33. Three end out at third and two out at home. SB credit is not synonymous with surviving the play.

Within the attribution-eligible audit population, 6,250 windows have SB credit and 1,723 have CS credit; none have neither or both. These are source credit reasons, reconciled internally against the same provider's box scores, not independent video labels. The out flag examines movements at response-action indexes and is not a full closure-state survival label.

Do not fit a generic success target or multiply the current threat by the coarse parser success rate. The next conditional model needs a separately named estimand: credited SB conditional on a recorded attributed attempt is feasible, while safe advancement at completed-play closure requires an additional state audit. Freeze the selected target, exclusions, earlier-game success histories and chronological model protocol before fitting. Neither target alone estimates the causal run value of running or defensive attention.

The current attempt and response predictors use prior opportunity and attempt counts, not these coarse success counts. The distinction therefore changes the requirements for a later conditional-success model without relabeling the verified current fits.

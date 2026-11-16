# Closest-work methods audit

Checked 2026-11-16. This is a targeted methods review, not a systematic review or a completed originality gate. Existing abstract summaries remain in literature_review.md; this note distinguishes newly inspected methods from unresolved access.

## Verified full-text sections

[Powers et al., arXiv v2](https://arxiv.org/html/2601.15608v2), sections 1.2–1.3, 2.1, 3.1–3.3 and 4.1: the study combines 2022–2023 proprietary optical lead measurements with public context. Leads are measured at first pitcher movement. Pickoff probability uses a logistic mixed model with count, outs, disengagements, lead distance and pitcher effects. Runner-going, interruption and conditional-success components have separate definitions. Validation uses 20-fold cross-validation; policy uncertainty uses 100 bootstrap refits and transition resamples. Section 3.3 does not establish a later-season holdout. References identify Downey/McGarrity (2015, 2019), Loughin/Bargen (2008) and Stanley (2023) as relevant predecessors; these are tracing leads, not independently reviewed full texts.

Our comparison: public-feed windows and forward threat are different inputs and units. Our 2024 evaluation is chronological development evaluation. Our bootstrap intervals condition on fitted models and therefore cannot be presented as equivalent to uncertainty propagated through policy fitting. The narrower contribution remains provisional; different validation does not itself prove novelty.

## Access and remaining comparison

| Work | Evidence inspected on this pass | Unresolved work |
|---|---|---|
| [Price, Harvard thesis](https://dash.harvard.edu/entities/publication/69bbabbc-7b57-4fd4-b179-39b2cd164fa7) | Indexed institutional record identifies Zoe Kaur Price, June 2, 2026, and the thesis PDF; direct record access returned HTTP 429 | Obtain public full text; compare opportunity construction, predictor cutoffs, hierarchical structure and validation. Do not infer these from the abstract. |
| [Melville et al., Sloan](https://www.sloansportsconference.com/research-papers/the-pitchers-dilemma-a-game-theoretical-model-of-pickoffs-and-stolen-bases) | Web-tool PDF retrieval failed; direct public download subsequently succeeded; methods and references inspected | Independent replication and exact comparison of validation remain open; see full-text notes below. |
| [Loughin/Bargen](https://pubmed.ncbi.nlm.nih.gov/17852677/) | PubMed abstract; publisher full-text retrieval failed | Verify full opportunity/outcome definitions, estimation and references. |

Access failures describe this retrieval attempt, not permanent unavailability. No paywall or access control was bypassed. No project 2025 game feeds were accessed during the literature review.

## Audit disposition

Documentation-only stage: checked source support, section references, access qualifications and distinction between prediction and causal policy. No model or data definitions changed; executable tests are not relevant to this edit. Full-text comparison and reference tracing remain incomplete. Release-tempo and action-completeness gates remain pending genuine video observations; bibliographic work cannot clear them.

## Subsequent full-text and citation-chain checks

The 24-page Sloan PDF was downloaded from the conference's public link, checksummed in results/literature_fulltext_provenance.json, extracted locally and visually checked for identity. Methods sections 2.2–2.5 and 3 describe imported lead-based pickoff-success probabilities, Retrosheet transitions from 2019–2023, pitch-outcome learning from 2022–2023, and steal-success models using 2016–2025 attempts. Generic steal-success inputs include lead, sprint speed, engineered jump speed and catcher pop time; the pitch-specific variant adds pitch information. The equilibrium calculation uses backward solution of subgames and excludes foul balls. These conditional outcome models and strategic solutions differ from our proposed pre-play probability of a recorded attempt. Their parameters cannot simply be imported as a prospectively available threat score. No later-season validation policy was identified in the reviewed methods. Reading published work that includes 2025 does not access this project's locked 2025 feeds. [Conference source](https://www.sloansportsconference.com/research-papers/the-pitchers-dilemma-a-game-theoretical-model-of-pickoffs-and-stolen-bases).

Reference 14 resolves to the [Powers/Ramani/Hahn/Schaefer project repository](https://github.com/jfhahn2/pickoff-game-theory), so the two strategic sources are not independent origins of the pickoff-success component. Repository identity was checked; its code was not independently reproduced.

The [Downey/McGarrity 2015 publisher page](https://link.springer.com/article/10.1007/s11293-015-9464-4) exposes the abstract, notes, references and data appendix, while the main article remains subscription content. Its appendix defines 2,046 pitch-or-throw observations from June 9–13, 2010, with first base occupied alone, a binary throw-to-first outcome and a career stolen-base/opportunities proxy for runner quality. This is important prior runner-quality/pickoff-response overlap. The notes trace Turocy's 2004 inspection-game working paper and 2005 speed/offensive-performance article; their full texts still need review. A simple runner-quality association with pickoffs is therefore not an originality claim here.

The 2019 Downey/McGarrity publisher URL was not retrievable. Harvard's Price record also returned HTTP 429 on the direct public-access attempt, so no further retries or thesis-method claims were made. Remaining access gaps are not filled by inference from abstracts. The full originality gate remains open.

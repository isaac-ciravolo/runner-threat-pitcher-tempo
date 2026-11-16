# Closest-work methods audit

Checked 2026-11-16. This is a targeted methods review, not a systematic review or a completed originality gate. Existing abstract summaries remain in literature_review.md; this note distinguishes newly inspected methods from unresolved access.

## Verified full-text sections

[Powers et al., arXiv v2](https://arxiv.org/html/2601.15608v2), sections 1.2–1.3, 2.1, 3.1–3.3 and 4.1: the study combines 2022–2023 proprietary optical lead measurements with public context. Leads are measured at first pitcher movement. Pickoff probability uses a logistic mixed model with count, outs, disengagements, lead distance and pitcher effects. Runner-going, interruption and conditional-success components have separate definitions. Validation uses 20-fold cross-validation; policy uncertainty uses 100 bootstrap refits and transition resamples. Section 3.3 does not establish a later-season holdout. References identify Downey/McGarrity (2015, 2019), Loughin/Bargen (2008) and Stanley (2023) as relevant predecessors; these are tracing leads, not independently reviewed full texts.

Our comparison: public-feed windows and forward threat are different inputs and units. Our 2024 evaluation is chronological development evaluation. Our bootstrap intervals condition on fitted models and therefore cannot be presented as equivalent to uncertainty propagated through policy fitting. The narrower contribution remains provisional; different validation does not itself prove novelty.

## Access and remaining comparison

| Work | Evidence inspected on this pass | Unresolved work |
|---|---|---|
| [Price, Harvard thesis](https://dash.harvard.edu/entities/publication/69bbabbc-7b57-4fd4-b179-39b2cd164fa7) | Indexed institutional record identifies Zoe Kaur Price, June 2, 2026, and the thesis PDF; direct record access returned HTTP 429 | Obtain public full text; compare opportunity construction, predictor cutoffs, hierarchical structure and validation. Do not infer these from the abstract. |
| [Melville et al., Sloan](https://www.sloansportsconference.com/research-papers/the-pitchers-dilemma-a-game-theoretical-model-of-pickoffs-and-stolen-bases) | Conference abstract and linked PDF address located; PDF retrieval failed in the web tool | Inspect full model assumptions, data and validation before making method-specific comparisons. |
| [Loughin/Bargen](https://pubmed.ncbi.nlm.nih.gov/17852677/) | PubMed abstract; publisher full-text retrieval failed | Verify full opportunity/outcome definitions, estimation and references. |

Access failures describe this retrieval attempt, not permanent unavailability. No paywall or access control was bypassed. No project 2025 game feeds were accessed during the literature review.

## Audit disposition

Documentation-only stage: checked source support, section references, access qualifications and distinction between prediction and causal policy. No model or data definitions changed; executable tests are not relevant to this edit. Full-text comparison and reference tracing remain incomplete. Release-tempo and action-completeness gates remain pending genuine video observations; bibliographic work cannot clear them.

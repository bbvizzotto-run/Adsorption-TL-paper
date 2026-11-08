# Manuscript code/data release checklist

This checklist is for the authors before creating a public GitHub release and archiving it to Zenodo. Items marked **approval required** should not be inferred from the fact that a file is already present in a private repository.

## 1. Freeze the scientific package

- [ ] Confirm the submitted/revised manuscript version and exact title.
- [ ] Select the one benchmark result directory that supports the manuscript tables and figures; exclude smoke tests and intermediate/partial runs from article-facing results.
- [ ] Confirm the protocol JSON, partition manifests, run manifest, final metrics, and manuscript numbers agree.
- [ ] Keep simulated rows separate from measured observations and held-out predictions.
- [ ] Record the Git commit, protocol hash, input-data hash, result-file hashes, environment versions, and commands required to recalculate metrics.
- [ ] Preserve historical/prototype code separately and label its scope; do not imply it reproduces the revised endpoint benchmark.

## 2. Resolve rights and metadata

- [ ] Obtain approval from all relevant authors/data owners to redistribute the workbook, processed records, predictions, figures, and model weights (**approval required**).
- [ ] Choose separate licenses for software and data. Do not apply the root MIT software license to experimental records unless redistribution rights permit it.
- [ ] Confirm author names, affiliations, corresponding-author details, ORCIDs if available, funding, and acknowledgments.
- [ ] Confirm the publication status and bibliographic metadata before completing `CITATION.cff` or Zenodo metadata.
- [ ] Remove reviewer reports, response letters, correspondence, and any private or identifying information from the public release.

## 3. Prepare a clean release branch

- [ ] Create a dedicated branch for the paper release; do not rewrite or delete the existing history.
- [ ] Migrate only selected files into the structure in `RECOMMENDED_STRUCTURE.md` and preserve provenance in a migration map.
- [ ] Label the old engine, its JSON files, models, and figures as legacy until their relation to the final manuscript is verified.
- [ ] Remove smoke/debug outputs and unnecessary intermediate checkpoints from the release package, while retaining test fixtures needed for reproducibility.
- [ ] Update the root README, including the article title, task scope, quick-start commands, data availability, license, and citation instructions.
- [ ] Add minimal deterministic tests and a lightweight CI workflow; CI must not start the full computationally expensive benchmark.

## 4. Verify reproducibility

- [ ] Clone the release branch into a clean environment and install the exact locked dependencies.
- [ ] Run fast tests and protocol-integrity checks.
- [ ] Recalculate the published metrics from the archived measured out-of-fold predictions and verify them against the manuscript.
- [ ] Confirm all exclusions, condition IDs, folds, fractions, and seeds are documented and reproducible.
- [ ] Check the release for raw-data rights, secrets, private paths, local machine details, and large or irrelevant files.
- [ ] Verify that figure-generation scripts reproduce the included figures from the archived result tables.

## 5. Release and Zenodo archive

- [ ] Obtain author approval for the exact public release contents.
- [ ] Create an immutable GitHub release tag only after the manuscript and release package are frozen.
- [ ] Connect the repository to Zenodo and archive that exact release; review the generated record before publication.
- [ ] Add the version-specific DOI and citation to the final manuscript and README only after Zenodo assigns them.
- [ ] Keep the repository release tag, Zenodo files, and manuscript data-availability statement synchronized.

**Current status:** planning only. This checklist and the recommended structure are local documentation; no files have been moved, no release/tag has been created, and nothing has been pushed or made public.

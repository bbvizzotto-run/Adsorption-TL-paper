# Zenodo DOI for this GitHub repository

## Current repository state

The GitHub repository is public, but no GitHub release or Zenodo record has been created. This code-only repository does not include the experimental workbook or row-level results, so a release here will archive the code snapshot—not reproduce or independently recalculate the manuscript metrics. Confirm that this is the intended scope with all authors before minting the first DOI.

## Before creating a release

1. Review the public tree and confirm that no experimental records, private manifests, predictions, weights, correspondence, or credentials are present.
2. Confirm the software license and author list. The current `CITATION.cff` follows the author order on the manuscript title page. No ORCIDs or final publication metadata were present, so they were not guessed.
3. Decide whether the repository snapshot is ready to cite as software. If it is only a preliminary code snapshot, identify that status in the release notes and do not present it as a full reproducibility package.
4. Choose the version tag and update `CITATION.cff` and the README to the same version/date. The current software metadata is set to `0.1.0`; review that choice before tagging.
5. Do not add a DOI manually before Zenodo creates the record. If later updating a DOI in `CITATION.cff`, remember that the file is part of the repository version and changing it after a release creates a new code state.

## Connect GitHub and Zenodo

1. Sign in to Zenodo using the account that can access the GitHub repository and connect the GitHub account if it is not already linked.
2. Open Zenodo’s GitHub settings, click **Sync now**, find `bbvizzotto-run/Adsorption-TL-paper`, and enable it.
3. Confirm the repository appears as enabled. Zenodo’s integration only processes new GitHub releases created after the repository is enabled.

## Create and archive a GitHub release

1. On GitHub, open **Releases → Draft a new release**.
2. Create a version tag matching the reviewed `CITATION.cff` version, such as `v0.1.0` only if the authors approve that version.
3. Use release notes that state this is a data-free code snapshot and that the experimental dataset and numeric result files are not included.
4. Check the source branch, tag, release files, repository license, and public file tree, then publish the release.
5. Return to Zenodo’s GitHub page and wait for the release to be processed. Open the generated Zenodo record and verify its title, creators/order, description, license, version, GitHub tag, and archived files. Check that its external-resources section reports the archive status.
6. Copy the DOI shown on the Zenodo record only after it resolves to the correct version. Zenodo distinguishes a version-specific DOI from a concept DOI covering all versions; normally cite the version-specific DOI for reproducibility.

## After Zenodo assigns the DOI

- Add the version-specific DOI to the manuscript’s software/code availability statement and cite it in the software reference list if the journal permits.
- Add it to a subsequent README or citation-file update only if that update is intentional and versioned; do not edit the already archived release in a way that suggests its contents changed.
- Keep the GitHub tag, Zenodo version, `CITATION.cff`, and article citation consistent. Use the concept DOI only when the citation is intentionally meant to refer to the evolving software as a whole.

## Official instructions

- [Enable a GitHub repository in Zenodo](https://help.zenodo.org/docs/github/enable-repository/)
- [Archive a GitHub release from Zenodo](https://help.zenodo.org/docs/github/archive-software/github-upload/)
- [Zenodo’s CITATION.cff guidance](https://help.zenodo.org/docs/github/describe-software/citation-file/)
- [GitHub: referencing and citing content with Zenodo](https://docs.github.com/repositories/archiving-a-github-repository/referencing-and-citing-content)
- [Zenodo: version DOI and concept DOI](https://zenodo.org/help/versioning)

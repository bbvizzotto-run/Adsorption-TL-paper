# Zenodo DOI for this GitHub repository

## Current repository state

The GitHub release `v0.1.0` has been published and archived in Zenodo as [record 24059033](https://zenodo.org/records/24059033). Its version-specific DOI is `10.5281/zenodo.24059033`; the concept DOI representing all versions is `10.5281/zenodo.24059032`. This code-only archive does not include the experimental workbook or row-level results, so it archives the code snapshot but cannot reproduce or independently recalculate the manuscript metrics.

## Before creating a release

1. For every future version, review the public tree and confirm that no experimental records, private manifests, predictions, weights, correspondence, or credentials have been added without approval.
2. Keep the software license and author list consistent with the approved project metadata. The v0.1.0 `CITATION.cff` follows the author order on the manuscript title page; the current manuscript supplied no ORCIDs, which were not guessed.
3. Describe the scope accurately. This archive is a preliminary code snapshot, not a full reproducibility package.
4. For a future release, select a new version/tag and update `CITATION.cff`, the README, and release notes consistently before creating the tag.
5. The v0.1.0 DOI has now been added to the current `CITATION.cff`. Do not alter or replace files in the already archived v0.1.0 snapshot. A metadata/code change after this archive belongs in a new commit and, if it is to be archived, a new release/version.

## Connect GitHub and Zenodo

The GitHub–Zenodo integration is active for this repository, as confirmed by the archived v0.1.0 record. If this link is ever reset, sign in to Zenodo using the GitHub account with repository access, open Zenodo’s GitHub settings, click **Sync now**, find `bbvizzotto-run/Adsorption-TL-paper`, and enable it again.

## Create and archive a GitHub release

For future releases only: on GitHub, open **Releases → Draft a new release**, select a new tag matching the updated `CITATION.cff` version, and include notes identifying the archive as data-free. Recheck the public file tree, license, and release assets before publishing. Then wait for Zenodo to process it, verify the metadata and archived files, and record the new version-specific DOI. Zenodo assigns a concept DOI for all versions as well; normally cite the exact version DOI for reproducibility.

## After Zenodo assigns the DOI

- The v0.1.0 version-specific DOI is `10.5281/zenodo.24059033`; its concept DOI is `10.5281/zenodo.24059032`.
- Cite the version-specific DOI in the manuscript’s software/code availability statement and reference list if the journal permits.
- Keep the GitHub tag, Zenodo version, `CITATION.cff`, and software citation consistent. Use the concept DOI only when referring to the evolving software across versions.

## Official instructions

- [Enable a GitHub repository in Zenodo](https://help.zenodo.org/docs/github/enable-repository/)
- [Archive a GitHub release from Zenodo](https://help.zenodo.org/docs/github/archive-software/github-upload/)
- [Zenodo’s CITATION.cff guidance](https://help.zenodo.org/docs/github/describe-software/citation-file/)
- [GitHub: referencing and citing content with Zenodo](https://docs.github.com/repositories/archiving-a-github-repository/referencing-and-citing-content)
- [Zenodo: version DOI and concept DOI](https://zenodo.org/help/versioning)

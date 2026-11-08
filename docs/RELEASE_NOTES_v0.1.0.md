# v0.1.0 — preliminary code snapshot

**Preparation date:** 2026-11-07  
**Status:** preliminary software snapshot; not a full reproducibility package.

The `v0.1.0` tag is prepared as the proposed first software release; no GitHub Release has been published yet.

## Included

- Endpoint benchmark runner, plotting and diagnostic utilities.
- Standalone LSTM architecture constructor.
- Minimal tests that do not require experimental data or train the full benchmark.
- `CITATION.cff` with the manuscript title and the nine authors in the order shown on its title page.
- MIT license for the code, plus scope, provenance, data-rights and Zenodo documentation.

## Privacy and reproducibility scope

No experimental workbook, record-level observations, partition manifests, predictions, trained weights, reviewer correspondence or credentials are included. Therefore, this snapshot cannot independently reproduce or recalculate the manuscript's numeric results. The runner requires an authorized workbook path supplied by the user.

The public source was sanitized to remove machine-specific paths and a workbook-specific expected hash. It is consequently not byte-identical to the source used in the archived benchmark run. Do not describe this release as a bit-for-bit reproduction of that run or as a complete reproducibility package.

## Validation

The data-free unit tests passed in the prepared environment, and `CITATION.cff` validates against Citation File Format schema 1.2.0. The full endpoint benchmark is not part of the tests and requires separately authorized experimental data.

## Citation metadata

The current article manuscript did not provide author ORCIDs, an article DOI, journal volume, pages, or publication date. These fields are intentionally omitted rather than guessed. No Zenodo DOI has been assigned; add one only after Zenodo processes and publishes the corresponding GitHub release. Use the DOI for the exact archived version when citing this code snapshot.

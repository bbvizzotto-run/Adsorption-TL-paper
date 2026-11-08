# Recommended GitHub structure for the article

**Status:** release plan only. This document does not move, delete, or publish repository files. Apply the migration after the authors approve the public data/code scope and freeze the manuscript-matched benchmark.

## Proposed layout

```text
Adsorption-Transfer-Learning/
├── README.md                         # article scope, quick start, citation, release status
├── CITATION.cff                      # complete only after author/DOI confirmation
├── LICENSE                           # software license; not automatically a data license
├── DATA_LICENSE.md                   # separate data rights/terms, after author approval
├── .zenodo.json                      # optional Zenodo metadata for an approved release
├── .gitignore
├── pyproject.toml                    # package/test configuration, if package install is needed
├── environment/
│   ├── requirements-lock.txt         # exact versions used for the reported benchmark
│   └── environment-tested.json       # OS, Python, libraries, CPU/device and run metadata
├── src/
│   └── adsorption_tl/                # maintained reusable code; distinguish from legacy engine
├── data/
│   ├── README.md                     # provenance, schema, license/status, permitted use
│   ├── raw/                          # include only with explicit coauthor/data-owner approval
│   └── processed/                    # derived records; retain source-cell provenance and hashes
├── benchmarks/
│   └── endpoints/
│       ├── README.md                 # exact task, scope, limitations, reproduction commands
│       ├── protocol/
│       │   ├── protocol.json
│       │   ├── condition_partition_manifest.csv
│       │   └── target_fraction_manifest.csv
│       ├── scripts/                  # runner, resume/merge, metrics, plots, diagnostics
│       ├── tests/                    # protocol, integrity and metric-recalculation tests
│       └── results/
│           └── v1.0.0/               # frozen final outputs only, never smoke/debug outputs
│               ├── metrics/
│               ├── predictions/      # measured held-out predictions, if cleared for release
│               ├── figures/
│               └── run_manifest.json
├── figures/                          # final article figures and their generating sources
├── docs/
│   ├── data_dictionary.md
│   ├── reproduction.md
│   ├── limitations.md
│   └── article_release/              # release-plan/checklist material
├── tests/                            # fast tests that do not train the full models
└── .github/
    └── workflows/
        └── tests.yml                 # lightweight lint/unit tests; no full benchmark on CI
```

## How this maps to the existing repository

- Keep `benchmarks/endpoints/` as the manuscript benchmark; do not confuse it with the earlier `src/final_adsorption_ai_engine_v3.py` pipeline or its saved models. Until a deliberate migration is reviewed, describe the latter as a historical/prototype implementation rather than renaming or deleting it.
- The current benchmark folder contains the frozen protocol, scripts, final benchmark outputs, integration-test outputs, and diagnostic material in one tree. For a release, place only the final, verified run under `benchmarks/endpoints/results/v1.0.0/`; label integration/smoke material as tests or exclude it from the archival release. Keep simulations in a separate, explicitly labeled location and never mix them with measured held-out predictions or reported metrics.
- Preserve the current protocol JSON and manifests byte-for-byte when freezing a release. Record SHA-256 checksums for the exact protocol, dataset inputs, final outputs, and source revision in `run_manifest.json`.
- Move only after review: the root `data/` workbook and derived experimental records require explicit permission and an applicable data license before a public GitHub or Zenodo release. The existing MIT `LICENSE` must not be assumed to grant redistribution rights to experimental data, figures, or trained weights.
- Keep reviewer reports, response letters, emails, private drafts, local logs, virtual environments, caches, and intermediate model checkpoints out of the public release unless there is a specific, approved reason to archive them.

## Release principles

1. Make the manuscript task explicit: prediction of recorded apparent-removal endpoints under temperature-held-out evaluation, not validation of unmeasured kinetic trajectories.
2. Give code, experimental data, and figures explicit provenance and licensing; a software license does not settle data redistribution rights.
3. Separate observed measurements, held-out predictions, and simulated outputs in filenames, directories, schemas, plots, and documentation.
4. Make the exact environment and the command for recalculating reported metrics easy to find from the root README.
5. Keep the small CI suite fast and deterministic; the full benchmark is a manually launched, compute-intensive reproducibility run.
6. Create an immutable GitHub release/tag only after the final manuscript, protocol, results, data permissions, and checksums agree. Then archive that exact release to Zenodo and cite its version DOI.

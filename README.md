# Adsorption TL endpoint benchmark — code release

This repository contains a data-free code snapshot and documentation for the endpoint benchmark associated with the manuscript *Transfer Learning-Based Recurrent Neural Networks for Predicting Al(III) and Fe(III) Removal by Raw and Functionalized Silicas*.

## Release status

Published software snapshot: version `0.1.0`, tag `v0.1.0`, archived in Zenodo on `2026-11-08`. This is a preliminary code snapshot, not a full reproducibility package. The version-specific DOI is [10.5281/zenodo.24059033](https://doi.org/10.5281/zenodo.24059033); the concept DOI, which resolves to the latest version, is [10.5281/zenodo.24059032](https://doi.org/10.5281/zenodo.24059032). The archive details and guidance for later versions are in [`docs/ZENODO_RELEASE_STEPS.md`](docs/ZENODO_RELEASE_STEPS.md).

## Scope and reproducibility status

The benchmark evaluates prediction of recorded endpoint responses under temperature-held-out partitions. It does not validate unmeasured kinetic trajectories, identify kinetic rate laws, establish adsorption-exclusive removal, or by itself prove laboratory savings.

**No experimental workbook, record-level observations, condition manifests, held-out predictions, trained weights, or reviewer correspondence are included.** Consequently, this code-only repository cannot independently reproduce or recalculate article metrics without a separately authorized dataset. The code requires an explicit workbook path and never defaults to a developer-local file. Do not commit the workbook or generated plans/results unless data owners and all relevant authors approve their redistribution.

The runner is based on the analysis code used for the endpoint benchmark, with local paths and a workbook-specific hash restriction removed. Because of this sanitization, this repository version is not byte-identical to the exact source snapshot used in the archived benchmark. It should not be cited as a bit-for-bit reproduction of that run.

## Repository layout

- `benchmarks/endpoints/endpoint_tl_benchmark.py`: endpoint benchmark CLI.
- `benchmarks/endpoints/historical_architecture.py`: architecture constructor only; historical ingestion/training code and local paths are excluded.
- `benchmarks/endpoints/plot_endpoint_metrics.py` and `diagnose_endpoint_metrics.py`: analysis utilities for approved result files.
- `tests/`: quick data-free import and architecture checks.
- `docs/`: scope, data-rights, release, and provenance notes.
- `environment/`: location for an environment lockfile after validation.

## Setup and quick checks

Use a clean Python 3.12 environment, then install the pinned dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The full benchmark needs an authorized workbook matching the documented schema. No dataset is bundled. Once an authorized workbook is available, the command requires an explicit path:

```bash
python benchmarks/endpoints/endpoint_tl_benchmark.py plan \
  --workbook /path/to/authorized_workbook.xlsx \
  --out /path/outside/this/repository/endpoint_plan
```

The generated plan contains observation-level data, row/cell provenance, exclusions, and partition manifests. Keep it outside a public repository unless redistribution is explicitly authorized. The `.gitignore` blocks common generated record-level files as a safety measure, but authors must still review `git status` before every commit.

## License and citation

The software code is licensed under MIT; this does not license experimental data or authorize redistribution of workbook-derived records. The article title and author order in `CITATION.cff` were taken from the current manuscript. No article DOI, journal volume, or publication date were present in the manuscript; the Zenodo DOI above identifies the software archive, not the article.

This code-only release is not a self-contained reproducibility archive. Review `docs/SCOPE_AND_LIMITATIONS.md`, `docs/DATA_AND_LICENSE_POLICY.md`, and `docs/SOURCE_PROVENANCE.md` before citing or reusing it.

## Zenodo

The `v0.1.0` GitHub release has been archived in Zenodo. Cite its version-specific DOI when referring to this exact code snapshot. Use the concept DOI only when referring to the software across versions.

# Adsorption TL endpoint benchmark — code release

This repository contains a reviewed, data-free code snapshot and documentation for the endpoint benchmark associated with the manuscript on transfer learning for Al(III)/Fe(III) removal endpoints using raw and functionalized silicas.

## Scope and reproducibility status

The benchmark evaluates prediction of recorded endpoint responses under temperature-held-out partitions. It does not validate unmeasured kinetic trajectories, identify kinetic rate laws, establish adsorption-exclusive removal, or by itself prove laboratory savings.

**No experimental workbook, record-level observations, condition manifests, held-out predictions, trained weights, or manuscript response letters are included.** Consequently, this code-only repository cannot independently reproduce or recalculate article metrics without a separately authorized dataset. The code requires an explicit workbook path and never defaults to a developer-local file. Do not commit the workbook or generated plans/results unless data owners and all relevant authors approve their redistribution.

The runner is based on the analysis code used for the endpoint benchmark, with local paths and a workbook-specific hash restriction removed. Because of this sanitization, this repository version is not byte-identical to the exact source snapshot used in the archived private run. It should not be cited as a bit-for-bit reproduction of that run.

## Repository layout

- `benchmarks/endpoints/endpoint_tl_benchmark.py`: endpoint benchmark CLI.
- `benchmarks/endpoints/historical_architecture.py`: architecture constructor only; historical ingestion/training code and local paths are excluded.
- `benchmarks/endpoints/plot_endpoint_metrics.py` and `diagnose_endpoint_metrics.py`: analysis utilities for approved result files.
- `tests/`: quick data-free import and architecture checks.
- `docs/`: scope and data-rights notes.
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

The full benchmark needs an authorized workbook matching the documented workbook schema. No dataset is bundled. Once an authorized workbook is available, the command requires an explicit path:

```bash
python benchmarks/endpoints/endpoint_tl_benchmark.py plan \
  --workbook /path/to/authorized_workbook.xlsx \
  --out /path/outside/this/repository/endpoint_plan
```

The generated plan contains observation-level data, row/cell provenance, exclusions, and partition manifests. Keep it outside a public repository unless redistribution is explicitly authorized. The `.gitignore` blocks common generated record-level files as a safety measure, but authors must still review `git status` before every commit.

## Data, software license, and citation

The software license and data redistribution rights are separate. No public data license has been assigned in this scaffold. Confirm authorship, data rights, and a suitable software license before making this repository public. Complete `CITATION.cff` from `CITATION.cff.template` only after publication and, if used, Zenodo has minted a version DOI.

## Status

This is a private, clean-history code repository prepared for author review. No article data or metrics are published here. It is not yet a public reproducibility archive.

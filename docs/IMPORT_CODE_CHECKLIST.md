# Code import checklist

Do not copy the existing repository wholesale. Before adding any source file, inspect it for absolute paths, user names, raw-data filenames, embedded credentials, local output paths, and stale claims. Verify that it can run with an explicitly supplied data path and does not silently load data from a developer's machine.

The current benchmark source includes a developer-specific workbook path and a workbook SHA check. The historical architecture file also contains local paths in its standalone example. A sanitized or modified source file is not byte-identical to the code that generated the archived run; document the change and do not claim exact-run reproduction unless the version and protocol hashes are reconciled.

Include only reviewed code, a matching protocol, tests that run without private data, and clear instructions about data access. Keep full training out of automated CI.

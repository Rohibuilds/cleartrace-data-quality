# Synthetic fixture notes

The included CSV was newly authored for this archive. It is **not** the original demo data from the prior chat and contains no user data.

Expected candidate cases (actual counts depend on scan settings and whether headers/columns are interpreted semantically):
- One intentionally duplicated entire row.
- Blank `email`, whitespace around `city`, case variation in `city`.
- Invalid date such as `2026-02-30`.
- Nonnumeric salary `unknown` in otherwise numeric-like field.
- A large `salary` value to probe an **outlier candidate**, not prove an error.
- An ID with a formula-style field in `notes` to test safe CSV export behavior.

Testing caution: `-` and `+` in real numerical values can be meaningful; decide how export escaping works without corrupting valid typed numbers. Use explicit date and numeric column settings in tests.

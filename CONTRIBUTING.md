# Contributing

Thank you for looking at the pipeline behind The Care Ratings Open Nursing Home Data. This repository holds the build code, schema, tests and documentation. The data itself is published to the research store (`https://data.thecareratings.com/`) and archived at Zenodo; it is never committed here.

## What we welcome

- **Corrections to published data.** Open a *Data correction* issue and name the release, table, column and the facility (CCN) or state, with the CMS file that shows the right value. We confirm every report against the raw CMS files kept with the release before changing anything, and every confirmed correction is recorded in the public [corrections log](https://thecareratings.com/data/corrections/).
- **Bugs in the build**, header changes at CMS that the guards did not catch, and mistakes in the codebook or methodology. An issue with the release name and the command you ran is enough.
- **Documentation fixes** as pull requests.
- **New derived columns or tables** — please open an issue first so we can agree on the definition and its provenance tag before you write code.

## What we do not accept

- Values that do not come from a published CMS file. Every `cms` column is a CMS value cast to a type and nothing more; if CMS is wrong, the fix belongs at CMS (facilities can correct their record through their state survey agency and CMS), and it reaches the next release automatically.
- Facility-supplied data, scraped data, or any private source.
- Changes to a published release's files. Releases are immutable; a corrected release is rebuilt under the same name with a changelog note and a new manifest.

## Pull requests

1. Fork the repository and create a branch.
2. `pip install -e . pytest` and run `pytest -q`; add or update tests for what you change.
3. If you change the schema, regenerate the codebook: `python -m tcr_open_data.cli codebook --out docs/codebook.md` (CI checks that it matches).
4. If you change a derivation, describe it in `docs/methodology.md` and add a line to `CHANGELOG.md`.
5. Open the pull request. CI runs the tests without access to any secret; a maintainer reviews and merges. Direct pushes to `main` are not possible for anyone.

Pull requests from outside collaborators wait for a maintainer to approve the workflow run; that is a GitHub setting, not a judgement of the change.

## Licensing of contributions

Code contributions are accepted under the MIT license of this repository; documentation under CC BY 4.0. Contributions must not add data under terms that conflict with `LICENSE-DATA.md`.

## Security

If you find a credential or a way to write to the research store, do not open a public issue; use the [contact page](https://thecareratings.com/contact/) and mention "open data security".

# Publishing checklist

How a release goes from this repository to a public URL, a DOI and an archived copy. Steps marked **dashboard** need the Cloudflare or Zenodo web interface; everything else is a command.

## 1. Build and publish a release

```bash
tcr-open-data release --strict                     # download, build, validate, write the manifest
tcr-open-data publish --release releases/v2026.09 --raw raw/v2026.09 --live
```

Uploads set `Content-Type` and `Cache-Control` (release and raw objects `immutable` for a year; manifests revalidate every five minutes). To rewrite those headers on objects published before this was in place:

```bash
tcr-open-data headers --prefix releases/ --live
tcr-open-data headers --prefix history/ --live
```

## 2. Serve the bucket on `data.thecareratings.com` (dashboard, once)

1. Cloudflare dashboard → R2 → `careratings-open-data` → **Settings** → **Custom Domains** → **Connect Domain** → `data.thecareratings.com`. The `thecareratings.com` zone must be on the same Cloudflare account; Cloudflare adds the DNS record and a certificate. This makes the bucket publicly readable on that hostname only.
2. Leave **Public Development URL** (`r2.dev`) disabled; it is rate-limited and not for production.
3. Do **not** add a lifecycle rule that expires objects. Releases must stay retrievable indefinitely.
4. Check: `curl -I https://data.thecareratings.com/manifest.json` returns `200`, `content-type: application/json` and the `cache-control` above.

## 3. CORS (read-only)

```bash
tcr-open-data cors            # prints the rules from infra/r2-cors.json
tcr-open-data cors --live     # applies them (GET and HEAD from any origin)
```

If the API token cannot set bucket configuration (`AccessDenied`), paste `infra/r2-cors.json` in the dashboard: R2 → bucket → **Settings** → **CORS Policy**. Browsers can then read files straight from the store (for example DuckDB-Wasm or a fetch of `manifest.json`); nothing can write.

## 4. Site configuration

The app reads the store at `PUBLIC_OPEN_DATA_BASE_URL` (default `https://data.thecareratings.com`). Set `PUBLIC_OPEN_DATA_DOI` in Vercel to the **concept DOI** once Zenodo has minted it (step 5) so every page can cite it before a release-specific DOI is in its manifest.

## 5. DOI at Zenodo

1. **Dashboard, once:** create the Zenodo account that will own the records (an organization login is fine), then a personal access token at *Applications → Personal access tokens* with scopes `deposit:write` and `deposit:actions`. Export it as `ZENODO_TOKEN` (never commit it). For a rehearsal, do the same at sandbox.zenodo.org and export `ZENODO_SANDBOX_TOKEN`.
2. Rehearse: `tcr-open-data doi --release releases/v2026.08 --sandbox` creates a draft on the sandbox, uploads every file, writes the pre-reserved DOI into the local `manifest.json`, and prints the draft link. Open it and check the metadata.
3. Real run: `tcr-open-data doi --release releases/v2026.08` (draft) then either `--publish` or press **Publish** on zenodo.org. Publishing is irreversible.
4. Re-upload the release so the store carries the DOI: `tcr-open-data publish --release releases/v2026.08 --raw raw/v2026.08 --live`. The release page shows the DOI from `manifest.json`.
5. For later releases pass `--concept-record-id <record id of the first release>` so Zenodo files them as versions of one record under the concept DOI. Put the concept DOI in `CITATION.cff` (`doi:`) and in `PUBLIC_OPEN_DATA_DOI`.

## 6. After the site deploy

- Archive the hub and release pages: `curl -X POST "https://web.archive.org/save/https://thecareratings.com/data/"` and the same for `/data/releases/<release>/`.
- Submit `https://thecareratings.com/sitemap-pages.xml` in Search Console (the `/data/` pages and every release page are listed there).
- Add the release to `CHANGELOG.md` if the format or the derivations changed.

## 7. Going public

Flip this repository to public only after counsel has read `LICENSE-DATA.md`. Until then the download pages work regardless: the store, not the repository, serves the files.

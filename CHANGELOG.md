# Changelog

## 0.1.0 (2026-10-11)

The first public release.

- `Client(profile=...)` drives `odoo-cli`; `Client(organization=..., connection=...)` drives the
  governed `asao` CLI.
- `read`, `iterate`, `group` (grouping computed by Odoo), `print` (PDF), `operations`, `describe`,
  `execute`, and `to_frame` for pandas.
- `ops` lists every catalog operation by domain, for completion in the editor.
- Writes run only with `allow_writes=True`; unverified results only with `allow_unverified=True`.

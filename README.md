<h1 align="center">Lunele Hub</h1>

<p align="center"><strong>English</strong> · <a href="./README.es.md">Español</a></p>

<p align="center">
Extensions (and, in time, widgets and more) for the <a href="https://github.com/iMacnucintosh/lunele-shell">Lunele</a> shell, and the catalogue that <strong>Things</strong> reads.
</p>

## What is in it

| Extension | What it does |
| --- | --- |
| [`tasks`](extensions/tasks) | A to-do list in the dashboard carousel |
| [`hydration`](extensions/hydration) | Track the water you drink, with reminders |
| [`games`](extensions/games) | Your Steam library on the dashboard: profile, achievements, sessions and an activity calendar |
| [`vpn-forticlient`](extensions/vpn-forticlient) | FortiClient VPN connections (openfortivpn) in Settings → Network, with OTP codes and client certificates |

The full catalogue, with versions, download links and `sha256`, is in [`index.json`](index.json).

## Install an extension

With **Things** (the **Lunele** section): click an extension to see its page (description, screenshots, requirements, what it touches on your computer and news) and then **Install**. It asks for confirmation and, only if the extension needs administrator rights, for your password. From a terminal: `lunele ext list`, `lunele ext install <zip>` and `lunele ext remove <id> [--purge]`.

For a loose zip: in Things, **Install from zip**, or `lunele ext install <zip>`. Removing an extension (the bin, with an optional box to delete its settings and data) also removes what it installed as administrator.

## The page of each extension (`store/`)

What Things shows when you open an extension (long description, highlights, news by version, links and screenshots) lives in `extensions/<id>/store/` and **is not inside the zip**:

- `details.json`: `about`, `highlights` (up to 6), `author`, `license`, `links` (`source`, `issues`, `web`; https only), `changelog` (`version`, `date`, `changes`) and `screenshots` (`file` + `caption`).
- `screenshots/`: png, jpg or webp images of up to 1.5 MB (at most 6). No personal data: use sample data.
- `i18n/<language>.json`: English text → translation, for all of the above.

`scripts/build.py` validates everything and generates `store/<id>.json` (what Things downloads); the index links it. The **requirements** (`requires`) and what it **touches on the computer** (`system`, `data`) come from the manifest, so they are not written twice.

## For those who publish here

Each extension is a folder `extensions/<id>/` with its `manifest.json` (see Lunele's `AGENTS.md`, the "Extensions" section). The rules of the project apply here too:

- **i18n always:** every visible text goes through `Tr.*` and is translated; the extension's catalogue lives in `i18n/es.json`.
- **Nothing private:** no credentials, hosts or data of your network. Each person's configuration lives in their own `shell.json` and files.

```sh
scripts/build.py            # generates dist/<id>-<version>.zip and rewrites index.json
scripts/build.py --check    # checks index.json and store/ are up to date and no published version changed its zip (for CI)
python3 -m unittest discover -s tests   # tests (store pages, zips, the Games scripts)
scripts/publish.sh <id>     # publishes the zip as the release <id>-<version>
```

To ship a new version: raise `version` in the manifest, `scripts/build.py`, commit, `scripts/publish.sh <id>`. The zips are deterministic: the same sources give the same bytes.

## License

GPL-3.0, like Lunele (see [`LICENSE`](LICENSE)). Copyright (C) 2026 Manuel López Mallorquín.

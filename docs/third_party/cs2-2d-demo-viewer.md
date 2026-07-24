# CS2 2D Demo Viewer (third party)

## Upstream

- Repository: https://github.com/sparkoo/csgo-2d-demo-viewer
- Pinned commit: `faa2fd3b052af0968cef2e3c4aeecc218f798590`
- License: MIT (Copyright (c) 2023 Michal Vala)
- Local path: `third_party/cs2-2d-demo-viewer` (git submodule)

The upstream `LICENSE` file is preserved in the submodule root. This project does not
modify upstream sources for the POC; it only launches the upstream Vite dev server locally.

## Scope

Included in this POC:

- Git submodule pin
- Local viewer startup via `python -m src.main --replay-demo ...`

Excluded from this POC:

- Backend download proxy
- Firebase deployment
- FACEIT browser extension integration

## Attribution

CS2 2D Demo Viewer — Copyright (c) 2023 Michal Vala — MIT License.

Uses [demoinfocs-golang](https://github.com/markus-wa/demoinfocs-golang) in the upstream parser.

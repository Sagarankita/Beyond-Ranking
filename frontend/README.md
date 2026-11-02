# Beyond Ranking Decision Studio

Read-only React frontend for the repository's versioned reporting, benchmark, scenario,
evidence, and provenance artifacts.

## Run locally

Node.js 20 or newer is recommended.

```bash
cd frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The development command first
syncs the allow-listed saved artifacts and the legacy static viewer into `public/`.

The preserved viewer is available at
[http://127.0.0.1:5173/legacy/index.html](http://127.0.0.1:5173/legacy/index.html).

## Verify and build

```bash
npm run typecheck
npm test
npm run build
```

The production bundle is written to `frontend/dist/`. Serve that directory from any
static host; the app uses a relative base and hash navigation.

## Data boundary

`npm run sync-artifacts` copies a deliberate allow-list of repository artifacts and
writes a SHA-256 catalog. The browser verifies those hashes and validates required
columns before rendering. Generated `public/data/` and `public/legacy/` directories are
ignored by Git and can always be rebuilt.

This application does not run an optimizer or reproduce evaluator math. See
`docs/frontend/ARCHITECTURE.md`, `DATA_CONTRACTS.md`, and `BACKEND_MAPPING.md` for the
boundary and source mapping.

# Deprecated React fallback

This React/Vite implementation is retained temporarily for rollback comparison. The
supported frontend is now the Python Streamlit application in `streamlit_app/`.

Use the repository-root instructions:

```bash
python -m pip install -r requirements-ui.txt
python -m streamlit run streamlit_app/app.py --server.address 127.0.0.1 --server.port 8501
```

Do not add new features here. Remove this directory only after the agreed fallback
window and Streamlit parity acceptance.

## Legacy React run command

## Run locally

Node.js 20 or newer is recommended.

```bash
cd frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173).

The preserved viewer is available at
[http://127.0.0.1:5173/legacy/index.html](http://127.0.0.1:5173/legacy/index.html).

## Legacy verification

```bash
npm run typecheck
npm test
npm run build
```

The production bundle is written to `frontend/dist/`. Serve that directory from any
static host; the app uses a relative base and hash navigation.

## Legacy data boundary

`npm run sync-artifacts` copies a deliberate allow-list of repository artifacts and
writes a SHA-256 catalog. The browser verifies those hashes and validates required
columns before rendering. Generated `public/data/` and `public/legacy/` directories are
ignored by Git and can always be rebuilt.

Neither frontend runs an optimizer or reproduces evaluator math. See
`docs/frontend/ARCHITECTURE.md`, `DATA_CONTRACTS.md`, and `BACKEND_MAPPING.md` for the
boundary and source mapping.

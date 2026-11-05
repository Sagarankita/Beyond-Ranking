# Streamlit Decision Studio

The supported read-only dashboard for versioned Beyond Ranking artifacts.

```bash
python -m pip install -r requirements-ui.txt
python -m streamlit run streamlit_app/app.py --server.address 127.0.0.1 --server.port 8501
```

The application validates every allow-listed file against
`streamlit_app/data/catalog.json` before rendering. It does not execute an optimizer,
repair candidates, or duplicate evaluator math.

Run tests with:

```bash
python -m unittest discover -s streamlit_app/tests -v
```

Refresh the integrity catalog only after intentionally reviewing changed versioned
artifacts:

```bash
python -m streamlit_app.data.catalog --write
```

# Thalamus viewer (frontend)

React + Cytoscape.js graph explorer. Built assets are committed to
`src/thalamus/viewer/static/` and served by the Python viewer API
(`src/thalamus/viewer/web.py`), so `thalamus visualize` works without a Node
toolchain present.

```bash
npm install
npm test          # vitest
npm run lint      # oxlint
npm run build     # -> ../src/thalamus/viewer/static
npm run dev       # dev server; proxies /api to http://127.0.0.1:8000
```

For dev, run the API separately on port 8000.

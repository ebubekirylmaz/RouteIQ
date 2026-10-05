# RouteIQ dashboard

React, TypeScript and Vite. Data comes from the RouteIQ API with TanStack Query, charts use Recharts, styles are CSS Modules.

## Development

Start the API from the repository root (the dashboard needs it for data):

```bash
uvicorn routeiq.api:app --reload
```

Then, in this folder:

```bash
npm install
npm run api:types     # generates src/api/schema.d.ts from openapi.json
npm run dev           # http://localhost:5173/dashboard/
```

The dev server forwards the API paths (`/review`, `/stats`, ...) to `http://localhost:8000`, so the browser sees one origin and no CORS setup is needed. Set `ROUTEIQ_API_URL` to use another address.

## Tests

```bash
npm test              # one run
npm run test:watch    # re-runs on every change
npm run typecheck
```

Vitest runs the tests in jsdom, and MSW stands in for the API (`src/test/`). A request without a handler fails the test.

The test tools are pinned to versions that work on Node 20 (`vitest` 4, `jsdom` 29, `@testing-library/jest-dom` 6.9, `msw` 2). Their newest releases need Node 22.12 or later, so they can move up together with Node.

## Build

```bash
npm run build         # type-checks, then writes dist/
```

The API serves `dist/` under `/dashboard/` when it exists (`ROUTEIQ_DASHBOARD_DIR` overrides the folder). The app is built for that base path, so the router uses `basename="/dashboard"`.

## When the API changes

`openapi.json` is the committed schema the TypeScript types are generated from, and a Python test fails when it is out of date:

```bash
python scripts/export_openapi.py     # from the repository root, with the virtual environment active
cd dashboard && npm run api:types
```

## Layout

```
src/
├── api/client.ts       fetch wrapper, ApiError, X-Total-Count, query strings
├── api/endpoints.ts    one typed function per endpoint
├── api/schema.d.ts     generated, not committed to be edited by hand
├── queryClient.ts      retry and cache defaults
├── components/         Layout
└── pages/              ReviewQueue, Overview, Charts, History
```

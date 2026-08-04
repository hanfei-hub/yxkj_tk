# Electron Frontend

This directory is the Electron migration frontend. It reuses the existing FastAPI backend and does not change backend routes.

## Development

```powershell
cd electron
pnpm install --ignore-scripts
pnpm dev
```

The default API endpoint is `http://120.26.207.89`. For a different environment, set `tk_api_base` in local storage or update `src/api.ts` during development.

## Build

```powershell
pnpm install --ignore-scripts
pnpm run build
```

The Electron shell is configured for portable and NSIS Windows packages with `pnpm run package` after approving the required Electron Builder install scripts.

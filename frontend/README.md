# Frontend (Phase 2)

Preact + TypeScript + Vite, built on the Windows PC (no Node on the Pi) into
`frontend/dist/`, which the Pi serves. Until it exists, the backend serves the
Phase 1 placeholder `setup-ui/home.html` at `/`.

Fonts: the TTFs in `/fonts` (served at `/fonts/...`) are the same files the
server-side renderer uses, so screen and paper match (BUILD_PLAN override 2).
Convert to woff2 for the SPA in Phase 2.

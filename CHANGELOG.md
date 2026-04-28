# Changelog

## 2026-04-26
- Initialized the AI-first shift planner monorepo plan in code.
- Added Docker Compose services for Postgres, FastAPI backend, FastMCP server, and Next.js frontend.
- Added project governance docs and standing FastMCP/i18n documentation rules.
- Added a FastMCP server with read resources and guarded mutating tools backed by the shared backend service layer.
- Added a bilingual Next.js PWA shell and core admin screens.
- Replaced Docker `psycopg[binary]` dependency usage with portable `psycopg` plus system `libpq5` to support Linux ARM builds.
- Changed the host Postgres port default to `5433` to avoid conflicts with local Postgres installations.
- Added matrix-first planning with `PlanningCell`, `DoctorPeriodNote`, REST endpoints, FastMCP resources/tools, validation, CSV export, and frontend matrix editing.
- Added planning-month creation directly to the matrix editor so new matrices can be created and loaded without using API docs.
- Made doctor and shift type lists load automatically when their routes are opened.
- Made the matrix/wishlist screen load the latest planning period automatically and documented Docker hot-reload behavior.
- Removed per-cell matrix save buttons; matrix status changes now save immediately and comments autosave after editing, with a top-level manual save/reload action.
- Added a separate final roster matrix backed by `RosterSlot` and `RosterSlotAssignment`, with rows as days and columns as active shift types.
- Added REST endpoints, CSV export, validation, and FastMCP resource/tools for the final roster matrix.
- Changed `/roster` to use the new shift-by-day final roster editor while `/requests` remains the doctor-by-day wishes matrix.
- Removed final roster comment editing from the UI and CSV export.
- Added wishes/status pills to final roster cells so assigned doctors' conflicts are visible inline.
- Added a unified `/planning` workspace with shared month selection, wishes, final roster, inline conflict summary, CSV exports, and workload stats.
- Simplified the navbar to Dashboard, Planning, Doctors, Shift Types, and Settings.
- Removed standalone frontend pages for wishes, roster, validation, and export while keeping backend validation/API compatibility.
- Moved doctor/month notes into per-doctor buttons in the wishes matrix header with modal editing.

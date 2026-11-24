# Print plan (Step 0 survey, 23 Nov 2026)

Maps `print-templates/IMPLEMENTATION_BRIEF.md` onto the real code. `print-templates/PRINT_TEMPLATES.md`
is the source of truth for anything printed.

## What exists

| Brief assumes | Real location |
|---|---|
| Renderer | `backend/walloftext/render/document.py` `Renderer.render(doc) → RenderResult` (block documents, 384-dot mode "1"). Used by `/api/preview`, `/api/print`, `Services.print_document` (button, schedules, guest, remote), template validation |
| Queue | `queue/worker.py` stores the rendered bitmap; the driver prints it `copies` times; rotation 180° only on the way to the printer |
| Fonts | Repo `fonts/` (rsynced to `/opt`), registry `render/fonts.py` (Create fonts: Space Mono, VT323, Silkscreen, Inter) |
| Weather | `sources/weather.py` `OpenMeteo.forecast()` → `Forecast` (1 day, current temp/code only). Cached 3 h in memory and the kv store (`weather_cache`) by `sources/hub.py` |
| Tasks | `sources/google_tasks.py` `GoogleTasks.tasks()` → `[{title, due}]` (first list only when none chosen, 15 max) |
| Calendar | `sources/calendar.py` `parse_events()` → `Event(title, start, end, all_day, calendar, location)` |
| Slip builders | `sources/hub.py` `Sources.section_blocks()` (date, weather, agenda, tasks, fortune, quote, countdown, shopping, divider, message); `actions.py` (`fortune_doc`, weather/agenda via hub); `templates_lists.py` `Lists.document()` (shopping); `remote/pipeline.py` `Pipeline.document()`; `api/access.py` `guest_doc()`; `api/printing.py` test page; `render/slips.py` setup/connected slips |
| Button and chips | `actions.run()` (`weather_now`, `agenda_today`, `random_fortune`, `shopping_list`), called by `Services.on_gesture` and `api/actions.py` |
| Routines | `scheduler/engine.py` → `Sources.routine_doc(sections, ctx)`; conditions in `Scheduler.check_conditions` (`has_tasks` = "Only if any are due") |

## Mapping

| WP | Where |
|---|---|
| WP1 kit | New `render/kit/` (`fonts.py` tokens and font cache, `nodes.py` layout primitives, `slip.py` slip builder + end mark). Fonts in repo `fonts/` with `OFL-*.txt` |
| WP2 icons | `tools/build_icons.py` → `backend/walloftext/assets/wx/<name>-<size>.png` (inside the package so `pip install` ships them); loader `render/kit/icons.py` |
| WP3 weather | Provider request widened in `sources/weather.py`; normaliser `sources/normalise.py`; templates `render/kit/weather.py`; hooks in `hub.py` and `actions.py` |
| WP4 tasks | `google_tasks.py` returns full task fields; normaliser in `normalise.py`; template `render/kit/todo.py`; `has_tasks` now means "any overdue or due today" |
| WP5 calendar | `calendar.py` reads attendees, description, conference links, multi-day ends; 14-day lookahead; template `render/kit/itinerary.py` |
| WP6 other slips | `render/kit/system.py` (note, guest, message, shopping, fortune, quote, countdown, date, test page, unavailable). End mark added in `Renderer.render()` (one per document = one per copy, since copies reprint the bitmap) and in `render/slips.py` |
| WP7 goldens | `backend/tests/golden/*.png`, `tools/update_goldens.py`, `tests/test_print_kit.py`, `tests/test_goldens.py` |

New document block: `{"type": "slip", "template": "<name>", "data": {...}}` renders one full kit slip.
Documents made only of slips and `cut` rules render edge to edge (no legacy margins or gaps).

## Not present (skipped or adapted)

- **No quick-note feature** outside Create, so the Note slip is used by the "Your own line" routine section only; Create prints keep their own layout and just gain the end mark.
- **Shopping list has no categories** (`list_items` has text only), so the slip has a single "TO BUY" section instead of FRIDGE / CUPBOARD / OTHER.
- **Countdowns don't store the day they were set**; `set_on` is now saved with the section the first time it is saved, and the meter is left out until it exists.
- Icons are rendered on the Pi with `cairosvg` (dev-only dependency); only the PNGs are used at run time.

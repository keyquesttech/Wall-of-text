# Print implementation brief

For Claude Code · 23 Nov 2026 · Scope: **printed output only**

The app is already built: the frontend, backend, queue, printer driver, schedules, settings, button, LED and connections. This brief covers one job: make everything that comes out of the printer match the final print designs. Don't rebuild or restyle anything else.

**Read in this order:** this brief → `PRINT_TEMPLATES.md` (the final design spec, which is the source of truth for every dimension and rule) → the `reference/*.dc.html` mockups when you need to see a layout. The rendered designs are on the canvas linked at the top of `PRINT_TEMPLATES.md`.

**Precedence:** for anything printed, `PRINT_TEMPLATES.md` wins over `BUILD_PLAN.md` and `design-handoff/HANDOFF.md`. For everything else, the existing code and `BUILD_PLAN.md` stand. Never edit `design-handoff/` or `print-templates/reference/`.

---

## 1. What "done" looks like

1. Every print is rendered by one shared **print kit** (fonts, type scale, tones, rules, boxes, icons, QR and end mark) on a 384-dot, 1-bit canvas, exactly as in `PRINT_TEMPLATES.md` sections 2–4.
2. **Four data slips** follow their specs:
   - the weather briefing, in all 14 conditions (§5)
   - Weather now, printed by the button and the quick chip (§6)
   - To do from Google Tasks, with its all-clear empty state (§7)
   - the itinerary from Google Calendar, with its free-day empty state (§8)
3. **Every other slip** (notes, guest notes, remote messages, the shopping list, fortunes, countdowns and the test page) follows the design system (§8b).
4. **Every printed copy ends with the end mark** (§4.7), added by the print pipeline. That includes Create prints and routines (one per routine).
5. **The "As printed" preview and the paper are the same bitmap** for every golden document.
6. **Golden-image tests** cover every template and empty state, and pass.
7. **One real print of each golden slip** has been checked on the Pi (section 5 of this brief).

## 2. Step 0: survey before you write code

The codebase was built from `BUILD_PLAN.md`, but names and structure may differ. Before changing anything, find and write down in `docs/PRINT_PLAN.md`:

- **The renderer.** Where documents become a 1-bit image: the `render/` module, the preview endpoint, and how the queue calls it.
- **Current fonts and assets.** What's bundled now, and where it lives.
- **The weather provider (Open-Meteo).** What fields it fetches today and how it caches them.
- **The tasks and calendar sources.** The Google Tasks and Google Calendar API clients (`sources/google.py`): what they return.
- **Who builds today's slips.** Which code currently produces the weather, tasks, agenda, note, guest, remote, shopping, fortune, countdown and test-page prints.
- **The button and chip actions.** Where "Print weather now" and the quick chips are wired.
- **Routines.** How they combine blocks into one job.

Then map each work package below onto those real locations. If something this brief assumes doesn't exist (for example, there's no shopping-list print yet), note it and skip that slip; don't build new features. Only then start WP1.

## 3. Work packages, in order

Each package ends with passing tests and a line in `docs/PROGRESS.md`.

### WP1: Print kit (layout primitives)

The foundation everything else uses. Suggested home: `render/kit/`, or whatever fits the existing renderer.

- **Fonts.** Bundle the static TTFs with their OFL license files: Space Grotesk Medium and Bold; JetBrains Mono Regular, Bold and ExtraBold. Put the same woff2 files in `frontend/public/fonts/` if the preview UI needs them. Render with `ImageDraw.fontmode = "1"`, never anti-aliased.
- **Tokens.** Turn the type scale (§3), spacing, border widths and the three dither tiles (§4.2) into code constants.
- **Primitives.**
  - Text, with wrapping, a line cap and "…"
  - Row, Column and Grid
  - Box (border and padding), inverted Band, Tag
  - Rule (`hr`, `hr2`, `hrd`, `cut`, section rule)
  - Checkbox (small and large), Meter, BarChart
  - QR (segno, error level M, 3 dots per module, 4-module quiet zone)
  - Icon, Spacer, EndMark
- **The slip builder.** `header(source, right_text)` (there is no footer) and `render(blocks) → PIL.Image mode "1"`. The canvas is 384 wide, height auto, with margins 20/30/36. It appends no end mark itself; the pipeline does that (WP6).
- **Tests.** One per primitive, checking size, margins and that every pixel is pure 0 or 1. Then render a kit test slip and compare it by eye with the "Print kit" and "Print design system" boards.

### WP2: Weather icons

- `tools/build_icons.py`, run on the PC, renders `print-templates/icons/*.svg` with resvg or cairosvg at 168, 104, 96, 52, 44 and 40 dots, then thresholds the results to 1-bit PNGs in `backend/assets/wx/`. Commit the PNGs; the Pi never renders SVG.
- An icon loader keyed by `(condition, size)`, with a test that every condition exists at every size.

### WP3: Weather slips

- **Normaliser:** from the existing Open-Meteo data to the shape in `samples/weather.json`. Add any missing fields to the provider's request (hourly visibility, gusts, UV, snowfall, sunrise and sunset). Work out the moon phase locally.
- **Condition chooser:** the WMO mapping plus the overrides in §5.1, with the thresholds in config.
- **Templates:** `weather_briefing(data)` (§5.2–5.3) and `weather_now(data)` (§6).
- **Hooks:** the "Weather" schedule or routine source uses the briefing. The button's "Print weather now" action and the "Weather now" chip use Weather now. On provider failure, print "Weather unavailable" with the last cached time.
- **Golden tests:** the sample, plus one briefing per condition built from the `D` table in `reference/Weather.dc.html`.

### WP4: To-do slip

- **Normaliser:** from the Google Tasks client to `samples/tasks.json`. Read the due time from the start of the notes ("10:00 …") or an "@10:00" in the title, and strip it from the printed text (§7.1).
- **Logic and templates:** Big 3 selection, the groups, numbering, due tags and the all-clear state (§7). Respect the schedule's "Only print if any are due" condition.

### WP5: Itinerary slip

- **Normaliser:** from the Google Calendar API client to `samples/calendar.json`. That covers all-day versus timed events, location splitting, attendee names, cleaned descriptions and conference links (§8.1).
- **Template:**
  - the timeline with an event ticket for each event
  - gap rows between events
  - overlap notes
  - a "Next up" header worked out from the print time
  - real map QR codes
  - the free-day state, looking up to 14 days ahead (§8)

### WP6: Every other slip, the end mark and routines

- **Other slips:** rebuild the existing note, guest note, remote message, shopping list, fortune, countdown and test-page layouts with the kit, following §8b. Only restyle slips that already exist.
- **Create prints:** keep their content exactly as the person designed it. Only make sure the end mark is added.
- **End mark:** add it in the print pipeline after rendering, once per copy and once per routine, and in the preview (§4.7).
- **Routines:** the block slips joined by `cut` rules, with one end mark at the end.
- **Tests:** a test proving every job type gets exactly one end mark per copy.

### WP7: Golden images and preview parity

- `tests/golden/`: one PNG per sample and state, plus `tools/update_goldens.py` to regenerate them on purpose.
- A test that the `/api/preview` PNG and the bitmap sent to the mock printer are byte-for-byte equal for every golden.
- **Edge-case documents:**
  - 40-character titles
  - 3-line notes
  - 9 events, overlapping events, and an event that runs past midnight
  - 12+ tasks
  - no attendees, no location
  - negative temperatures
  - a 0% rain day and a 100% rain day

  None may clip, overlap or exceed 384 dots.

### WP8: Real-printer check on the Pi

Print every golden slip once, then check:

- the darkness setting gives solid bands without smearing
- the end mark (rules and black tag) and the `d50` bars don't streak or stall
- 12-dot labels are readable
- each QR code scans with a phone and opens the right place
- icons read clearly at 40 dots
- the end mark makes untorn slips easy to tell apart

Record the results in `docs/PROGRESS.md`. Tune printer settings (heat, band size, pause), not the design. If a design change seems needed, list it as a question instead of changing it.

## 4. Decisions already made (don't re-ask)

- **Fonts:** Space Grotesk and JetBrains Mono only. Create-mode print fonts stay as they are.
- **Footer:** none, on any slip. Context such as update time or list names goes in the header row.
- **End mark:** one per printed copy and one per routine, added by the pipeline.
- **Due times:** parsed from the task text, because the Tasks API drops them. With no time found, show the date tag only.
- **Weather warnings:** none. Open-Meteo doesn't provide them.
- **QR codes:** real codes, never the mockups' placeholder pattern.
- **Sample content:** all names, places and forecasts in the mockups are sample data. Never hard-code them.

## 5. Constraints

- The Pi has no internet at times. Fonts, icons and fortunes must be local.
- Keep render time under about 1 s per slip on a Pi 4. Cache loaded fonts and icon PNGs.
- No grey pixels, nothing under 12 dots of text height, nothing under 2-dot strokes, and nothing wider than 384 dots.
- Don't touch the UI beyond what the "As printed" preview gets automatically from the new renderer.

## 6. Start prompt

Paste this into Claude Code from the repo root:

> Read `print-templates/IMPLEMENTATION_BRIEF.md`, then `print-templates/PRINT_TEMPLATES.md`. Do Step 0 only: survey the existing renderer, data sources, slip builders, button actions and routines, and write `docs/PRINT_PLAN.md` mapping each work package (WP1–WP8) to real files and functions. List anything the brief assumes that doesn't exist. Don't change any code yet. Stop and show me the plan.

After the plan is approved, run one package per session: "Do WP1 from the print brief. Stop when its tests pass."

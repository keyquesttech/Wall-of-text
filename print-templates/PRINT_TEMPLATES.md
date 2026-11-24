# Wall of Text — Print templates

Version 2 (final) · 23 Nov 2026 · Design canvas: https://claude.ai/artifact/NJffJaVJZMvnBnBP3XmjeV (rows "Final — merged prints", "Weather — every condition" and "Print design system")

This is the build spec for the printed slips: the weather briefing, the weather slip printed when the button is pressed, the to-do list, and the day's itinerary. It sits next to `BUILD_PLAN.md` and `design-handoff/HANDOFF.md`. Where this file covers a printed template, this file wins. For everything else, `BUILD_PLAN.md` still wins.

## 0. What's in this folder

| Path | What it is |
|---|---|
| `PRINT_TEMPLATES.md` | This spec, the final design handoff. Source of truth for what each slip contains, its layout in dots, and the data rules |
| `IMPLEMENTATION_BRIEF.md` | The work plan for building the print part into the existing app: order of work, integration points, tests, start prompt |
| `print-kit.css` | The CSS used in the mockups. Read it for exact sizes, borders and dither patterns. Not used at runtime |
| `icons/*.svg` | The 14 weather icons, 64 × 64 viewBox, black on white. Source for the icon PNGs (section 4.6) |
| `reference/*.dc.html` | Design mockups of each slip with sample data, plus `System.dc.html`, the design system for every other slip. Pictures to match, not code to run (section 9) |
| `samples/*.json` | Normalised sample data for each template. Use them for golden-image tests |

## 1. Which slip prints when

| Trigger | Slip | Reference | If there's nothing to show |
|---|---|---|---|
| Schedule or routine with source **Weather** (the "weather briefing") | **Weather briefing**: one of 14 condition layouts | `Weather.dc.html` with `layout="hero"`, `cond=<condition>` | Never empty. If the provider is down, print "Weather unavailable" (BUILD_PLAN §7) |
| Arcade button action **Print weather now**, and the "Weather now" quick chip | **Weather now**: today emphasised, next 12 hours, rest of the week | `Final-WeatherButton.dc.html` | Same as above |
| Source **Google Tasks** | **To do**: Big 3 + checklist, every task in its own box | `Final-Todo.dc.html` | `Todo-AllClear.dc.html`, but only when the schedule's "Only print if any are due" condition is off. With it on, skip the print |
| Source **Google Calendar agenda** | **Itinerary**: timeline, each event expanded as a ticket | `Final-Calendar.dc.html` | `Cal-Free.dc.html` (the free-day slip) |

Inside a routine (for example "Morning briefing"), print each block's slip one after another. Put one dashed cut rule (section 4.3) between blocks, and print a single end mark (section 4.7) after the last block.

Every other print (notes, guest notes, remote messages, the shopping list, fortunes, countdowns, the test page, and anything made in Create) follows the design system in section 8b.

## 2. Paper and rendering rules

- **Width:** 384 dots. 1 design px = 1 printer dot. Content area 344 dots (20-dot side margins). Top padding 30, bottom padding 36.
- **Colour:** pure 1-bit. Black ink on white. The paper colour `#F7F5F0` and the torn zig-zag edges in the mockups are screen-only. The renderer outputs mode `1` with white = paper.
- **Height:** grows with content. The mockup heights are examples, not limits.
- **Gaps:** 14 dots between blocks unless a section says otherwise (the To-do slip uses 12).
- **Grey:** never. Tones are dither tiles (section 4.2).
- **Smallest text:** 12 dots high (labels). Nothing smaller.
- **Thinnest stroke:** 2 dots. Borders are 2, 3 or 4 dots.
- **Renderer:** Pillow, as BUILD_PLAN §6.1 says. Set `ImageDraw.fontmode = "1"` so text renders with anti-aliasing off. The "As printed" preview uses the same function.

## 3. Fonts

Both fonts are on Google Fonts under the SIL Open Font License. Bundle the **static** TTFs (not the variable fonts) in `backend/fonts/` and the woff2 files in `frontend/public/fonts/`, per BUILD_PLAN override 2.

| Role | Font | Weights |
|---|---|---|
| Headings, body, numbers | Space Grotesk | Medium 500, Bold 700 |
| Labels, data, tickets | JetBrains Mono | Regular 400, Bold 700, ExtraBold 800 |

Type scale for the print templates. This is separate from the Create editor's S/M/L/XL sizes, which stay as BUILD_PLAN says.

| Token | Font | Size / line height (dots) | Weight | Notes |
|---|---|---|---|---|
| `t-xxl` | Space Grotesk | 92 / 78 | 700 | Big temperature. Tracking −5% |
| `t-xl` | Space Grotesk | 36 / 36 | 700 | Slip titles (TO DO, THE BIG 3, condition name). Tracking −2.5% |
| `t-l` | Space Grotesk | 23 / 25 | 700 | Item titles, detail values |
| `t-m` | Space Grotesk | 17 / 21 | 500 | Body lines |
| `t-s` | Space Grotesk | 15 / 19 | 500 | Notes, secondary lines |
| `px` | JetBrains Mono | 12 / 15 | 700 (`px b` = 800) | Labels. UPPERCASE, tracking +6% |
| `mono` | JetBrains Mono | 15 / 20 | 400 (`mono b` = 700) | Ticket data: places, people, notes |

One-off sizes in the mockups: the To-do "No." numbers (52 large, 24 small), the calendar date (80), the button slip's chart labels (13).

**Text that doesn't fit:** wrap at word boundaries. Titles wrap to at most 2 lines, then end in "…". Notes wrap to at most 3 lines. Never shrink text to fit.

## 4. Shared building blocks

Build these once as small Python layout components. Each template is then a function `data → list of blocks`.

### 4.1 Header row (and no footer)

- **Header row:** `px b` source name on the left ("WEATHER", "GOOGLE TASKS", "GOOGLE CALENDAR"); `px` date and time on the right ("MON 23 NOV · 07:30").
- **No footer.** Slips have no footer row. Where a slip needs context (update time, lists, calendars), it goes in the header row's right side or the second header line.
- **End mark:** always the very last thing on every slip (section 4.7).

### 4.2 Tones (4 × 4-dot tiles, 1 = black)

| Name | Tile rows | Use |
|---|---|---|
| `d25` | `1010 / 0000 / 1010 / 0000` (one dot in 4) | Light fill |
| `d50` | `1100 / 1100 / 0011 / 0011` (2 × 2 checker) | Rain bars, rain meters, heavy-cloud icons |
| `d75` | inverse of `d25` | Dark fill |
| solid | all black | Temperature bars, inverted bands |

### 4.3 Rules (horizontal lines)

| Name | Spec |
|---|---|
| `hr` | 2-dot dashed line, 6 on / 4 off |
| `hr2` | Double rule: 3-dot solid, 2 dots of space, 2-dot solid (7 dots in total) |
| `hrd` | 3-dot dotted line, 3 on / 3 off |
| `cut` | Label in `px` (e.g. "MAP", "CUT") centred between two 2-dot dashed lines |
| section rule | `px b` label, then a dashed line filling the rest of the row (e.g. "DUE TODAY ----") |

### 4.4 Boxes and bands

- **Inverted band:** solid black, text in paper white, padding 3–8 dots vertically and 8–12 horizontally.
- **Box:** 3-dot border, 8 × 10 dots padding.
- **Ticket box (To-do):** a box split into a number column and a content column by a dashed vertical rule. Large: 4-dot border, 64-dot number column, 3-dot dashed divider. Small: 3-dot border, 48-dot number column, 2-dot dashed divider.
- **Checkbox:** small = 20 × 20 with a 3-dot border; large = 30 × 30 with a 4-dot border. Always empty: people tick them with a pen.
- **Meter:** 16 dots tall with a 2-dot border, filled with `d50` from the left to the value %.

### 4.5 QR code

Use `segno` with error correction level M. The data is `https://www.google.com/maps/search/?api=1&query=<URL-encoded location>`. Draw it at 3 dots per module with a 4-module quiet zone. Most locations fit in versions 3–5 (29–37 modules), so about 87–111 dots plus the quiet zone. The mockups show a 21-module **placeholder** pattern, not a real code. Every printed QR must be a real one.

### 4.6 Weather icons

Use the 14 SVGs in `icons/`. On the PC, a `tools/` script renders each one with resvg or cairosvg at every size it's needed and thresholds the result to 1-bit PNGs in `backend/assets/wx/<name>-<size>.png`. The Pi only loads PNGs. Sizes needed: **168, 104, 96, 52, 44, 40**.

| Key | Name printed |
|---|---|
| `sunny` | SUNNY |
| `night` | CLEAR NIGHT |
| `partly` | SUNNY SPELLS |
| `cloudy` | OVERCAST |
| `fog` | FOG |
| `drizzle` | DRIZZLE |
| `rain` | RAIN |
| `heavy` | HEAVY RAIN |
| `thunder` | THUNDERSTORMS |
| `snow` | SNOW |
| `sleet` | SLEET & HAIL |
| `frost` | FROST |
| `wind` | WINDY |
| `heat` | HEATWAVE |

### 4.7 End mark (on every slip)

So that a slip nobody tore off never blends into the next print, every print ends with an end mark after its last block:

- At least 14 dots of space after the last block, then the end mark, **63 dots tall, across the full paper width** (384 dots, edge to edge, ignoring the 20-dot margins). From top to bottom:
  - a 3-dot solid rule;
  - 17 dots of space, then the **tear line**: a 2-dot dashed line (6 on / 5 off) running across, inset 12 dots from each edge, with a **176 × 23-dot black tag** centred on it. Inside the tag, **"END · TEAR HERE"** in paper white, JetBrains Mono ExtraBold 12, uppercase, tracking +20%, centred;
  - 17 dots of space, then the same 3-dot solid rule.
  It's symmetrical, light enough not to streak, and impossible to miss between two slips. The tear line sits at the dashed line through the tag.
- Then the printer's normal blank feed (Settings › Printer › Blank feed after print).

Rules: one end mark per printed copy (2 copies = 2 end marks). One end mark per routine, after the last block. It is added by the print pipeline, not by each template, so it is never forgotten, and it appears in the "As printed" preview too. Reference: `print-kit.css` (`.endmark`, `.rc::after`) and the design system board.

## 5. Weather briefing (14 conditions)

Reference: `reference/Weather.dc.html`, the `hero` block. The `D` table in its script holds the sample data for all 14 conditions. Data: `samples/weather.json`, built from one Open-Meteo call (BUILD_PLAN §9.1).

### 5.1 Choosing the condition

1. Map the Open-Meteo weather code (WMO) for the day (daily `weather_code`, or the current hour's code if the briefing prints after 18:00):

| WMO codes | Condition |
|---|---|
| 0, 1 | `sunny` (`night` if printed between sunset and sunrise) |
| 2 | `partly` |
| 3 | `cloudy` |
| 45, 48 | `fog` |
| 51, 53, 55 | `drizzle` |
| 56, 57, 66, 67 | `sleet` (freezing drizzle or rain) |
| 61, 63, 80, 81 | `rain` |
| 65, 82 | `heavy` |
| 71, 73, 75, 77, 85, 86 | `snow` |
| 95, 96, 99 | `thunder` |

2. Then apply these overrides, first match wins:
   - `heat`: daily max ≥ 28 °C and code 0–3.
   - `wind`: daily max gusts ≥ 60 km/h and the condition is not `heavy`, `thunder` or `snow`.
   - `frost`: daily min ≤ 0 °C, code 0–3, and printed before 12:00.

Keep the thresholds in config so they can be tuned.

### 5.2 Layout, top to bottom (344-dot content width)

1. Header row: "WEATHER" | "MON 23 NOV · 07:30".
2. Second row: `px` place name | `px b` "TODAY" (or "TONIGHT" for `night`).
3. `hr2`.
4. Icon, 168 dots, centred, with 6 dots of space above and 2 below.
5. Condition name, `t-xl`, centred.
6. Summary sentence, `t-m`, centred (section 5.3).
7. Temperature row, centred: current temperature `t-xxl` ("9°"), then an 18-dot gap, then a column of "H 10°" and "L 6°" in `t-l`.
8. `hr`.
9. Detail grid, 2 × 2 (12 dots between rows, 16 between columns). Each cell is a `px` label over a `t-l` value. Cell 1 is CHANCE OF RAIN (today's max %). Cell 2 is WIND (current, km/h). Cells 3 and 4 depend on the condition (table below).
10. `hr`.
11. Hourly strip: 5 equal columns, each with a `px` time over a 44-dot icon over a `t-m` temperature. Daytime slots are every 3 hours from 09:00; for `night`, 21:00, 00:00, 03:00, 06:00, 09:00.
12. Tip, in an inverted band, `t-l`, centred (table below).

| Condition | Cell 3 | Cell 4 | Default sentence | Tip |
|---|---|---|---|---|
| sunny | UV (index + LOW/MOD/HIGH) | SUNSET | Clear blue skies all day. | SUNSCREEN ON (UV ≥ 3), else ENJOY THE SUN |
| night | MOON (phase, worked out locally) | SUNRISE | Clear and still. Cold by dawn. | A NIGHT FOR STARS |
| partly | UV | SUNSET | Bright spells between clouds. | LIGHT JACKET |
| cloudy | FEELS LIKE | SUNSET | Grey all day but staying dry. | GREY BUT DRY |
| fog | VISIBILITY (lowest, m) | CLEARS (first hour with visibility > 1000 m) | Thick fog until late morning. | LIGHTS ON, GO SLOW |
| drizzle | FEELS LIKE | SUNSET | Fine drizzle on and off. | HOOD UP |
| rain | RAINFALL (daily mm) | SUNSET | Rain from {first hour ≥ 50%}, easing tonight. | TAKE AN UMBRELLA |
| heavy | RAINFALL | GUSTS | Downpours. Puddles everywhere. | WATERPROOFS ON |
| thunder | GUSTS | RAINFALL | Storms this afternoon. Hail possible. | STAY IN IF YOU CAN |
| snow | SNOWFALL (cm) | FEELS LIKE | Snow showers, settling on grass. | BOOTS ON, GO SLOW |
| sleet | FEELS LIKE | PAVEMENTS (ICY if min ≤ 1 °C) | Wintry showers with some hail. | SLIPPY UNDERFOOT |
| frost | FEELS LIKE (min) | THAW BY (first hour > 0 °C) | Hard frost, then crisp sunshine. | ICE ON THE ROADS |
| wind | GUSTS | FEELS LIKE | Strong winds, gusting to {max gust}. | HOLD ON TO YOUR HAT |
| heat | UV | SUNSET | Hot and sunny. Peak at {hour of max}. | WATER AND SHADE |

Open-Meteo has no official weather warnings, so no slip shows one.

### 5.3 Summary sentence

Use the default sentence for the condition and fill in its `{…}` gaps from the hourly data. When rain is coming (any hour today with chance ≥ 50%) and the condition is not already rain, heavy or thunder, use "Rain from {HH:00}." instead. Keep sentences to one line where possible, two at most.

## 6. Weather now (button press)

Reference: `reference/Final-WeatherButton.dc.html`. Data: same as the briefing (`samples/weather.json`). The design merges the 5-day and 12-hour layouts and puts **today** in a heavy box at the top.

1. Header: "WEATHER NOW" | "MON 23 NOV · 08:00". Second row: place name only.
2. **Today box:** 4-dot border, no gap at the top. Inside it:
   - An inverted band, "TODAY" on the left and "MONDAY 23" on the right, padding 8 × 12.
   - Content (14 dots padding, 10-dot gaps):
     - A row: today's icon (104) beside a column of current temperature (`t-xxl`) over "H 10° · L 6°" (`t-l`).
     - A headline in `t-xl`. "RAIN AT {h}" (12-hour clock, no leading zero) if any of the next 12 hours has rain chance ≥ 50%; otherwise the condition name.
     - A one-line summary in `t-m` (section 5.3), plus "Wind {n} km/h.".
     - `hr`.
     - **Temperature chart:** the label "NEXT 12 HOURS · TEMPERATURE °C", then 12 columns (3-dot gaps) of solid bars standing on a 3-dot baseline, each with its value in 13-dot type above it. The chart area is 112 dots tall. Bar height = 17 + (t − min) / (max − min) × 68 dots, or 34 for every bar when max = min. Under the baseline, the hours ("08" … "19") in `px`.
     - **Rain chart:** the label "CHANCE OF RAIN %", then 12 columns of `d50` bars with a 2-dot border, hanging down from a 3-dot top line, with the % below each. Bar height = % × 0.75 dots (0–75). The chart area is 104 dots.
     - Tip band (inverted, `t-l`). If rain is coming: "LEAVE BEFORE {first rainy hour − 30 min}". Otherwise use the condition's tip from 5.2.
3. Section rule "REST OF THE WEEK".
4. The next 4 days, one row each: day (`t-l`, 52 wide), 40-dot icon, "11° / 7°" (`t-m` bold), then a 92-wide meter of rain chance with "Rain 80%" (13-dot type) under it. An `hrd` after each row.
5. One summary line in `t-s`. Name the coldest night, and add "Frost likely {day} morning." when any day's min ≤ 0. Name the windiest day when gusts ≥ 60.

## 7. To do (Google Tasks)

Reference: `reference/Final-Todo.dc.html`. Data: `samples/tasks.json`. It merges the checklist and Big 3 designs: every task sits in a ticket box (4.4), and the tear-off tickets are gone.

### 7.1 Data rules

- Read the lists chosen in Settings with `tasks.list(showCompleted=false, showHidden=false)`. Order the tasks by list order, then by each task's `position`.
- **Due time:** print it on every dated task ("10:00" today, "FRI 17:00" when late). The Tasks API returns `due` as a date only and drops the time set in the Tasks app, so read the time from the task itself: a time at the start of the notes ("10:00 Ask for Thursday") or after an `@` in the title ("Call landlord @10:00"). Strip it from the printed text. No time found → date tag only. The API also doesn't expose starred tasks, so don't print stars.
- **Big 3:** the first 3 top-level tasks (no `parent`) that are overdue or due today, in that order. People choose the Big 3 by dragging tasks in Google Tasks.
- **Groups**, for the remaining top-level tasks: OVERDUE, then DUE TODAY, then NO DATE (at most 5 tasks, then a "+N more" line in `t-s`). Tasks due on a later date are left out.
- **Sub-tasks:** list them under their parent with small checkboxes, but only inside Big 3 boxes. Small boxes add "· {n} steps" to the meta line instead.
- **Due tag:** "TODAY"; "{n} DAYS LATE" (or "1 DAY LATE") in an inverted `px b` tag; "ANY TIME" when there's no date. The due time sits just left of the tag: Space Grotesk bold, 20 in Big 3 boxes and 17 (`t-m`) in small boxes.
- **Notes:** the first 2 lines, at most 80 characters, in `t-s`.
- **Counts:** "{n} tasks · {m} late" counts the top-level tasks printed (the Big 3 plus the groups).

### 7.2 Layout (12-dot gaps)

1. Header: "GOOGLE TASKS" | "MON 23 NOV · 07:30".
2. "TO DO" as an inverted `t-xl` band, centred, padding 10 / 8.
3. A row: the list names joined with " + " (`t-l`) | "7 tasks · 2 late" (`t-m`).
4. `hr2`.
5. "THE BIG 3" (`t-xl`), with "Do these and the day is a win." (`t-m`) under it.
6. 3 large ticket boxes:
   - Number column: "NO." (`px`) over the digit (52, bold).
   - Content column (padding 10 / 12 / 12, gaps 6):
     - The title (`t-l`) with a large checkbox on the right, aligned to the top.
     - Notes, if any.
     - Sub-tasks, each a small checkbox and `t-m` text.
     - A meta row: list name (`px`) | due time + due tag.
7. `hr2`.
8. For each group that has tasks:
   - A section rule. Use an inverted "! OVERDUE" tag for the overdue group; plain `px b` "DUE TODAY" and "NO DATE" for the others.
   - Small ticket boxes:
     - Number column: a two-digit number ("04") at 24 bold.
     - Content column: the title (`t-m` bold) with a small checkbox, over a meta row (list | due time + due tag).
9. Progress: "PROGRESS" (`px`) | "0 / 7" (`t-m`), then one empty 18-dot cell per task (2-dot border, up to 12 cells; above 12, show the count only).
10. Centred `t-s` line: "Big 3 = the first 3 late or due-today tasks, in your list order. Drag to reorder in Google Tasks."

### 7.3 Nothing due

Print `reference/Todo-AllClear.dc.html`:

- a big tick-in-a-box drawing (150 dots)
- "ALL CLEAR" (`t-xl`)
- "Nothing due today and nothing late."
- "COMING UP": the next 3 tasks that have a due date, as title | short date
- an inverted "ENJOY THE DAY" band

## 8. Itinerary (Google Calendar)

Reference: `reference/Final-Calendar.dc.html`. Data: `samples/calendar.json`, from the private iCal URLs (BUILD_PLAN §9.1). The timeline is the base design, and each event is expanded into a "Next up" ticket.

### 8.1 Data rules

- **Today only:** local time zone, with recurring events expanded. Sort timed events by start time.
- **All-day events:** one inverted band each ("ALL DAY" | title), at most 3, then "+N more".
- **Next up:** the first event whose end is after the print time. Its header says "IN {x}" (for example "IN 2 H" or "IN 45 MIN"), or "NOW" if it has already started. If every event has ended, no event gets the label.
- **Title:** `SUMMARY`.
- **Where:** `LOCATION`, split at the first comma. The part before the comma is the place name (`mono b`); the rest is the address (`mono`, at most 2 lines).
- **With:** `ATTENDEE` common names, leaving out the calendar owner: "A, B and N others" (show 2 names at most). Leave the row out when there are no attendees.
- **Notes:** `DESCRIPTION` with HTML and the Google Meet boilerplate removed, at most 3 lines. Leave the row out when it's empty.
- **Online events:** when the location is empty and a conference link is found (`X-GOOGLE-CONFERENCE`, or a meet/zoom/teams URL in the description), show a "JOIN ONLINE" box with the link without `https://`, and print no QR code.
- **Map QR:** only when there's a location (4.5).
- **Free gaps:** a gap of 15 minutes or more between one event's end and the next event's start gets a gap row, for example "1 H 30 FREE".
- **Overlaps:** overlapping events get no gap row. Add the line "Overlaps with {title}" (`t-s`) inside the later ticket.
- **Events that run past midnight:** the Ends cell says "→ TUE 01:00".

### 8.2 Layout

1. Header: "GOOGLE CALENDAR" | "PRINTED 07:30".
2. Date block: the day number (80, bold), with the weekday and month in `t-l` beside it, aligned to the bottom.
3. Summary line: "{n} events · first at {start} · done by {last end}" (`t-m`).
4. All-day bands, then `hr2`.
5. **Timeline:** a 3-column grid (50 | 20 | rest).
   - Column 1: the start time, `t-m` bold, 6 dots from the top.
   - Column 2: the rail, a 4-dot line. It's solid beside events and dashed (4 on, 5 off) beside free gaps. Each event has an 18-dot solid square on the rail, 8 dots from the top.
   - Column 3: the ticket card, 6 dots left padding and 4 dots below.
6. **Ticket card** (3-dot border):
   - Header strip, padding 6 × 8. For Next up: inverted, "NEXT UP" | "IN 2 H". For other events: plain, "EVENT 2 OF 5" | "11:00–12:30". Both in `px b`.
   - Body (padding 8 / 10 / 10, gaps 8):
     - The title (`t-l`).
     - A 3-cell grid with a 2-dot border and dividers: STARTS | ENDS | LENGTH, each a `px` label over a `t-m` bold value.
     - WHERE, then WITH and NOTES when present, each a `px` label over `mono` text.
     - Then either a `cut` rule labelled "MAP" with a row of the QR code and "Scan for directions on your phone." (`mono`, 13), or the JOIN ONLINE box.
7. **Gap row:** the `px` label ("1 H FREE"), padding 12 dots above and below, beside the dashed rail.
8. `hr2`, then "Busy {total} · Free {total}" (`t-m`, left | right). Count only from the first start to the last end.

### 8.3 Nothing on today

Print `reference/Cal-Free.dc.html`:

- header
- `hr2`
- an empty-calendar drawing (140 dots)
- "NOTHING ON" (`t-xl`)
- "No events today. The whole day is yours." (`t-m`)
- `hr`
- a box with NEXT EVENT and the title on the left, and the weekday and start time on the right

Look up to 14 days ahead for the next event. If there's none, the box says "Nothing in the next 2 weeks".

## 8b. Every other slip: the print design system

`reference/System.dc.html` (canvas board "Print design system") is the rule book for any slip not specified above. It shows the skeleton, the tokens, every component, a worked example of each slip below, and the composition, print-safety and voice rules. Build new slips only from the blocks in section 4.

**Skeleton:** header row → title → `hr2` → body sections → end mark. Nothing above the header, nothing after the end mark.

| Slip | Header (left) | Body | Notes |
|---|---|---|---|
| Note (Create text, quick notes) | NOTE | Message in Space Grotesk bold 28/32, then any extra lines in `t-m` | No signature line on the example; a Create print keeps whatever the person designed between header and end mark |
| Guest note | GUEST NOTE | Same as Note. Put "from {name}" in the header's right side with the time | Prints only after approval if Settings says so |
| Remote message (email, Telegram) | MESSAGE | Subject in `t-l`, then the body in `t-m` | No "from · via" band in the design. Only when the text was truncated (over 600 characters or 40 lines) does it end with "… (cut)" |
| Shared shopping list | SHOPPING LIST | Inverted `t-xl` band "SHOPPING", a "This week · {n} items" row, `hr2`, then sections (FRIDGE, CUPBOARD, OTHER…) of small-checkbox rows | No initials or "added by" marks |
| Fortune or quote | FORTUNE (or QUOTE) | A big opening quote mark (92), the text in Space Grotesk bold 30/34, `hr`, then "LUCKY NUMBER" with the number in a box | |
| Countdown | COUNTDOWN | The day count in `t-xxl` beside "DAYS" in `t-xl`, the event name in `t-m`, a meter from the day it was set to the date, then a tip band | |
| Printer test page | PRINTER | Inverted "TEST PAGE" band, the four tones, a mm ruler (a tick every 8 dots, labels every 10 mm), then a 2 × 2 grid of paper, darkness, speed and address | |

## 9. Reading the reference files

`reference/*.dc.html` are design-tool mockups.

- The markup is inside `<x-dc>`. `{{name}}` is filled from `renderVals()` at the bottom, where the sample data lives. `<sc-for>` is a loop and `<sc-if>` is a condition. `<dc-import name="WxIcon" icon="rain" size="104">` places an icon.
- The classes come from `print-kit.css`. Its values are the ones used in sections 2–4.
- They don't run outside the design tool. Open the canvas link at the top to see them rendered.
- All names, places, times and forecasts are sample data. The QR patterns are placeholders.

## 10. Done when

- Golden-image tests: render each template from `samples/*.json`, plus one weather briefing per condition (14, built from the `D` table in `Weather.dc.html`). Compare the result by eye with the canvas once, then lock it in as the golden image.
- Every output is exactly 384 dots wide and pure 1-bit, with no text under 12 dots and no stroke under 2 dots.
- The `/api/preview` PNG equals the bitmap sent to the printer for every golden document (BUILD_PLAN §6.1).
- Every printed copy ends with exactly one end mark (4.7), and routines end with one.
- Empty states print as described in 7.3 and 8.3. The weather slips print "Weather unavailable" when the provider fails.
- Long titles, long notes and more than 8 events all print without overlapping or clipping.
- Each printed QR code scans on a phone and opens the right place in maps.

## 11. Where this fits in the build

The layout components and icon PNGs (sections 3 and 4) belong in Phase 2, with the renderer. The four templates belong in Phase 4, with the schedule sources. The button action in Phase 3 calls the Weather now template, so build that one first if Phase 3 comes before Phase 4.

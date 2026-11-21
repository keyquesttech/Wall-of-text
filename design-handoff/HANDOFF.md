# Wall Printer — Design Handoff

Version 1 · 19 Nov 2026 · Design canvas: https://claude.ai/code/artifact/a617d12b-b8fd-42b4-a38e-23b4317db97c

This file is the build spec for the Wall Printer web app. It is written for Claude Code (or a person) to implement from. Read it top to bottom once, then use the section you need.

What's in this folder:

| Path | What it is |
|---|---|
| `HANDOFF.md` | This spec. Source of truth for behaviour, layout and states. |
| `tokens.css` | The real design tokens and component classes used in the mockups. Lift it into the app as the base stylesheet. |
| `reference/*.dc.html` | The mockup source for every screen. Reference only, not production code (see "Reading the reference files"). |

---

## 1. Product in one paragraph

A mobile-first web app that controls a wall-mounted thermal receipt printer. It is served by a Raspberry Pi 4 on the home Wi-Fi and opened in a phone browser by two flatmates (sometimes on a laptop). People write, draw or add a picture, then print now or schedule it. No sign-up, no login; at most an optional 4-digit PIN. It must feel like a native app, installable to the home screen.

Design goals, in priority order:

1. Print something in two taps from opening the app.
2. Playful and reactive: every touch answers with motion, light or sound.
3. What you see is what prints: the preview looks like the real receipt.
4. Scheduling is as easy as setting a phone alarm.

## 2. Hardware facts the UI depends on

| Part | UI consequence |
|---|---|
| Thermal printer (Pi Hut), USB, 58 mm paper | Output is **1-bit black only**, about **384 dots wide** (48 mm print area). Confirm against the datasheet before hard-coding. Every preview maps to this. |
| Raspberry Pi 4 + Power/Fan HAT | Hosts the app. Temperature, fan state and uptime shown in Settings › Device. Keep the front end light. |
| Sanwa arcade button | One button. Single, double and long press each map to an action set in Settings › Button. |
| Panel LED (assumed single colour) | Brightness plus a pattern per event (Off, Solid, Slow pulse, Blink). |

## 3. Suggested build approach (not prescriptive)

- Front end: any light stack works. Vanilla JS/Web Components, Preact, Svelte or plain React all fit. Avoid heavy UI libraries; the look comes from `tokens.css`.
- The Pi serves the static front end and a small JSON API (section 12). The rendering of a job to a 384-px 1-bit bitmap should happen **on the Pi**, with the same function also used to make the "As printed" preview, so the preview and the paper cannot drift apart.
- Installable PWA: manifest plus a service worker that caches the shell (section 11).
- Status updates: Server-Sent Events or WebSocket for printer state, queue and progress. Fall back to polling every 3 s.

## 4. Design tokens

All tokens are CSS custom properties in `tokens.css` under `:root`. Use them; don't retype hexes.

### Colour

| Token | Hex | Role | Contrast |
|---|---|---|---|
| `--bg` | `#121315` | Page background | — |
| `--raised` | `#1C1D21` | Solid surfaces, glass fallback | — |
| `--silver` | `#C9CDD4` | Main text, icons, glass edges | 11.6:1 on bg, 10.4:1 on glass |
| `--hi` | `#ECEEF2` | Headings, active labels | higher than silver |
| `--muted` | `#8A8F98` | Secondary text, inactive tabs | 5.7:1 on bg, 5.1:1 on glass |
| `--green` | `#39FF88` | Print and main actions, online, success | 14.0:1; text on green uses `--green-ink` `#06210F` (12.9:1) |
| `--pink` | `#FF2E9A` | Schedules, time, creative tools, alerts | 5.4:1 on bg. **Pink text uses `--pink-text` `#FF63B4`** (6.1:1 on glass). Text on pink fills uses `--pink-ink` `#2A0016` |
| `--paper` | `#F7F5F0` | Receipt preview only | ink `#0E0E0E` 17.7:1 |

Rules:
- Green means "do it now". Pink means "later" or "look at this". Screens stay mostly greyish black and silver; neon is light, not paint.
- Errors: pink **plus** an icon **plus** a plain sentence. Never colour alone.
- Toggles are pink inside Schedules, green everywhere else.

### Glass

| Class | Spec |
|---|---|
| `.glass` | `rgba(30,31,36,.52)` fill, `backdrop-filter: blur(26px) saturate(170%)`, 1 px border `rgba(201,205,212,.16)` with top edge `rgba(236,238,242,.36)`, inner top highlight, lift shadow `0 12px 32px rgba(0,0,0,.38)` |
| `.glass.tg` / `.glass.tp` | Green or pink tint: a top-down gradient of the neon at 11–13% |
| `.glass.sel` / `.glass.selg` | Selected: pink or green edge plus a soft glow |
| `.glass.prs` | Pressed: scale .97, slightly lighter fill |
| `.solid .glass`, `.glass.solidf` | Fallback: no blur, `--raised` fill. Use when "Reduce transparency" is on, when `backdrop-filter` is unsupported, or on low-power devices |

Background light: two or three blurred blobs (`.blob.g`, `.blob.p`, blur 72 px, opacity ~.35) drifting on a 22–30 s loop. Glass picks up the colour under it automatically through the blur.

### Type

| Style | Size / line | Weight |
|---|---|---|
| Display (`.h1`) | 34/40, tracking -0.02em | 800 |
| Title (`.h2`) | 22/28 | 700 |
| Headline (`.h3`) | 17/22 | 600 |
| Body | 16/22 | 400 |
| Caption (`.cap`) | 13/18 | 500, muted |
| Label (`.lbl`) | 12/16 uppercase, tracking .07em | 700, muted |

Interface font: system font on iPhone (`-apple-system`), Inter elsewhere. The mockups list Inter first; in production put `-apple-system, "SF Pro Text"` first if you want the native face on iOS.

Receipt preview font: whatever print font the user picked. Default is a bitmap thermal face (mockups use **VT323** from Google Fonts as a stand-in). Print sizes S/M/L/XL = 18/22/30/40 px in the preview.

### Spacing, radius, shadow

- Spacing scale: 4, 8, 12, 16, 20, 24, 32, 48 px. Screen side gutter 16 px.
- Radius: 12 inputs/chips · 18 buttons · 24 cards · 28 tab bar · 32 sheets · pill.
- Shadows: lift `0 12px 32px rgba(0,0,0,.38)`; green glow `0 8px 30px rgba(57,255,136,.45)`; pink glow `0 8px 26px rgba(255,46,154,.42)`.
- Easing: spring `cubic-bezier(.34,1.56,.64,1)`, ease `cubic-bezier(.2,.8,.2,1)`.

## 5. Layout and navigation

Phone first at **390 × 844**. Main actions sit in the bottom half.

Four tabs in a floating glass tab bar (16 px from the sides, 24 px from the bottom, 72 px tall, radius 28):

| Tab | Route (suggested) | Icon |
|---|---|---|
| Create (home) | `/` | sparkle |
| Schedules | `/schedules` | clock |
| History | `/history` | receipt |
| Settings | `/settings`, `/settings/:group` | gear |

The History tab shows a pink badge with the number of new prints since it was last opened.

Always visible on every main screen: a glass **status pill** top-left (dot + label + "· N waiting"). Tapping it opens the status bottom sheet (state, queue count, paper level, Test print, Cancel queue).

Leave 52 px at the top for the phone's status area (don't draw a fake status bar) and ~120 px at the bottom for the tab bar.

Responsive:

| Width | Layout |
|---|---|
| < 768 | Bottom tab bar, one column, sheets slide up from the bottom |
| 768–1199 | Tab bar becomes a 92 px glass side rail on the left. Create shows editor and "As printed" preview side by side |
| ≥ 1200 | Side rail, editor, preview, plus a 300 px queue column. Schedules adds a detail panel for the selected schedule |

Reference: `Tablet-Create`, `Wide-Create`, `Tablet-Schedules`, `Wide-Schedules`.

## 6. Components

All classes exist in `tokens.css`.

| Component | Class | States / notes |
|---|---|---|
| Glass card | `.glass` | default, pressed (`.prs`), selected (`.sel`) |
| Primary button | `.btn-print` | 64 px tall, radius 22, green with glow. Pressed: squash to 95% × 90%. Printing: inner progress fill (`.prog`) + label "Printing… 60%". Busy: spinner. Done: tick for 1 s. **Long-press** opens a small sheet: copies (1–5) and extra blank feed |
| Schedule button | `.btn-sched` | Glass with pink edge and pink text. Opens the schedule wizard with the current message attached |
| Secondary button | `.btn` | Glass, silver text. Pink text variant for destructive (Shut down) |
| Solid buttons | `.btn-green`, `.btn-pink` | Used inside sheets and cards (Save schedule, Test print, Try again) |
| Icon button | `.ib` | 44 × 44 minimum, `.on` for active tool. Always `aria-label` |
| Status pill | `.pill` + `.dot` | Online: green dot. Printing: green dot pulsing (`.pulse`). Paper out: pink dot. Offline: grey dot. Always has a text label |
| Segmented control | `.seg` + `.hl` | Glass track; highlight slides with the spring easing. `.seg.sm` compact variant |
| Toggle | `.tog` (`.on`, `.pk`) | `role="switch"` with `aria-checked`. 52 × 32 |
| Chip | `.chip` | Quick actions and filters, 40 px tall. `.chip.warn` = pink warning chip ("Sign in again") |
| Bottom sheet | `.sheet` + `.grab` + `.scrim` | Glass, radius 32 top corners, grab handle |
| Time picker | `.wheel` / `.wcol` / `.band` | Wheel style like the phone alarm, 5-minute steps |
| Day chips | `.day` (`.on`) | M T W T F S S, 44 px circles, pink when on |
| Receipt preview | `.receipt` inside `.rwrap` | Paper-white, zig-zag torn bottom (CSS mask), drop shadow on the wrapper. `.receipt.bits` = "As printed" (no smoothing). Helpers: `.r-c` centre, `.r-s/.r-l/.r-xl` sizes, `.r-inv` white on black, `.r-hr` dashed divider, `.r-cb` checkbox |
| Toolbar | glass bar of `.ib` | Floats above the keyboard in the editor; scrolls horizontally with a fade on the right |
| Toast | `.toast` | Drops from the top, auto-hides after ~1.8 s. "Printed", "Scheduled for 07:30", "Added to the queue · 3rd" |
| List row | `.lrow` inside `.grp` | Icon tile (`.ico`, `.ico.g`, `.ico.p`), label, value (`.v`), chevron |
| Banner | `.banner` (`.pk`) | Inline alert with icon, sentence and an action |
| Progress | `.bar` (`.pk`) | 6 px track with glowing fill |
| Loading | `.shim` | Shimmering glass placeholder. Never show a blank screen |

Reference: `Components.dc.html`, `TabBar.dc.html`.

## 7. Screens

File names in brackets are the reference mockups in `reference/`.

### 7.1 Create (home) [`Main`, `Create-Draw`, `Create-Image`, `Create-Templates`, `Create-Printed`]

Vertical stack, top to bottom (flex column, 12 px gap):

1. Top row: status pill (left) and a small Edit | As printed segmented control (right).
2. Quick-action chips, scrolling sideways: Weather now, Today's agenda, Shopping list (with item count badge), Fortune. One tap prints.
3. Mode switcher, 4-way segmented: **Text, Draw, Image, Templates**.
4. The canvas panel (glass, fills remaining height): the paper strip, narrow and growing downwards, faded at the bottom. A column of three icon buttons on the right: Save as template, "From" signature (shows initial), Clear.
5. Mode toolbar (56 px glass bar).
6. Action row: **Print** (green, flex 1) + **Schedule** (pink, 128 px).

Modes:
- **Text**: type straight onto the strip. Toolbar: print font picker (each font shown as a printed sample), size S/M/L/XL, bold, underline, white-on-black, alignment, checkbox line, date/time stamp, divider, QR from a link, stickers (simple black icons). Text caret is pink.
- **Draw**: finger drawing, black only. Toolbar: pen sizes (3), eraser, straight-line tool, undo, redo. Clear lives in the side column.
- **Image**: take or pick a photo, crop to strip width, choose style (Photo dither, Sharp black and white, Halftone) as chips in the toolbar. Brightness and contrast sliders sit under the image on the paper. The converted 1-bit result updates live.
- **Templates**: 2-column gallery of mini receipts: Shopping list, To-do, Note for flatmate, Birthday card, Out of milk, Quote of the day, plus the user's own. Filter chips in the toolbar: All, Lists, Notes, Cards, Mine.

**As printed** view: same strip rendered as the real 1-bit output on paper white at true proportions, with a caption "384 DOTS · 48 MM · 1-BIT". No caret, no editing chrome, no sliders. This must be produced by the same renderer the printer uses.

The "from" signature appends a white-on-black "from <name>" line so notes show who sent them.

### 7.2 Schedules [`Schedules`, `Schedules-Empty`]

1. Status pill + pink **New** button.
2. Title "Schedules".
3. **Holiday mode** card: pink toggle, "Pause every schedule until you're back".
4. **Up next · today** timeline (pink-tinted glass): a 06:00–24:00 track, past prints as hollow grey dots with a tick, a white "Now" marker, upcoming prints as pink dots (next one solid and glowing). Top-right text: "Shopping list in 2 h 18 min".
5. Schedule cards: icon tile, name, when in pink ("Every weekday at 07:30"), what + next run in caption, pink toggle. Paused cards dimmed to 75% with grey "when" text. **Swipe left** reveals Pause, Copy, Delete (Delete is a solid pink tile).
6. Empty state: illustration (receipt + pink clock), "Nothing scheduled yet", one line of help, **New schedule** button, plus a secondary "Start from Morning briefing".

### 7.3 Schedule wizard [`Wizard`, `Wizard-2`, `Wizard-3`, `Wizard-4`]

Bottom sheet over a dimmed Schedules screen, top at ~92 px. Header: "Step N of 4 · Name" (pink label), a question as title, close button, and a 4-segment pink progress bar. Footer: Back/Cancel (glass, 110 px) + Next/Save schedule (pink, flex).

1. **What** — 2-column tiles: My message (with "Shopping list attached" when opened from Create), Weather, Calendar agenda, Tasks, Countdown, Quote or fortune, Saved template, Routine.
2. **When** — chips: Once, Daily, Weekdays, Weekly, Every few hours, On a condition. Wheel time picker. Day chips. A plain-language summary: "Prints every day at 07:45. First one tomorrow."
3. **Options** (depends on the source). Weather: Location, Units °C/°F, Show Today / + Tomorrow. Then "Only print if": Rain is likely (≥ 50%), It drops below (temperature), Not in quiet hours. Calendar: which calendars, how far ahead. Tasks: which list, due today only.
4. **Preview and save** — editable name field, the receipt it will print rendered with today's real data, note "Preview uses today's forecast. Tomorrow's print uses tomorrow's."

### 7.4 Routine builder [`Routine`]

A routine bundles several sources into one print (e.g. "Morning briefing": date and greeting, weather, today's calendar, today's tasks, quote). Blocks are glass rows with a drag handle and a number; conditions show as pink chips ("Only if any due", "If rain likely"). While dragging, the lifted block tilts −2°, gains a pink edge and glow, and a glowing pink line marks the drop position. "Add a block" is a dashed row. Below: a live receipt preview. Footer: Print now (green) + Save routine (pink). No tab bar on this pushed screen; back button top-left.

### 7.5 History [`History`, `State-Loading`]

1. Status pill, title, search field, filter chips (All, Manual, Schedules, Button, Guest).
2. **Waiting · N**: queue cards. The active job has a green tint, "Printing 60%" and a progress bar; the others say "Next in line". Each has Cancel.
3. **Printed**: 2-column grid of receipt thumbnails with title and "time · source" caption. Tap: reprint, edit and print again, or save as template.
4. Failed print: pink edge, faded thumbnail, "⚠ Paper ran out" in pink, Retry button.
5. Loading: shimmer placeholders in the same layout.

### 7.6 Settings [`Settings` and `Settings-*`]

Home: title, a device card (printer glyph, "Wall Printer · Online · printer.local", paper roll bar "About 60% left", "Pi 52 °C · fan quiet · up 6 days"), then a grouped list linking to each group with a current value:

| Group | Contents |
|---|---|
| Printer | Live status + Test print; print darkness slider; print speed (Slow/Normal/Fast); Print fonts → font manager; default size S–XL; line spacing; blank feed after print (stepper, lines); paper roll level, "Warn me when paper is low", "I loaded a new roll" (resets the counter) |
| Print fonts | Each font as a printed sample on a paper strip: name, Built-in / Uploaded, Default chip. Warning in pink with icon when a font is too thin or small to print clearly ("Below size L this font may not print clearly"). Upload a font (.ttf, .otf) |
| Button | Arcade button illustration + last press. Single, double, long press rows. Action choices: Reprint last, Print weather now, Print today's agenda, Print a random fortune, Cancel the queue, Run any routine |
| LED | Live preview with Stop; brightness; per event (Idle, Printing, New message waiting, Paper out, Error) a 4-way control Off / Solid / Slow pulse / Blink and a Test link |
| Connections | Google Calendar, Google Tasks, Weather (provider + location), each with state and account. Expired: pink sentence + "Sign in again" chip, and affected schedules get a warning. "Coming later": Home Assistant (Set up), Webhook link (Copy) |
| Schedules | Time zone, Quiet hours (pink toggle, 23:00–07:00), daily print limit stepper. Paper saver card: paper used this week, prints count, 7-day bar chart (today green), Compact print style toggle |
| Access | Require a PIN (4 digits). Guest note page on/off with its address; Guest notes: Print straight away / Wait for my OK; Show a QR code for visitors; "Waiting for your OK" list with Decline / Print it |
| Device | Wi-Fi, web address, temperature, fan, uptime, software updates, backup and restore, Restart, Shut down (pink text). Too-hot state: pink banner "Pi is too hot: 81 °C. Fan is at full speed. Check the vents aren't blocked." and the temperature value in pink |
| Appearance | Dark / Light, Reduce motion, Reduce transparency, Sounds. A glass-vs-solid preview tile |

Group screens have a "‹ Settings" back button and the group name as title. The tab bar stays.

### 7.7 Guest note page [`Guest`]

Stripped-down page at `printer.local/note` for visitors on the Wi-Fi. No tab bar, no settings. Big "Leave a note" heading, one line of help, a paper-strip textarea, "Your name" field, sticker buttons (heart, smiley, star, draw), a full-width green **Leave note** button, and a caption explaining whether notes print straight away or wait for approval (from Settings › Access).

## 8. States

| State | What the user sees | Reference |
|---|---|---|
| Printing | Pill "Printing · N waiting" with pulsing dot; Print button shows progress; paper-feed animation | `State-Printing` |
| Queue busy | Print still works; a dark "4th" badge in the button shows the job's place; toast on submit | `State-Queue` |
| Paper out | Pink banner replaces the quick chips: "Paper ran out. Load a new roll, then tap Retry." + Retry. Pill pink. Print becomes "Add to queue" (glass). Jobs wait | `State-PaperOut` |
| Printer offline | Pill grey "Offline". Tip banner: "Printer is offline. Check its USB cable and power. Prints wait in the queue." Print becomes "Add to queue" | `State-Offline` |
| App can't reach the Pi | Full-screen glass card: "Can't reach Wall Printer", 3-step checklist, "Looking for printer.local", green Try again | `State-NoPi` |
| Connection expired | Pink chip "Sign in again" in Connections; warning on affected schedules | `Settings-Connections` |
| Pi too hot | Pink banner and value in Settings › Device | `Settings-Device` |
| Empty | Friendly empty state with one action and a small illustration | `Schedules-Empty` |
| Loading | Shimmering glass placeholders | `State-Loading` |

## 9. Motion

Springy and physical. Everything below has a reduce-motion version: a 150 ms fade, and the background blobs stop.

The print moment (signature interaction), in ms from the tap:

| Start | Length | What happens |
|---|---|---|
| 0 | 90 | Print button squashes to 95% wide × 90% tall; glow tightens |
| 90 | 380 | Button springs back past 100% and settles |
| 120 | 200 | A slot at the top of the canvas lights green; status pill starts pulsing |
| 140 | 1400 | Paper feeds out of the slot in 24 small steps (CSS `steps(24)` on a clip-path reveal), like the motor |
| 1560 | 90 | Tear: paper tips −3° and drops 4 px; play a click sound |
| 1650 | 520 | Strip flies down to the History tab, shrinking to 12% and fading |
| 2170 | 400 | History badge pops in on a spring |
| 2200 | 1800 | Toast "Printed" drops from the top, then lifts away |

Keyframes `feed`, `tear`, `pop`, `drop`, `pulse`, `drift`, `shim` are already in `tokens.css`. Interactive reference: `Motion.dc.html` and the Print button in `Main.dc.html`.

Everywhere else:

| Element | Motion |
|---|---|
| Tab change | Highlight slides 480 ms on the spring; screen fades and rises 12 px in 180 ms |
| Bottom sheet | Slides up 520 ms with about 6% overshoot; backdrop fades 200 ms |
| Toggle | Knob snaps 340 ms on the spring; track colour fades 250 ms |
| Segmented | Highlight slides 480 ms on the spring |
| Status pill | Dot breathes every 1.4 s while printing, steady otherwise |
| Background | Blobs drift on a 22–30 s loop and lean slightly toward touch and scroll |
| Buttons | Every press squashes; release springs back |

Sound (when Sounds is on): soft click on presses, a short chirp when a print finishes, a "tear" click, and a surprise sound for flatmate doodles.

## 10. Accessibility

- Body text ≥ 4.5:1 against glass. Use `--pink-text` for pink text, never `--pink`.
- Tap targets ≥ 44 × 44 px.
- Status is never colour alone: the pill always has a label; errors have an icon and a sentence.
- Real `<button>`, `<a>`, `<input>` + `<label>`; `role="switch"` + `aria-checked` on toggles; `aria-label` on every icon-only button; `role="alert"` on error banners, `role="status"` on toasts.
- Honour `prefers-reduced-motion` and `prefers-reduced-transparency`, plus the in-app Reduce motion / Reduce transparency settings (apply `.rm` / `.solid` on the root).
- Plain words in labels: "Print now", "Every weekday at 07:30". Never "cron", "job ID", "queue ID".

## 11. Installable web app

- `manifest.webmanifest`: name and short_name "Wall Printer" (working name), `display: standalone`, `orientation: portrait`, `theme_color` and `background_color` `#121315` (no white flash).
- Icons: 512, 192, 180 (apple-touch-icon) and a maskable 512 with the slot inside the safe circle. Design: dark rounded square, green blob bottom-left, pink blob top-right, glass panel with a glowing green slot and a paper strip with a zig-zag bottom coming out. Reference: `Icon.dc.html` (export the icon from there or redraw as SVG).
- Splash: icon centred over the gradient, "Wall Printer", and "Finding the printer…" with a pulsing dot until the Pi answers.

## 12. Data the UI needs (suggested API)

Shapes are suggestions to keep front end and Pi in step.

| Endpoint | Purpose |
|---|---|
| `GET /api/status` (+ SSE `/api/events`) | `{ printer: "online"|"printing"|"paper_out"|"offline", queue: n, progress: 0–100, paperPercent, pi: { tempC, fan, uptimeS } }` |
| `POST /api/print` | Body: the document (blocks), copies, extraFeedLines, from. Returns job id + queue position |
| `POST /api/preview` | Same body, returns the 1-bit PNG at 384 px wide (the "As printed" view) |
| `GET/DELETE /api/queue/:id` | Queue list, cancel |
| `GET /api/history?source=&q=` · `POST /api/history/:id/reprint` | History feed, reprint |
| `GET/POST/PATCH/DELETE /api/schedules` | Schedules and routines; `POST /api/schedules/:id/preview` for wizard step 4 |
| `GET/POST /api/templates` | Built-in and saved templates |
| `GET/PATCH /api/settings/:group` | printer, button, led, connections, schedules, access, device, appearance |
| `POST /api/fonts` | Upload font; server returns a printed sample and a "min readable size" |
| `POST /api/led/test`, `POST /api/print/test` | Test controls |
| `POST /api/guest-notes` · `POST /api/guest-notes/:id/approve` | Guest page and approvals |

A document is a list of blocks, e.g. `text {content, font, size, bold, underline, inverse, align}`, `checkbox {label}`, `divider`, `datetime`, `qr {url}`, `sticker {name}`, `drawing {strokes or bitmap}`, `image {bitmap, style, brightness, contrast}`, `signature {name}`.

Image styles map to: Photo dither = Floyd–Steinberg (or Atkinson), Sharp = threshold, Halftone = ordered/dot pattern.

## 13. Reading the reference files

`reference/*.dc.html` files are design-tool mockups, not app code. To read them:

- Markup sits inside `<x-dc>`; `{{name}}` holes are filled from the `renderVals()` method in the `<script type="text/x-dc">` block at the bottom, where the sample data lives.
- `<sc-if value="{{flag}}">` is a conditional and `<sc-for list="{{items}}" as="x">` is a loop.
- `<dc-import name="TabBar" active="history">` embeds another file with props. Many frames are thin wrappers, e.g. `State-PaperOut` is just `Main` with `printer="paperout"`, and `Settings-LED` is `Settings` with `group="led"`. Look in `Main.dc.html` and `Settings.dc.html` for the real markup.
- `./support.js` is the design tool's runtime and is not included; the files won't run standalone. Classes come from `tokens.css`.
- Sample content (shopping list, London forecast, "Sam", "Flatmate", 60% paper, 81 °C) is placeholder.

| Reference file | Screen |
|---|---|
| `Tokens` · `Components` · `TabBar` | Foundations |
| `Main` (props `mode`, `view`, `printer`) | Create, all modes and printer states |
| `Create-Draw/Image/Templates/Printed` | Create variants |
| `Guest` | Guest note page |
| `Schedules` (prop `empty`) · `Schedules-Empty` | Schedules list |
| `Wizard` (prop `step`) · `Wizard-2/3/4` | Schedule wizard |
| `Routine` | Routine builder |
| `History` (prop `loading`) · `State-Loading` | History |
| `Settings` (prop `group`) · `Settings-*` | Settings home and groups |
| `State-Printing/Queue/PaperOut/Offline/NoPi` | Key states |
| `Wide-Create` / `Wide-Schedules` (prop `layout`) · `Tablet-*` | Tablet and desktop |
| `Motion` | Motion study |
| `Icon` | App icon and splash |

## 14. Open questions

- Product name and logo: working name "Wall Printer".
- LED: designed as one colour with brightness and patterns. Confirm the hardware.
- Light mode: only the switch is designed. No light screens yet.
- Should the arcade button also approve guest notes? Not designed in.
- Exact dot width (384) and supported built-in printer fonts: confirm from the printer datasheet.

## 15. Suggested build order

1. Shell: tokens, background, tab bar / side rail, status pill + status sheet, routing, PWA manifest.
2. Create in Text mode + the Pi-side renderer + "As printed" + Print with the full print-moment animation.
3. Queue and History, including failed jobs and Retry.
4. Printer states: paper out, offline, can't reach the Pi.
5. Schedules list, wizard, conditions, routines.
6. Settings groups, button and LED.
7. Draw, Image and Templates modes; guest page; quick actions; paper saver.
8. Tablet and desktop layouts; reduce motion and reduce transparency passes; accessibility check.

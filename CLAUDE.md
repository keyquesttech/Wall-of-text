# Wall Printer web app

Build spec: `design-handoff/HANDOFF.md` — read it before writing UI code. It is the source of truth for screens, states, motion and accessibility.

- Base stylesheet: `design-handoff/tokens.css` (colour tokens, glass, components, keyframes). Use its CSS variables; don't hard-code hexes.
- Visual reference: `design-handoff/reference/*.dc.html` are design mockups, not runnable code. See HANDOFF.md section 13 for how to read them.
- Mobile first at 390 × 844; side rail from 768 px; three columns from 1200 px.
- Printed output is 1-bit black, about 384 dots wide. The "As printed" preview must come from the same renderer that drives the printer.

## Backend, Pi setup and build order

`BUILD_PLAN.md` covers everything the UI spec does not: Raspberry Pi OS, first-boot Wi-Fi setup (the Pi hosts `WallOfText-Setup`, then the site lives at `http://walloftext.local/`), the backend, hardware, scheduling and the phase plan. Read it before writing any backend or deploy code. Where it disagrees with `HANDOFF.md`, `BUILD_PLAN.md` wins (see its section 3). Start at the phase named in section 13; section 16 has the start prompts.

# Print document format

`POST /api/preview` and `POST /api/print` take `{"document": {...}, "copies": 1}`.
A document is a list of blocks rendered top to bottom on a 384-dot-wide, 1-bit canvas
(`backend/walloftext/render/document.py`). The preview PNG is exactly the bitmap sent to the printer.

```json
{"blocks": [ ... ], "options": {"border": false, "gap": 8}}
```

| type | fields |
|---|---|
| `text` | `text`, `size` S/M/L/XL (18/22/30/40 px), `font` (`mono` `pixel` `silk` `sans` or an uploaded `u-…` id), `align` left/center/right, `bold`, `invert`, `underline`, `max_lines` |
| `heading` | `text`, `size` (default XL), `font`, `align` (default center), `invert` |
| `banner` | `text`: a white-on-black line (used for "from Sam · via Email · 18:42") |
| `datetime` | `format` (strftime), `size`, `align` |
| `divider` | `style` solid/dashed/dotted/wave/double/stars |
| `spacer` | `height` in dots (1–400) |
| `qr` | `data`, `size` S/M/L, `caption` |
| `checklist` | `items: [{text, done}]`, `size`, `font` |
| `columns` | `left`, `right`, `size`, `font` |
| `image` | `src` (data URL), `style` photo/sharp/halftone, `dither` floyd/atkinson/ordered, `brightness`, `contrast`, `invert`, `lighten`, `rotate`, `width` |
| `drawing` | `src` (data URL); rendered with the sharp threshold |

Characters the chosen font lacks print as `□` so the paper never has silent gaps.
Prints over 50 % black come back with a warning; `lighten: true` on images is the paper-safe limiter.
Unknown block types print as a small note instead of failing the whole print. Prints over 2 m are refused.

Preview response headers: `X-Wot-Rows`, `X-Wot-Length-Mm`, `X-Wot-Coverage`, `X-Wot-Warnings`.

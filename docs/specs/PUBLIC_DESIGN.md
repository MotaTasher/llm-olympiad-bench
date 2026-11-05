# Public-site design reference

Checked against live pages, bucket entry points and browser-computed styles on
**2026-11-05**. The owner's later correction on the same date overrides the
initial redesign: preserve Reasoning's compact composition and the formula-covered
**torn-paper** hero, recoloring the gray paper blue. Do not replace it with the
main site's liquid/abstract artwork, a staggered uppercase title or marketing-size
vertical gaps. Compare typography and shared brand details with the main site
without turning this benchmark into a copy of its landing-page layout.

## Sources of truth

Use the public [CS Space site](https://csspace.io/) for public-page layout and
the active production [LMS](https://lms.csspace.io/) for shared-component checks.
Both use Montserrat for body text, Unbounded for headings and `#030207` as the
page background. Their CSS variable named `--font-inter` actually resolves to
**Montserrat**; do not infer the font from the variable's name. The previous
Reasoning stylesheet used Inter and is not the brand source.

| Bucket | Observed contents and role | Design use |
| --- | --- | --- |
| `csspace-bucket` | Shared images, icons and logos; no HTML/CSS application entry point | Original brand assets |
| `csspace-public-prod` | Uploaded partner assets; no frontend entry point | Not a page-layout reference |
| `csspace-lms-prod` | Course/content objects; no frontend entry point | Not a page-layout reference |
| `lms.csspace.io` | Production LMS; entry references `assets/index-6N6VYEiR.css`, deployed 2026-11-03 | Current shared components and fonts |
| `dev.lms.csspace.io` | Development LMS; entry references `assets/index-D9xkbH_R.css`, deployed 2026-08-20 | Development comparison only |
| `newyear.csspace.io` | Seasonal site; entry references `assets/index-ZgGg0O-J.css`, deployed 2026-01-04 | Separate older visual language |
| Reasoning destination from `PUBLIC_RESULTS_S3_URI` | Benchmark frontend and sanitized generated results | Implementation target |

Only frontend entry points and design assets were read. Course content and
personal uploads are not design references. Old hashed CSS objects do not
identify the running application: always read `index.html` first.

The main public site currently references
`/_next/static/css/518056d7961a928b.css`; component rules are also emitted in
server-rendered `style[data-styled]` elements. Reading only its Tailwind bundle
misses the real layout. Hashes above record the audit; refresh the entry point
before future visual changes.

## Reference measurements, not a replacement page template

| Property | Mobile, below 744 px | Tablet, 744–1279 px | Desktop, at least 1280 px |
| --- | --- | --- | --- |
| Outer wrapper maximum | 1396 px | 1396 px | 1396 px |
| Wrapper horizontal padding | 24 px | 42 px | 42 px |
| Header top spacing | 40 px | 40 px | 42 px |
| Navigation capsule | 56 px high, radius 32 px | Same | Same |
| Hero top padding | 38 px | 211 px | 162 px |
| Hero heading | Unbounded 900, 32/40 px | Unbounded 900, 64/79 px | Unbounded 900, 100/124 px |
| Section heading | Unbounded 900, 24/30 px | Unbounded 900, 42/52 px | Unbounded 900, 64/79 px |
| Major section spacing | 150 px | 200 px | 250 px |
| Shared card padding/radius | 16/24 px | 24/32 px | 24/32 px |
| Outline button padding/radius | 12 px 16 px / 42 px | Same | Same |
| Outline button type | Montserrat 400, 14/18 px | Montserrat 400, 16/21 px | Same as tablet |

The source body uses Montserrat 400 at 16/24 px. Heading letter spacing is
normal. Navigation labels use 14/18 px, inactive white at 50% opacity and solid
white for active/hover states. The navigation surface is white at 10% opacity.
Outline controls use a white border at 20% opacity; filled controls are white
with `#04010b` text. Match the applicable component's interaction states rather
than inventing another accent palette.

Reasoning keeps the compact benchmark layout. Its shared content maximum is
1312 px, with 42 px viewport gutters and 24 px below 744 px. At viewport widths
1440 and 390, content starts at x=64 and x=24 respectively. The table scrolls
inside this container. The mixed-case two-line title stays left-aligned. Do not
import the source landing page's 150–250 px section spacing into the benchmark.

## Fonts and production restrictions

Use Montserrat for UI/body text and Unbounded for headings, matching the actual
brand fonts. The production proxy currently permits font downloads only from
`https://fonts.gstatic.com`; its `font-src` does **not** include `'self'`.
Local WOFF2 files introduced in the rejected redesign were therefore blocked,
and the browser substituted installed fonts despite the expected CSS family name.

The stylesheet imports the required weights from `https://fonts.googleapis.com`,
which is allowed by the existing `style-src`, and font files load from the
allowed Google Fonts host. Do not switch to local fonts until the proxy policy
has been updated and verified. Do not weaken CSP in application code.

For visual QA, use the production CSP in the preview and inspect actual font
requests and browser-rendered font data. A computed `font-family` string or
`document.fonts.check()` alone can pass when an installed fallback is used.
`CSS.getPlatformFontsForNode` must report the downloaded Montserrat/Unbounded
faces (`isCustomFont: true`) for representative Latin and Cyrillic text.

## Paper and page assets

- `public_results/styles.css` preserves the compact page structure, reading
  layouts and responsive table behavior.
- `assets/torn-paper-mask.svg` supplies the irregular outline for both paper
  layers; `assets/blue-paper-texture.svg` changes the original gray grain to
  a dark navy pigment. Keep the grain and all four torn edges visible.
  The later contrast correction requires pure-white hero text, a solid dark
  description panel. The owner subsequently requested white writing on the
  paper itself: render its formula artwork as pure white at full opacity,
  with `brightness(0) invert(1)` rather than a translucent gray treatment.
  Text contrast
  takes priority over the brightness of the decorative blue. Secondary text
  uses white at 78% opacity, and faint text at 66%; do not restore the previous
  low-opacity labels.
- `assets/formula-pattern-{desktop,mobile}.svg` supplies the original formula
  artwork. Use the same mask for it and the paper; do not stretch the formulas
  or substitute the main site's decorative WebP shapes.
- `assets/graphite-texture.svg` remains the original gray reference.
- All six HTML shells use the same stylesheet revision and the full CS Space
  logo remains readable in the mobile header.

Green/ochre/terracotta continue to encode full/partial/zero scores; reference
cards stay neutral. Preserve sorting, filters, complete-cell links, horizontal
table scrolling, Markdown/KaTeX and persisted reading-section states.

## Verification and publication

Inspect reference and local pages at matching desktop and mobile widths.
Check actual downloaded fonts, wrapper positions, button padding/radius, heading
sizes, all four paper edges, horizontal overflow, filters, catalog navigation and
an expanded math solution. Compare screenshots visually, not only CSS values.
Use a fresh browser context so existing site accounts/cookies are not involved.

Follow root `AGENTS.md` for Object Storage access. For a design-only release,
publish assets and CSS before HTML. Update existing extensionless route objects
from their corresponding shells. Preserve the deployed `generated/` snapshot;
do not replace production data with a local export during a visual change.
Verify bucket objects and public-domain responses; report TLS failures
separately from successful uploads.

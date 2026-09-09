---

name: Research Companion
description: A local research assistant with persistent project memory
colors:
ink-navy: "#202b3a"
rust-evidence: "#ad4937"
rust-wash: "#f8e7df"
paper: "#f4efe6"
paper-card: "#fbf8f2"
graphite-border: "#d8cdbd"
brass-active: "#e2b965"
night-ink: "#111820"
night-card: "#1a232c"
field-success: "#3e7656"
field-warning: "#b87925"
typography:
display:
fontFamily: "Georgia, Times New Roman, serif"
fontSize: "clamp(1.5rem, 3vw, 2rem)"
fontWeight: 600
lineHeight: 1.25
letterSpacing: "-0.02em"
body:
fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Arial, sans-serif"
fontSize: "1rem"
fontWeight: 400
lineHeight: 1.5
label:
fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Arial, sans-serif"
fontSize: "0.6875rem"
fontWeight: 600
lineHeight: 1.2
letterSpacing: "0.12em"
rounded:
sm: "6px"
md: "8px"
lg: "12px"
xl: "16px"
spacing:
xs: "4px"
sm: "8px"
md: "16px"
lg: "24px"
xl: "32px"
components:
button-primary:
backgroundColor: "{colors.ink-navy}"
textColor: "{colors.paper-card}"
rounded: "{rounded.md}"
padding: "8px 16px"
button-primary-hover:
backgroundColor: "{colors.rust-evidence}"
textColor: "{colors.paper-card}"
rounded: "{rounded.md}"
input:
backgroundColor: "{colors.paper-card}"
textColor: "{colors.ink-navy}"
rounded: "{rounded.md}"
padding: "8px 12px"
card:
backgroundColor: "{colors.paper-card}"
textColor: "{colors.ink-navy}"
rounded: "{rounded.lg}"
padding: "16px"

# Design System: Research Companion

## Overview

**Creative North Star: "The Research Field Notes"**

Research Companion now feels like a working archive: warm paper, ink-blue structure, and deliberate marks for evidence, attention, and state. The interface is calm enough for sustained reading but has a visible point of view suited to a portfolio artifact about agentic research and persistent memory.

The system uses editorial contrast instead of generic dashboard gray. Serif headings give the product a human, note-taking voice; the body remains a pragmatic system sans for scanability; monospace stays reserved for IDs, timestamps, arguments, and source material. Surfaces are layered tonally with restrained shadows, while rust and brass are reserved for meaningful signals.

**Key Characteristics:**

- Warm paper canvas with ink-navy structure.
- Rust evidence marks and brass active states.
- Editorial serif headings with utilitarian sans body copy.
- Rounded, tactile controls with quiet borders.
- Evidence and state remain visible without decorative noise.

## Colors

The palette is an archival paper-and-ink foundation with two functional accents: rust for evidence and attention, brass for active or in-progress states.

### Primary

- **Ink Navy** (#202b3a): Primary action surfaces, headings, and structural emphasis on the light theme.
- **Brass Active** (#e2b965): Primary action and focus accent in the night theme, preserving warmth against dark ink.

### Secondary

- **Rust Evidence** (#ad4937): Error, evidence, attention, and the occasional high-value interaction cue.
- **Field Success** (#3e7656): Completed tasks and successful operations.
- **Field Warning** (#b87925): In-progress work and approval attention.

### Neutral

- **Paper** (#f4efe6): The primary light-theme canvas.
- **Paper Card** (#fbf8f2): Raised content surfaces and readable controls.
- **Graphite Border** (#d8cdbd): Quiet dividers and input strokes.
- **Night Ink** (#111820): The dark-theme canvas.
- **Night Card** (#1a232c): Dark raised surfaces.

### Named Rules

**The Evidence Mark Rule.** Rust and brass should communicate a state or provenance cue; never use them as ambient decoration.

## Typography

**Display Font:** Georgia, Times New Roman, serif
**Body Font:** -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Arial, sans-serif
**Label/Mono Font:** SF Mono, Monaco, Cascadia Code, Roboto Mono, Consolas, monospace

**Character:** Headings feel like a research notebook; body copy is direct and highly readable. Labels use measured uppercase spacing only when they describe a system region or status.

### Hierarchy

- **Display** (600, 1.5–2rem, 1.25): Product and empty-state headings.
- **Headline** (600, 1.25rem, 1.25): Major local sections and dialog titles.
- **Title** (600, 1rem, 1.25): Thread titles and content headings.
- **Body** (400, 1rem, 1.5): Conversation copy and explanatory text, with long-form measure capped near 65–75ch.
- **Label** (600, 0.6875rem, 0.12em, uppercase where needed): Metadata, region labels, and status vocabulary.

### Named Rules

**The Instrument Rule.** Monospace is for information that behaves like an instrument reading—not for the whole interface.

## Layout

The app is a full-height two-pane workspace: optional thread history on the left and the active conversation on the right. The conversation column is capped at 1024px and keeps the composer anchored to the bottom. Memory context sits above the conversation as an inspectable strip, while task and file details remain close to the composer. On narrow screens, controls collapse to icon-plus-label combinations and panels stay fluid rather than imposing a fixed sidebar width.

Spacing follows a 4px base with 8px, 16px, 24px, and 32px groupings. Tight metadata stays together; content blocks receive generous separation.

## Elevation & Depth

The system uses tonal layering first and restrained ambient shadows second. Cards and dialogs use a single soft shadow when they need separation; borders handle most resting states. No hard offset shadows or decorative blur are used.

### Shadow Vocabulary

- **Low lift** (`0 1px 2px rgba(32, 43, 58, 0.06)`): Composer, active file tiles, and small raised controls.
- **Dialog lift** (`0 20px 25px -5px rgba(32, 43, 58, 0.12), 0 10px 10px -5px rgba(32, 43, 58, 0.06)`): Protected modal surfaces.

### Named Rules

**The Quiet Surface Rule.** A surface is either separated by a border or a shadow; use both only when the component needs protected focus.

## Shapes

Controls use gently rounded 6–8px corners. Content containers use 12px corners; larger empty-state surfaces use 16px. Borders are 1px and warm in the light theme, blue-gray in the night theme. Evidence excerpts use tonal blocks and full borders rather than thick side tabs.

## Components

### Buttons

- **Shape:** Gently rounded (8px), compact and tactile.
- **Primary:** Ink navy on paper with 8px 16px padding; brass on the night theme.
- **Hover / Focus:** Move toward rust on hover; use the shared ring token for focus without layout shift.
- **Secondary / Ghost:** Paper-card or transparent surfaces with quiet graphite borders and tonal hover fills.

### Chips

- **Style:** Small rounded-full status chips use a tinted background, 1px border, and matching readable text.
- **State:** Rust is reserved for attention; brass or field-success indicates active progress or completion.

### Cards / Containers

- **Corner Style:** 12px for content cards, 16px for major surfaces.
- **Background:** Paper Card over Paper; Night Card over Night Ink.
- **Shadow Strategy:** Low lift only where the surface must read as raised.
- **Border:** 1px Graphite Border, or a semantic state border when necessary.
- **Internal Padding:** 16px standard, 24px for protected dialogs.

### Inputs / Fields

- **Style:** Paper Card or Night Card fill, 1px border, 8px radius, 8–12px internal padding.
- **Focus:** Rust ring with a subtle tinted halo; preserve the visible caret and selection color.
- **Error / Disabled:** Rust error surface for actionable validation; disabled fields lower contrast without disappearing.

### Navigation

- **Style:** The app header is a quiet paper-card band with the product mark, current assistant context, and task actions.
- **Default / Hover / Active:** Thread selection uses a thin semantic border and tinted paper; hover uses a tonal fill.
- **Mobile:** Secondary labels hide before controls overflow; every icon-only control keeps an accessible name.

### Research Evidence

Memory recall, changes, connections, source excerpts, and operation history use compact bordered sections with explicit metadata. Evidence is visually distinct through tonal paper and typography, never through a decorative accent stripe.

## Do's and Don'ts

### Do:

- **Do** use warm paper, ink navy, rust, and brass as functional visual language.
- **Do** reserve monospace for source IDs, arguments, timestamps, and code.
- **Do** make memory provenance and state readable within seconds.
- **Do** keep borders quiet and use one elevation treatment per surface.

### Don't:

- **Don't** bring back the teal/gray dashboard palette.
- **Don't** use gradients, glass, or decorative blur as theme substitutes.
- **Don't** use thick colored side borders for evidence, alerts, or cards.
- **Don't** use accent colors without a state, provenance, or interaction reason.

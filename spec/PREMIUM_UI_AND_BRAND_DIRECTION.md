# Premium UI and visual design specification

## Design goal
A high-quality, expensive-looking B2B data operations platform: calm, clear, credible, and purposefully animated. Functional clarity must exceed decorative polish.

### Confirmed name and language
- Logo/name: **ClearTrace**
- Tagline: **Every issue explained. Every fix traceable.**
- Tone: trustworthy, technically capable, approachable and concise.
- Use the exact product name consistently.

### Recovered visual direction
- Light, restrained canvas.
- Deep navy text and headings.
- Cool blue-gray surfaces/cards.
- Restrained teal highlight/action color.
- Very limited warm gold accents for highlights/attention.
- Fine CSS background grid, subtle layered gradient, modest glow; never overpower data.
- Typography with confident hierarchy and generous whitespace.
- High quality micro-interactions, but respect reduced-motion preferences.
- Avoid stock photography, decorative neon, excessive blur, loud gradients, generic-looking template arrangements and tiny unreadable labels.

## Proposed semantic palette (guide, not recovered exact hex values)
- Canvas: `#F6F8FB`
- Text: `#11273A`
- Panel: `#FFFFFF`
- Soft surface: `#EDF3F6`
- Teal: `#137F83`
- Gold: `#C39A4B`
- Muted text: `#586C7C`
Choose final contrast-compliant shades with design review.

## Screen anatomy
1. **Sidebar:** ClearTrace identity, Overview, Data Quality, Repair Review, Audit Trail; active navigation and sensible collapsed mobile variant.
2. **Top bar:** current dataset file name, session-only indicator, global actions/controls that are real once connected.
3. **Hero:** “Understand every anomaly. Control every correction.” (new proposed copy) and short workflow.
4. **Upload and preview:** elegant CSV drag-and-drop surface and sample mode.
5. **Metric row:** completeness, duplicate rows, missing values, format/validation issues, with definitions.
6. **Findings workbench:** issue, affected field/rows, priority, plain-language explanation, proposed action and status.
7. **Repair review:** side-by-side before/after with Approve/Reject controls and risk copy.
8. **Audit trail:** timestamp, action, rows affected, reason, result; filter if implemented.
9. **Trust note:** unusual values, fuzzy merges and outliers require human judgment.
10. **Exports:** Download clean CSV, findings and audit log; disabled or visually honest until wired.

## Required states
- Empty upload; demo example; scan in progress; actual findings; zero findings; pending approvals; repair applied; undo performed; error; unsupported file; no data.
- All metrics must be bound to live app state once integrated.
- If standalone static page: mark numbers and controls `Illustrative demo`; do not fake backend success.

## Technical handoff constraints
- Produce `index.html`, `style.css`, `app.js`, optional local assets; modular named CSS tokens and background definitions.
- No external libraries/fonts/APIs/CDNs or network calls for the visual prototype.
- Mobile and desktop responsive, semantic markup, visible keyboard focus and accessible labels.
- Include `DESIGN_INTEGRATION_NOTES.md` describing where real data/handlers replace mocks.
- Preserve the Python functional core, existing data rules and audit behavior when integrating.

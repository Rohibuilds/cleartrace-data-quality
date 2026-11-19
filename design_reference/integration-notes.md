# ClearTrace — Streamlit Integration Notes

> **Audience:** Codex (or any developer) porting the visual design into an existing Streamlit app.
> These notes explain what to take, what to skip, and how to wire each piece.

---

## File Map

| File | Purpose | Port to Streamlit? |
|---|---|---|
| `cleartrace-background.css` | Design tokens, page background, surfaces, typography, badges, buttons | ✅ Yes — primary target |
| `index.html` | Full visual prototype (layout + markup) | 🔶 Reference only — do not copy the HTML structure directly |

---

## What to Port (from `cleartrace-background.css`)

### 1. Design Tokens (`:root` block)
Inject the entire `:root { ... }` block into Streamlit via:

```python
st.markdown("""
<style>
:root {
  --ct-canvas: #F4F6F9;
  --ct-teal-500: #24A99A;
  /* ... all other tokens ... */
}
</style>
""", unsafe_allow_html=True)
```

This makes every color, spacing, radius, and font variable available to custom HTML components you render via `st.components.v1.html()` or inline `st.markdown()`.

---

### 2. Page Background (`.ct-page-bg`)
Apply the layered dot-grid + gradient background to Streamlit's main container:

```python
st.markdown("""
<style>
/* Target Streamlit's main block wrapper */
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
  background-color: var(--ct-canvas);
  background-image:
    radial-gradient(ellipse 68% 48% at 92% 8%,
      rgba(36,169,154,0.08) 0%, transparent 70%),
    radial-gradient(ellipse 42% 36% at 4% 88%,
      rgba(200,154,46,0.055) 0%, transparent 65%),
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='28'%3E%3Ccircle cx='1' cy='1' r='1' fill='%231E3A5F' fill-opacity='0.055'/%3E%3C/svg%3E");
  background-size: 100% 100%, 100% 100%, 28px 28px;
  background-repeat: no-repeat, no-repeat, repeat;
}

/* Hide default Streamlit white header bar */
[data-testid="stHeader"] { background: transparent !important; }

/* Optional: remove default side padding */
.block-container { padding-top: 1.5rem !important; }
</style>
""", unsafe_allow_html=True)
```

> **Note:** Streamlit's internal CSS class names (`stAppViewContainer`, `stMain`, etc.) can change between Streamlit versions. Test after upgrades.

---

### 3. Card & Panel Surfaces
Use the `.ct-card` rules when wrapping content in `st.markdown()` HTML blocks.

Example metric card in Python:

```python
st.markdown(f"""
<div style="
  background: var(--ct-surface-0, #fff);
  border: 1px solid var(--ct-navy-100, #E4EAF2);
  border-radius: var(--ct-radius-lg, 14px);
  box-shadow: var(--ct-shadow-card);
  padding: 20px;
">
  <div style="font-size:11px;font-weight:600;letter-spacing:.07em;
              text-transform:uppercase;color:var(--ct-navy-500,#3A5880);">
    Completeness
  </div>
  <div style="font-size:2.1rem;font-weight:700;letter-spacing:-0.04em;
              color:var(--ct-navy-900,#0F1D35);line-height:1;">
    {completeness_pct:.1f}%
  </div>
</div>
""", unsafe_allow_html=True)
```

---

### 4. Badge / Risk Chips
Use inline styles drawing from token fallback values:

```python
def risk_badge(label: str, level: str) -> str:
    colors = {
        "high":   ("var(--ct-risk-high-bg,#FDE8E8)",   "var(--ct-risk-high-txt,#9B1C1C)"),
        "medium": ("var(--ct-risk-med-bg,#FEF3CD)",    "var(--ct-risk-med-txt,#7D5A00)"),
        "low":    ("var(--ct-risk-low-bg,#DCF5EE)",    "var(--ct-risk-low-txt,#145A45)"),
    }
    bg, txt = colors.get(level.lower(), ("var(--ct-surface-2)", "var(--ct-navy-500)"))
    return f"""
    <span style="display:inline-flex;align-items:center;padding:2px 10px;
                 border-radius:999px;background:{bg};color:{txt};
                 font-size:11px;font-weight:600;letter-spacing:.04em;">
      {label}
    </span>"""
```

---

### 5. Left Navigation
The HTML nav is **visual reference only** — Streamlit's sidebar is used instead.

**Recommended Streamlit approach:**

```python
with st.sidebar:
    # Branding
    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;
                padding:0 0 20px;border-bottom:1px solid rgba(255,255,255,0.08);">
      <!-- logo mark + name -->
    </div>
    """, unsafe_allow_html=True)

    page = st.radio("", ["Overview", "Data Quality", "Repair Review", "Audit Trail"],
                    label_visibility="collapsed")

    # Style the sidebar background
    st.markdown("""
    <style>
    [data-testid="stSidebar"] {
      background: var(--ct-surface-nav, #1A2E4A) !important;
    }
    [data-testid="stSidebar"] * { color: var(--ct-surface-nav-txt, #C8D8EC) !important; }
    </style>
    """, unsafe_allow_html=True)
```

---

### 6. Topbar / Dataset Header
Render as a `st.markdown()` sticky div above the main content.

```python
st.markdown(f"""
<div style="
  display:flex;align-items:center;justify-content:space-between;
  padding:12px 24px;
  background:rgba(244,246,249,0.9);
  border-bottom:1px solid var(--ct-navy-100,#E4EAF2);
  margin:-1.5rem -1rem 1.5rem;
">
  <div style="font-weight:600;color:var(--ct-navy-900,#0F1D35);">
    {dataset_name}
  </div>
  <div style="
    display:inline-flex;align-items:center;gap:6px;
    background:var(--ct-gold-100,#FBF3DC);
    border:1px solid rgba(200,154,46,0.25);
    border-radius:999px;padding:4px 12px;
    font-size:11px;font-weight:600;color:var(--ct-gold-500,#C89A2E);
  ">
    🔒 Session only
  </div>
</div>
""", unsafe_allow_html=True)
```

---

## What NOT to Port

| HTML element | Why |
|---|---|
| `<nav class="nav">` | Replace with Streamlit sidebar |
| `<div class="app-shell">` | Streamlit provides its own flex shell |
| `<div class="page-content">` | Streamlit's column layout handles this |
| `<script>` block | Prototype-only JS; replace with Streamlit callbacks (`st.button`, `st.session_state`) |
| Upload drop zone HTML | Use `st.file_uploader()` and style its wrapper |
| Responsive `@media` queries | Streamlit handles most responsiveness internally |

---

## Mock-Only Controls in the Prototype

The following controls in `index.html` perform **no real actions** and must be replaced with real Streamlit widgets:

| Prototype control | Streamlit equivalent |
|---|---|
| "Browse" / "Analyse File" buttons | `st.file_uploader()` → trigger backend |
| "Approve" / "Reject" repair buttons | `st.button()` → update `st.session_state` |
| "Export" / "Export Log" buttons | `st.download_button()` |
| "Edit" value button | `st.text_input()` in an expander or modal |
| Nav item clicks | `st.radio()` or `st.page_link()` |

---

## Streamlit Version Compatibility

Tested CSS selector patterns against **Streamlit ≥ 1.30**. If you are on an older version, replace `[data-testid="stMain"]` with `.main .block-container`.

---

## Font Note

The prototype references `"Inter"` as the primary font. This loads from the system if installed (no network call in the prototype). For Streamlit production:

- **Option A (zero CDN):** Use the system font stack already defined in `--ct-font-sans`. Works everywhere.
- **Option B (CDN):** Add Google Fonts import to Streamlit's config if network access is acceptable.

```python
# Option B — only if CDN fonts are permitted
st.markdown(
  '<link rel="preconnect" href="https://fonts.googleapis.com">'
  '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">',
  unsafe_allow_html=True
)
```

---

## Summary Checklist for Codex

- [ ] Copy `:root` token block from `cleartrace-background.css` → inject via `st.markdown`
- [ ] Apply page background CSS to `[data-testid="stAppViewContainer"]`
- [ ] Style `[data-testid="stSidebar"]` with `--ct-surface-nav`
- [ ] Replace HTML nav with `st.sidebar` + `st.radio`
- [ ] Replace upload drop zone with `st.file_uploader`
- [ ] Replace Approve/Reject buttons with `st.button` + `st.session_state`
- [ ] Render metric cards and findings table as `st.markdown(unsafe_allow_html=True)`
- [ ] Replace Export buttons with `st.download_button`
- [ ] Do **not** replace any existing backend/data-processing logic

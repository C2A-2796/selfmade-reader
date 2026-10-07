# Demo deck — Selfmade_Reader_Demo.pptx

14 slides with speaker notes: problem, root cause, how it works, 5-step demo, three app screens,
data and forwarding, run anywhere, deployment hardening, tested vs not tested, next steps.

## Just open it
`Selfmade_Reader_Demo.pptx` is already built (PowerPoint, Keynote, LibreOffice, Google Slides).
Fonts used: Cambria (titles) and Calibri (text).

## Rebuild or edit it (any PC)
Needs Node.js 18+.

    cd deck
    npm install
    node build.js          # writes Selfmade_Reader_Demo.pptx

`build.js` is the single source of the deck (edit text, colours, layout there).
`img/` holds the three app screenshots (recorded reads replayed through a stand-in reader) and
`rows.json` holds five real rows from the reader's CSV.

Theme colours: the script ends by calling the Claude Code *pptx* skill's `apply_theme.js`
(set `PPTX_SKILL_DIR` to the skill folder). Without it the file still opens, but scheme colours
fall back to Office's default palette. In that case ask Claude Code: "run the pptx skill applyTheme
step on deck/Selfmade_Reader_Demo.pptx using THEME from deck/build.js".

## Retake the screenshots
Run the app with sample data and open `http://127.0.0.1:8088/?theme=light#dash`
(also `#setup`, `#data`, `#log`), then crop the pages.

## Resume with Claude Code on another PC
    git clone https://github.com/C2A-2796/selfmade-reader.git
    cd selfmade-reader
    claude
Then say: "Read README.md, docs/SOP.md and deck/README.md. Continue from there:
rebuild the deck in deck/ if needed and tell me what is left to test (Windows/macOS, WiFi, real cloud endpoint)."
(Claude Code does not carry memory between computers; the repository is the memory.)

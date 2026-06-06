# AIOS Animations

Motion graphics and technical animations for the AIOS YouTube video series by DivineSide.

## Getting started

1. Clone this repo
2. Read `brief/video-brief.md` — section breakdown, what to animate, timestamps
3. Watch the video: [ADD ONEDRIVE LINK HERE]
4. Open Claude Code in this folder
5. Type `/hyperframes` to activate the Hyperframes skill
6. Tell Claude which section you want to animate

## Tools you need
- [Node.js](https://nodejs.org) — already installed if you set up this machine
- Hyperframes: `npm install -g hyperframes`
- Hyperframes skills: `npx skills add heygen-com/hyperframes`

## Project structure
```
brief/          ← video brief and transcription
src/sections/   ← one HTML file per animation
assets/         ← exported MP4s and media files
references/     ← style reference screenshots
CLAUDE.md       ← Claude Code instructions (read automatically)
```

## Style
Dark background, white text, purple glow. See `CLAUDE.md` for full details and `references/` for visual examples.

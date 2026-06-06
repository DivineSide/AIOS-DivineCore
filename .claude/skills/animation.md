# AIOS Animations — Claude Code Guide

## What this project is
This project contains motion graphics and technical animations for a YouTube video series about AI Operating Systems (AIOS) by DivineSide. Animations are built with Hyperframes (HTML + CSS + JS) and rendered to MP4 clips that get overlaid on the main video in CapCut.

## Your role
You are helping build professional motion graphics in the style of Apple, Google, and ElevenLabs product videos. The animator (your user) is not a developer — describe what you're doing in plain language, ask for feedback often, and keep iterations small.

## Visual style — strictly follow this
- **Background:** Deep dark `#0A0A0A` (not pure black)
- **Primary text/elements:** White `#FFFFFF`
- **Accent glow:** Purple `#9B30FF` — used on key elements, connectors, highlights
- **Font:** Inter (clean, modern, geometric)
- **Aesthetic:** Minimal, lots of breathing room, never cluttered
- **Motion:** Smooth ease-in-out, nothing snaps or jumps
- **Glow:** Soft light bloom on key elements (CSS box-shadow or filter: drop-shadow in purple)

## Animation types we use
- **Flowcharts** — showing how data or requests move between components (nodes connected by animated lines)
- **Text reveals** — words or phrases fade/slide in with precise timing
- **System diagrams** — AI agent architecture, component relationships
- **Data flows** — animated lines/particles moving through a system
- **Comparison tables** — two columns appearing side by side
- **Stat callouts** — a number or key fact zooms/fades in for emphasis

## How to start every session
1. Type `/hyperframes` to load the Hyperframes skill
2. Read the brief file in `/brief/` folder — it has section breakdowns and animation suggestions
3. Ask the user which section they want to work on
4. Build one animation at a time, preview it, get feedback before moving to the next

## Workflow for each animation
1. Plan what will appear on screen (describe it to the user first)
2. Write the HTML composition in `/src/sections/` — one file per animation
3. Run `npx hyperframes lint` to check for errors
4. Run `npx hyperframes preview` to show the user
5. Iterate based on feedback
6. Run `npx hyperframes render` to export the final MP4 to `/assets/`

## File naming
Name files by section number and topic:
- `src/sections/01-intro-hook.html`
- `src/sections/02-what-is-aios.html`
- `src/sections/03-agent-flowchart.html`

## Assets
- Place any images, video clips, or audio in `/assets/`
- Reference them as relative paths: `../assets/filename.mp4`

## References
- Check `/references/` folder for visual style examples
- The target aesthetic: clean dark tech, purple glow accents, smooth motion

## Important rules
- Never use white backgrounds
- Never use bright/neon colors other than the purple accent
- Keep animations under 15 seconds each (they are overlays, not standalone videos)
- Always preview before rendering
- Ask the user for feedback after every preview

# Frontend skill roles

Several design skills are installed and their advice overlaps on typography, color and layout. When building or restyling UI, give each skill one job so they don't compete:

1. **Research (optional):** `ui-ux-pro-max`, for an unfamiliar industry or when choosing palettes and font pairings. Treat its output as candidates, not the direction. Don't run it with `--persist` unless the user asks for design-system files.
2. **Direction (pick one):** `frontend-design` for a new page or project, `impeccable` for work inside an existing design system and for critique or polish passes. The chosen skill's decisions override ui-ux-pro-max.
3. **Motion:** `emil-design-eng` and `animate` when building animations, `apple-design` for gesture and spring-driven UI, `improve-animations` for a codebase-wide motion audit. `review-animations` only runs when the user types it.
4. **React/Next.js code:** `vercel-react-best-practices` for performance, `web-design-guidelines` for an accessibility and UX review.
5. **Verify before calling UI work done:** screenshot the rendered page (Playwright or Chrome) at desktop and phone widths. For pages that ship, also run the Chrome DevTools MCP Lighthouse audit and a performance trace, and fix what they flag.

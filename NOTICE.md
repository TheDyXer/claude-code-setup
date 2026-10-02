# Third-party notices

The installer, exporter, tests and docs in this repo are MIT licensed (see `LICENSE`).

The folders under `config/skills/` are **third-party skills**. They are included so that one
install gives you the same skill set. They keep their own authors and terms. Plugins
(superpowers, impeccable, cloudflare, claude-mem, fast-jev-compaction, unity) are **not**
copied here: the installer fetches them from their own public repos.

If you wrote one of these skills and want it credited differently or removed, open an issue
and it will be handled.

## Skills with a known source

| Skill | Source | Terms |
|---|---|---|
| grill-me, grill-with-docs, grilling, domain-modeling | github.com/mattpocock/skills | MIT, see below |
| requirements-clarity | github.com/davila7/claude-code-templates | MIT, see below |
| spec | github.com/dualform-labs/spec-skill | no license declared in that repo |
| web-design-guidelines | github.com/vercel-labs/agent-skills (author: vercel) | no license detected in that repo |
| vercel-react-best-practices | Vercel (author: vercel) | MIT, as declared in the skill's own `SKILL.md` |
| frontend-design | Anthropic | see `config/skills/frontend-design/LICENSE.txt` |

## Skills whose source was not recorded

animate, api-design, apple-design, database-migrations, emil-design-eng, improve-animations,
minimal-patch, no-ai-slop, performance-profiling, release-workflow, repo-analysis,
review-animations, security-review, ui-ux-pro-max, unity-mcp-skill.

These were collected over time and no license or origin was kept with them. They are shared
here in good faith. If you are the author, please open an issue.

## MIT notices for the skills above

```
MIT License

Copyright (c) 2026 Matt Pocock
Copyright (c) 2025 Daniel (San) Ávila

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Status line

The optional `statusline` extra downloads `statusline.ps1` from github.com/TheDyXer/claude-statusline
(MIT) at a pinned commit and checks its SHA-256 before installing it.

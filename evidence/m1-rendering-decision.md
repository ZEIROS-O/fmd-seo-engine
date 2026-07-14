# Rendering integration decision — measured 2026-07-14T14:59:29+00:00

**Verified V1 integration path: TanStack SSR route src/routes/blog/$slug.tsx over build-baked content/blog/<slug>.json**

Method: real `bun run build` in the isolated worktree, production preview
server, raw fetch of /blog/_spike and /blog/_spike/ with no JavaScript.

Static export under public/blog/<slug>/ was measured first and REJECTED:
nitro's static handler 307-redirects the trailing-slash variant to the
extensionless path, which has no directory-index resolution and falls
through to the SSR router as a 404. Only /blog/<slug>/index.html itself
served. The SSR route passes both slash variants with full head artifacts
(title, canonical, JSON-LD) in the initial HTML.

Checks:
- production_build: PASS — bun run build exit 0
- preview_server: PASS — listening on 4173
- variant:bare: PASS — 200 -> http://127.0.0.1:4173/blog/_spike
- variant:slash: PASS — 200 -> http://127.0.0.1:4173/blog/_spike
- fetch: PASS — 200 http://127.0.0.1:4173/blog/_spike
- title: PASS — Rendering Spike — Fresh Mobile Detailing Blog
- canonical: PASS — https://freshmobiledetail.com/blog/_spike
- body_substantial: PASS — 5179 chars
- structured_data: PASS — 1 JSON-LD block(s)
- internal_links: PASS — 19 internal link(s)
- cta: PASS — CTA text present
- image_metadata: PASS — 1 image(s) with alt

Receipt: 20260714T145920Z-rendering-spike-45339

# DCP landing site

Vue 3 + Vite 7 + Tailwind CSS v4. No router, no state management, no SSR —
intentionally a single-page marketing/intro site. Build output is a small
static bundle.

## Stack

- **Vue 3.5+** with `<script setup>` composition API
- **Vite 7** (rolldown-ready)
- **Tailwind CSS v4** via the new `@tailwindcss/vite` plugin (no
  `tailwind.config.js`; design tokens live in `src/style.css` under
  `@theme`)
- Inter + JetBrains Mono fonts via Google Fonts

## Run

```powershell
cd docs/site
npm install
npm run dev          # http://localhost:5173
npm run build        # static output → dist/
npm run preview      # serve dist/ on http://localhost:4173
```

## Project layout

```
docs/site/
├── package.json
├── vite.config.js
├── index.html              # Vite entry, mounts <div id="app">
├── public/
│   └── favicon.svg         # placeholder navy "D" mark
└── src/
    ├── main.js             # mounts App
    ├── style.css           # @import "tailwindcss" + @theme tokens
    ├── App.vue             # composes the sections
    └── components/
        ├── NavBar.vue
        ├── HeroSection.vue
        ├── FeaturesSection.vue
        ├── ArchitectureSection.vue   # inline SVG architecture diagram
        ├── QuickstartSection.vue
        ├── CompareSection.vue
        ├── SpecSection.vue
        └── SiteFooter.vue
```

## Design tokens

All brand colors and fonts are defined in `src/style.css` under `@theme`.
Tailwind v4 turns each `--color-*` into a utility automatically:

```css
@theme {
  --color-brand:       #1f4e79;   /* → bg-brand / text-brand / border-brand */
  --color-brand-dark:  #163a5c;
  --color-ink:         #0f172a;
  --color-ink-soft:    #475569;
  /* ... */
}
```

Change one number here and the whole site updates. The palette matches
the matplotlib figures in `docs/paper/figures/` — keep them in sync.

## Deploy

### GitHub Pages

```powershell
npm run build
# upload dist/ to the gh-pages branch
```

A `.github/workflows/deploy-site.yml` would automate this — left as
TODO until the public repo exists.

### Vercel / Netlify / Cloudflare Pages

Point them at this directory:
- Build command: `npm run build`
- Output directory: `dist`
- Install command: `npm install`
- Node version: 20+

All three vendors will detect Vue + Vite automatically.

### Custom domain

Add the domain in your hosting provider's dashboard. For GitHub Pages,
drop a `CNAME` file into `public/` containing one line:
```
dcp-protocol.dev
```

## Edit checklist before going public

1. **Logo / favicon.** `public/favicon.svg` is a CSS-rendered "D"
   placeholder. Commission a real mark before launch.
2. **OpenGraph image.** Add a 1200×630 PNG at `public/og.png` and link it
   in `index.html`.
3. **GitHub URLs.** Every `github.com/device-context-protocol/...` link
   is a placeholder. Replace once the org is registered.
4. **Domain.** Add `<meta property="og:url" content="...">` once you
   have one.
5. **Analytics decision.** Decide before launch. Plausible / Fathom are
   privacy-friendly drop-ins. Don't reach for GA on a protocol site that
   advertises minimalism.
6. **Spelling pass.** Read every line of `src/components/HeroSection.vue`
   and `FeaturesSection.vue` aloud once with fresh eyes.

## When to migrate beyond this

This minimalist setup is right while DCP is one page. Migrate when you
need any of:

- **Multiple spec pages** → swap to [Astro Starlight](https://starlight.astro.build/)
  or [Docusaurus](https://docusaurus.io). Both can wrap the existing Vue
  components.
- **Interactive demos** → keep Vue, add features incrementally.
- **Blog / changelog** → Astro is the cleanest path.
- **i18n** → Vue I18n if staying on Vue; otherwise the docs frameworks
  handle it.

Until then, eight components and one CSS file is the right amount of
complexity.

## Notes on Tailwind v4

If you've used v3, the differences worth knowing:

- **No `tailwind.config.js`.** Configuration lives in CSS via `@theme`.
- **Single import.** `@import "tailwindcss"` instead of three `@tailwind`
  directives.
- **`@tailwindcss/vite` plugin.** No PostCSS pipeline needed.
- **Automatic class detection** scans `index.html`, `src/**/*.{vue,js,ts}`
  by default — no `content:` array.
- **CSS variables for everything.** Every theme value is a CSS custom
  property at runtime; debugging is much easier.

See [tailwindcss.com/docs/v4-beta](https://tailwindcss.com/docs) for the
official migration guide.

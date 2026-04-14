# crypto.guru — React + Vite PWA Frontend

## Stack
- React + Vite + TypeScript
- Tailwind CSS v3 + shadcn/ui
- Recharts for Kronos forecast chart
- jsPDF + html2canvas for PDF export
- vite-plugin-pwa for PWA manifest + service worker

## API
Calls the live Render backend at `https://crypto-sniper-api.onrender.com`
- `POST /analyse` — V/P/R/T signal analysis
- `POST /kronos` — Kronos AI forecast

## Dev
```bash
npm install
npm run dev        # http://localhost:5000
```

## Build
```bash
npm run build      # outputs to dist/public/
```

## Deploy
Netlify / Cloudflare Pages — point to `dist/public/` after build.
Custom domain: **crypto.guru**

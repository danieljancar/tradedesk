# Dashboard

React 19, Vite, Tailwind 4, shadcn/ui on Radix, TanStack Query for every GET (`useApi` in `src/lib/query.ts`), lightweight-charts for candles, Recharts for small charts. `pnpm build` writes to `../src/tradedesk/web/dist`, which is committed.

## Text in the UI

The root `CLAUDE.md` writing rules apply. On top of that:

- No footnotes or captions under a panel saying where data comes from, how often it refreshes or how it's sized.
- No helper sentences under values unless the value is unreadable without it. A tooltip or the glossary (`Term`) is the place for explanations.
- Labels are short nouns: "Size", "Margin", "Open interest". Empty states say what's missing in one line.
- Fixed explanation text lives in `src/lib/learn.ts` and the components. It's ours, not agent output, so keep it as tight as the rest.

## Behaviour

- Panels with a title fold from their header (`Box` in `shell.tsx`). Layout choices, layers and order are kept in localStorage, wrapped in try/catch.
- Charts are built once per asset and bar size and updated in place. Never rebuild a chart on a data refresh, it throws away the user's zoom.
- Show skeletons while loading, keep showing the last data while refreshing.
- Check new pages at 320, 375, 768, 1280 and 1440 wide with no horizontal scroll.

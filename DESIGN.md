# Chromantis interface direction

Chromantis is a family photo library for finding and classifying an existing archive.
The Android client uses Kotlin, Compose and Material 3. Code stays in English; the
family interface is Spanish. Use the same service, people and permission model.

## Visual and interaction rules

- Give the library a readable hierarchy: app identity, page title, content, then actions.
- Show years as large, quiet tiles with real indexed album counts. Never fabricate totals.
- Use compact, rounded Material icons from one family, always paired with labels for destinations.
- Put the three phone destinations within thumb reach: Folders, Organize, Search.
- Show album covers only when entering an album list. Lazy visible cards request one
  small preview through the existing client and its bounded cache. The year library
  uses index metadata only. Missing previews fall back to a folder tile.
- Keep album names readable without changing their indexed names or paths. Show full
  paths in the gallery, and retain stable identities for edits.
- Treat people as selectable rows with initials, names and saved aliases. Do not
  introduce face identification into manual tagging.
- Present quick classification as one calm folder card. Explain the exact source
  of a suggestion, keep swipe gestures optional, and provide equally clear buttons
  for accepting, leaving pending and opening the full editor.
- Make search read like a short conversation: offer grounded example prompts, keep
  the current request visible, accept one refinement at a time, and show removable
  deterministic filters beside visual results. Do not imply that a model ran when
  the local rules handled the request.
- Keep Save visible outside the scrolling review form, including conflict feedback.
- Use warm neutral surfaces, forest-green actions and restrained clay accents. Dark
  mode must preserve the same hierarchy. Avoid gradients, arbitrary arrows, emoji
  controls, decorative dashboards and promotional copy.
- Prefer grouping and spacing over divider lines. Touch controls need meaningful
  labels and adequate targets. Do not shrink text to squeeze in more controls.

## References and tools reviewed

| Resource | Useful for | Boundary |
| --- | --- | --- |
| [Android layout and navigation patterns](https://developer.android.com/design/ui/mobile/guides/layout-and-content/layout-and-nav-patterns) | Native navigation, hierarchy, reachable actions | Phone layout comes first; validate wider and larger-text layouts separately |
| [Android UI kit and Theme Builder](https://developer.android.com/design/ui/mobile) | Type, spacing, palettes, Figma references | No runtime dependency on Figma or an online theme service |
| [Ente Photos](https://ente.io/) and [Immich](https://immich.app/) | Photo-first browsing, albums, people and search | Learn interaction patterns; do not add their backup or AI services |
| [UI/UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | Its Compose-specific guidelines and review vocabulary | Reviewed as a resource, not installed as a project dependency |
| [Impeccable](https://impeccable.style/designing/) | Critique, hierarchy, consistency and iteration | Primarily a frontend workflow; adapt principles to Compose rather than generating web UI |
| [Mobbin](https://mobbin.com/) | References from shipped screens and flows | Optional research resource; no subscription required by Chromantis |

## Review loop

Run the existing synthetic Compose flow and inspect its exported light, dark,
album-cover, gallery and curation screens. The integration fixture keeps its offline
HTTP-client archive separate from its visual archive. Assert that Ana can still be
selected, saved and found by alias, and that Save is visible without scrolling.

Screenshots of production composables in a test host are not proof of launcher
cold-start recovery or physical-device behavior. Keep those checks explicit in
PLANNING.md. Use synthetic content for all published screenshots and comparisons.

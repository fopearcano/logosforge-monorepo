/**
 * @logosforge/whiteboard-shared-ui — the Whiteboard (Free) shared DESIGN LAYER.
 *
 * Themes (the Claude Design palettes), tokens + token application, the syntax
 * colour palette, persistence, and the React theme glue. The stylesheet itself
 * lives at `./styles/app.css` (import it directly: `@logosforge/whiteboard-shared-ui/styles/app.css`).
 *
 * Single source of truth for the Whiteboard visual identity — consumed by
 * whiteboard-desktop (Electron) today and whiteboard-web later, so the two stay
 * in lock-step. Never shares UI with the Pro line.
 */

export * from './styles/themes/themeTokens';
export * from './styles/themes/predefinedThemes';
export * from './styles/themes/syntaxThemes';
export * from './styles/themes/customThemeStorage';
export * from './styles/themes/ThemeProvider';
export * from './styles/themes/useTheme';

# Theme System Documentation

The RVC2API frontend supports a theming system that allows users to switch between different visual themes.

## Available Themes

The following themes are available:

- **Default**: The standard dark blue theme
- **Dark**: A darker blue-gray theme
- **Light**: A light theme with dark text on light background

## How to Use

1. The theme selection dropdown is located in the top-right corner of the application
2. Select a theme from the dropdown to immediately apply it
3. Your theme selection is saved to localStorage and will persist between sessions

## How Themes Work

The theming system uses CSS variables defined in `src/styles/themes.css` and applied through Tailwind CSS classes. The theme is stored in localStorage and applied via a class on the HTML element.

## Adding New Themes

To add a new theme:

1. Edit `src/styles/themes.css` to add your new theme class with custom CSS variables
2. Add your theme to the `themeOptions` array in `src/components/ThemeSelector.tsx`
3. Optionally customize Tailwind config if needed for new color options

### Example: Adding a "Night" Theme

```css
/* In themes.css */
.theme-night {
  --rv-primary: #1E40AF;
  --rv-secondary: #047857;
  --rv-accent: #6D28D9;
  --rv-background: #030712;
  --rv-surface: #111827;
  --rv-text: #E5E7EB;
  --rv-error: #B91C1C;
  --rv-warning: #B45309;
  --rv-success: #047857;
}
```

```typescript
// In ThemeSelector.tsx
const themeOptions: ThemeOption[] = [
  { id: "theme-default", label: "Default", value: "default" },
  { id: "theme-dark", label: "Dark", value: "dark" },
  { id: "theme-light", label: "Light", value: "light" },
  { id: "theme-night", label: "Night", value: "night" }
];
```

## Technical Implementation

- `ThemeContext.tsx`: Provides theme state management and localStorage persistence
- `ThemeSelector.tsx`: UI component for selecting themes
- `themes.css`: CSS variables for each theme
- `tailwind.config.js`: Maps CSS variables to Tailwind color classes

Changes are applied in real-time without requiring page reload.

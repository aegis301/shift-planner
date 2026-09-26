# UI primitives

Shared controls for the workbench and the member area. Pages pass labels in; these components do not read the i18n dictionaries.

| Component | Use |
|---|---|
| `Dialog` | Non-destructive overlays. Escape, focus trap, and focus return come from Radix. |
| `AlertDialog` | Destructive confirmation (delete a month, regenerate a roster, delete a template, remove a membership, delete an organization). |
| `DropdownMenu` | App shell organization and user menus, planning-period status menu. |
| `Popover` | Anchored panels. The roster picker uses `ComboboxAnchor` so the cell button can keep `aria-haspopup="listbox"`. |
| `Combobox` | `cmdk` inside a popover. Roster assignment search, clear, and member pick. |
| `Tooltip` | Short hints. Wrap the tree in `TooltipProvider` (the app shell does). |
| `Tabs` | Tab lists. |
| `Select` | Single-value lists. |
| `ToggleGroup` | Exclusive or multiple toggles. |
| `ScrollArea` | Scrollable regions. |
| `Button` | `primary`, `secondary`, `ghost`, `danger`; sizes `sm` and `md`. |
| `Badge` | `neutral`, `info`, `warning`, `error`. |
| `Input`, `Textarea`, `Kbd` | Fields and keyboard hints. |

Every component forwards a ref, accepts `className`, and uses the tokens below.

## Tokens

Defined on `:root` and `[data-density="comfortable"]` in `app/globals.css`. `[data-density="compact"]` overrides the cell metrics. `<html data-density="comfortable">` is the default. There is no dark theme and no density toggle in the UI yet.

| Token | Tailwind |
|---|---|
| `--color-surface` | `bg-surface` |
| `--color-surface-muted` | `bg-surface-muted` |
| `--color-border` | `border-default`, `border-border` |
| `--color-text` | `text-text` |
| `--color-text-muted` | `text-muted` |
| `--color-accent` | `bg-accent`, `text-accent` |
| `--color-danger` | `bg-danger`, `text-danger` |
| `--color-warning` | `text-warning` |
| `--color-info` | `text-info` |
| `--color-severity-info`, `--color-severity-warning`, `--color-severity-error` | `bg-severity-info`, `bg-severity-warning`, `bg-severity-error` |
| `--radius-sm`, `--radius-md`, `--radius-lg` | `rounded-token-sm`, `rounded-token-md`, `rounded-token-lg` |
| `--space-cell-x`, `--space-cell-y` | `px-cell-x`, `py-cell-y` |
| `--font-size-cell` | `text-cell` |

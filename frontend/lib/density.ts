export const DENSITY_STORAGE_KEY = "shift-planner-density";

export type Density = "comfortable" | "compact";

export function readDensity(): Density {
  try {
    return window.localStorage.getItem(DENSITY_STORAGE_KEY) === "compact" ? "compact" : "comfortable";
  } catch {
    return "comfortable";
  }
}

export function applyDensity(density: Density) {
  document.documentElement.dataset.density = density;
  try {
    window.localStorage.setItem(DENSITY_STORAGE_KEY, density);
  } catch {
    return;
  }
}

export function memberAreaHref(path: string, search: URLSearchParams, tab: "roster" | "shifts" | null = null): string {
  const params = new URLSearchParams();
  const period = search.get("period");
  const shiftGroup = search.get("shiftGroup");
  if (period) {
    params.set("period", period);
  }
  if (shiftGroup) {
    params.set("shiftGroup", shiftGroup);
  }
  if (path === "/my-planning" && tab) {
    params.set("tab", tab);
  }
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

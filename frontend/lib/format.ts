export function titleCase(value: string | null | undefined): string {
  if (!value) return "Not available";
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatDuration(value: number | null | undefined): string {
  if (value === null || value === undefined) return "Not available";
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}

export function formatMetric(value: unknown): string {
  if (value === null || value === undefined) return "N/A";
  if (typeof value === "number") {
    if (value >= 0 && value <= 1) return `${(value * 100).toFixed(1)}%`;
    return value.toLocaleString();
  }
  return String(value);
}

export function truncate(value: string, length = 86): string {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

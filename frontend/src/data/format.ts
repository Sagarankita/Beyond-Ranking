export function titleCase(value: string): string {
  return value
    .replace(/^policy_/, "")
    .replaceAll("__", " · ")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatNumber(value: number, maximumFractionDigits = 2): string {
  return value.toLocaleString("en-IN", { maximumFractionDigits });
}

export function formatMoney(value: number): string {
  const sign = value < 0 ? "−" : "";
  const absolute = Math.abs(value);
  if (absolute >= 10_000_000) return `${sign}₹${(absolute / 10_000_000).toFixed(2)} Cr`;
  if (absolute >= 100_000) return `${sign}₹${(absolute / 100_000).toFixed(1)} L`;
  return `${sign}₹${formatNumber(absolute, 0)}`;
}

export function formatValue(value: number, unit: string): string {
  if (unit === "INR") return formatMoney(value);
  if (Math.abs(value) < 1 && value !== 0) return formatNumber(value, 3);
  return `${formatNumber(value)}${unit && unit !== "configured decision unit" ? ` ${unit}` : ""}`;
}

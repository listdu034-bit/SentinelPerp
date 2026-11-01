import { format, isValid, parseISO } from "date-fns";
export const number = (value?: number | null) =>
  value == null
    ? "—"
    : new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 8 }).format(
        value,
      );
export const timestamp = (value?: string | null) => {
  if (!value) return "—";
  const date = parseISO(value);
  return isValid(date) ? format(date, "yyyy-MM-dd HH:mm:ss") : "—";
};

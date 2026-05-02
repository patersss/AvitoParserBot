export function formatDate(value: string | null | undefined) {
  if (!value) {
    return "не задано";
  }
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatPrice(value: number | null) {
  if (value === null || value === undefined) {
    return "цена не указана";
  }
  return new Intl.NumberFormat("ru-RU").format(value) + " ₽";
}

export function toDateTimeLocal(value: string | null | undefined) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60_000);
  return local.toISOString().slice(0, 16);
}

export function fromDateTimeLocal(value: string) {
  return value ? new Date(value).toISOString() : null;
}

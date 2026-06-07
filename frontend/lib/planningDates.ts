function padDatePart(value: number): string {
  return String(value).padStart(2, "0");
}

function toIsoDate(year: number, month: number, day: number): string {
  return `${year}-${padDatePart(month)}-${padDatePart(day)}`;
}

export function monthDateBounds(year: number, month: number): { min: string; max: string } {
  const lastDay = new Date(year, month, 0).getDate();
  return {
    min: toIsoDate(year, month, 1),
    max: toIsoDate(year, month, lastDay)
  };
}

export function expandInclusiveDateRange(from: string, to: string): string[] {
  const start = new Date(`${from}T12:00:00`);
  const end = new Date(`${to}T12:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) {
    return [];
  }
  const dates: string[] = [];
  const cursor = new Date(start);
  while (cursor <= end) {
    dates.push(
      toIsoDate(cursor.getFullYear(), cursor.getMonth() + 1, cursor.getDate())
    );
    cursor.setDate(cursor.getDate() + 1);
  }
  return dates;
}

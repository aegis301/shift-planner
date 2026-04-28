export function Card({ children }: { children: React.ReactNode }) {
  return <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-soft">{children}</section>;
}

export function Field({
  label,
  children
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="grid gap-1 text-sm font-medium text-slate-700">
      {label}
      {children}
    </label>
  );
}

export const inputClass =
  "h-11 rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none ring-mint/20 transition focus:ring-4";


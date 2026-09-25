export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`min-w-0 rounded-lg border border-slate-200 bg-white p-5 shadow-soft ${className ?? ""}`}>
      {children}
    </section>
  );
}

export function Field({
  label,
  hint,
  children
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="grid gap-1 text-sm font-medium text-slate-700">
      {label}
      {children}
      {hint ? <span className="font-normal text-xs text-slate-500">{hint}</span> : null}
    </label>
  );
}

export const inputClass =
  "h-11 rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none ring-mint/20 transition focus:ring-4";


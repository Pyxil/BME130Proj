import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "record";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand-700 text-white hover:bg-brand-800 disabled:bg-slate-300 disabled:text-slate-600",
  secondary:
    "bg-white text-brand-800 ring-1 ring-inset ring-brand-700/30 hover:bg-brand-50 dark:bg-slate-900 dark:text-brand-200 dark:ring-brand-500/40 dark:hover:bg-slate-800",
  ghost: "text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800",
  danger: "bg-rose-700 text-white hover:bg-rose-800",
  record: "bg-record text-white hover:bg-rose-700",
};

export function Button({
  variant = "primary", size = "md", className = "", children, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "md" | "lg"; children: ReactNode }) {
  const sizes = size === "lg" ? "min-h-14 px-6 text-lg" : "min-h-12 px-5 text-base";
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-xl font-bold transition-colors disabled:cursor-not-allowed ${sizes} ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Card({ children, className = "", as: Tag = "section", ...rest }: {
  children: ReactNode; className?: string; as?: "section" | "div" | "article"; "aria-labelledby"?: string;
}) {
  return (
    <Tag className={`rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 sm:p-6 dark:bg-slate-900 dark:ring-slate-800 ${className}`} {...rest}>
      {children}
    </Tag>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-3 text-slate-700 dark:text-slate-300">
      <span className="h-6 w-6 animate-spin rounded-full border-4 border-brand-200 border-t-brand-700" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function Alert({ kind = "info", title, children }: { kind?: "info" | "error" | "warning" | "success"; title?: string; children: ReactNode }) {
  const styles = {
    info: "bg-sky-50 text-sky-900 ring-sky-200 dark:bg-sky-950 dark:text-sky-100 dark:ring-sky-900",
    error: "bg-rose-50 text-rose-900 ring-rose-200 dark:bg-rose-950 dark:text-rose-100 dark:ring-rose-900",
    warning: "bg-amber-50 text-amber-900 ring-amber-200 dark:bg-amber-950 dark:text-amber-100 dark:ring-amber-900",
    success: "bg-emerald-50 text-emerald-900 ring-emerald-200 dark:bg-emerald-950 dark:text-emerald-100 dark:ring-emerald-900",
  }[kind];
  return (
    <div role={kind === "error" ? "alert" : "status"} className={`rounded-xl p-4 ring-1 ${styles}`}>
      {title && <p className="font-bold">{title}</p>}
      <div>{children}</div>
    </div>
  );
}

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "good" | "fair" | "poor" | "brand" }) {
  const tones = {
    slate: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
    good: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-100",
    fair: "bg-amber-100 text-amber-900 dark:bg-amber-900/60 dark:text-amber-100",
    poor: "bg-rose-100 text-rose-800 dark:bg-rose-900/60 dark:text-rose-100",
    brand: "bg-brand-100 text-brand-900 dark:bg-brand-900/60 dark:text-brand-100",
  }[tone];
  return <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-bold ${tones}`}>{children}</span>;
}

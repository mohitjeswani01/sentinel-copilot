/**
 * DemoDataBadge — A subtle pill indicator showing that the adjacent
 * data is hardcoded / mock and not yet wired to a real backend.
 *
 * Remove this component (and its imports) once real backend data
 * replaces the mock values.
 */
export function DemoDataBadge({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full bg-muted text-[10px] font-mono uppercase tracking-widest text-muted-foreground select-none ${className}`}
    >
      Demo Data
    </span>
  );
}

export function Pill({ children, tone = 'success' }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

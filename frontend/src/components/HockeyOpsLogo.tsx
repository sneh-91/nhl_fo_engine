export function HockeyOpsLogo(props: { className?: string; title?: string }) {
  const { className, title = "HockeyOps" } = props;

  return (
    <img
      className={className}
      src="/hockeyops_ai_circuit_lockup.svg"
      alt={title}
      width={1280}
      height={360}
    />
  );
}

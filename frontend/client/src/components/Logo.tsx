export function Logo({ size = 32 }: { size?: number }) {
  return (
    <img
      src="/logo-mark.png"
      width={size}
      height={size}
      alt="Crypto Sniper logo"
      style={{ display: "block", objectFit: "contain", flexShrink: 0 }}
    />
  );
}

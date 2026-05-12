export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-label="Crypto Sniper logo"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="hexOuter" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#7c3aed" />
          <stop offset="100%" stopColor="#6d28d9" />
        </linearGradient>
        <linearGradient id="hexInner" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#0f0a1a" />
          <stop offset="100%" stopColor="#1a0f2e" />
        </linearGradient>
        <linearGradient id="crosshair" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#22d3ee" />
          <stop offset="100%" stopColor="#38bdf8" />
        </linearGradient>
      </defs>

      {/* Outer hexagon */}
      <polygon
        points="16,1.5 27,7.75 27,20.25 16,26.5 5,20.25 5,7.75"
        fill="url(#hexOuter)"
      />

      {/* Cyan edge highlight */}
      <polygon
        points="16,1.5 27,7.75 27,20.25 16,26.5 5,20.25 5,7.75"
        fill="none"
        stroke="#22d3ee"
        strokeWidth="0.5"
        opacity="0.6"
      />

      {/* Inner dark hexagon */}
      <polygon
        points="16,6 22.5,9.75 22.5,20.25 16,24 9.5,20.25 9.5,9.75"
        fill="url(#hexInner)"
      />

      {/* Crosshair — vertical */}
      <line
        x1="16" y1="10.5"
        x2="16" y2="18.5"
        stroke="url(#crosshair)"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      {/* Crosshair — horizontal */}
      <line
        x1="11.5" y1="14.5"
        x2="20.5" y2="14.5"
        stroke="url(#crosshair)"
        strokeWidth="1.5"
        strokeLinecap="round"
      />

      {/* Centre dot */}
      <circle cx="16" cy="14.5" r="1.8" fill="#22d3ee" />
    </svg>
  );
}

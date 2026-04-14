export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-label="crypto.guru logo"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Outer ring — gradient */}
      <defs>
        <linearGradient id="logoGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#7c3aed" />
          <stop offset="50%" stopColor="#818cf8" />
          <stop offset="100%" stopColor="#38bdf8" />
        </linearGradient>
      </defs>
      <circle cx="16" cy="16" r="14" stroke="url(#logoGrad)" strokeWidth="2" />
      {/* Inner G letterform */}
      <path
        d="M20 11.5C18.7 10.5 17.4 10 16 10C12.7 10 10 12.7 10 16C10 19.3 12.7 22 16 22C18.6 22 20.8 20.3 21.7 17.9H16.5V15.5H24C24 15.7 24 15.9 24 16C24 20.4 20.4 24 16 24C11.6 24 8 20.4 8 16C8 11.6 11.6 8 16 8C18.2 8 20.2 8.9 21.7 10.3L20 11.5Z"
        fill="url(#logoGrad)"
      />
    </svg>
  );
}

export function LogoMark({ size = 38 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <defs>
        <linearGradient id="cuspia-mark" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#14808a" />
          <stop offset="1" stopColor="#0b3d4a" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill="url(#cuspia-mark)" />
      <g transform="translate(8 8)">
        <path
          fill="#fff"
          d="M12 5.2c-1.5-1-3-1.7-4.6-1.5C4.9 4 3.5 6.1 3.6 8.8c.1 2 .8 3.5 1.3 5.2.5 1.8.6 3.4 1.1 5 .3 1 .8 1.8 1.6 1.8 1 0 1.4-1 1.7-2.2.3-1.3.6-3.1 2.7-3.1s2.4 1.8 2.7 3.1c.3 1.2.7 2.2 1.7 2.2.8 0 1.3-.8 1.6-1.8.5-1.6.6-3.2 1.1-5 .5-1.7 1.2-3.2 1.3-5.2.1-2.7-1.3-4.8-3.8-5.1-1.6-.2-3.1.5-4.6 1.5Z"
        />
        <path
          fill="none"
          stroke="#14808a"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          d="m8.6 9.6 2.5 2.5 4.4-4.6"
        />
      </g>
    </svg>
  );
}

export function Logo() {
  return (
    <span className="logo">
      <LogoMark />
      <span className="logo-text">
        <strong>Cuspia</strong>
        <small>Treatment Planning</small>
      </span>
    </span>
  );
}

export function Logo({ size = 28, withWordmark = true, className = '' }) {
  const height = size;
  const width = withWordmark ? size * 4.1 : size;

  return (
    <svg
      className={`brand-logo ${className}`}
      width={width}
      height={height}
      viewBox={withWordmark ? '0 0 205 50' : '0 0 50 50'}
      role="img"
      aria-label="Indatta"
    >
      <g fill="none" fillRule="evenodd">
        <path
          className="brand-logo-mark"
          d="M6 27c0-11.6 9.4-21 21-21s21 9.4 21 21-9.4 21-21 21S6 38.6 6 27Zm14-8.4a8.4 8.4 0 1 0 0 16.8 8.4 8.4 0 0 0 0-16.8Z"
          fill="currentColor"
        />
        {withWordmark && (
          <>
            <text
              x="58"
              y="36"
              fontFamily="Inter, 'Segoe UI', sans-serif"
              fontWeight="700"
              fontSize="30"
              letterSpacing="-0.5"
              fill="currentColor"
              className="brand-logo-text"
            >
              indatta
            </text>
            <path
              className="brand-logo-flame"
              d="M182 12c3 4 9 5 15 3-3 5-10 9-17 7-5-1.4-7-6-6-10 2.6-2 6 0 8 0Z"
              fill="url(#flameGradient)"
            />
            <defs>
              <linearGradient id="flameGradient" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#f6b52c" />
                <stop offset="55%" stopColor="#f0812f" />
                <stop offset="100%" stopColor="#e2432c" />
              </linearGradient>
            </defs>
          </>
        )}
      </g>
    </svg>
  );
}

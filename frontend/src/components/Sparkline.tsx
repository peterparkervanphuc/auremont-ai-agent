interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
}

// Đường xu hướng nhỏ dưới stat card — không dùng thư viện chart ngoài cho một biểu đồ đơn giản.
export function Sparkline({ values, width = 96, height = 28 }: SparklineProps) {
  if (values.length < 2) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / range) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const trendUp = values[values.length - 1] >= values[0];

  return (
    <svg
      className={`sparkline ${trendUp ? "sparkline--up" : "sparkline--down"}`}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
    >
      <polyline points={points} fill="none" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

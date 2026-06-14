import type { TimelinePoint } from "@/types/api";

interface ProbabilityChartProps {
  points: TimelinePoint[];
  activeSequence?: number;
}

export function ProbabilityChart({
  points,
  activeSequence,
}: ProbabilityChartProps) {
  const width = 760;
  const height = 190;
  const padding = 22;
  const path = points
    .map((point, index) => {
      const x =
        padding +
        (index / Math.max(points.length - 1, 1)) * (width - padding * 2);
      const y = padding + (1 - point.home_probability) * (height - padding * 2);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  const area = path
    ? `${path} L ${width - padding} ${height - padding} L ${padding} ${height - padding} Z`
    : "";
  const activeIndex = Math.max(
    0,
    points.findIndex((point) => point.sequence === activeSequence),
  );
  const active = points[activeIndex] ?? points.at(-1);
  const activeX =
    padding +
    (activeIndex / Math.max(points.length - 1, 1)) * (width - padding * 2);
  const activeY = active
    ? padding + (1 - active.home_probability) * (height - padding * 2)
    : height / 2;

  return (
    <div className="chart-wrap" aria-label="Home win probability over time">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Home win probability over time"
      >
        {[0.25, 0.5, 0.75].map((level) => {
          const y = padding + (1 - level) * (height - padding * 2);
          return (
            <g key={level}>
              <line className="chart-grid" x1={padding} x2={width - padding} y1={y} y2={y} />
              <text className="chart-label" x={0} y={y + 4}>
                {Math.round(level * 100)}%
              </text>
            </g>
          );
        })}
        <path className="chart-area" d={area} />
        <path className="chart-line" d={path} />
        {active ? (
          <circle className="chart-point" cx={activeX} cy={activeY} r={5} />
        ) : null}
      </svg>
      <div className="quarter-axis" aria-hidden="true">
        <span>Q1</span>
        <span>Q2</span>
        <span>Q3</span>
        <span>Q4</span>
      </div>
    </div>
  );
}

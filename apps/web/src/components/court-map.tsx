"use client";

import type { TimelinePoint } from "@/types/api";

interface CourtMapProps {
  points: TimelinePoint[];
  selectedSequence?: number;
  onSelect: (point: TimelinePoint) => void;
}

export function CourtMap({ points, selectedSequence, onSelect }: CourtMapProps) {
  const shots = points.filter((point) => point.x !== null && point.y !== null);

  return (
    <div className="court" aria-label="Shot map">
      <svg viewBox="0 0 500 470" role="img">
        <rect className="court-line" x="10" y="10" width="480" height="450" />
        <path className="court-line" d="M110 10 V190 H390 V10" />
        <circle className="court-line" cx="250" cy="190" r="60" />
        <circle className="court-line" cx="250" cy="55" r="10" />
        <path className="court-line" d="M40 10 V95 A245 245 0 0 0 460 95 V10" />
        <line className="court-line" x1="215" x2="285" y1="42" y2="42" />
        {shots.map((point) => {
          const x = 250 + (point.x ?? 0) * 8.7;
          const y = 55 + (point.y ?? 0) * 7.4;
          const selected = point.sequence === selectedSequence;
          return (
            <circle
              key={point.sequence}
              className={`shot-dot ${point.event_type === "shot_made" ? "made" : "missed"} ${
                selected ? "selected" : ""
              }`}
              cx={x}
              cy={y}
              r={selected ? 8 : 6}
              tabIndex={0}
              role="button"
              aria-label={point.description}
              onClick={() => onSelect(point)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onSelect(point);
              }}
            />
          );
        })}
      </svg>
      <p>Click a shot to inspect the moment</p>
    </div>
  );
}

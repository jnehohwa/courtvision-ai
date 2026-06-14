"use client";

import { Pause, Play, RotateCcw } from "lucide-react";

interface ReplayControlsProps {
  isReplaying: boolean;
  progress: number;
  onStart: () => void;
}

export function ReplayControls({
  isReplaying,
  progress,
  onStart,
}: ReplayControlsProps) {
  return (
    <div className="replay-controls">
      <strong>Replay</strong>
      <button
        type="button"
        className="icon-button"
        onClick={onStart}
        disabled={isReplaying}
        aria-label={isReplaying ? "Replay playing" : "Start replay"}
      >
        {isReplaying ? <Pause size={19} /> : <Play size={19} />}
      </button>
      <RotateCcw size={17} aria-hidden="true" />
      <span className="replay-time">{Math.round(progress * 12)}:00 / 12:00</span>
      <div className="replay-track" aria-label="Replay progress">
        <span style={{ width: `${progress * 100}%` }} />
      </div>
      <span className="speed">1.0x</span>
    </div>
  );
}

import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ProbabilityChart } from "@/components/probability-chart";

test("renders an accessible probability chart", () => {
  render(
    <ProbabilityChart
      points={[
        {
          sequence: 1,
          period: 1,
          clock_seconds: 700,
          home_probability: 0.55,
          description: "Opening possession",
          event_type: "shot_made",
          home_score: 2,
          away_score: 0,
          x: 1,
          y: 3,
          shot_value: 2,
        },
      ]}
    />,
  );
  expect(screen.getByRole("img")).toHaveAccessibleName(
    "Home win probability over time",
  );
});

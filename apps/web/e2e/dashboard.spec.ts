import { expect, test } from "@playwright/test";

test("shows the dashboard and selects a shot", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Tonight's Games" })).toBeVisible();
  await expect(page.getByText("Boston vs New York")).toBeVisible();
  await page
    .getByRole("button", {
      name: "02:18 Q4 Tatum driving layup 102 – 99",
      exact: true,
    })
    .click();
  await expect(page.getByRole("status")).toContainText("Tatum driving layup");
});

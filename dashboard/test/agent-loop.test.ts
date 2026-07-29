import { describe, it, expect } from "vitest";
import { shouldFinalize, MAX_STEPS, SOFT_DEADLINE_MS, HARD_ABORT_MS } from "../api/_agent.js";

// Guards the budget decision that forces a written answer before the run dies. The real
// end-to-end proof (against the live model) is api/_agent.smoke.mts; this pins the boundaries.
describe("shouldFinalize — force an answer before the step/time budget is spent", () => {
  const budget = { maxSteps: 15, softMs: 70_000 };

  it("keeps gathering while there's step and time budget left", () => {
    expect(shouldFinalize(0, 0, budget)).toBe(false);
    expect(shouldFinalize(5, 60_000, budget)).toBe(false);
    expect(shouldFinalize(13, 69_999, budget)).toBe(false);
  });

  it("forces a finalize on the last allowed step (never spend the ceiling on a tool call)", () => {
    expect(shouldFinalize(14, 0, budget)).toBe(true);   // step 14 = maxSteps-1
    expect(shouldFinalize(20, 0, budget)).toBe(true);
  });

  it("forces a finalize once the time budget is reached, at any step", () => {
    expect(shouldFinalize(1, 70_000, budget)).toBe(true);
    expect(shouldFinalize(1, 95_000, budget)).toBe(true);
  });

  it("the soft deadline leaves headroom before the hard abort and the 120s wall", () => {
    expect(SOFT_DEADLINE_MS).toBeLessThan(HARD_ABORT_MS);
    expect(HARD_ABORT_MS).toBeLessThan(120_000);
    // enough room after the soft deadline for the model to actually write the answer
    expect(HARD_ABORT_MS - SOFT_DEADLINE_MS).toBeGreaterThanOrEqual(20_000);
    expect(MAX_STEPS).toBeGreaterThan(1);
  });
});

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

// jsdom has no object URLs; the preview only needs a stable string.
URL.createObjectURL = () => "blob:preview";
URL.revokeObjectURL = () => undefined;

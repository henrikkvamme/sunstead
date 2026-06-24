import { describe, expect, it } from "vite-plus/test";

import { cn } from "./cn";

describe("cn", () => {
  it("merges conditional and conflicting Tailwind classes", () => {
    const isHidden = false;

    expect(cn("px-2", isHidden && "hidden", "px-4")).toBe("px-4");
  });
});

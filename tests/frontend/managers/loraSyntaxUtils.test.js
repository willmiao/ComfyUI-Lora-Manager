import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { applyLoraValuesToText, debounce, __testables } from "../../../web/comfyui/lora_syntax_utils.js";
import { mergeLoras } from "../../../web/comfyui/utils.js";
import { parseLbwSyntax } from "../../../web/comfyui/lora_block_weight.js";

const { normalizeStrengthValue, shouldIncludeClipStrength, cleanupLoraSyntax } = __testables();

describe("applyLoraValuesToText", () => {
  it("updates existing LoRA strengths", () => {
    const original = "<lora:StrengthTest:0.50>";
    const result = applyLoraValuesToText(original, [
      { name: "StrengthTest", strength: 0.8 }
    ]);

    expect(result).toBe("<lora:StrengthTest:0.80>");
  });

  it("updates clip strength while preserving syntax", () => {
    const original = "<lora:ClipTest:1.00:0.50>";
    const result = applyLoraValuesToText(original, [
      { name: "ClipTest", strength: 1, clipStrength: 0.75 }
    ]);

    expect(result).toBe("<lora:ClipTest:1.00:0.75>");
  });

  it("appends missing LoRAs to the input text", () => {
    const original = "<lora:Present:0.70>";
    const result = applyLoraValuesToText(original, [
      { name: "Present", strength: 0.7 },
      { name: "Additional", strength: 0.4 }
    ]);

    expect(result).toBe("<lora:Present:0.70> <lora:Additional:0.40>");
  });

  it("keeps clip entry when expanded even if values match", () => {
    const original = "<lora:Expanded:1.00>";
    const result = applyLoraValuesToText(original, [
      { name: "Expanded", strength: 1, clipStrength: 1, expanded: true }
    ]);

    expect(result).toBe("<lora:Expanded:1.00:1.00>");
  });

  it("preserves repeated spaces inside LoRA names", () => {
    const original = "<lora:test -  0021:1.00>";
    const result = applyLoraValuesToText(original, [
      { name: "test -  0021", strength: 0.5 }
    ]);

    expect(result).toBe("<lora:test -  0021:0.50>");
  });

  it("serializes active block weights without changing ordinary syntax", () => {
    const result = applyLoraValuesToText("", [
      {
        name: "BlockTest",
        strength: 0.8,
        clipStrength: 0.6,
        lbw: { enabled: true, weights: { IN: 0.5, OUT03: 0 } },
      },
    ]);

    expect(result).toBe("<lora:BlockTest:0.80:0.60:LBW=IN=0.5;OUT03=0>");
  });

  it("removes block syntax when the saved configuration is disabled", () => {
    const result = applyLoraValuesToText(
      "<lora:BlockTest:0.80:LBW=IN=0.5>",
      [{ name: "BlockTest", strength: 0.8, lbw: { enabled: false, weights: { IN: 0.5 } } }],
    );

    expect(result).toBe("<lora:BlockTest:0.80>");
  });

  it("keeps block configuration through text merges and parses new entries", () => {
    const existing = mergeLoras("<lora:BlockTest:0.80>", [{
      name: "BlockTest",
      strength: 0.8,
      active: true,
      lbw: { enabled: true, weights: { IN04: 0.25 } },
    }]);
    expect(existing[0].lbw.weights).toEqual({ IN04: 0.25 });

    const added = mergeLoras("<lora:Added:1:LBW=D00=0;SINGLE=0.5>", []);
    expect(added[0].lbw).toEqual({
      enabled: true,
      weights: { D00: 0, SINGLE: 0.5 },
    });
    expect(parseLbwSyntax("LBW=D00=0;SINGLE=0.5")).toEqual(added[0].lbw);
  });
});

describe("normalizeStrengthValue", () => {
  it("defaults to 1.00 for non-numeric input", () => {
    expect(normalizeStrengthValue("foo")).toBe("1.00");
  });

  it("formats numeric input to two decimals", () => {
    expect(normalizeStrengthValue(0.3333)).toBe("0.33");
  });
});

describe("shouldIncludeClipStrength", () => {
  it("returns true when clip differs", () => {
    expect(
      shouldIncludeClipStrength({ strength: 1, clipStrength: 0.8 }, undefined)
    ).toBe(true);
  });

  it("returns true when expanded despite equal values", () => {
    expect(
      shouldIncludeClipStrength({ strength: 1, clipStrength: 1, expanded: true }, undefined)
    ).toBe(true);
  });

  it("falls back to existing syntax when clip missing", () => {
    expect(shouldIncludeClipStrength({}, "0.7")).toBe(true);
  });
});

describe("cleanupLoraSyntax", () => {
  it("collapses whitespace and stray commas", () => {
    expect(cleanupLoraSyntax("  <lora:A:1.00>  , ," )).toBe("<lora:A:1.00>");
  });

  it("preserves repeated spaces inside LoRA names", () => {
    expect(cleanupLoraSyntax("<lora:test -  0021:1.00>  , ,")).toBe(
      "<lora:test -  0021:1.00>"
    );
  });

  it("still normalizes whitespace between entries", () => {
    expect(
      cleanupLoraSyntax("  <lora:A:1.00>   <lora:test -  0021:0.50>  ")
    ).toBe("<lora:A:1.00> <lora:test -  0021:0.50>");
  });
});

describe("debounce", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("delays execution and keeps latest arguments", () => {
    const spy = vi.fn();
    const debounced = debounce(spy, 100);

    debounced("first");
    debounced("second");

    expect(spy).not.toHaveBeenCalled();

    vi.advanceTimersByTime(100);

    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith("second");
  });

  it("flushes pending calls immediately", () => {
    const spy = vi.fn();
    const debounced = debounce(spy, 200);

    debounced("queued");
    debounced.flush();

    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith("queued");
  });
});

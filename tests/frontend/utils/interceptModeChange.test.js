import { beforeEach, describe, expect, it, vi } from "vitest";

const { APP_MODULE, UTILS_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
  UTILS_MODULE: new URL("../../../web/comfyui/utils.js", import.meta.url).pathname,
}));

vi.mock(APP_MODULE, () => ({
  app: {
    graph: null,
    registerExtension: vi.fn(),
    ui: {
      settings: {
        getSettingValue: vi.fn(),
      },
    },
  },
}));

describe("interceptModeChange", () => {
  let interceptModeChange;

  beforeEach(async () => {
    vi.resetModules();
    ({ interceptModeChange } = await import(UTILS_MODULE));
  });

  describe("legacy frontend (mode as plain data property)", () => {
    it("reads and writes the mode through the installed accessor", () => {
      const node = { mode: 0 };
      interceptModeChange(node, vi.fn());

      node.mode = 4;
      expect(node.mode).toBe(4);
    });

    it("invokes the callback only when the mode actually changes", () => {
      const node = { mode: 0 };
      const onModeChange = vi.fn();
      interceptModeChange(node, onModeChange);

      node.mode = 0;
      expect(onModeChange).not.toHaveBeenCalled();

      node.mode = 4;
      expect(onModeChange).toHaveBeenCalledWith(4, 0);
    });
  });

  describe("ECS frontend (mode as prototype accessor backed by shell state)", () => {
    function createEcsNode() {
      class LGraphNode {
        constructor() {
          this._state = { mode: 0 };
        }
        get mode() {
          return this._state.mode;
        }
        set mode(value) {
          this._state.mode = value;
        }
      }
      return new LGraphNode();
    }

    it("keeps writes flowing into the shell state so serialization stays correct", () => {
      const node = createEcsNode();
      interceptModeChange(node, vi.fn());

      node.mode = 4;

      expect(node._state.mode).toBe(4);
      expect(node.mode).toBe(4);
    });

    it("invokes the callback with new and old mode on change", () => {
      const node = createEcsNode();
      const onModeChange = vi.fn();
      interceptModeChange(node, onModeChange);

      node.mode = 4;
      expect(onModeChange).toHaveBeenCalledWith(4, 0);

      node.mode = 4;
      expect(onModeChange).toHaveBeenCalledTimes(1);

      node.mode = 0;
      expect(onModeChange).toHaveBeenCalledWith(0, 4);
    });

    it("keeps the installed accessor configurable so it can be redefined", () => {
      const node = createEcsNode();
      interceptModeChange(node, vi.fn());

      const descriptor = Object.getOwnPropertyDescriptor(node, "mode");
      expect(descriptor.configurable).toBe(true);
    });
  });

  describe("multiple listeners", () => {
    it("notifies every registered listener while intercepting only once", () => {
      const node = { mode: 0 };
      const first = vi.fn();
      const second = vi.fn();
      interceptModeChange(node, first);
      interceptModeChange(node, second);

      node.mode = 2;
      expect(first).toHaveBeenCalledWith(2, 0);
      expect(second).toHaveBeenCalledWith(2, 0);

      // The second registration must not replace the accessor: the value is
      // still tracked across registrations.
      node.mode = 4;
      expect(first).toHaveBeenCalledWith(4, 2);
      expect(second).toHaveBeenCalledWith(4, 2);
    });

    it("keeps notifying remaining listeners when one of them throws", () => {
      const node = { mode: 0 };
      const failing = vi.fn(() => {
        throw new Error("boom");
      });
      const healthy = vi.fn();
      interceptModeChange(node, failing);
      interceptModeChange(node, healthy);

      node.mode = 2;
      expect(failing).toHaveBeenCalledWith(2, 0);
      expect(healthy).toHaveBeenCalledWith(2, 0);
      expect(node.mode).toBe(2);
    });
  });
});

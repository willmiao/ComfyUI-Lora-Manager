import { beforeEach, describe, expect, it, vi } from "vitest";

const { APP_MODULE, UTILS_MODULE, WRITEBACK_MODULE, appMock, toastMock, registeredExtensions } =
  vi.hoisted(() => {
    const registeredExtensions = [];
    const appMock = {
      rootGraph: null,
      graph: null,
      registerExtension: (ext) => registeredExtensions.push(ext),
    };
    const toastMock = vi.fn();
    return {
      APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
      UTILS_MODULE: new URL("../../../web/comfyui/utils.js", import.meta.url).pathname,
      WRITEBACK_MODULE: new URL("../../../web/comfyui/workflow_writeback.js", import.meta.url).pathname,
      appMock,
      toastMock,
      registeredExtensions,
    };
  });

vi.mock(APP_MODULE, () => ({ app: appMock }));
vi.mock(UTILS_MODULE, () => ({ showToast: toastMock }));

function createRootGraph({ marker = null, serialized = null } = {}) {
  const extra = marker ? { lm_source: marker, ds: { scale: 1 } } : { ds: { scale: 1 } };
  return {
    extra,
    serialize: vi.fn(() => serialized ?? { nodes: [], links: [], extra: JSON.parse(JSON.stringify(extra)) }),
  };
}

describe("LoraManager.WorkflowWriteback", () => {
  let extension;
  let moduleExports;
  let fetchMock;

  beforeEach(async () => {
    vi.resetModules();
    registeredExtensions.length = 0;
    appMock.rootGraph = null;
    appMock.graph = null;
    toastMock.mockClear();
    fetchMock = vi.fn();
    global.fetch = fetchMock;
    moduleExports = await import(WRITEBACK_MODULE);
    extension = registeredExtensions.find(
      (ext) => ext.name === "LoraManager.WorkflowWriteback"
    );
    expect(extension).toBeDefined();
  });

  it("registers the write-back command in the File menu group", () => {
    expect(extension.commands).toHaveLength(1);
    expect(extension.commands[0].id).toBe("LoraManager.UpdateManagedWorkflow");
    expect(extension.menuCommands).toEqual([
      { path: ["File"], commands: ["LoraManager.UpdateManagedWorkflow"] },
    ]);
  });

  describe("getActiveLmSource", () => {
    it("returns null when the graph carries no marker", () => {
      appMock.rootGraph = createRootGraph();
      expect(moduleExports.getActiveLmSource()).toBeNull();
    });

    it("returns the marker when present", () => {
      const marker = { file_path: "/lib/flow.json", sha256: "abc" };
      appMock.rootGraph = createRootGraph({ marker });
      expect(moduleExports.getActiveLmSource()).toBe(marker);
    });

    it("returns null when the marker has no usable file_path", () => {
      appMock.rootGraph = createRootGraph({ marker: { sha256: "abc" } });
      expect(moduleExports.getActiveLmSource()).toBeNull();
    });
  });

  describe("updateManagedWorkflow", () => {
    it("warns and does not call the backend without a marker", async () => {
      appMock.rootGraph = createRootGraph();

      await moduleExports.updateManagedWorkflow();

      expect(fetchMock).not.toHaveBeenCalled();
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ severity: "warn" })
      );
    });

    it("PUTs the serialized graph without the marker and refreshes the hash", async () => {
      const marker = { file_path: "/lib/flow.json", sha256: "old-hash" };
      appMock.rootGraph = createRootGraph({ marker });
      fetchMock.mockResolvedValue({
        status: 200,
        json: async () => ({ success: true, sha256: "new-hash" }),
      });

      await moduleExports.updateManagedWorkflow();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toBe("/api/lm/workflows/content");
      expect(options.method).toBe("PUT");
      const body = JSON.parse(options.body);
      expect(body.file_path).toBe("/lib/flow.json");
      expect(body.base_sha256).toBe("old-hash");
      expect(body.force).toBe(false);
      expect(body.workflow.extra.lm_source).toBeUndefined();
      // Other extra keys survive the strip.
      expect(body.workflow.extra.ds).toEqual({ scale: 1 });

      expect(marker.sha256).toBe("new-hash");
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ severity: "success" })
      );
    });

    it("retries with force after a conflict only when the user confirms", async () => {
      const marker = { file_path: "/lib/flow.json", sha256: "old-hash" };
      appMock.rootGraph = createRootGraph({ marker });

      const confirmMock = vi.fn().mockReturnValue(false);
      vi.stubGlobal("confirm", confirmMock);
      fetchMock.mockResolvedValue({
        status: 409,
        json: async () => ({ success: false, error: "conflict" }),
      });

      await moduleExports.updateManagedWorkflow();
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(toastMock).not.toHaveBeenCalledWith(
        expect.objectContaining({ severity: "success" })
      );

      confirmMock.mockReturnValue(true);
      fetchMock
        .mockResolvedValueOnce({
          status: 409,
          json: async () => ({ success: false, error: "conflict" }),
        })
        .mockResolvedValueOnce({
          status: 200,
          json: async () => ({ success: true, sha256: "forced-hash" }),
        });

      await moduleExports.updateManagedWorkflow();
      expect(fetchMock).toHaveBeenCalledTimes(3);
      const forcedBody = JSON.parse(fetchMock.mock.calls[2][1].body);
      expect(forcedBody.force).toBe(true);
      expect(marker.sha256).toBe("forced-hash");

      vi.unstubAllGlobals();
    });

    it("reports backend errors via toast", async () => {
      const marker = { file_path: "/lib/flow.json", sha256: "abc" };
      appMock.rootGraph = createRootGraph({ marker });
      fetchMock.mockResolvedValue({
        status: 400,
        json: async () => ({ success: false, error: "workflow is not a ComfyUI graph document" }),
      });

      await moduleExports.updateManagedWorkflow();

      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ severity: "error" })
      );
    });
  });
});

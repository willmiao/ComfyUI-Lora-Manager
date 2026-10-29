import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  APP_MODULE,
  API_MODULE,
  UTILS_MODULE,
  WRITEBACK_MODULE,
  appMock,
  apiMock,
  toastMock,
  registeredExtensions,
} = vi.hoisted(() => {
  const registeredExtensions = [];
  const appMock = {
    rootGraph: null,
    graph: null,
    registerExtension: (ext) => registeredExtensions.push(ext),
  };
  const apiMock = {
    clientId: "client-1",
    initialClientId: null,
    listeners: {},
    addEventListener: (event, handler) => {
      (apiMock.listeners[event] ??= []).push(handler);
    },
  };
  const toastMock = vi.fn();
  return {
    APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
    API_MODULE: new URL("../../../scripts/api.js", import.meta.url).pathname,
    UTILS_MODULE: new URL("../../../web/comfyui/utils.js", import.meta.url).pathname,
    WRITEBACK_MODULE: new URL("../../../web/comfyui/workflow_writeback.js", import.meta.url).pathname,
    appMock,
    apiMock,
    toastMock,
    registeredExtensions,
  };
});

vi.mock(APP_MODULE, () => ({ app: appMock }));
vi.mock(API_MODULE, () => ({ api: apiMock }));
vi.mock(UTILS_MODULE, () => ({ showToast: toastMock }));

function createRootGraph({ marker = null, serialized = null } = {}) {
  const extra = marker ? { lm_source: marker, ds: { scale: 1 } } : { ds: { scale: 1 } };
  return {
    extra,
    serialize: vi.fn(() => serialized ?? { nodes: [], links: [], extra: JSON.parse(JSON.stringify(extra)) }),
  };
}

function fetchCalls(fetchMock, url) {
  return fetchMock.mock.calls.filter(([callUrl]) => callUrl === url);
}

function okResponse(body = { success: true, sha256: "new-hash" }) {
  return { status: 200, json: async () => body };
}

describe("LoraManager.WorkflowWriteback", () => {
  let extension;
  let moduleExports;
  let fetchMock;

  beforeEach(async () => {
    vi.resetModules();
    registeredExtensions.length = 0;
    apiMock.listeners = {};
    appMock.rootGraph = null;
    appMock.graph = null;
    toastMock.mockClear();
    fetchMock = vi.fn().mockResolvedValue(okResponse());
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

  describe("link state reporting", () => {
    it("reports the marker state after a graph load (afterConfigureGraph)", async () => {
      const marker = { file_path: "/lib/flow.json", sha256: "abc" };
      appMock.rootGraph = createRootGraph({ marker });

      await extension.afterConfigureGraph();

      const reports = fetchCalls(fetchMock, "/api/lm/workflows/comfyui-state");
      expect(reports).toHaveLength(1);
      const body = JSON.parse(reports[0][1].body);
      expect(body).toEqual({
        client_id: "client-1",
        state: { file_path: "/lib/flow.json", sha256: "abc", dirty: false },
      });
    });

    it("reports a null state when the active graph is not LM-linked", async () => {
      appMock.rootGraph = createRootGraph();

      await extension.afterConfigureGraph();

      const reports = fetchCalls(fetchMock, "/api/lm/workflows/comfyui-state");
      const body = JSON.parse(reports[0][1].body);
      expect(body.state).toBeNull();
    });

    it("marks the graph dirty and reports on the first graphChanged", async () => {
      const marker = { file_path: "/lib/flow.json", sha256: "abc" };
      appMock.rootGraph = createRootGraph({ marker });
      extension.setup();

      const handler = apiMock.listeners["graphChanged"][0];
      handler({});
      expect(marker.dirty).toBe(true);
      await vi.waitFor(() =>
        expect(fetchCalls(fetchMock, "/api/lm/workflows/comfyui-state")).toHaveLength(1)
      );
      const body = JSON.parse(
        fetchCalls(fetchMock, "/api/lm/workflows/comfyui-state")[0][1].body
      );
      expect(body.state.dirty).toBe(true);

      // A second change does not re-report (already dirty).
      handler({});
      expect(fetchCalls(fetchMock, "/api/lm/workflows/comfyui-state")).toHaveLength(1);
    });

    it("ignores graphChanged when the active graph is not LM-linked", () => {
      appMock.rootGraph = createRootGraph();
      extension.setup();

      apiMock.listeners["graphChanged"][0]({});
      expect(fetchCalls(fetchMock, "/api/lm/workflows/comfyui-state")).toHaveLength(0);
    });
  });

  describe("updateManagedWorkflow", () => {
    it("warns and does not call the backend without a marker", async () => {
      appMock.rootGraph = createRootGraph();

      await moduleExports.updateManagedWorkflow();

      expect(fetchCalls(fetchMock, "/api/lm/workflows/content")).toHaveLength(0);
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ severity: "warn" })
      );
    });

    it("PUTs the serialized graph without the marker and refreshes the hash", async () => {
      const marker = { file_path: "/lib/flow.json", sha256: "old-hash", dirty: true };
      appMock.rootGraph = createRootGraph({ marker });

      await moduleExports.updateManagedWorkflow();

      const puts = fetchCalls(fetchMock, "/api/lm/workflows/content");
      expect(puts).toHaveLength(1);
      const [url, options] = puts[0];
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
      // Write-back clears the dirty flag and re-reports the link state.
      expect(marker.dirty).toBe(false);
      await vi.waitFor(() =>
        expect(fetchCalls(fetchMock, "/api/lm/workflows/comfyui-state")).toHaveLength(1)
      );
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ severity: "success" })
      );
    });

    it("retries with force after a conflict only when the user confirms", async () => {
      const marker = { file_path: "/lib/flow.json", sha256: "old-hash", dirty: true };
      appMock.rootGraph = createRootGraph({ marker });

      const confirmMock = vi.fn().mockReturnValue(false);
      vi.stubGlobal("confirm", confirmMock);
      fetchMock.mockImplementation(async (url) =>
        url === "/api/lm/workflows/content"
          ? { status: 409, json: async () => ({ success: false, error: "conflict" }) }
          : okResponse()
      );

      await moduleExports.updateManagedWorkflow();
      expect(fetchCalls(fetchMock, "/api/lm/workflows/content")).toHaveLength(1);
      expect(toastMock).not.toHaveBeenCalledWith(
        expect.objectContaining({ severity: "success" })
      );

      confirmMock.mockReturnValue(true);
      let conflictServed = false;
      fetchMock.mockImplementation(async (url) => {
        if (url !== "/api/lm/workflows/content") return okResponse();
        if (!conflictServed) {
          conflictServed = true;
          return { status: 409, json: async () => ({ success: false, error: "conflict" }) };
        }
        return okResponse({ success: true, sha256: "forced-hash" });
      });

      await moduleExports.updateManagedWorkflow();
      const puts = fetchCalls(fetchMock, "/api/lm/workflows/content");
      expect(puts).toHaveLength(3);
      const forcedBody = JSON.parse(puts[2][1].body);
      expect(forcedBody.force).toBe(true);
      expect(marker.sha256).toBe("forced-hash");

      vi.unstubAllGlobals();
    });

    it("reports backend errors via toast", async () => {
      const marker = { file_path: "/lib/flow.json", sha256: "abc", dirty: true };
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

  describe("lm_collect_workflow handling", () => {
    function fireCollect(detail) {
      extension.setup();
      const handler = apiMock.listeners["lm_collect_workflow"][0];
      return handler({ detail });
    }

    it("ignores requests for workflows this tab does not hold", async () => {
      const marker = { file_path: "/lib/other.json", sha256: "abc", dirty: true };
      appMock.rootGraph = createRootGraph({ marker });

      await fireCollect({ request_id: "r1", file_path: "/lib/flow.json" });

      expect(fetchCalls(fetchMock, "/api/lm/workflows/content")).toHaveLength(0);
      expect(fetchCalls(fetchMock, "/api/lm/workflows/collect-result")).toHaveLength(0);
    });

    it("answers no_changes without writing back when the graph is clean", async () => {
      const marker = { file_path: "/lib/flow.json", sha256: "abc", dirty: false };
      appMock.rootGraph = createRootGraph({ marker });

      await fireCollect({ request_id: "r2", file_path: "/lib/flow.json" });

      expect(fetchCalls(fetchMock, "/api/lm/workflows/content")).toHaveLength(0);
      const results = fetchCalls(fetchMock, "/api/lm/workflows/collect-result");
      expect(results).toHaveLength(1);
      expect(JSON.parse(results[0][1].body)).toEqual({
        request_id: "r2",
        success: false,
        error: "no_changes",
      });
    });

    it("writes back and posts the outcome when the graph is dirty", async () => {
      const marker = { file_path: "/lib/flow.json", sha256: "old-hash", dirty: true };
      appMock.rootGraph = createRootGraph({ marker });

      await fireCollect({ request_id: "r3", file_path: "/lib/flow.json" });

      expect(fetchCalls(fetchMock, "/api/lm/workflows/content")).toHaveLength(1);
      const results = fetchCalls(fetchMock, "/api/lm/workflows/collect-result");
      expect(results).toHaveLength(1);
      expect(JSON.parse(results[0][1].body)).toEqual({
        request_id: "r3",
        success: true,
        sha256: "new-hash",
      });
      expect(marker.dirty).toBe(false);
    });
  });
});

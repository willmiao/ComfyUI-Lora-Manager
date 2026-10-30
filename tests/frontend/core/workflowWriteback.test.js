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
    queuePrompt: async () => ({ prompt_id: "p-1" }),
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

function fetchCallsStartingWith(fetchMock, prefix) {
  return fetchMock.mock.calls.filter(
    ([callUrl]) => typeof callUrl === "string" && callUrl.startsWith(prefix)
  );
}

function okResponse(body = { success: true, sha256: "new-hash" }) {
  return { ok: true, status: 200, json: async () => body };
}

describe("LoraManager.WorkflowWriteback", () => {
  let extension;
  let moduleExports;
  let fetchMock;

  beforeEach(async () => {
    vi.resetModules();
    registeredExtensions.length = 0;
    apiMock.listeners = {};
    delete apiMock.__lmQueuePromptHooked;
    apiMock.queuePrompt = async () => ({ prompt_id: "p-1" });
    document.body.innerHTML = "";
    appMock.rootGraph = null;
    appMock.graph = null;
    appMock.extensionManager = {
      workflow: { activeWorkflow: { filename: "My Flow" } },
    };
    toastMock.mockClear();
    fetchMock = vi.fn().mockResolvedValue(okResponse());
    global.fetch = fetchMock;
    moduleExports = await import(WRITEBACK_MODULE);
    extension = registeredExtensions.find(
      (ext) => ext.name === "LoraManager.WorkflowWriteback"
    );
    expect(extension).toBeDefined();
  });

  it("registers the create and write-back commands in the File menu group", () => {
    expect(extension.commands.map((command) => command.id)).toEqual([
      "LoraManager.CreateManagedWorkflow",
      "LoraManager.UpdateManagedWorkflow",
    ]);
    expect(extension.menuCommands).toEqual([
      {
        path: ["File"],
        commands: [
          "LoraManager.CreateManagedWorkflow",
          "LoraManager.UpdateManagedWorkflow",
        ],
      },
    ]);
  });

  describe("workflow actions menu injection", () => {
    function mountMenu() {
      document.body.innerHTML = `
        <div data-testid="view-mode-toggle"></div>
        <div role="menu">
          <i class="pi pi-pencil"></i>
          <i class="pi pi-save"></i>
          <i class="pi pi-download"></i>
        </div>
      `;
    }

    it("appends both items without throwing on multi-class state", async () => {
      mountMenu();
      extension.setup();
      document.querySelector('[data-testid="view-mode-toggle"]').click();

      await vi.waitFor(() => {
        expect(
          document.querySelector('[data-lm-action="create-workflow"]')
        ).not.toBeNull();
      });

      const createItem = document.querySelector(
        '[data-lm-action="create-workflow"]'
      );
      const updateItem = document.querySelector(
        '[data-lm-action="update-workflow"]'
      );
      expect(createItem.textContent).toContain("Create LM-managed workflow");
      expect(updateItem.textContent).toContain("Update LM-managed workflow");
      // Not linked: create is enabled (optimistic), update is disabled.
      expect(createItem.className).toContain("cursor-pointer");
      expect(updateItem.className).toContain("opacity-50");
      // Both entries keep the shared menu-item layout (padding/alignment);
      // missing base classes make the item look shifted left.
      for (const item of [createItem, updateItem]) {
        expect(item.className).toContain("flex");
        expect(item.className).toContain("min-h-6");
        expect(item.className).toContain("gap-2");
        expect(item.className).toContain("p-2");
      }
    });
  });

  describe("workflow tab context menu injection", () => {
    function mountTabs({ marker = null } = {}) {
      document.body.innerHTML = `
        <div class="workflow-tab" data-state="closed" aria-controls="tab-menu-other">
          <span class="workflow-label">Other Flow</span>
        </div>
        <div class="workflow-tab" data-state="closed" aria-controls="tab-menu-target">
          <span class="workflow-label">My Flow</span>
        </div>
        <div id="tab-menu-target" role="menu">
          <div role="menuitem"><i class="pi pi-pencil"></i><span>Rename</span></div>
          <div role="separator"></div>
          <div role="menuitem"><i class="pi pi-save"></i><span>Save</span></div>
          <div role="separator"></div>
          <div role="menuitem"><i class="pi pi-times"></i><span>Close Tab</span></div>
          <div role="menuitem">
            <span><i class="pi pi-times"></i><i class="pi pi-arrows-h"></i></span>
            <span>Close Other Tabs</span>
          </div>
        </div>
      `;
      const activeWorkflow = { filename: "Other Flow" };
      const targetWorkflow = {
        filename: "My Flow",
        activeState: marker ? { extra: { lm_source: marker } } : {},
      };
      appMock.extensionManager.workflow = {
        activeWorkflow,
        openWorkflows: [activeWorkflow, targetWorkflow],
        openWorkflow: vi.fn(),
      };
      return { activeWorkflow, targetWorkflow };
    }

    function openTabMenu() {
      const tabs = document.querySelectorAll(".workflow-tab");
      tabs[1].dispatchEvent(
        new MouseEvent("contextmenu", { bubbles: true, cancelable: true })
      );
    }

    it("adds create/update before the close group using the tab's own marker", async () => {
      const marker = { file_path: "/lib/target.json", sha256: "abc" };
      mountTabs({ marker });
      appMock.rootGraph = createRootGraph();
      extension.setup();

      openTabMenu();
      await vi.waitFor(() => {
        expect(
          document.querySelector('[data-lm-tab-action="create-workflow"]')
        ).not.toBeNull();
      });

      const menu = document.getElementById("tab-menu-target");
      const createItem = menu.querySelector(
        '[data-lm-tab-action="create-workflow"]'
      );
      const updateItem = menu.querySelector(
        '[data-lm-tab-action="update-workflow"]'
      );
      expect(createItem.textContent).toContain("Create LM-managed workflow");
      expect(updateItem.textContent).toContain("Update LM-managed workflow");
      // Active graph has no marker, but the right-clicked tab does.
      expect(updateItem.className).toContain("cursor-pointer");
      // Both keep the native menu-item layout and sit before Close Tab.
      for (const item of [createItem, updateItem]) {
        expect(item.className).toContain("flex");
        expect(item.className).toContain("p-2");
      }
      const closeTab = Array.from(menu.querySelectorAll('[role="menuitem"]')).find(
        (item) => item.textContent.includes("Close Tab")
      );
      expect(
        createItem.compareDocumentPosition(closeTab) &
          Node.DOCUMENT_POSITION_FOLLOWING
      ).toBeTruthy();
      // Re-opening the same menu instance must not duplicate the entries.
      openTabMenu();
      await new Promise((resolve) => setTimeout(resolve, 150));
      expect(
        menu.querySelectorAll('[data-lm-tab-action="create-workflow"]').length
      ).toBe(1);
    });

    it("activates the right-clicked tab before updating it", async () => {
      const marker = { file_path: "/lib/target.json", sha256: "abc" };
      const { targetWorkflow } = mountTabs({ marker });
      appMock.rootGraph = createRootGraph();
      const openWorkflow = appMock.extensionManager.workflow.openWorkflow;
      openWorkflow.mockImplementation(async (workflow) => {
        appMock.extensionManager.workflow.activeWorkflow = workflow;
        appMock.rootGraph = createRootGraph({ marker });
        return workflow;
      });
      fetchMock.mockImplementation(async (url) => {
        if (
          typeof url === "string" &&
          url.startsWith("/api/lm/workflows/link-status")
        ) {
          return okResponse({ success: true, exists: true });
        }
        return okResponse();
      });
      extension.setup();

      openTabMenu();
      await vi.waitFor(() => {
        expect(
          document.querySelector('[data-lm-tab-action="update-workflow"]')
        ).not.toBeNull();
      });
      document
        .querySelector('[data-lm-tab-action="update-workflow"]')
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));

      await vi.waitFor(() => {
        expect(fetchCalls(fetchMock, "/api/lm/workflows/content")).toHaveLength(1);
      });
      expect(openWorkflow).toHaveBeenCalledWith(targetWorkflow);
      const body = JSON.parse(
        fetchCalls(fetchMock, "/api/lm/workflows/content")[0][1].body
      );
      expect(body.file_path).toBe(marker.file_path);
    });
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

    it("drops a marker whose library entry is gone and reports null", async () => {
      const marker = { file_path: "/lib/deleted.json", sha256: "abc" };
      appMock.rootGraph = createRootGraph({ marker });
      fetchMock.mockImplementation(async (url) =>
        url.startsWith("/api/lm/workflows/link-status")
          ? okResponse({ success: true, exists: false })
          : okResponse()
      );

      await extension.afterConfigureGraph();

      expect(appMock.rootGraph.extra.lm_source).toBeUndefined();
      const reports = fetchCalls(fetchMock, "/api/lm/workflows/comfyui-state");
      expect(reports.length).toBeGreaterThan(0);
      expect(JSON.parse(reports.at(-1)[1].body).state).toBeNull();
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
    it("clears the marker when the library copy is gone", async () => {
      const marker = { file_path: "/lib/deleted.json", sha256: "abc", dirty: true };
      appMock.rootGraph = createRootGraph({ marker });
      fetchMock.mockResolvedValue({
        status: 404,
        json: async () => ({ success: false, error: "not_found" }),
      });

      await moduleExports.updateManagedWorkflow();

      expect(appMock.rootGraph.extra.lm_source).toBeUndefined();
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ severity: "warn" })
      );
    });
  });

  describe("createManagedWorkflow", () => {
    it("warns and does not call the backend without an open graph", async () => {
      await moduleExports.createManagedWorkflow();

      expect(fetchCalls(fetchMock, "/api/lm/workflows/create")).toHaveLength(0);
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ severity: "warn" })
      );
    });

    it("POSTs the graph without the marker and stamps the new link", async () => {
      const marker = { file_path: "/lib/old.json", sha256: "old-hash" };
      appMock.rootGraph = createRootGraph({ marker });
      vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
      fetchMock.mockImplementation(async (url) => {
        if (url === "/api/lm/workflows/create") {
          return okResponse({
            success: true,
            file_path: "/lib/new.json",
            sha256: "new-hash",
            name: "My Flow",
            preview: false,
          });
        }
        return okResponse();
      });

      await moduleExports.createManagedWorkflow();

      const posts = fetchCalls(fetchMock, "/api/lm/workflows/create");
      expect(posts).toHaveLength(1);
      const body = JSON.parse(posts[0][1].body);
      expect(body.name).toBe("My Flow");
      expect(body.workflow.extra.lm_source).toBeUndefined();
      expect(body.workflow.extra.ds).toEqual({ scale: 1 });

      // The created entry is linked immediately: marker replaced, state reported.
      expect(appMock.rootGraph.extra.lm_source).toEqual({
        file_path: "/lib/new.json",
        sha256: "new-hash",
      });
      expect(
        fetchCalls(fetchMock, "/api/lm/workflows/comfyui-state")
      ).toHaveLength(1);
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ severity: "success" })
      );
    });

    it("replaces a stale marker without prompting", async () => {
      appMock.rootGraph = createRootGraph({
        marker: { file_path: "/lib/deleted.json", sha256: "old" },
      });
      const confirmMock = vi.fn().mockReturnValue(true);
      vi.stubGlobal("confirm", confirmMock);
      fetchMock.mockImplementation(async (url) => {
        if (url.startsWith("/api/lm/workflows/link-status")) {
          return okResponse({ success: true, exists: false });
        }
        if (url === "/api/lm/workflows/create") {
          return okResponse({
            success: true,
            file_path: "/lib/new.json",
            sha256: "new-hash",
            name: "My Flow",
          });
        }
        return okResponse();
      });

      await moduleExports.createManagedWorkflow();

      expect(confirmMock).not.toHaveBeenCalled();
      expect(fetchCalls(fetchMock, "/api/lm/workflows/create")).toHaveLength(1);
      expect(appMock.rootGraph.extra.lm_source).toEqual({
        file_path: "/lib/new.json",
        sha256: "new-hash",
      });
      vi.unstubAllGlobals();
    });

    it("sends the prompt id of the last run queued from this tab", async () => {
      apiMock.queuePrompt = vi.fn(async () => ({ prompt_id: "p-preview" }));
      extension.setup();
      await apiMock.queuePrompt(0, {});
      apiMock.listeners["execution_success"][0]({ detail: { prompt_id: "p-preview" } });

      appMock.rootGraph = createRootGraph();
      await moduleExports.createManagedWorkflow();

      const posts = fetchCalls(fetchMock, "/api/lm/workflows/create");
      expect(posts).toHaveLength(1);
      expect(JSON.parse(posts[0][1].body).preview_prompt_id).toBe("p-preview");
    });

    it("confirms before copying an already linked graph", async () => {
      const marker = { file_path: "/lib/old.json", sha256: "old-hash" };
      appMock.rootGraph = createRootGraph({ marker });

      const confirmMock = vi.fn().mockReturnValue(false);
      vi.stubGlobal("confirm", confirmMock);

      await moduleExports.createManagedWorkflow();

      expect(confirmMock).toHaveBeenCalledTimes(1);
      expect(fetchCalls(fetchMock, "/api/lm/workflows/create")).toHaveLength(0);

      confirmMock.mockReturnValue(true);
      await moduleExports.createManagedWorkflow();

      expect(fetchCalls(fetchMock, "/api/lm/workflows/create")).toHaveLength(1);
      vi.unstubAllGlobals();
    });

    it("reports backend errors via toast", async () => {
      appMock.rootGraph = createRootGraph();
      fetchMock.mockResolvedValue({
        status: 400,
        json: async () => ({
          success: false,
          error: "The workflow library folder is not configured in LoRA Manager settings",
        }),
      });

      await moduleExports.createManagedWorkflow();

      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({
          severity: "error",
          detail: expect.stringContaining("workflow library folder"),
        })
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

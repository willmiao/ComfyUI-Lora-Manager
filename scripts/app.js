const settingsStore = new Map();

export const app = {
  canvas: { ds: { scale: 1 } },
  extensionManager: {
    toast: {
      add: () => {},
    },
    setting: {
      get: (id) => (settingsStore.has(id) ? settingsStore.get(id) : undefined),
      set: async (id, value) => {
        settingsStore.set(id, value);
      },
    },
  },
  registerExtension: () => {},
  graphToPrompt: async () => ({ workflow: { nodes: new Map() } }),
};

export default app;

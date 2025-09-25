export const app = {
  canvas: { ds: { scale: 1 } },
  extensionManager: {
    toast: {
      add: () => {},
    },
  },
  registerExtension: () => {},
  graphToPrompt: async () => ({ workflow: { nodes: new Map() } }),
};

export default app;

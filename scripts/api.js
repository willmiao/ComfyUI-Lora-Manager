export const api = {
  fetchApi: (...args) => fetch(...args),
  addEventListener: (eventName, handler) => document.addEventListener(eventName, handler),
  removeEventListener: (eventName, handler) => document.removeEventListener(eventName, handler),
};

export default api;

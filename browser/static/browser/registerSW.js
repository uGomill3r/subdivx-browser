// Registro del Service Worker
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then(
      (reg) => console.log("SW registrado:", reg.scope),
      (err) => console.warn("SW error:", err)
    );
  });
}

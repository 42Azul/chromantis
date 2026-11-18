(() => {
  const storageKey = "chromantis-appearance";
  const system = matchMedia("(prefers-color-scheme: light)");
  let preference = "system";
  try {
    const saved = localStorage.getItem(storageKey);
    if (["system", "light", "dark"].includes(saved)) preference = saved;
  } catch {}

  function apply() {
    document.documentElement.dataset.theme = preference === "system"
      ? (system.matches ? "light" : "dark") : preference;
  }

  apply();
  system.addEventListener("change", apply);
  document.addEventListener("DOMContentLoaded", () => {
    const select = document.getElementById("appearance");
    select.value = preference;
    select.addEventListener("change", () => {
      preference = select.value;
      apply();
      try {
        localStorage.setItem(storageKey, preference);
      } catch {}
    });
  });
})();

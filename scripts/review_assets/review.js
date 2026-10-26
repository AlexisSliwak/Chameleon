/* Offline review notes are local to a frozen run; never sent to a server. */
"use strict";
const RATINGS = new Set(["unreviewed", "acceptable", "needs-work", "unusable"]);
function validateReview(value, runId, caseIds) {
  if (!value || value.version !== 1 || value.run_id !== runId ||
      !value.reviews || typeof value.reviews !== "object" || Array.isArray(value.reviews)) {
    throw new Error("Review file belongs to another run or has an invalid format.");
  }
  const allowed = new Set(caseIds), reviews = Object.create(null);
  for (const [id, entry] of Object.entries(value.reviews)) {
    if (!allowed.has(id) || !entry || !RATINGS.has(entry.rating) ||
        typeof entry.notes !== "string" || entry.notes.length > 10000) {
      throw new Error("Review contains an unknown case, invalid rating or oversized note.");
    }
    reviews[id] = {rating: entry.rating, notes: entry.notes};
  }
  return reviews;
}
function visibleCase(item, review, family, filter) {
  if (family !== "all" && family !== item.family) return false;
  if (filter === "failed") return item.status === "failed";
  if (filter === "flagged") return item.status === "review";
  if (filter === "unreviewed") return !review || review.rating === "unreviewed";
  return true;
}
if (typeof module !== "undefined") module.exports = {validateReview, visibleCase};
if (typeof document !== "undefined") {
  const data = JSON.parse(document.getElementById("review-data").textContent);
  const key = "chameleon-review:" + data.run_id;
  const ids = data.cases.map(item => item.id);
  const cards = new Map([...document.querySelectorAll(".case")].map(el => [el.dataset.case, el]));
  const status = document.getElementById("storage-status");
  const family = document.getElementById("family"), filter = document.getElementById("filter");
  let reviews = Object.create(null);
  const bundle = () => ({version: 1, run_id: data.run_id, reviews});
  try {
    const saved = localStorage.getItem(key);
    if (saved) reviews = validateReview(JSON.parse(saved), data.run_id, ids);
  } catch { status.textContent = "Saved notes unavailable. You can still review and export this session."; }
  function persist() {
    try { localStorage.setItem(key, JSON.stringify(bundle())); return true; }
    catch {
      status.textContent = "Browser storage unavailable. Export notes before closing this page.";
      return false;
    }
  }
  function update() {
    let visible = 0, reviewed = 0;
    for (const item of data.cases) {
      const card = cards.get(item.id), review = reviews[item.id];
      card.hidden = !visibleCase(item, review, family.value, filter.value);
      if (!card.hidden) visible++;
      if (review && review.rating !== "unreviewed") reviewed++;
    }
    document.getElementById("count").textContent = visible + " shown · " + reviewed + "/" + ids.length + " reviewed";
  }
  function populate() {
    for (const [id, card] of cards) {
      card.querySelector(".rating").value = reviews[id]?.rating || "unreviewed";
      card.querySelector(".notes").value = reviews[id]?.notes || "";
    }
    update();
  }
  for (const [id, card] of cards) {
    card.addEventListener("input", event => {
      if (!event.target.matches(".rating,.notes")) return;
      reviews[id] = {rating: card.querySelector(".rating").value, notes: card.querySelector(".notes").value};
      persist(); update();
    });
    card.addEventListener("click", event => {
      const button = event.target.closest("button[data-zoom]");
      if (!button) return;
      card.classList.remove("native", "double");
      if (button.dataset.zoom !== "fit") card.classList.add(button.dataset.zoom);
      card.querySelectorAll("button[data-zoom]").forEach(b => b.setAttribute("aria-pressed", String(b === button)));
    });
  }
  family.addEventListener("change", update); filter.addEventListener("change", update);
  document.getElementById("export").addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(bundle(), null, 2)], {type:"application/json"}));
    const a = document.createElement("a"); a.href = url; a.download = "chameleon-review-" + data.run_id.slice(0,12) + ".json";
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  document.getElementById("import").addEventListener("change", async event => {
    const file = event.target.files[0]; if (!file) return;
    try {
      if (file.size > 2000000) throw new Error("Review file is too large.");
      const incoming = validateReview(JSON.parse(await file.text()), data.run_id, ids);
      reviews = incoming;
      const saved = persist();
      populate();
      if (saved) status.textContent = "Imported notes for this exact run.";
    } catch (error) { status.textContent = error.message; }
    event.target.value = "";
  });
  populate();
}

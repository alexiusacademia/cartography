// cartography's website: colours the Tessel code, copies the install
// command, and on the docs page filters the reference and marks the section
// you're reading.
// Author: Alexius Academia
// Date: 2026-11-22
(function () {
  const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const keywords = /^(import|fn|var|let|if|else|for|in|while|return|match|try|true|false|nil|app|state|struct|enum|view|bind|public)$/;
  const token = /(\/\/[^\n]*)|("(?:\\.|[^"\\])*")|(\b\d+(?:[._]\d+)*(?:e-?\d+)?\b)|([A-Za-z_]\w*)/g;
  for (const pre of document.querySelectorAll("pre.tsl")) {
    const text = pre.textContent;
    let out = "", last = 0, m;
    token.lastIndex = 0;
    while ((m = token.exec(text))) {
      out += esc(text.slice(last, m.index));
      const t = esc(m[0]);
      if (m[1]) out += '<span class="c">' + t + "</span>";
      else if (m[2]) out += '<span class="s">' + t + "</span>";
      else if (m[3]) out += '<span class="n">' + t + "</span>";
      else if (keywords.test(m[4])) out += '<span class="k">' + t + "</span>";
      else out += t;
      last = token.lastIndex;
    }
    pre.innerHTML = out + esc(text.slice(last));
  }

  for (const b of document.querySelectorAll("[data-copy]")) {
    b.addEventListener("click", () => {
      navigator.clipboard.writeText(b.dataset.copy).then(() => {
        b.textContent = "Copied";
        setTimeout(() => { b.textContent = "Copy"; }, 1500);
      }, () => {});
    });
  }

  // Copy buttons on the examples' programs.
  for (const pre of document.querySelectorAll(".program pre")) {
    const b = document.createElement("button");
    b.className = "copy code-copy";
    b.type = "button";
    b.textContent = "Copy";
    b.addEventListener("click", () => {
      navigator.clipboard.writeText(pre.textContent).then(() => {
        b.textContent = "Copied";
        setTimeout(() => { b.textContent = "Copy"; }, 1500);
      }, () => {});
    });
    pre.parentNode.insertBefore(b, pre);
  }

  // Docs: the filter box hides entries (and sections) that don't match.
  const filter = document.getElementById("filter");
  if (filter) {
    const sections = [...document.querySelectorAll("section.doc")];
    const empty = document.getElementById("no-match");
    const run = () => {
      const q = filter.value.trim().toLowerCase();
      document.body.classList.toggle("filtering", q !== "");
      let any = false;
      for (const s of sections) {
        let shown = 0;
        for (const a of s.querySelectorAll(".api")) {
          const hit = q === "" || a.textContent.toLowerCase().includes(q);
          a.hidden = !hit;
          if (hit) shown++;
        }
        for (const tr of s.querySelectorAll(".methods tr")) {
          if (tr.querySelector("th")) continue;
          const hit = q === "" || tr.textContent.toLowerCase().includes(q);
          tr.hidden = !hit;
          if (hit) shown++;
        }
        s.hidden = q !== "" && shown === 0;
        any = any || !s.hidden;
      }
      if (empty) empty.hidden = any;
    };
    filter.addEventListener("input", run);
    document.addEventListener("keydown", e => {
      if (e.key === "/" && document.activeElement !== filter) {
        e.preventDefault();
        filter.focus();
      } else if (e.key === "Escape" && document.activeElement === filter) {
        filter.value = "";
        run();
        filter.blur();
      }
    });
  }

  // Docs and examples: mark the side menu's link for the section in view.
  const links = new Map();
  for (const a of document.querySelectorAll(".sidenav a[href^='#']")) links.set(a.getAttribute("href").slice(1), a);
  if (links.size && "IntersectionObserver" in window) {
    const seen = new Set();
    const mark = () => {
      const first = [...links.keys()].find(id => seen.has(id));
      for (const [id, a] of links) a.classList.toggle("here", id === first);
    };
    const io = new IntersectionObserver(entries => {
      for (const e of entries) {
        if (e.isIntersecting) seen.add(e.target.id); else seen.delete(e.target.id);
      }
      mark();
    }, { rootMargin: "-70px 0px -55% 0px" });
    for (const id of links.keys()) {
      const el = document.getElementById(id);
      if (el) io.observe(el);
    }
  }
})();

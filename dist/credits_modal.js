/**
 * SwtorSim About & Credits Modal
 * Reads CREDITS.md (stopping at `---`) so CREDITS.md is the single source of truth.
 */
(function (global) {
  "use strict";

  const STYLE_ID = "swtorsim-credits-styles";
  const BACKDROP_ID = "swtorsim-credits-backdrop";
  const BODY_ID = "swtorsim-credits-body";

  const FALLBACK_HTML = `
    <div class="cred-section">
      <h3>Core Authors</h3>
      <ul class="cred-list">
        <li><strong>Mudkip</strong> &mdash; Creator, Combat Engine &amp; Math, Web UI Design, Maintainer</li>
        <li><strong>Sinrai</strong> &mdash; Game Data Extraction and Parsing, Combat Math, Statistical Analysis</li>
      </ul>
    </div>
    <div class="cred-section">
      <h3>Contributors</h3>
      <ul class="cred-list">
        <li><strong>Azreal</strong> &mdash; Fixes &amp; minor improvements</li>
        <li><strong>Randomno</strong> &mdash; HeroScripts for understanding game mechanics</li>
        <li><strong>Dantiko</strong> &mdash; Valuable debugging insights</li>
      </ul>
    </div>
    <div class="cred-section">
      <h3>Testing</h3>
      <ul class="cred-list">
        <li><strong>Perseus</strong> &mdash; Early testing &amp; feedback</li>
        <li><strong>Eisenhorn</strong> &mdash; Early testing &amp; feedback</li>
      </ul>
    </div>
    <div class="cred-section">
      <h3>Special Thanks</h3>
      <ul class="cred-list">
        <li><strong>Jedipedia</strong> (<a href="https://swtor.jedipedia.net" target="_blank" rel="noopener noreferrer">swtor.jedipedia.net</a>) &mdash; Invaluable SWTOR game data references&mdash;our extractor relies heavily on their work.</li>
      </ul>
    </div>
  `;

  let loadedFromMd = false;

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatInlineMd(text) {
    let out = escapeHtml(text);
    out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_, label, url) => {
      return `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`;
    });
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    return out;
  }

  function parseCreditsMarkdown(md) {
    const main = String(md || "").split(/\r?\n---\s*(?:\r?\n|$)/)[0];
    const lines = main.split(/\r?\n/);
    const sections = [];
    let current = null;

    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line || line.startsWith("# ")) continue;
      if (line.startsWith("## ")) {
        current = { title: line.slice(3).trim(), items: [] };
        sections.push(current);
      } else if (line.startsWith("- ") && current) {
        current.items.push(line.slice(2).trim());
      }
    }

    if (!sections.length) return null;
    return sections
      .map((sec) => {
        const lis = sec.items.map((item) => `<li>${formatInlineMd(item)}</li>`).join("");
        return `<div class="cred-section"><h3>${escapeHtml(sec.title)}</h3><ul class="cred-list">${lis}</ul></div>`;
      })
      .join("");
  }

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      #${BACKDROP_ID} {
        position: fixed;
        inset: 0;
        z-index: 10010;
        background: rgba(8, 14, 24, 0.65);
        display: none;
        align-items: center;
        justify-content: center;
        padding: 16px;
      }
      #${BACKDROP_ID}.open {
        display: flex;
      }
      .cred-modal {
        width: min(540px, 100%);
        max-height: 85vh;
        overflow-y: auto;
        background: var(--bg-card, #1c2331);
        color: var(--text-main, #f1f5f9);
        border: 1px solid var(--border, #263144);
        border-radius: 10px;
        box-shadow: 0 18px 44px rgba(0, 0, 0, 0.42);
        padding: 18px 20px 14px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-size: 13px;
        line-height: 1.48;
      }
      .cred-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding-bottom: 10px;
        margin-bottom: 12px;
        border-bottom: 1px solid var(--border-subtle, #19202c);
      }
      .cred-head h2 {
        margin: 0;
        font-size: 16px;
        font-weight: 700;
        color: var(--text-main, #f1f5f9);
      }
      .cred-close {
        background: transparent;
        border: none;
        color: var(--text-muted, #869ab3);
        font-size: 18px;
        line-height: 1;
        cursor: pointer;
        padding: 2px 6px;
        border-radius: 4px;
      }
      .cred-close:hover {
        color: var(--text-main, #f1f5f9);
        background: var(--bg-input, rgba(255, 255, 255, 0.08));
      }
      .cred-section {
        margin-bottom: 12px;
      }
      .cred-section:last-child {
        margin-bottom: 2px;
      }
      .cred-section h3 {
        margin: 0 0 5px;
        font-size: 11.5px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: var(--accent, #ff7818);
      }
      .cred-list {
        margin: 0;
        padding-left: 16px;
      }
      .cred-list li {
        margin-bottom: 4px;
      }
      .cred-list a {
        color: var(--cyan, #58abdf);
        text-decoration: none;
      }
      .cred-list a:hover {
        text-decoration: underline;
      }
    `;
    document.head.appendChild(style);
  }

  function ensureModal() {
    injectStyles();
    let backdrop = document.getElementById(BACKDROP_ID);
    if (backdrop) return backdrop;

    backdrop = document.createElement("div");
    backdrop.id = BACKDROP_ID;
    backdrop.setAttribute("role", "dialog");
    backdrop.setAttribute("aria-modal", "true");
    backdrop.setAttribute("aria-label", "SwtorSim Credits & Contributors");
    backdrop.innerHTML = `
      <div class="cred-modal">
        <div class="cred-head">
          <h2>SwtorSim Credits &amp; Contributors</h2>
          <button type="button" class="cred-close" id="credCloseBtn" title="Close (Esc)">&#10005;</button>
        </div>
        <div id="${BODY_ID}">${FALLBACK_HTML}</div>
      </div>
    `;

    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) api.close();
    });
    backdrop.querySelector("#credCloseBtn").addEventListener("click", () => api.close());
    document.body.appendChild(backdrop);
    return backdrop;
  }

  async function refreshFromMarkdown() {
    if (loadedFromMd) return;
    try {
      const res = await fetch("CREDITS.md", { cache: "no-store" });
      if (!res.ok) return;
      const md = await res.text();
      const html = parseCreditsMarkdown(md);
      if (html) {
        const body = document.getElementById(BODY_ID);
        if (body) body.innerHTML = html;
        loadedFromMd = true;
      }
    } catch (_) {}
  }

  function onKeyDown(e) {
    if (e.key === "Escape") api.close();
  }

  const api = {
    open() {
      const backdrop = ensureModal();
      backdrop.classList.add("open");
      document.addEventListener("keydown", onKeyDown);
      refreshFromMarkdown();
    },
    close() {
      const backdrop = document.getElementById(BACKDROP_ID);
      if (backdrop) backdrop.classList.remove("open");
      document.removeEventListener("keydown", onKeyDown);
    },
  };

  global.SwtorCredits = api;
})(window);

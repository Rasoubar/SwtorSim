/**
 * SwtorSim In-Page Tutorial Showcase
 * Zero-dependency spotlight & guided walkthrough engine.
 */
(function (global) {
  "use strict";

  const STYLE_ID = "swtorsim-tutorial-styles";

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .tut-backdrop {
        position: fixed;
        inset: 0;
        z-index: 9997;
        background: transparent;
      }
      .tut-spotlight {
        position: fixed;
        z-index: 9998;
        pointer-events: none;
        border-radius: 8px;
        box-shadow:
          0 0 0 9999px rgba(8, 14, 24, 0.62),
          0 0 0 2px var(--accent, #ff7818),
          0 0 20px rgba(255, 120, 24, 0.45);
        transition: top 0.22s ease, left 0.22s ease, width 0.22s ease, height 0.22s ease, opacity 0.18s ease;
      }
      .tut-spotlight.is-centered {
        top: 50% !important;
        left: 50% !important;
        width: 0 !important;
        height: 0 !important;
        box-shadow: 0 0 0 9999px rgba(8, 14, 24, 0.62);
      }
      .tut-popover {
        position: fixed;
        z-index: 9999;
        width: min(390px, calc(100vw - 24px));
        background: var(--bg-card, #ffffff);
        color: var(--text-main, #0c2138);
        border: 1px solid var(--border, #388bc2);
        border-radius: 10px;
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.34);
        padding: 14px 16px 13px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-size: 13px;
        line-height: 1.48;
        transition: top 0.22s ease, left 0.22s ease, opacity 0.18s ease;
      }
      .tut-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 6px;
      }
      .tut-step-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.4px;
        color: var(--accent, #ff7818);
        background: var(--accent-bg, rgba(255, 120, 24, 0.14));
        padding: 2px 8px;
        border-radius: 999px;
      }
      .tut-close {
        background: transparent;
        border: none;
        color: var(--text-muted, #496885);
        cursor: pointer;
        font-size: 16px;
        line-height: 1;
        padding: 2px 5px;
        border-radius: 4px;
      }
      .tut-close:hover {
        color: var(--text-main, #0c2138);
        background: var(--bg-input, rgba(0, 0, 0, 0.06));
      }
      .tut-title {
        font-size: 15px;
        font-weight: 700;
        margin: 0 0 6px;
        color: var(--text-main, #0c2138);
      }
      .tut-body {
        margin: 0 0 12px;
        color: var(--text-main, #0c2138);
        font-size: 12.5px;
      }
      .tut-body p {
        margin: 0 0 6px;
      }
      .tut-body p:last-child {
        margin-bottom: 0;
      }
      .tut-body code {
        background: var(--bg-input, #f0f7fc);
        border: 1px solid var(--border-subtle, #c5e2f5);
        border-radius: 4px;
        padding: 1px 5px;
        font-size: 11.5px;
      }
      .tut-action-row {
        margin-bottom: 11px;
      }
      .tut-action-btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: var(--accent-bg, rgba(255, 120, 24, 0.14));
        color: var(--accent, #ff7818);
        border: 1px solid var(--accent, #ff7818);
        border-radius: 6px;
        padding: 5px 11px;
        font-size: 12px;
        font-weight: 700;
        cursor: pointer;
        transition: background 0.15s ease, color 0.15s ease;
      }
      .tut-action-btn:hover:not(:disabled) {
        background: var(--accent, #ff7818);
        color: #ffffff;
      }
      .tut-action-btn:disabled {
        opacity: 0.6;
        cursor: wait;
      }
      .tut-footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        padding-top: 8px;
        border-top: 1px solid var(--border-subtle, #c5e2f5);
      }
      .tut-dots {
        display: flex;
        align-items: center;
        gap: 5px;
      }
      .tut-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: var(--border, #388bc2);
        opacity: 0.4;
        cursor: pointer;
        transition: transform 0.15s ease, opacity 0.15s ease;
      }
      .tut-dot.active {
        opacity: 1;
        transform: scale(1.3);
        background: var(--accent, #ff7818);
      }
      .tut-nav {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .tut-btn {
        border: 1px solid var(--border, #388bc2);
        background: var(--bg-input, #f0f7fc);
        color: var(--text-main, #0c2138);
        border-radius: 5px;
        padding: 5px 10px;
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
      }
      .tut-btn:hover:not(:disabled) {
        border-color: var(--accent, #ff7818);
      }
      .tut-btn:disabled {
        opacity: 0.45;
        cursor: not-allowed;
      }
      .tut-btn-primary {
        background: var(--accent, #ff7818);
        border-color: var(--accent, #ff7818);
        color: #ffffff;
      }
      .tut-btn-primary:hover:not(:disabled) {
        background: var(--accent-hover, #e65c00);
        border-color: var(--accent-hover, #e65c00);
      }
      .tut-welcome-toast {
        position: fixed;
        right: 18px;
        bottom: 18px;
        z-index: 9990;
        width: min(330px, calc(100vw - 24px));
        background: var(--bg-card, #ffffff);
        color: var(--text-main, #0c2138);
        border: 1px solid var(--accent, #ff7818);
        border-radius: 10px;
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.28);
        padding: 12px 14px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-size: 12.5px;
      }
      .tut-welcome-toast-title {
        font-weight: 700;
        font-size: 13.5px;
        margin-bottom: 4px;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .tut-welcome-toast-actions {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-top: 10px;
      }
    `;
    document.head.appendChild(style);
  }

  const state = {
    config: null,
    active: false,
    index: 0,
    backdropEl: null,
    spotlightEl: null,
    popoverEl: null,
    toastEl: null,
    rafId: null,
  };

  function resolveTargets(step) {
    if (!step || !step.target) return [];
    const raw = typeof step.target === "function" ? step.target() : step.target;
    const list = Array.isArray(raw) ? raw : [raw];
    const els = [];
    for (const item of list) {
      const el = typeof item === "string" ? document.querySelector(item) : item;
      if (!el) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;
      els.push(el);
    }
    return els;
  }

  function getUnionRect(els) {
    let left = Infinity;
    let top = Infinity;
    let right = -Infinity;
    let bottom = -Infinity;
    for (const el of els) {
      const r = el.getBoundingClientRect();
      if (r.left < left) left = r.left;
      if (r.top < top) top = r.top;
      if (r.right > right) right = r.right;
      if (r.bottom > bottom) bottom = r.bottom;
    }
    return { left, top, right, bottom, width: right - left, height: bottom - top };
  }

  function clamp(val, min, max) {
    return Math.max(min, Math.min(max, val));
  }

  function positionOverlay() {
    if (!state.active || !state.popoverEl || !state.spotlightEl) return;
    const step = state.config.steps[state.index];
    const targetEls = resolveTargets(step);
    const pop = state.popoverEl;
    const spot = state.spotlightEl;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const pad = 6;
    const gap = 14;

    const popRect = pop.getBoundingClientRect();
    const popW = popRect.width || 360;
    const popH = popRect.height || 200;

    if (!targetEls.length) {
      spot.classList.add("is-centered");
      pop.style.left = `${Math.round((vw - popW) / 2)}px`;
      pop.style.top = `${Math.round((vh - popH) / 2)}px`;
      return;
    }

    spot.classList.remove("is-centered");
    const r = getUnionRect(targetEls);
    const sx = Math.max(4, r.left - pad);
    const sy = Math.max(4, r.top - pad);
    const sw = Math.min(vw - sx - 4, r.width + pad * 2);
    const sh = Math.min(vh - sy - 4, r.height + pad * 2);

    spot.style.left = `${Math.round(sx)}px`;
    spot.style.top = `${Math.round(sy)}px`;
    spot.style.width = `${Math.round(sw)}px`;
    spot.style.height = `${Math.round(sh)}px`;

    const candidates = [];
    const pref = step.placement || "auto";
    if (pref !== "auto") candidates.push(pref);
    candidates.push("right", "bottom", "left", "top");

    let chosen = null;
    for (const side of candidates) {
      let left = 0;
      let top = 0;
      if (side === "right") {
        left = sx + sw + gap;
        top = sy + (sh - popH) / 2;
        if (left + popW <= vw - 12) {
          chosen = { left, top };
          break;
        }
      } else if (side === "left") {
        left = sx - popW - gap;
        top = sy + (sh - popH) / 2;
        if (left >= 12) {
          chosen = { left, top };
          break;
        }
      } else if (side === "bottom") {
        left = sx + (sw - popW) / 2;
        top = sy + sh + gap;
        if (top + popH <= vh - 12) {
          chosen = { left, top };
          break;
        }
      } else if (side === "top") {
        left = sx + (sw - popW) / 2;
        top = sy - popH - gap;
        if (top >= 12) {
          chosen = { left, top };
          break;
        }
      }
    }

    if (!chosen) {
      // Fallback: place on the side with the most vertical room
      const spaceBelow = vh - (sy + sh);
      const spaceAbove = sy;
      chosen = {
        left: sx + (sw - popW) / 2,
        top: spaceBelow >= spaceAbove ? sy + sh + gap : sy - popH - gap,
      };
    }

    pop.style.left = `${Math.round(clamp(chosen.left, 12, Math.max(12, vw - popW - 12)))}px`;
    pop.style.top = `${Math.round(clamp(chosen.top, 12, Math.max(12, vh - popH - 12)))}px`;
  }

  function scheduleReposition() {
    if (!state.active) return;
    if (state.rafId) cancelAnimationFrame(state.rafId);
    state.rafId = requestAnimationFrame(() => {
      state.rafId = null;
      positionOverlay();
    });
  }

  function markSeen() {
    if (state.config && state.config.storageKey) {
      try {
        localStorage.setItem(state.config.storageKey, "1");
      } catch (_) {}
    }
  }

  function dismissToast() {
    if (state.toastEl) {
      state.toastEl.remove();
      state.toastEl = null;
    }
  }

  function createOverlayElements() {
    if (!state.backdropEl) {
      state.backdropEl = document.createElement("div");
      state.backdropEl.className = "tut-backdrop";
      document.body.appendChild(state.backdropEl);
    }
    if (!state.spotlightEl) {
      state.spotlightEl = document.createElement("div");
      state.spotlightEl.className = "tut-spotlight";
      document.body.appendChild(state.spotlightEl);
    }
    if (!state.popoverEl) {
      state.popoverEl = document.createElement("div");
      state.popoverEl.className = "tut-popover";
      state.popoverEl.setAttribute("role", "dialog");
      state.popoverEl.setAttribute("aria-modal", "true");
      document.body.appendChild(state.popoverEl);
    }
  }

  async function renderStep(index) {
    if (!state.config || !state.config.steps.length) return;
    const steps = state.config.steps;
    state.index = clamp(index, 0, steps.length - 1);
    const step = steps[state.index];

    if (typeof step.onEnter === "function") {
      try {
        await step.onEnter(api);
      } catch (err) {
        console.warn("[SwtorTutorial] onEnter error:", err);
      }
    }

    const targetEls = resolveTargets(step);
    if (targetEls.length && typeof targetEls[0].scrollIntoView === "function") {
      targetEls[0].scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    }

    const dotsHtml = steps
      .map((_, i) => `<span class="tut-dot${i === state.index ? " active" : ""}" data-tut-dot="${i}" title="Step ${i + 1}"></span>`)
      .join("");

    const actionHtml = step.action
      ? `<div class="tut-action-row"><button type="button" class="tut-action-btn" id="tutActionBtn">${step.action.label}</button></div>`
      : "";

    const isFirst = state.index === 0;
    const isLast = state.index === steps.length - 1;

    state.popoverEl.innerHTML = `
      <div class="tut-header">
        <span class="tut-step-pill">Step ${state.index + 1} of ${steps.length}</span>
        <button type="button" class="tut-close" id="tutCloseBtn" title="Close Tutorial (Esc)">&#10005;</button>
      </div>
      <h3 class="tut-title">${step.title}</h3>
      <div class="tut-body">${step.body}</div>
      ${actionHtml}
      <div class="tut-footer">
        <div class="tut-dots">${dotsHtml}</div>
        <div class="tut-nav">
          <button type="button" class="tut-btn" id="tutPrevBtn" ${isFirst ? "disabled" : ""}>Back</button>
          <button type="button" class="tut-btn tut-btn-primary" id="tutNextBtn">${isLast ? "Finish" : "Next"}</button>
        </div>
      </div>
    `;

    state.popoverEl.querySelector("#tutCloseBtn").onclick = () => api.close();
    state.popoverEl.querySelector("#tutPrevBtn").onclick = () => api.prev();
    state.popoverEl.querySelector("#tutNextBtn").onclick = () => {
      if (isLast) api.close();
      else api.next();
    };
    state.popoverEl.querySelectorAll("[data-tut-dot]").forEach((dot) => {
      dot.onclick = () => renderStep(parseInt(dot.dataset.tutDot, 10));
    });

    const actionBtn = state.popoverEl.querySelector("#tutActionBtn");
    if (actionBtn && step.action && typeof step.action.run === "function") {
      actionBtn.onclick = async () => {
        actionBtn.disabled = true;
        const origText = actionBtn.textContent;
        actionBtn.textContent = "Running...";
        try {
          await step.action.run(api);
        } finally {
          if (document.body.contains(actionBtn)) {
            actionBtn.disabled = false;
            actionBtn.textContent = origText;
          }
          scheduleReposition();
        }
      };
    }

    positionOverlay();
    // Reposition once more after smooth scroll settles
    setTimeout(scheduleReposition, 240);
  }

  function onKeyDown(e) {
    if (!state.active) return;
    const tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
      if (e.key === "Escape") api.close();
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      api.close();
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      if (state.index < state.config.steps.length - 1) api.next();
      else api.close();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      api.prev();
    }
  }

  function showWelcomeToastIfNeeded() {
    const cfg = state.config;
    if (!cfg || !cfg.showWelcomeToast) return;
    let seen = false;
    try {
      seen = localStorage.getItem(cfg.storageKey) === "1";
    } catch (_) {}
    if (seen) return;

    dismissToast();
    const toast = document.createElement("div");
    toast.className = "tut-welcome-toast";
    toast.innerHTML = `
      <div class="tut-welcome-toast-title">
        <span>${cfg.welcomeTitle || "New to SwtorSim?"}</span>
        <button type="button" class="tut-close" id="tutToastDismissX" title="Dismiss">&#10005;</button>
      </div>
      <div style="color:var(--text-muted, #496885);">${cfg.welcomeBody || "Take a quick interactive tour of the controls and live telemetry."}</div>
      <div class="tut-welcome-toast-actions">
        <button type="button" class="tut-btn tut-btn-primary" id="tutToastStartBtn">Start Guided Tour</button>
        <button type="button" class="tut-btn" id="tutToastLaterBtn">Maybe Later</button>
      </div>
    `;
    document.body.appendChild(toast);
    state.toastEl = toast;

    toast.querySelector("#tutToastStartBtn").onclick = () => {
      dismissToast();
      api.start(0);
    };
    const dismiss = () => {
      markSeen();
      dismissToast();
    };
    toast.querySelector("#tutToastLaterBtn").onclick = dismiss;
    toast.querySelector("#tutToastDismissX").onclick = dismiss;
  }

  const api = {
    init(config) {
      injectStyles();
      state.config = config;
      if (config.buttonId) {
        const btn = document.getElementById(config.buttonId);
        if (btn) btn.addEventListener("click", () => api.start(0));
      }
      showWelcomeToastIfNeeded();
    },

    start(index = 0) {
      if (!state.config || !state.config.steps || !state.config.steps.length) return;
      injectStyles();
      dismissToast();
      markSeen();
      createOverlayElements();
      if (!state.active) {
        state.active = true;
        window.addEventListener("resize", scheduleReposition);
        window.addEventListener("scroll", scheduleReposition, true);
        document.addEventListener("keydown", onKeyDown);
      }
      renderStep(index);
    },

    next() {
      if (!state.active) return;
      if (state.index < state.config.steps.length - 1) {
        renderStep(state.index + 1);
      }
    },

    prev() {
      if (!state.active) return;
      if (state.index > 0) {
        renderStep(state.index - 1);
      }
    },

    close() {
      if (!state.active) return;
      state.active = false;
      markSeen();
      window.removeEventListener("resize", scheduleReposition);
      window.removeEventListener("scroll", scheduleReposition, true);
      document.removeEventListener("keydown", onKeyDown);
      if (state.rafId) {
        cancelAnimationFrame(state.rafId);
        state.rafId = null;
      }
      if (state.backdropEl) {
        state.backdropEl.remove();
        state.backdropEl = null;
      }
      if (state.spotlightEl) {
        state.spotlightEl.remove();
        state.spotlightEl = null;
      }
      if (state.popoverEl) {
        state.popoverEl.remove();
        state.popoverEl = null;
      }
    },

    resetSeen() {
      if (state.config && state.config.storageKey) {
        try {
          localStorage.removeItem(state.config.storageKey);
        } catch (_) {}
      }
    },
  };

  global.SwtorTutorial = api;
})(window);

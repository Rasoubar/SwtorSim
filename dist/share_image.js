/* Share Image: draws a simulator result or a rotation as PNG cards on a canvas, with a dialog to
 * copy them to the clipboard or download them. Display-only: it reads the data it is given.
 *
 * Shared by the Combat Simulator dashboard (tools/simulator_ui.html: summary card, rotation on the
 * card / as a separate image / off) and the Rotation Builder (tools/rotation_builder_ui.html: rotation
 * image only). Served as /share_image.js by both servers; tools/build_web_release.py copies it to
 * dist/share_image.js.
 *
 * ShareImage.open(res, { placement, button }): res is a simulator result (or a result-shaped object
 * from the builder) carrying class_name, spec, environment, rotation_snapshot ({pre_combat, sequence,
 * weave, icons, names, slugs, off_gcd}) and _rotationLabel / _shareContext.
 */
(function (global) {
  "use strict";

  const SHARE_W = 1200;
  const SHARE_PAD = 32;
  const SHARE_FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

  function shareColors() {
    const cs = getComputedStyle(document.documentElement);
    const v = (name, fb) => (cs.getPropertyValue(name) || "").trim() || fb;
    return {
      bg: v("--bg-base", "#0e121a"),
      card: v("--bg-card", "#1c2331"),
      input: v("--bg-input", "#10141d"),
      border: v("--border-subtle", "#19202c"),
      text: v("--text-main", "#f1f5f9"),
      muted: v("--text-muted", "#869ab3"),
      accent: v("--accent", "#ff7818"),
      accentBg: v("--accent-bg", "rgba(255, 120, 24, 0.14)"),
      amber: v("--amber", "#f59e0b"),
      amberBg: v("--amber-bg", "rgba(245, 158, 11, 0.14)"),
      green: v("--green", "#22c55e"),
      cyan: v("--cyan", "#58abdf"),
      cyanBg: v("--cyan-bg", "rgba(88, 171, 223, 0.14)"),
    };
  }

  // Drawing calls do nothing while `dry` is set, so the same layout code measures and paints.
  function makeSharePainter(ctx, dry) {
    return {
      ctx,
      dry,
      font(size, weight = 400) { ctx.font = `${weight} ${size}px ${SHARE_FONT}`; },
      w(text) { return ctx.measureText(String(text)).width; },
      text(t, x, y, color, align = "left") {
        if (this.dry) return;
        ctx.fillStyle = color;
        ctx.textAlign = align;
        ctx.textBaseline = "alphabetic";
        ctx.fillText(String(t), x, y);
      },
      rect(x, y, w, h, fill, r = 0, stroke = null, dash = null) {
        if (this.dry) return;
        ctx.beginPath();
        if (r && ctx.roundRect) ctx.roundRect(x, y, w, h, r);
        else ctx.rect(x, y, w, h);
        if (fill) { ctx.fillStyle = fill; ctx.fill(); }
        if (stroke) {
          ctx.strokeStyle = stroke;
          ctx.lineWidth = dash ? 1.5 : 1;
          ctx.setLineDash(dash || []);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      },
      img(im, x, y, s) {
        if (this.dry || !im) return;
        ctx.drawImage(im, x, y, s, s);
      },
      measure(fn) {
        const prev = this.dry;
        this.dry = true;
        try { return fn(); } finally { this.dry = prev; }
      },
      fit(text, maxW) {
        let t = String(text ?? "");
        if (this.w(t) <= maxW) return t;
        while (t.length > 1 && this.w(t + "…") > maxW) t = t.slice(0, -1);
        return t + "…";
      },
      wrap(text, maxW) {
        const words = String(text ?? "").split(/\s+/).filter(Boolean);
        const lines = [];
        let cur = "";
        for (const word of words) {
          const next = cur ? `${cur} ${word}` : word;
          if (cur && this.w(next) > maxW) { lines.push(cur); cur = word; } else cur = next;
        }
        if (cur) lines.push(cur);
        return lines.length ? lines : [""];
      },
    };
  }

  // Plain-text rule labels; same wording as the Rotation Builder's rule pills.
  function shareRuleText(key, val) {
    const list = (v, j) => (Array.isArray(v) ? v.join(j) : String(v));
    const pct = (v) => `${Math.round(Number(v) * 100)}%`;
    const named = (lbl) => (val && typeof val === "object" ? `${lbl.replace("{v}", val.value)}: ${val.name}` : `${key}: ${JSON.stringify(val)}`);
    const ops = { lt: "<", le: "≤", lte: "≤", gt: ">", ge: "≥", gte: "≥", eq: "=", "==": "=", ne: "≠" };
    const opOf = (o, fallback) => ops[String(o || fallback).toLowerCase()] || String(o || fallback);
    const obj = val && typeof val === "object" && !Array.isArray(val) ? val : null;
    switch (key) {
      case "caster_buff_remaining":
        return obj ? `Buff left ${opOf(obj.comparison || obj.operator, "<")} ${obj.value}s: ${obj.name}` : `${key}: ${JSON.stringify(val)}`;
      case "target_debuff_remaining":
        return obj ? `Debuff left ${opOf(obj.comparison || obj.operator, "<")} ${obj.value}s: ${obj.name}` : `${key}: ${JSON.stringify(val)}`;
      case "target_hp_pct": {
        const sym = opOf(obj && (obj.comparison || obj.operator), "≤");
        const shown = `Target HP ${sym} ${pct(obj ? obj.pct ?? 0.3 : val)}`;
        return obj && obj.bypass_if_buff_active ? `${shown} (or buff: ${obj.bypass_if_buff_active})` : shown;
      }
      case "caster_energy":
        return `Energy/Force ${opOf(obj && (obj.comparison || obj.operator), "≥")} ${obj ? (obj.value ?? obj.threshold) : val}`;
      case "proc_cooldown": return named(`Proc ICD ${opOf(obj && (obj.comparison || obj.operator), ">")} {v}s`);
      case "ability_cooldown": return named(`Ability CD ${opOf(obj && (obj.comparison || obj.operator), "<")} {v}s`);
      case "target_hp_below_pct":
        if (val && typeof val === "object") return `Target HP ≤ ${pct(val.pct ?? 0.3)} (or buff: ${val.bypass_if_buff_active})`;
        return `Target HP ≤ ${pct(val)}`;
      case "target_hp_above_pct": return `Target HP > ${pct(val)}`;
      case "caster_has_buff": return `Caster Buff: ${list(val, " OR ")}`;
      case "caster_does_not_have_buff": return `No Caster Buff: ${list(val, ", ")}`;
      case "target_has_debuff": return `Target Debuff: ${list(val, " OR ")}`;
      case "target_doesnt_have_debuff": return `No Target Debuff: ${list(val, ", ")}`;
      case "caster_energy_below": return `Energy/Force < ${val}`;
      case "caster_energy_above": return `Energy/Force ≥ ${val}`;
      case "proc_cooldown_above": return named("Proc ICD > {v}s");
      case "ability_cooldown_under": return named("Ability CD < {v}s");
      case "ability_cooldown_above": return named("Ability CD > {v}s");
      case "caster_buff_stacks":
      case "caster_has_buff_stacks":
      case "caster_buff_charges":
      case "target_debuff_stacks":
      case "target_has_debuff_stacks": {
        const lbl = key.startsWith("target") ? "Target Debuff Stacks" : "Caster Buff Stacks";
        const op = (o) => opOf(o, ">=");
        if (Array.isArray(val)) return `${lbl}: ${val[0]} ${op(val[2])} ${val[1]}`;
        if (val && typeof val === "object") {
          const bName = val.name || val.buff || val.debuff || val.ability_spec || "?";
          return `${lbl}: ${bName} ${op(val.comparison || val.operator)} ${val.stacks ?? val.count ?? val.value ?? 1}`;
        }
        return `${key}: ${JSON.stringify(val)}`;
      }
      default:
        return `${key.replace(/_/g, " ")}: ${val && typeof val === "object" ? JSON.stringify(val) : val}`;
    }
  }

  function shareEntryRules(entry) {
    const out = Object.entries((entry && entry.rules) || {}).map(([k, v]) => shareRuleText(k, v));
    if (entry && Number(entry.lead_time) > 0) out.push(`Lead time ${entry.lead_time}s`);
    return out;
  }

  function shareAbility(snap, aid) {
    const slugs = snap.slugs || {};
    const names = snap.names || {};
    const slug = slugs[aid] || String(aid || "").toLowerCase().replace(/ /g, "_");
    return {
      name: names[aid] || names[slug] || String(aid || "?"),
      icon: (snap.icons || {})[slug] || "",
      offGcd: Boolean((snap.off_gcd || {})[slug]),
    };
  }

  // Icon for a breakdown row: its own name, else the ability in parentheses ("Bleeding (Deadly Saber)").
  function shareBreakdownIcon(snap, rowName) {
    const icons = (snap && snap.icons) || {};
    const slug = (s) => String(s || "").trim().toLowerCase().replace(/ /g, "_");
    const inner = /\(([^()]+)\)\s*$/.exec(String(rowName || ""));
    return icons[slug(rowName)] || (inner ? icons[slug(inner[1])] : "") || "";
  }

  function shareIconNames(res) {
    const snap = res.rotation_snapshot || {};
    const out = new Set(Object.values(snap.icons || {}));
    return [...out].filter(Boolean);
  }

  function shareLoadIcon(name) {
    return new Promise((resolve) => {
      const clean = name.toLowerCase().endsWith(".png") ? name : `${name}.png`;
      const urls = [...new Set([`icons/${encodeURIComponent(clean)}`, `icons/${encodeURIComponent(clean.toLowerCase())}`])];
      const tryAt = (i) => {
        if (i >= urls.length) { resolve(null); return; }
        const im = new Image();
        im.onload = () => resolve(im);
        im.onerror = () => tryAt(i + 1);
        im.src = urls[i];
      };
      tryAt(0);
    });
  }

  // Lays out (and, when the painter is not dry, draws) one image; returns its height.
  // opts.kind: "summary" (header, KPIs, loadout, breakdown, rotation) or "rotation" (header + rotation);
  // opts.rotation: "full" | "compact" | null. A res without `mode` (Rotation Builder) gets a
  // "ROTATION BUILDER" header tag instead of the run mode / seed, and no DPS.
  function paintShareCard(p, res, icons, C, opts = {}) {
    const kind = opts.kind || "summary";
    const W = SHARE_W;
    const PAD = SHARE_PAD;
    const inner = W - PAD * 2;
    const GAP = 16;
    const snap = res.rotation_snapshot || null;
    const sc = res._shareContext || {};
    const isBatch = res.mode === "BATCH";
    const fmt1 = (n) => Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const fmt0 = (n) => Math.round(Number(n || 0)).toLocaleString();
    const iconOf = (name) => (name ? icons[name] || null : null);
    let y = PAD;

    // Card frame + title; body(y) returns the y where its content ends.
    const card = (x, cy, w, title, right, body) => {
      const top = cy + 44;
      const end = p.measure(() => body(top));
      const h = end - cy + 18;
      p.rect(x, cy, w, h, C.card, 10, C.border);
      p.font(12, 700);
      p.text(title, x + 20, cy + 28, C.accent);
      if (right) {
        p.font(12, 600);
        p.text(p.fit(right, w - 60 - p.w(title)), x + w - 20, cy + 28, C.muted, "right");
      }
      body(top);
      return h;
    };

    // ---- Header ----
    {
      const h = 96;
      p.rect(PAD, y, inner, h, C.card, 10, C.border);
      p.rect(PAD, y + 14, 5, h - 28, C.accent, 2);
      const modeTxt = !res.mode
        ? "ROTATION BUILDER"
        : isBatch ? `BATCH · ${fmt0(res.iterations)} fights · seed ${res.seed}` : `TEST · single fight · seed ${res.seed}`;
      let when = "";
      try { when = new Date(sc.ran_at || Date.now()).toLocaleString(); } catch (e) { when = ""; }
      p.font(13, 700);
      const rightW = Math.max(p.w(modeTxt), 120);
      p.text(modeTxt, PAD + inner - 24, y + 34, C.cyan, "right");
      p.font(12, 400);
      p.text(when, PAD + inner - 24, y + 56, C.muted, "right");
      if (kind === "rotation" && res.mode && Number.isFinite(Number(res.dps))) {
        p.font(13, 700);
        p.text(`${fmt1(res.dps)} ${isBatch ? "mean " : ""}DPS`, PAD + inner - 24, y + 80, C.accent, "right");
      }
      const leftW = inner - 48 - rightW - 24;
      p.font(12, 700);
      p.text(kind === "rotation" ? "SWTORSIM · ROTATION" : "SWTORSIM · COMBAT SIMULATOR", PAD + 24, y + 28, C.accent);
      p.font(28, 700);
      p.text(p.fit(`${res.class_name} — ${res.spec}`, leftW), PAD + 24, y + 62, C.text);
      p.font(14, 400);
      const env = String(res.environment || "live").toUpperCase();
      const sub = [res._rotationLabel ? `Rotation: ${res._rotationLabel}` : "", env, res.level ? `Level ${res.level}` : ""].filter(Boolean).join("  ·  ");
      p.text(p.fit(sub, leftW), PAD + 24, y + 84, C.muted);
      y += h + GAP;
    }

    if (kind === "summary") {
      // ---- KPI tiles ----
      {
        const ex = res.execute_phase || {};
        const st = res.stalls || {};
        const tiles = [
          {
            label: isBatch ? "MEAN DPS" : "DPS",
            value: fmt1(res.dps),
            color: C.accent,
            sub: isBatch ? `±${fmt1(res.std_dev)} SD · median ${fmt1(res.median_dps)}` : `${fmt0(res.total_damage)} total damage`,
          },
          {
            label: "FIGHT DURATION",
            value: `${Number(res.duration || 0).toFixed(1)}s`,
            color: C.text,
            sub: isBatch ? `avg ${fmt0(res.total_damage)} damage` : (res.killed_target ? "target killed" : "time cap reached"),
          },
          {
            label: "EXECUTE (<30% HP)",
            value: ex.active ? fmt1(ex.dps) : "N/A",
            color: C.text,
            sub: ex.active ? `${Number(ex.duration || 0).toFixed(1)}s window` : "no <30% HP window",
          },
          {
            label: "CRIT RATE",
            value: `${Number(res.overall_crit_pct || 0).toFixed(1)}%`,
            color: C.amber,
            sub: `${isBatch ? "avg " : ""}${Number(res.total_hits || 0).toLocaleString()} hits`,
          },
          isBatch
            ? { label: "DPS P10 – P90", value: `${fmt0(res.p10_dps)} – ${fmt0(res.p90_dps)}`, color: C.text, sub: `min ${fmt0(res.min_dps)} · max ${fmt0(res.max_dps)}` }
            : { label: "ROTATION IDLE", value: `${Number(st.total_stalled_time || 0).toFixed(2)}s`, color: Number(st.total_stalled_time) > 0 ? C.amber : C.green, sub: `${st.stall_count || 0} gap(s)` },
        ];
        const tw = (inner - GAP * (tiles.length - 1)) / tiles.length;
        const th = 92;
        tiles.forEach((t, i) => {
          const x = PAD + i * (tw + GAP);
          p.rect(x, y, tw, th, C.card, 10, C.border);
          p.font(11, 700);
          p.text(t.label, x + 16, y + 24, C.muted);
          let size = 30;
          p.font(size, 700);
          while (size > 16 && p.w(t.value) > tw - 32) { size -= 2; p.font(size, 700); }
          p.text(t.value, x + 16, y + 60, t.color);
          p.font(12, 400);
          p.text(p.fit(t.sub, tw - 32), x + 16, y + 80, C.muted);
        });
        y += th + GAP;
      }

      // ---- Loadout + character sheet ----
      {
        const colW = (inner - GAP) / 2;
        const s = sc.settings || {};
        const yesNo = (v) => (v ? "Yes" : "No");
        const loadout = [
          ["Build", sc.build || "—"],
          ["Tactical", sc.tactical || "—"],
          ["Legendaries", (sc.legendaries || []).join(", ") || "—"],
          ["Relics", (sc.relics || []).join(", ") || "—"],
        ];
        const settings = sc.settings ? [
          ["Dummy HP", fmt0(s.dummy_hp)],
          ["Time cap", `${s.duration}s`],
          ["Debuff Module", yesNo(s.armor_debuff)],
          ["In operation", yesNo(s.in_operation)],
          ["Distance", `${s.combat_distance}m`],
          ["Flight time", yesNo(s.flight_time)],
          ["GCD stall", `${Math.round(Number(s.gcd_stall || 0) * 100)}%`],
          ["Attacked every", Number(s.incoming_attack_interval) > 0 ? `${Number(s.incoming_attack_interval)}s` : "off"],
          // TEMPORARY stand-in for a defense / shield roll (see TODO.md): shown only when used.
          ...(Number(s.incoming_attack_interval) > 0 && (Number(s.incoming_avoid_chance) > 0 || Number(s.incoming_shield_chance) > 0)
            ? [["Avoided / shielded", `${Number(s.incoming_avoid_chance || 0)}% / ${Number(s.incoming_shield_chance || 0)}%`]] : []),
        ] : [];
        const cs = res.computed_player_stats || {};
        const pct2 = (v) => `${Number(v || 0).toFixed(2)}%`;
        const bonus = Math.max(cs.force_bonus_dmg || 0, cs.tech_bonus_dmg || 0, cs.melee_bonus_dmg || 0, cs.ranged_bonus_dmg || 0);
        const ftPower = Math.round(cs.force_power || 0) === Math.round(cs.tech_power || 0)
          ? fmt0(cs.force_power)
          : `${fmt0(cs.force_power)} / ${fmt0(cs.tech_power)}`;
        const sheet = [
          ["Mastery", fmt0(cs.mastery)],
          ["Power", fmt0(cs.power)],
          ["Force/Tech Power", ftPower],
          ["Bonus Damage", fmt0(bonus)],
          ["Critical Rating", fmt0(cs.crit_rating)],
          ["Crit Chance", pct2(cs.crit_chance_pct)],
          ["Alacrity Rating", fmt0(cs.alacrity_rating)],
          ["Crit Multiplier", pct2(cs.crit_multiplier_pct)],
          ["Accuracy Rating", fmt0(cs.accuracy_rating)],
          ["Alacrity", pct2(cs.alacrity_pct)],
          ["GCD", `${Number(cs.gcd_seconds || 1.5).toFixed(2)}s`],
          ["Accuracy", pct2(cs.accuracy_pct)],
          [`Max ${String(cs.resource_type || "resource").replace(/^./, (c) => c.toUpperCase())}`, fmt0(cs.max_resource)],
        ];
        const kvGrid = (x, gy, w, pairs, cols) => {
          const cw = (w - (cols - 1) * 24) / cols;
          pairs.forEach(([k, v], i) => {
            const cx = x + (i % cols) * (cw + 24);
            const ry = gy + Math.floor(i / cols) * 24;
            p.font(13, 400);
            p.text(k, cx, ry + 16, C.muted);
            p.font(13, 700);
            p.text(p.fit(v, cw - p.w(k) - 12), cx + cw, ry + 16, C.text, "right");
          });
          return gy + Math.ceil(pairs.length / cols) * 24;
        };
        const loadoutBody = (top) => {
          let ly = top;
          for (const [k, v] of loadout) {
            p.font(13, 400);
            p.text(k, PAD + 20, ly + 16, C.muted);
            p.font(13, 700);
            const lines = p.wrap(v, colW - 40 - 100);
            lines.forEach((ln, i) => p.text(ln, PAD + 120, ly + 16 + i * 18, C.text));
            ly += Math.max(24, lines.length * 18 + 6);
          }
          if (settings.length) {
            ly += 10;
            p.font(11, 700);
            p.text("FIGHT SETTINGS", PAD + 20, ly + 12, C.muted);
            ly = kvGrid(PAD + 20, ly + 20, colW - 40, settings, 2);
          }
          return ly;
        };
        const sheetBody = (top) => kvGrid(PAD + colW + GAP + 20, top, colW - 40, sheet, 2);
        // Both cards get the taller body's height.
        const bodyH = p.measure(() => Math.max(loadoutBody(0), sheetBody(0)));
        card(PAD, y, colW, "LOADOUT", "", (top) => Math.max(loadoutBody(top), top + bodyH));
        const h = card(PAD + colW + GAP, y, colW, "CHARACTER SHEET", cs.level ? `Level ${cs.level}` : "", (top) => Math.max(sheetBody(top), top + bodyH));
        y += h + GAP;
      }

      // ---- Ability breakdown ----
      {
        const rows = [...(res.breakdown || [])].sort((a, b) => (b.total_damage || 0) - (a.total_damage || 0));
        const x0 = PAD + 20;
        const R = PAD + inner - 20;
        const col = { crit: R, dpc: R - 90, casts: R - 190, shareR: R - 270, shareL: R - 470, dps: R - 500 };
        const h = card(PAD, y, inner, "ABILITY BREAKDOWN", isBatch ? `Full fight · averages over ${fmt0(res.iterations)} fights` : "Full fight", (top) => {
          let ry = top;
          p.font(11, 700);
          p.text("ABILITY", x0 + 30, ry + 12, C.muted);
          p.text("DPS", col.dps, ry + 12, C.muted, "right");
          p.text("DAMAGE SHARE", col.shareL, ry + 12, C.muted);
          p.text(isBatch ? "AVG CASTS" : "CASTS", col.casts, ry + 12, C.muted, "right");
          p.text("DMG / CAST", col.dpc, ry + 12, C.muted, "right");
          p.text("CRIT %", col.crit, ry + 12, C.muted, "right");
          ry += 22;
          if (!rows.length) {
            p.font(13, 400);
            p.text("No ability damage recorded.", x0, ry + 18, C.muted);
            return ry + 28;
          }
          rows.forEach((r, i) => {
            const rh = 30;
            if (i % 2 === 0) p.rect(x0 - 8, ry, R - x0 + 16, rh, C.input, 4);
            const ic = iconOf(shareBreakdownIcon(snap, r.name));
            if (ic) p.img(ic, x0, ry + 4, 22);
            else p.rect(x0, ry + 4, 22, 22, C.border, 4);
            p.font(13, 700);
            p.text(p.fit(r.name, col.dps - 70 - (x0 + 30)), x0 + 30, ry + 20, C.text);
            p.text(fmt1(r.dps), col.dps, ry + 20, C.accent, "right");
            const share = Math.max(0, Math.min(100, Number(r.share_pct || 0)));
            const barW = col.shareR - col.shareL - 56;
            p.rect(col.shareL, ry + 11, barW, 8, C.border, 4);
            if (share > 0) p.rect(col.shareL, ry + 11, Math.max(3, barW * share / 100), 8, C.accent, 4);
            p.font(13, 600);
            p.text(`${share.toFixed(1)}%`, col.shareR, ry + 20, C.text, "right");
            p.font(13, 400);
            p.text(r.casts == null ? "—" : Number(r.casts).toLocaleString(), col.casts, ry + 20, C.text, "right");
            p.text(r.dmg_per_cast == null ? "—" : fmt0(r.dmg_per_cast), col.dpc, ry + 20, C.text, "right");
            p.font(13, 600);
            p.text(`${Number(r.crit_pct || 0).toFixed(1)}%`, col.crit, ry + 20, C.amber, "right");
            ry += rh;
          });
          return ry;
        });
        y += h + GAP;
      }
    }

    // ---- Rotation ----
    if (opts.rotation) {
      const style = opts.rotation;
      const x0 = PAD + 20;
      const R = PAD + inner - 20;
      const typeInfo = {
        priority_block: ["Priority", C.accent, C.accentBg],
        optional: ["Optional", C.amber, C.amberBg],
        fixed: ["Fixed", C.cyan, C.cyanBg],
      };
      const label = (ly, text) => {
        p.font(11, 700);
        p.text(text, x0, ly + 12, C.muted);
        return ly + 22;
      };
      const preCombat = (ly) => {
        const pre = snap.pre_combat || [];
        if (!pre.length) return ly;
        ly = label(ly, "PRE-COMBAT");
        let cx = x0;
        let cy = ly;
        pre.forEach((st, i) => {
          let txt;
          let ic = null;
          if (st.ability) {
            const a = shareAbility(snap, st.ability);
            txt = a.name;
            ic = iconOf(a.icon);
          } else if (st.swap_tactical) {
            const tn = (sc.tacticalNames || {})[st.swap_tactical] || String(st.swap_tactical).split(".").pop();
            txt = `Tactical: ${tn}`;
          } else if (st.wait != null) {
            txt = `Wait ${st.wait}s`;
          } else {
            txt = JSON.stringify(st);
          }
          p.font(13, 600);
          const cw = Math.min(R - x0, p.w(txt) + (ic ? 50 : 24));
          const arrowW = i ? 22 : 0;
          if (cx + arrowW + cw > R) { cx = x0; cy += 40; }
          else if (i) { p.font(16, 700); p.text("›", cx + 7, cy + 22, C.muted); cx += arrowW; p.font(13, 600); }
          p.rect(cx, cy, cw, 32, C.input, 6, C.border);
          if (ic) p.img(ic, cx + 6, cy + 5, 22);
          p.text(p.fit(txt, cw - (ic ? 44 : 20)), cx + (ic ? 36 : 12), cy + 21, C.text);
          cx += cw;
        });
        return cy + 32 + 18;
      };

      // Full view: one line per ability (icon, name, off-GCD tag, rules wrapped on the right).
      const entryLine = (ex, ly, entry) => {
        const a = shareAbility(snap, entry.ability_id);
        const ic = iconOf(a.icon);
        if (ic) p.img(ic, ex, ly + 2, 24);
        else p.rect(ex, ly + 2, 24, 24, C.border, 4);
        p.font(14, 700);
        const nameX = ex + 34;
        const nameW = 250;
        const nm = p.fit(a.name, nameW);
        p.text(nm, nameX, ly + 19, C.text);
        if (a.offGcd) {
          const tx = nameX + p.w(nm) + 8;
          p.font(10, 700);
          const tw = p.w("OFF-GCD") + 10;
          p.rect(tx, ly + 6, tw, 16, C.cyanBg, 4);
          p.text("OFF-GCD", tx + 5, ly + 18, C.cyan);
        }
        const rules = shareEntryRules(entry);
        p.font(13, 400);
        const rx = nameX + nameW + 80;
        const lines = rules.length ? p.wrap(rules.join("  ·  "), R - rx) : [];
        lines.forEach((ln, i) => p.text(ln, rx, ly + 19 + i * 18, C.muted));
        return ly + Math.max(30, lines.length * 18 + 12);
      };
      // Full view step: number badge + type on the left, its abilities on the right.
      const stepBlock = (ly, step, num) => {
        const [tLabel, tColor, tBg] = typeInfo[step.type] || [String(step.type || "Step"), C.muted, C.input];
        const entries = step.type === "priority_block" ? (step.pool || []) : [step];
        p.rect(x0, ly + 3, 38, 22, tBg, 5);
        p.font(12, 700);
        p.text(String(num), x0 + 19, ly + 19, tColor, "center");
        p.font(11, 700);
        p.text(tLabel.toUpperCase(), x0 + 46, ly + 18, tColor);
        let leftY = ly + 36;
        if (step.type === "priority_block" && step.name) {
          p.font(12, 400);
          p.wrap(step.name, 130).forEach((ln) => { p.text(p.fit(ln, 130), x0, leftY, C.muted); leftY += 16; });
        }
        if (step.type === "priority_block") {
          for (const rt of shareEntryRules(step)) {
            p.font(12, 400);
            p.wrap(rt, 130).forEach((ln) => { p.text(ln, x0, leftY, C.muted); leftY += 16; });
          }
        }
        let ey = ly;
        if (!entries.length) {
          p.font(13, 400);
          p.text("Empty block", x0 + 150, ey + 19, C.muted);
          ey += 30;
        }
        entries.forEach((e) => { ey = entryLine(x0 + 150, ey, e); });
        const end = Math.max(ey, leftY - 6) + 8;
        p.rect(x0, end - 1, R - x0, 1, C.border);
        return end + 6;
      };

      // Compact view: each step is a tile of icons in priority order (left = first choice); numbered
      // markers point to the conditions listed under the lanes.
      const compactBody = (ly, opener, loop, weave) => {
        const ICON = 30;
        const IG = 4;
        const TH = 46;
        const notes = [];
        const noteIds = {};
        // The same ability + conditions shares one number wherever it appears.
        const noteFor = (who, rules) => {
          if (!rules.length) return 0;
          const text = rules.join("  ·  ");
          const key = `${who}|${text}`;
          if (!noteIds[key]) {
            notes.push({ n: notes.length + 1, who, text });
            noteIds[key] = notes.length;
          }
          return noteIds[key];
        };
        const bubble = (n, bx, by) => {
          p.font(10, 700);
          const t = String(n);
          const w = Math.max(15, p.w(t) + 8);
          p.rect(bx - w / 2, by - 8, w, 16, C.accent, 8);
          p.text(t, bx, by + 4, "#ffffff", "center");
        };
        const keyLine = (ky) => {
          let kx = x0;
          const swatch = ([, color, fill], txt, dash = null) => {
            p.rect(kx, ky + 3, 14, 14, fill, 3, color, dash);
            p.font(12, 400);
            p.text(txt, kx + 20, ky + 15, C.muted);
            kx += 20 + p.w(txt) + 18;
          };
          swatch(typeInfo.fixed, "Fixed");
          swatch(typeInfo.priority_block, "Priority (left = first choice)");
          swatch(typeInfo.optional, "Optional", [3, 2]);
          p.rect(kx, ky + 12, 16, 3, C.cyan, 1);
          p.font(12, 400);
          p.text("off-GCD", kx + 22, ky + 15, C.muted);
          kx += 22 + p.w("off-GCD") + 18;
          bubble(1, kx + 8, ky + 10);
          p.font(12, 400);
          p.text("condition (listed below)", kx + 22, ky + 15, C.muted);
          return ky + 30;
        };
        const lane = (ly2, tiles) => {
          let cx = x0;
          let cy = ly2;
          tiles.forEach((t, i) => {
            const [, tColor, tBg] = typeInfo[t.type] || ["", C.muted, C.input];
            p.font(12, 700);
            const bw = Math.max(26, p.w(t.badge) + 12);
            const n = Math.max(1, t.entries.length);
            const tw = 8 + bw + 8 + n * (ICON + IG) - IG + 10;
            const sep = i ? 18 : 0;
            if (i && cx + sep + tw > R) { cx = x0; cy += TH + 14; }
            else if (i) { p.font(16, 700); p.text("›", cx + 5, cy + TH / 2 + 6, C.muted); cx += sep; }
            // Optional steps get a dashed outline, as in the Rotation Map.
            p.rect(cx, cy, tw, TH, tBg, 8, tColor, t.type === "optional" ? [5, 4] : null);
            p.rect(cx + 8, cy + (TH - 22) / 2, bw, 22, C.card, 5);
            p.font(12, 700);
            p.text(t.badge, cx + 8 + bw / 2, cy + TH / 2 + 4, tColor, "center");
            const stepNote = noteFor(t.who, t.stepRules || []);
            if (stepNote) bubble(stepNote, cx + 8 + bw, cy + 9);
            let ix = cx + 8 + bw + 8;
            const iy = cy + (TH - ICON) / 2 - 1;
            if (!t.entries.length) {
              p.font(11, 400);
              p.text("empty", ix, cy + TH / 2 + 4, C.muted);
            }
            t.entries.forEach((e) => {
              const a = shareAbility(snap, e.ability_id);
              const im = iconOf(a.icon);
              if (im) p.img(im, ix, iy, ICON);
              else {
                p.rect(ix, iy, ICON, ICON, C.border, 4);
                p.font(10, 700);
                p.text(a.name.slice(0, 2), ix + ICON / 2, iy + ICON / 2 + 4, C.text, "center");
              }
              if (a.offGcd) p.rect(ix, iy + ICON + 2, ICON, 3, C.cyan, 1);
              const nn = noteFor(a.name, shareEntryRules(e));
              if (nn) bubble(nn, ix + ICON - 3, iy + 2);
              ix += ICON + IG;
            });
            cx += tw;
          });
          return cy + TH + 18;
        };
        let num = 1;
        const tilesOf = (steps) => steps.filter((s) => s && s.type !== "loop_anchor").map((s) => {
          const n = num++;
          const isPool = s.type === "priority_block";
          return {
            badge: String(n),
            type: s.type,
            entries: isPool ? (s.pool || []) : [s],
            stepRules: isPool ? shareEntryRules(s) : [],
            who: `Step ${n}${isPool && s.name ? ` (${s.name})` : ""}`,
          };
        });
        const openerTiles = tilesOf(opener);
        const loopTiles = tilesOf(loop);
        ly = keyLine(ly);
        if (openerTiles.length) {
          ly = label(ly, "OPENER");
          ly = lane(ly, openerTiles);
        }
        ly = label(ly, openerTiles.length ? "LOOP (repeats from here)" : "LOOP");
        if (loopTiles.length) ly = lane(ly, loopTiles);
        else {
          p.font(13, 400);
          p.text("No loop steps.", x0, ly + 18, C.muted);
          ly += 30;
        }
        if (weave.length) {
          ly = label(ly, "WEAVE");
          ly = lane(ly, [{ badge: "W", type: "weave", entries: weave, who: "Weave" }]);
        }
        if (notes.length) {
          ly = label(ly, "CONDITIONS");
          // Two columns, filled row by row.
          const colW = (R - x0 - 32) / 2;
          const note = (nt, nx, ny) => {
            bubble(nt.n, nx + 9, ny + 10);
            p.font(13, 700);
            const who = p.fit(`${nt.who}:`, colW - 26 - 80);
            p.text(who, nx + 26, ny + 15, C.text);
            const wx = nx + 26 + p.w(who) + 8;
            p.font(13, 400);
            const lines = p.wrap(nt.text, nx + colW - wx);
            lines.forEach((ln, i) => p.text(p.fit(ln, nx + colW - wx), wx, ny + 15 + i * 18, C.muted));
            return Math.max(24, lines.length * 18 + 6);
          };
          for (let i = 0; i < notes.length; i += 2) {
            const h1 = note(notes[i], x0, ly);
            const h2 = notes[i + 1] ? note(notes[i + 1], x0 + colW + 32, ly) : 0;
            ly += Math.max(h1, h2);
          }
        }
        return ly;
      };

      const h = card(PAD, y, inner, "ROTATION", res._rotationLabel || "", (top) => {
        let ly = top;
        if (!snap) {
          p.font(13, 400);
          p.text("Rotation details are not in this result (re-run the simulation to include them).", x0, ly + 18, C.muted);
          return ly + 28;
        }
        ly = preCombat(ly);
        const seq = snap.sequence || [];
        const anchor = seq.findIndex((s) => s && s.type === "loop_anchor");
        const opener = anchor >= 0 ? seq.slice(0, anchor) : [];
        const loop = anchor >= 0 ? seq.slice(anchor + 1) : seq;
        const weave = snap.weave || [];
        if (style === "compact") return compactBody(ly, opener, loop, weave);
        let num = 1;
        if (opener.length) {
          ly = label(ly, "OPENER");
          opener.forEach((st) => { ly = stepBlock(ly, st, num++); });
          ly += 12;
        }
        ly = label(ly, opener.length ? "LOOP (repeats from here)" : "LOOP");
        if (!loop.length) {
          p.font(13, 400);
          p.text("No loop steps.", x0, ly + 18, C.muted);
          ly += 30;
        }
        loop.forEach((st) => { if (st && st.type !== "loop_anchor") ly = stepBlock(ly, st, num++); });
        if (weave.length) {
          ly += 12;
          ly = label(ly, "WEAVE");
          weave.forEach((e) => { ly = entryLine(x0, ly, e); });
        }
        return ly;
      });
      y += h + GAP;
    }

    // ---- Footer ----
    p.font(12, 400);
    p.text("SwtorSim is in beta, think critically", PAD, y + 8, C.muted);
    const seedTxt = res.seed != null ? ` · seed ${res.seed}` : "";
    p.text(`${String(res.environment || "live").toUpperCase()} data${seedTxt}`, PAD + inner, y + 8, C.muted, "right");
    return y + PAD;
  }

  function renderShareCanvas(res, icons, C, opts) {
    const measureCtx = document.createElement("canvas").getContext("2d");
    const H = Math.ceil(paintShareCard(makeSharePainter(measureCtx, true), res, icons, C, opts));
    // Browsers cap a canvas side near 32k px: drop to 1x for very long images.
    const scale = H * 2 <= 32000 ? 2 : 1;
    const canvas = document.createElement("canvas");
    canvas.width = SHARE_W * scale;
    canvas.height = H * scale;
    const ctx = canvas.getContext("2d");
    ctx.scale(scale, scale);
    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, SHARE_W, H);
    paintShareCard(makeSharePainter(ctx, false), res, icons, C, opts);
    return canvas;
  }

  // Dialog choices (kept per browser, shared by both pages): rotation "card" | "separate" | "off"
  // (simulator only), style "full" | "compact".
  const SHARE_OPTS_KEY = "swtorsim_share_image_opts";
  const SHARE_OPTS_DEFAULT = { rotation: "card", style: "full" };

  function loadShareOpts() {
    try {
      const saved = JSON.parse(localStorage.getItem(SHARE_OPTS_KEY) || "{}") || {};
      return { ...SHARE_OPTS_DEFAULT, ...saved };
    } catch (e) {
      return { ...SHARE_OPTS_DEFAULT };
    }
  }

  function saveShareOpts(o) {
    try { localStorage.setItem(SHARE_OPTS_KEY, JSON.stringify({ ...loadShareOpts(), ...o })); } catch (e) {}
  }

  // placement=false (Rotation Builder): the rotation image only.
  function buildShareImages(res, icons, C, o, placement) {
    if (!placement) {
      return [{
        title: "Rotation",
        canvas: renderShareCanvas(res, icons, C, { kind: "rotation", rotation: o.style }),
        filename: shareImageFilename(res, "rotation"),
      }];
    }
    const images = [{
      title: "Summary",
      canvas: renderShareCanvas(res, icons, C, {
        kind: "summary",
        rotation: o.rotation === "card" ? o.style : null,
      }),
      filename: shareImageFilename(res),
    }];
    if (o.rotation === "separate") {
      images.push({
        title: "Rotation",
        canvas: renderShareCanvas(res, icons, C, { kind: "rotation", rotation: o.style }),
        filename: shareImageFilename(res, "rotation"),
      });
    }
    return images;
  }

  let SHARE_RENDERING = false;

  // options.placement: show the simulator's rotation placement choice (summary card + rotation);
  // without it only the rotation image is made. options.button shows "Rendering..." while icons load.
  async function openShareDialog(res, options = {}) {
    if (!res || SHARE_RENDERING) return;
    SHARE_RENDERING = true;
    const btn = options.button || null;
    const label = btn ? btn.textContent : "";
    if (btn) btn.textContent = "Rendering...";
    try {
      const C = shareColors();
      const icons = {};
      await Promise.all(shareIconNames(res).map(async (n) => { icons[n] = await shareLoadIcon(n); }));
      showShareModal(res, icons, C, Boolean(options.placement));
    } catch (err) {
      console.error(err);
      alert("Could not build the share image:\n" + err.message);
    } finally {
      SHARE_RENDERING = false;
      if (btn) btn.textContent = label;
    }
  }

  function shareCanvasBlob(canvas) {
    return new Promise((resolve, reject) => {
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("PNG encoding failed"))), "image/png");
    });
  }

  function shareImageFilename(res, suffix = "") {
    const slug = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    const tail = suffix ? `_${suffix}` : `_${Math.round(res.dps || 0)}dps`;
    return `swtorsim_${slug(res.class_name)}_${slug(res.spec)}${tail}.png`;
  }

  function closeShareModal() {
    const el = document.getElementById("shareImageOverlay");
    if (el) el.remove();
    document.removeEventListener("keydown", shareEscHandler);
  }

  function shareEscHandler(ev) {
    if (ev.key === "Escape") closeShareModal();
  }

  function showShareModal(res, icons, C, placement) {
    closeShareModal();
    const placementHtml = placement ? `
          <label style="display:flex;align-items:center;gap:6px;">Rotation
            <select id="shareOptRotation">
              <option value="card">On the card</option>
              <option value="separate">Separate image</option>
              <option value="off">Off</option>
            </select>
          </label>` : "";
    const overlay = document.createElement("div");
    overlay.id = "shareImageOverlay";
    overlay.style.cssText = "position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;padding:24px;";
    overlay.innerHTML = `
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;width:min(1260px,96vw);max-height:94vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,0.4);">
        <div style="display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--border-subtle);flex-wrap:wrap;">
          <b style="flex:1;font-size:14px;">${placement ? "Share Image" : "Rotation Image"}</b>
          <span id="shareImageStatus" style="font-size:12px;color:var(--text-muted);"></span>
          <button type="button" class="btn btn-sm" id="shareCloseBtn">Close</button>
        </div>
        <div style="display:flex;align-items:center;gap:18px;padding:8px 14px;border-bottom:1px solid var(--border-subtle);flex-wrap:wrap;font-size:12px;">${placementHtml}
          <label style="display:flex;align-items:center;gap:6px;">Rotation style
            <select id="shareOptStyle">
              <option value="full">Full (a line per ability, rules inline)</option>
              <option value="compact">Compact (icon tiles, rules listed below)</option>
            </select>
          </label>
        </div>
        <div id="shareImagePreview" style="overflow:auto;padding:14px;background:var(--bg-input);"></div>
      </div>`;
    document.body.appendChild(overlay);
    const $ = (sel) => overlay.querySelector(sel);
    const status = (msg) => { $("#shareImageStatus").textContent = msg; };
    const o = loadShareOpts();
    if (placement) $("#shareOptRotation").value = o.rotation;
    $("#shareOptStyle").value = o.style;
    let images = [];

    const redraw = () => {
      const opts = { style: $("#shareOptStyle").value };
      if (placement) opts.rotation = $("#shareOptRotation").value;
      saveShareOpts(opts);
      $("#shareOptStyle").disabled = placement && opts.rotation === "off";
      images = buildShareImages(res, icons, C, { ...o, ...opts }, placement);
      const preview = $("#shareImagePreview");
      preview.innerHTML = "";
      images.forEach((img, i) => {
        const block = document.createElement("div");
        block.style.cssText = `max-width:${SHARE_W}px;margin:0 auto ${i < images.length - 1 ? 22 : 0}px;`;
        block.innerHTML = `
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
            <b style="font-size:13px;">${images.length > 1 ? `${i + 1}. ` : ""}${img.title}</b>
            <span style="flex:1;font-size:11px;color:var(--text-muted);">${img.canvas.width} × ${img.canvas.height} px</span>
            <button type="button" class="btn btn-sm" data-copy="${i}">Copy Image</button>
            <button type="button" class="btn btn-sm" data-download="${i}">Download PNG</button>
          </div>`;
        img.canvas.style.cssText = `width:${SHARE_W}px;max-width:100%;height:auto;display:block;border-radius:6px;`;
        block.appendChild(img.canvas);
        preview.appendChild(block);
      });
      status("");
    };

    if (placement) $("#shareOptRotation").onchange = redraw;
    $("#shareOptStyle").onchange = redraw;
    $("#shareCloseBtn").onclick = closeShareModal;
    overlay.addEventListener("click", async (e) => {
      if (e.target === overlay) { closeShareModal(); return; }
      const btn = e.target.closest("button[data-copy], button[data-download]");
      if (!btn) return;
      const img = images[Number(btn.dataset.copy ?? btn.dataset.download)];
      if (!img) return;
      if (btn.dataset.copy != null) {
        try {
          if (!navigator.clipboard || !navigator.clipboard.write || typeof ClipboardItem === "undefined") {
            throw new Error("Clipboard image write unavailable");
          }
          await navigator.clipboard.write([new ClipboardItem({ "image/png": shareCanvasBlob(img.canvas) })]);
          status(`[OK] ${img.title} copied to clipboard`);
        } catch (err) {
          console.warn(err);
          status("[WARN] The browser blocked copying the image; use Download PNG.");
        }
        return;
      }
      try {
        const blob = await shareCanvasBlob(img.canvas);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = img.filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
        status(`[OK] ${img.title} downloaded`);
      } catch (err) {
        status(err.message || "Download failed");
      }
    });
    document.addEventListener("keydown", shareEscHandler);
    redraw();
  }

  global.ShareImage = { open: openShareDialog, paintShareCard, renderShareCanvas, shareRuleText };
})(window);

// Guided rule (condition) form shared by the Rotation Builder's rule modal and the Rotation Map's
// rule popover. Served as rule_form.js by data/rotation_builder.py and copied to dist/ by
// tools/build_web_release.py. One form at a time per page: the fields use fixed element ids.
(function (global) {
  "use strict";

  function escapeHtml(str) {
    return String(str ?? "").replace(/[&<>]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[m]));
  }

  function escapeAttr(str) {
    return String(str ?? "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
  }

  // The five operators compare_values accepts. Same labels the stack rule already used.
  const COMPARISON_OPTIONS = [
    ["gte", "&ge; (At least)", ["gte", ">="]],
    ["eq", "== (Exactly)", ["eq", "==", "="]],
    ["lte", "&le; (At most)", ["lte", "<="]],
    ["gt", "&gt; (Greater than)", ["gt", ">"]],
    ["lt", "&lt; (Less than)", ["lt", "<"]]
  ];

  function comparisonSelect(id, curOp) {
    const current = String(curOp ?? "");
    const opts = COMPARISON_OPTIONS.map(([value, label, aliases]) => {
      const selected = aliases.indexOf(current) !== -1 ? "selected" : "";
      return `<option value="${value}" ${selected}>${label}</option>`;
    }).join("");
    return `<select id="${id}" style="width:100%;">${opts}</select>`;
  }

  // Old keys keep their historical operator when a pill is opened, then Save writes the new key.
  const LEGACY_RULES = {
    target_hp_below_pct: { key: "target_hp_pct", comparison: "lte", kind: "hp" },
    target_hp_above_pct: { key: "target_hp_pct", comparison: "gt", kind: "hp" },
    caster_energy_below: { key: "caster_energy", comparison: "lt", kind: "energy" },
    caster_energy_above: { key: "caster_energy", comparison: "gte", kind: "energy" },
    proc_cooldown_above: { key: "proc_cooldown", comparison: "gt", kind: "named" },
    ability_cooldown_under: { key: "ability_cooldown", comparison: "lt", kind: "named" },
    ability_cooldown_above: { key: "ability_cooldown", comparison: "gt", kind: "named" }
  };

  function prepare(key, value) {
    const legacy = LEGACY_RULES[key];
    if (!legacy) return { key: key, value: value };
    if (legacy.kind === "hp") {
      if (value && typeof value === "object" && !Array.isArray(value)) {
        return { key: legacy.key, value: Object.assign({}, value, { comparison: legacy.comparison }) };
      }
      return { key: legacy.key, value: { pct: value, comparison: legacy.comparison } };
    }
    if (legacy.kind === "energy") {
      const amount = (value && typeof value === "object") ? (value.value ?? value.threshold ?? 0) : value;
      return { key: legacy.key, value: { value: amount, comparison: legacy.comparison } };
    }
    const named = (value && typeof value === "object") ? value : {};
    return {
      key: legacy.key,
      value: { name: named.name || "", value: named.value, comparison: legacy.comparison }
    };
  }

  // Pick lists for the form, built from the builder's loadout catalog.
  function listsFromLoadout(loadout) {
    const lo = loadout || {};
    return {
      buffItems: (lo.caster_buffs || []).map(b => ({
        name: b.name,
        label: `${b.name} (${b.source_name}${b.max_stacks > 1 ? `, max ${b.max_stacks} stacks` : ""})`
      })),
      debuffItems: (lo.target_debuffs || []).map(d => ({
        name: d.name,
        label: `${d.name} (${d.source_name}${d.is_dot ? ", DoT" : ""})`
      })),
      procItems: (lo.procs || []).map(p => ({
        name: p.name,
        label: `${p.name} (${p.icd}s ICD)`
      })),
      abilityItems: (lo.abilities || []).map(a => ({
        name: a.name,
        label: `${a.name} (CD: ${a.cooldown}s)`
      }))
    };
  }

  function buildDatalistOrSelect(id, items, currentVal, placeholder) {
    const listId = `${id}_datalist`;
    const opts = items.map(it => `<option value="${escapeAttr(it.name)}">${escapeHtml(it.label || it.name)}</option>`).join("");
    const dlOpts = items.map(it => `<option value="${escapeAttr(it.name)}"></option>`).join("");
    return `
    <div style="display:flex;gap:6px;">
      <select onchange="document.getElementById('${id}').value = this.value" style="flex:1;">
        <option value="">-- Pick Discovered ${escapeHtml(placeholder)} --</option>
        ${opts}
      </select>
      <input type="text" id="${id}" list="${listId}" value="${escapeAttr(currentVal || "")}" placeholder="Or type exact name..." style="flex:1;">
      <datalist id="${listId}">${dlOpts}</datalist>
    </div>
  `;
  }

  // HTML of the value fields for one condition key; null when the key has no guided form.
  function fieldsHtml(key, existingVal, lists) {
    const prepared = prepare(key, existingVal);
    key = prepared.key;
    existingVal = prepared.value;
    const buffItems = (lists && lists.buffItems) || [];
    const debuffItems = (lists && lists.debuffItems) || [];
    const procItems = (lists && lists.procItems) || [];
    const abilityItems = (lists && lists.abilityItems) || [];

    if (key === "caster_has_buff" || key === "caster_does_not_have_buff") {
      const cur = typeof existingVal === "string" ? existingVal : (buffItems[0]?.name || "");
      return `
      <div class="form-group">
        <label>Caster Buff Name</label>
        ${buildDatalistOrSelect("ruleBuffInput", buffItems, cur, "Caster Buff")}
      </div>
    `;
    }

    if (key === "target_has_debuff" || key === "target_doesnt_have_debuff") {
      const cur = typeof existingVal === "string" ? existingVal : (debuffItems[0]?.name || "");
      return `
      <div class="form-group">
        <label>Target Debuff / DoT Name</label>
        ${buildDatalistOrSelect("ruleDebuffInput", debuffItems, cur, "Target Debuff")}
      </div>
    `;
    }

    if (key === "caster_buff_stacks" || key === "target_debuff_stacks") {
      const isTarget = key === "target_debuff_stacks";
      const items = isTarget ? debuffItems : buffItems;
      let curName = items[0]?.name || "";
      let curStacks = 3;
      let curOp = "gte";
      if (Array.isArray(existingVal)) {
        curName = existingVal[0] || curName;
        curStacks = existingVal[1] ?? 3;
        curOp = existingVal[2] || "gte";
      } else if (existingVal && typeof existingVal === "object") {
        curName = existingVal.name || existingVal.buff || existingVal.debuff || curName;
        curStacks = existingVal.stacks ?? existingVal.count ?? existingVal.value ?? 3;
        curOp = existingVal.comparison || existingVal.operator || "gte";
      }
      return `
      <div class="form-group">
        <label>${isTarget ? "Target Debuff / DoT Name" : "Caster Buff Name"}</label>
        ${buildDatalistOrSelect("ruleStackBuffInput", items, curName, isTarget ? "Debuff" : "Buff")}
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Comparison Operator</label>
          ${comparisonSelect("ruleStackOpInput", curOp)}
        </div>
        <div class="form-group">
          <label>Required Stacks</label>
          <input type="number" id="ruleStackCountInput" min="1" max="99" step="1" value="${escapeAttr(curStacks)}" style="width:100%;">
        </div>
      </div>
    `;
    }

    if (key === "caster_buff_remaining" || key === "target_debuff_remaining") {
      const isTarget = key === "target_debuff_remaining";
      const items = isTarget ? debuffItems : buffItems;
      const curName = (existingVal && existingVal.name) ? existingVal.name : (items[0]?.name || "");
      const curVal = (existingVal && existingVal.value !== undefined) ? existingVal.value : 3;
      const curOp = (existingVal && (existingVal.comparison || existingVal.operator)) || "lt";
      return `
      <div class="form-group">
        <label>${isTarget ? "Target Debuff / DoT Name" : "Caster Buff Name"}</label>
        ${buildDatalistOrSelect("ruleRemainNameInput", items, curName, isTarget ? "Debuff" : "Buff")}
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Comparison Operator</label>
          ${comparisonSelect("ruleRemainOpInput", curOp)}
        </div>
        <div class="form-group">
          <label>Time Left (seconds)</label>
          <input type="number" id="ruleRemainSecInput" min="0" max="600" step="0.1" value="${escapeAttr(curVal)}" style="width:100%;">
        </div>
      </div>
    `;
    }

    if (key === "target_hp_pct") {
      let curDec = 0.4;
      let curBypass = "";
      let curOp = "lte";
      if (typeof existingVal === "number") {
        curDec = existingVal;
      } else if (existingVal && typeof existingVal === "object") {
        curDec = existingVal.pct ?? 0.4;
        curBypass = existingVal.bypass_if_buff_active || "";
        curOp = existingVal.comparison || existingVal.operator || "lte";
      }
      return `
      <div class="form-row">
        <div class="form-group">
          <label>Comparison Operator</label>
          ${comparisonSelect("ruleHpOpInput", curOp)}
        </div>
        <div class="form-group">
          <label>Decimal Fraction (0.0 - 1.0)</label>
          <input type="number" id="ruleHpDecInput" min="0.01" max="1.0" step="0.05" value="${escapeAttr(curDec)}" style="width:100%;" oninput="document.getElementById('ruleHpPctPreview').textContent = Math.round(this.value * 100) + '%'">
        </div>
        <div class="form-group">
          <label>Target Health %</label>
          <div id="ruleHpPctPreview" style="padding:6px 10px;font-weight:700;color:var(--accent);font-size:14px;">${Math.round(curDec * 100)}%</div>
        </div>
      </div>
      <div class="form-group">
        <label>Optional: Bypass HP Check if Caster Buff Active</label>
        ${buildDatalistOrSelect("ruleHpBypassInput", buffItems, curBypass, "Bypass Buff")}
      </div>
    `;
    }

    if (key === "caster_energy") {
      let cur = 35;
      let curOp = "gte";
      if (typeof existingVal === "number") {
        cur = existingVal;
      } else if (existingVal && typeof existingVal === "object") {
        cur = existingVal.value ?? existingVal.threshold ?? 35;
        curOp = existingVal.comparison || existingVal.operator || "gte";
      }
      return `
      <div class="form-row">
        <div class="form-group">
          <label>Comparison Operator</label>
          ${comparisonSelect("ruleEnergyOpInput", curOp)}
        </div>
        <div class="form-group">
          <label>Resource Threshold (Force / Energy / Heat)</label>
          <input type="number" id="ruleResourceInput" min="0" max="600" step="5" value="${escapeAttr(cur)}" style="width:100%;">
        </div>
      </div>
    `;
    }

    if (key === "proc_cooldown") {
      const curName = (existingVal && existingVal.name) ? existingVal.name : (procItems[0]?.name || "Bloodletting");
      const curVal = (existingVal && existingVal.value !== undefined) ? existingVal.value : 1.5;
      const curOp = (existingVal && (existingVal.comparison || existingVal.operator)) || "gt";
      return `
      <div class="form-group">
        <label>Proc / Lockout Name</label>
        ${buildDatalistOrSelect("ruleProcNameInput", procItems, curName, "Proc")}
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Comparison Operator</label>
          ${comparisonSelect("ruleProcOpInput", curOp)}
        </div>
        <div class="form-group">
          <label>Remaining Lockout / ICD (seconds)</label>
          <input type="number" id="ruleProcSecInput" min="0" max="120" step="0.1" value="${escapeAttr(curVal)}" style="width:100%;">
        </div>
      </div>
    `;
    }

    if (key === "ability_cooldown") {
      const curName = (existingVal && existingVal.name) ? existingVal.name : (abilityItems[0]?.name || "");
      const curVal = (existingVal && existingVal.value !== undefined) ? existingVal.value : 1.5;
      const curOp = (existingVal && (existingVal.comparison || existingVal.operator)) || "lt";
      return `
      <div class="form-group">
        <label>Ability Name</label>
        ${buildDatalistOrSelect("ruleAblCdNameInput", abilityItems, curName, "Ability")}
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Comparison Operator</label>
          ${comparisonSelect("ruleAblCdOpInput", curOp)}
        </div>
        <div class="form-group">
          <label>Remaining Cooldown (seconds)</label>
          <input type="number" id="ruleAblCdSecInput" min="0" max="180" step="0.1" value="${escapeAttr(curVal)}" style="width:100%;">
        </div>
      </div>
    `;
    }

    return null;
  }

  // A non-negative number from an input; the fallback is only for blank / invalid text (0 is a valid value).
  function readNonNegative(inputEl, fallback) {
    const n = parseFloat(inputEl.value);
    return Number.isFinite(n) && n >= 0 ? n : fallback;
  }

  // Read the form back into a rule value: { value } on success, { error } when a field is missing.
  function readValue(key) {
    const prepared = prepare(key, null);
    key = prepared.key;
    const el = (id) => document.getElementById(id);
    let value = null;

    if (key === "caster_has_buff" || key === "caster_does_not_have_buff") {
      value = el("ruleBuffInput").value.trim();
      if (!value) return { error: "Please select or enter a buff name." };
    } else if (key === "target_has_debuff" || key === "target_doesnt_have_debuff") {
      value = el("ruleDebuffInput").value.trim();
      if (!value) return { error: "Please select or enter a debuff name." };
    } else if (key === "caster_buff_stacks" || key === "target_debuff_stacks") {
      const name = el("ruleStackBuffInput").value.trim();
      const op = el("ruleStackOpInput").value;
      const count = parseInt(el("ruleStackCountInput").value, 10) || 1;
      if (!name) return { error: "Please select or enter an effect name." };
      value = op === "gte" ? [name, count] : [name, count, op];
    } else if (key === "caster_buff_remaining" || key === "target_debuff_remaining") {
      const name = el("ruleRemainNameInput").value.trim();
      const sec = readNonNegative(el("ruleRemainSecInput"), 3);
      if (!name) return { error: "Please select or enter an effect name." };
      value = { name: name, value: sec, comparison: el("ruleRemainOpInput").value };
    } else if (key === "target_hp_pct") {
      let dec = parseFloat(el("ruleHpDecInput").value);
      if (isNaN(dec) || dec <= 0) dec = 0.4;
      if (dec > 1.0) dec = Number((dec / 100.0).toFixed(4));
      const bypassEl = el("ruleHpBypassInput");
      const bypass = bypassEl ? bypassEl.value.trim() : "";
      value = { pct: dec, comparison: el("ruleHpOpInput").value };
      if (bypass) value.bypass_if_buff_active = bypass;
    } else if (key === "caster_energy") {
      value = {
        value: parseFloat(el("ruleResourceInput").value) || 0,
        comparison: el("ruleEnergyOpInput").value
      };
    } else if (key === "proc_cooldown") {
      const name = el("ruleProcNameInput").value.trim();
      const sec = readNonNegative(el("ruleProcSecInput"), 0.5);
      if (!name) return { error: "Please select or enter a proc name." };
      value = { name: name, value: sec, comparison: el("ruleProcOpInput").value };
    } else if (key === "ability_cooldown") {
      const name = el("ruleAblCdNameInput").value.trim();
      const sec = readNonNegative(el("ruleAblCdSecInput"), 1.5);
      if (!name) return { error: "Please select or enter an ability name." };
      value = { name: name, value: sec, comparison: el("ruleAblCdOpInput").value };
    }

    return { value: value, key: key };
  }

  global.RuleForm = { listsFromLoadout, fieldsHtml, readValue, prepare };
})(window);

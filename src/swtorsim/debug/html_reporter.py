"""Generates a rich, interactive, standalone HTML combat replay and diagnostic report."""

import json
from pathlib import Path
from typing import Any, Dict


def generate_debug_html(trace_data: Dict[str, Any], output_path: str | Path) -> str:
    """Renders the collected trace telemetry into a self-contained interactive HTML file."""
    output_file = Path(output_path).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Serialize trace data safely for JS embedding
    raw_json = json.dumps(trace_data, indent=None, ensure_ascii=False)
    # Prevent closing script tags in JSON strings
    safe_json = raw_json.replace("</script>", "<\\/script>")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SwtorSim Debugger & Combat Replay</title>
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #151d2e;
      --card-hover: #1b263b;
      --card-border: #24324a;
      --border-subtle: #1c273c;
      --text-main: #e2e8f0;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.18);
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --purple: #a855f7;
      --indigo: #6366f1;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: var(--bg);
      color: var(--text-main);
      line-height: 1.5;
      font-size: 14px;
      overflow-x: hidden;
    }}
    code, pre, .mono {{
      font-family: ui-monospace, SFMono-Regular, "Cascadia Code", Menlo, Consolas, monospace;
    }}

    /* Header */
    header {{
      background: linear-gradient(180deg, #162032 0%, #101726 100%);
      border-bottom: 1px solid var(--card-border);
      padding: 16px 24px;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      position: sticky;
      top: 0;
      z-index: 100;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .brand h1 {{
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: #fff;
    }}
    .brand .badge {{
      background: var(--accent-glow);
      color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.35);
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .meta-pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .pill {{
      background: var(--card-bg);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 4px 10px;
      font-size: 12px;
      display: flex;
      gap: 6px;
    }}
    .pill .label {{ color: var(--text-dim); text-transform: uppercase; font-size: 10px; font-weight: 600; }}
    .pill .val {{ font-weight: 600; color: #fff; }}

    /* KPI Cards Bar */
    .kpi-bar {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 12px;
      padding: 16px 24px 0 24px;
    }}
    .kpi-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}
    .kpi-card .kpi-label {{
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
    }}
    .kpi-card .kpi-val {{
      font-size: 20px;
      font-weight: 700;
      color: #fff;
      font-family: ui-monospace, monospace;
    }}
    .kpi-card.accent .kpi-val {{ color: var(--accent); }}
    .kpi-card.success .kpi-val {{ color: var(--success); }}
    .kpi-card.warning .kpi-val {{ color: var(--warning); }}

    /* Navigation Tabs */
    .nav-tabs {{
      display: flex;
      gap: 4px;
      padding: 16px 24px 0 24px;
      border-bottom: 1px solid var(--card-border);
      overflow-x: auto;
    }}
    .tab-btn {{
      background: transparent;
      border: none;
      color: var(--text-muted);
      padding: 10px 18px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      display: flex;
      align-items: center;
      gap: 8px;
      white-space: nowrap;
      transition: all 0.15s ease;
    }}
    .tab-btn:hover {{
      color: #fff;
    }}
    .tab-btn.active {{
      color: var(--accent);
      border-bottom-color: var(--accent);
      background: rgba(56, 189, 248, 0.05);
      border-radius: 6px 6px 0 0;
    }}
    .tab-btn .tab-count {{
      background: rgba(255, 255, 255, 0.08);
      padding: 1px 6px;
      border-radius: 10px;
      font-size: 11px;
    }}

    /* Main Container */
    main {{
      padding: 20px 24px 40px 24px;
    }}
    .tab-pane {{
      display: none;
    }}
    .tab-pane.active {{
      display: block;
    }}

    /* Controls & Search */
    .filter-bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      margin-bottom: 16px;
    }}
    .search-input {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: #fff;
      padding: 8px 14px;
      border-radius: 6px;
      font-size: 13px;
      min-width: 260px;
      outline: none;
    }}
    .search-input:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--accent-glow);
    }}
    .btn-chip {{
      background: var(--card-bg);
      border: 1px solid var(--border-subtle);
      color: var(--text-muted);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      cursor: pointer;
      font-weight: 500;
      transition: all 0.15s;
    }}
    .btn-chip:hover {{
      color: #fff;
      border-color: var(--card-border);
    }}
    .btn-chip.active {{
      background: var(--accent-glow);
      color: var(--accent);
      border-color: var(--accent);
    }}

    /* Table Styles */
    .table-container {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      overflow: hidden;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
    }}
    th {{
      background: rgba(15, 23, 42, 0.6);
      padding: 10px 14px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      border-bottom: 1px solid var(--card-border);
      white-space: nowrap;
    }}
    td {{
      padding: 10px 14px;
      border-bottom: 1px solid var(--border-subtle);
      font-size: 13px;
      vertical-align: middle;
    }}
    tr:last-child td {{
      border-bottom: none;
    }}
    tr:hover td {{
      background: rgba(255, 255, 255, 0.02);
    }}
    .clickable-row {{
      cursor: pointer;
    }}

    /* Tags & Status Badges */
    .badge-tag {{
      display: inline-block;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.06);
      color: var(--text-muted);
    }}
    .badge-ok {{ background: rgba(16, 185, 129, 0.15); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); }}
    .badge-fail {{ background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); }}
    .badge-warn {{ background: rgba(245, 158, 11, 0.15); color: var(--warning); border: 1px solid rgba(245, 158, 11, 0.3); }}
    .badge-crit {{ background: rgba(168, 85, 247, 0.2); color: var(--purple); font-weight: 700; }}
    .badge-selected {{ background: rgba(16, 185, 129, 0.2); color: var(--success); border: 1px solid var(--success); font-weight: 700; }}

    /* Cards Grid */
    .grid-2 {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }}
    .grid-3 {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 16px;
    }}
    .card-title {{
      font-size: 14px;
      font-weight: 700;
      color: #fff;
      margin-bottom: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    /* Gear Showcase Cards */
    .gear-item-card {{
      background: #0f172a;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .gear-item-card .gear-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .gear-item-card .gear-title {{
      font-size: 14px;
      font-weight: 700;
      color: #fff;
    }}

    /* Skill Tree Tier Layout */
    .tree-tier-row {{
      background: #0f172a;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 12px;
    }}
    .tree-tier-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
    }}
    .tree-options-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 10px;
    }}
    .tree-option-card {{
      background: var(--card-bg);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 4px;
      transition: all 0.15s ease;
    }}
    .tree-option-card.selected {{
      border-color: var(--success);
      background: rgba(16, 185, 129, 0.08);
      box-shadow: 0 0 10px rgba(16, 185, 129, 0.15);
    }}
    .tree-option-card .opt-title {{
      font-weight: 600;
      font-size: 13px;
      color: #fff;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    /* Rotation Sequence Step Cards */
    .rot-step-card {{
      background: #0f172a;
      border-left: 4px solid var(--accent);
      border-radius: 6px;
      padding: 12px 14px;
      margin-bottom: 10px;
    }}
    .rot-step-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }}
    .rot-pool-item {{
      background: var(--card-bg);
      border: 1px solid var(--border-subtle);
      border-radius: 4px;
      padding: 6px 10px;
      margin-top: 4px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
    }}

    /* Timeline Specifics */
    .timeline-wrapper {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 20px;
    }}
    .timeline-toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      gap: 12px;
    }}
    .timeline-scrubber-hud {{
      background: #0f172a;
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 12px;
      display: flex;
      gap: 16px;
    }}
    .timeline-scrubber-hud .hud-item {{
      display: flex;
      gap: 6px;
    }}
    .timeline-canvas-container {{
      width: 100%;
      height: 380px;
      overflow-x: auto;
      overflow-y: hidden;
      position: relative;
      background: #0b0f19;
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      user-select: none;
    }}
    #timelineSvg {{
      width: 100%;
      height: 100%;
      display: block;
    }}

    /* Inspector Drawer / Modal */
    .inspector-pane {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 18px;
      margin-top: 20px;
      display: none;
    }}
    .inspector-pane.open {{
      display: block;
      animation: fadeIn 0.2s ease-in-out;
    }}
    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(6px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}

    /* Math Auditor Breakdown */
    .math-tree {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }}
    .math-block {{
      background: #0f172a;
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 12px;
    }}
    .math-block h4 {{
      font-size: 11px;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 8px;
      letter-spacing: 0.05em;
    }}
    .math-row {{
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      padding: 3px 0;
      border-bottom: 1px dashed rgba(255, 255, 255, 0.05);
    }}
    .math-row:last-child {{
      border-bottom: none;
      font-weight: 700;
      color: #fff;
      padding-top: 6px;
    }}

    /* Rotation Candidates Tree */
    .candidate-card {{
      background: #0f172a;
      border-left: 3px solid var(--text-dim);
      border-radius: 4px;
      padding: 8px 12px;
      margin-bottom: 6px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 13px;
    }}
    .candidate-card.accepted {{
      border-left-color: var(--success);
      background: rgba(16, 185, 129, 0.05);
    }}
    .candidate-card.rejected {{
      border-left-color: var(--danger);
      opacity: 0.85;
    }}
  </style>
</head>
<body>

  <!-- Top Sticky Bar -->
  <header>
    <div class="brand">
      <h1>SwtorSim Combat Replay & Diagnostics</h1>
      <span class="badge" id="envBadge">LIVE</span>
    </div>
    <div class="meta-pills" id="metaPills"></div>
  </header>

  <!-- KPI Overview -->
  <div class="kpi-bar" id="kpiBar"></div>

  <!-- Navigation -->
  <div class="nav-tabs">
    <button class="tab-btn active" onclick="switchTab('timeline')">
      Interactive Timeline
    </button>
    <button class="tab-btn" onclick="switchTab('loadout')">
      Initial Character & Loadout <span class="tab-count" id="passivesCountBadge">0</span>
    </button>
    <button class="tab-btn" onclick="switchTab('tree')">
      Skill Tree & Choices <span class="tab-count" id="treeLevelsCountBadge">8</span>
    </button>
    <button class="tab-btn" onclick="switchTab('rotprofile')">
      Rotation Sequence <span class="tab-count" id="rotStepsCountBadge">0</span>
    </button>
    <button class="tab-btn" onclick="switchTab('rotation')">
      Live Rotation Decisions <span class="tab-count" id="decisionsCountBadge">0</span>
    </button>
    <button class="tab-btn" onclick="switchTab('math')">
      Hit Math Auditor <span class="tab-count" id="hitsCountBadge">0</span>
    </button>
    <button class="tab-btn" onclick="switchTab('events')">
      Event Log <span class="tab-count" id="eventsCountBadge">0</span>
    </button>
  </div>

  <main>
    <!-- Tab 1: Interactive Timeline -->
    <div id="pane-timeline" class="tab-pane active">
      <div class="timeline-wrapper">
        <div class="timeline-toolbar">
          <div class="timeline-scrubber-hud" id="scrubberHud">
            <div class="hud-item"><span class="label">Time:</span> <span class="val mono" id="hudTime">0.00s</span></div>
            <div class="hud-item"><span class="label">Resource:</span> <span class="val mono" id="hudResource">--</span></div>
            <div class="hud-item"><span class="label">Target HP:</span> <span class="val mono" id="hudHp">--</span></div>
            <div class="hud-item"><span class="label">Active Buffs:</span> <span class="val mono" id="hudBuffs">0</span></div>
          </div>
          <div style="display: flex; gap: 8px;">
            <button class="btn-chip" onclick="zoomTimeline(1.2)">Zoom +</button>
            <button class="btn-chip" onclick="zoomTimeline(0.8)">Zoom -</button>
            <button class="btn-chip" onclick="resetTimelineZoom()">Reset</button>
          </div>
        </div>

        <div class="timeline-canvas-container" id="timelineContainer">
          <svg id="timelineSvg"></svg>
        </div>
      </div>

      <!-- Quick Inspection Drawer below Timeline -->
      <div class="inspector-pane" id="quickInspector">
        <div class="card-title">
          <span id="quickInspectorTitle">Event Inspector</span>
          <button class="btn-chip" onclick="closeInspector()">Close</button>
        </div>
        <div id="quickInspectorBody"></div>
      </div>
    </div>

    <!-- Tab 2: Initial Character & Loadout -->
    <div id="pane-loadout" class="tab-pane">
      <!-- Showcase Cards: Tactical, Implants & Relics -->
      <div class="card" style="margin-bottom: 20px;">
        <div class="card-title">Equipped Tactical, Legendary Implants & Relics</div>
        <div class="grid-3" id="gearShowcaseGrid"></div>
      </div>

      <div class="grid-2">
        <!-- Derived Attributes Card (Calculated After Passives & Buffs) -->
        <div class="card">
          <div class="card-title">
            <span>Derived Combat Attributes</span>
            <span class="badge-ok badge-tag">Applied After Passives & Buffs</span>
          </div>
          <table id="derivedStatsTable"></table>
        </div>

        <!-- Target Setup Card -->
        <div class="card">
          <div class="card-title">Target Dummy Setup & Preloaded Raid Debuffs</div>
          <div id="targetDebuffsContainer"></div>
        </div>
      </div>

      <!-- Active Abilities Directory -->
      <div class="card" style="margin-bottom: 20px;">
        <div class="card-title">Active Abilities Roster</div>
        <div class="table-container">
          <table id="activeAbilitiesTable">
            <thead>
              <tr>
                <th>Ability Name</th>
                <th>Origin</th>
                <th>Cooldown</th>
                <th>Energy / Force</th>
                <th>Cast / Channel</th>
                <th>Damage Type</th>
                <th>Tags</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>

      <!-- Passives Directory -->
      <div class="card" style="margin-bottom: 20px;">
        <div class="card-title">
          <span>Loaded Passives, Talents & Gear Blueprints</span>
          <input type="text" class="search-input" id="passiveSearch" placeholder="Filter passives or stat changes..." oninput="filterPassivesTable()">
        </div>
        <div class="table-container">
          <table id="passivesTable">
            <thead>
              <tr>
                <th>Name / FQN</th>
                <th>Origin</th>
                <th>Stat Changes / Modifiers</th>
                <th>Triggers / Effects</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>

      <!-- Procs Registry -->
      <div class="card">
        <div class="card-title">Registered Procs & ICD Timers</div>
        <div class="table-container">
          <table id="procsTable">
            <thead>
              <tr>
                <th>Canonical Name</th>
                <th>Source Ability</th>
                <th>ICD Duration</th>
                <th>Proc Kind</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Tab 3: Skill Tree & Choices -->
    <div id="pane-tree" class="tab-pane">
      <div class="card" style="margin-bottom: 20px;">
        <div class="card-title">
          <span>Discipline Skill Tree & Tier Choices</span>
          <span style="font-size: 12px; color: var(--text-dim); font-weight: normal;">Highlighted card indicates the selected choice tier</span>
        </div>
        <div id="skillTreeContainer"></div>
      </div>
    </div>

    <!-- Tab 4: Rotation Sequence Profile -->
    <div id="pane-rotprofile" class="tab-pane">
      <div class="card">
        <div class="card-title">
          <span>Active Rotation Profile Sequence</span>
          <span id="rotationProfileTitle" style="font-size: 12px; color: var(--accent);"></span>
        </div>
        <div id="rotationSequenceContainer"></div>
      </div>
    </div>

    <!-- Tab 5: Live Rotation Decisions -->
    <div id="pane-rotation" class="tab-pane">
      <div class="filter-bar">
        <input type="text" class="search-input" id="rotationSearch" placeholder="Search ability or step..." oninput="filterRotationList()">
        <button class="btn-chip active" id="chipAllDecisions" onclick="filterDecisionsType('all')">All Steps</button>
        <button class="btn-chip" id="chipStalls" onclick="filterDecisionsType('stalls')">Stalls / Deadlocks</button>
      </div>
      <div id="rotationListContainer"></div>
    </div>

    <!-- Tab 6: Hit Math Auditor -->
    <div id="pane-math" class="tab-pane">
      <div class="filter-bar">
        <input type="text" class="search-input" id="mathSearch" placeholder="Filter hit by ability name..." oninput="filterMathTable()">
        <button class="btn-chip" id="chipMathCrits" onclick="toggleMathCrits()">Critical Hits Only</button>
      </div>
      <div class="table-container">
        <table id="mathHitsTable">
          <thead>
            <tr>
              <th>Time</th>
              <th>Ability</th>
              <th>Damage</th>
              <th>Crit?</th>
              <th>Attack / Damage Type</th>
              <th>Target HP After</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>

      <!-- Math Inspector Card -->
      <div class="inspector-pane" id="mathInspector">
        <div class="card-title">
          <span id="mathInspectorTitle">Hit Math Audit</span>
          <button class="btn-chip" onclick="document.getElementById('mathInspector').classList.remove('open')">Close</button>
        </div>
        <div id="mathInspectorBody"></div>
      </div>
    </div>

    <!-- Tab 7: Chronological Event Log -->
    <div id="pane-events" class="tab-pane">
      <div class="filter-bar">
        <input type="text" class="search-input" id="eventSearch" placeholder="Search event log..." oninput="filterEventsTable()">
        <button class="btn-chip active" onclick="filterEventsType('all')">All</button>
        <button class="btn-chip" onclick="filterEventsType('cast')">Casts</button>
        <button class="btn-chip" onclick="filterEventsType('damage_hit')">Damage Hits</button>
        <button class="btn-chip" onclick="filterEventsType('buff')">Buffs</button>
        <button class="btn-chip" onclick="filterEventsType('resource')">Resource</button>
        <button class="btn-chip" onclick="filterEventsType('rotation_eval')">Rotation</button>
        <button class="btn-chip" onclick="filterEventsType('proc')">Procs</button>
        <button class="btn-chip" onclick="filterEventsType('stall')">Stalls</button>
      </div>
      <div class="table-container">
        <table id="eventsTable">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Event Type</th>
              <th>Details</th>
              <th>Impact / Values</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </main>

  <!-- Embedded Trace Data & Interactive Engine -->
  <script>
    const TRACE = {safe_json};

    let currentTab = 'timeline';
    let timelineZoom = 1.0;
    let selectedEventFilter = 'all';
    let selectedDecisionFilter = 'all';
    let showMathCritsOnly = false;

    // Initialize UI on load
    window.addEventListener('DOMContentLoaded', () => {{
      renderHeaderAndKpis();
      renderGearShowcase();
      renderDerivedStats();
      renderSkillTree();
      renderRotationProfile();
      renderPassivesTable();
      renderActiveAbilitiesTable();
      renderProcsTable();
      renderTargetDebuffs();
      renderRotationDecisions();
      renderMathHitsTable();
      renderEventsTable();
      renderTimeline();
    }});

    function switchTab(tabId) {{
      currentTab = tabId;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      const activeBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick').includes(`'${{tabId}}'`));
      if (activeBtn) activeBtn.classList.add('active');
      const pane = document.getElementById(`pane-${{tabId}}`);
      if (pane) pane.classList.add('active');

      if (tabId === 'timeline') {{
        setTimeout(renderTimeline, 50);
      }}
    }}

    // Render Header & KPIs
    function renderHeaderAndKpis() {{
      const char = TRACE.initial_state.character || {{}};
      const summary = TRACE.summary || {{}};

      document.getElementById('envBadge').textContent = char.environment || 'LIVE';

      const pillsHtml = `
        <div class="pill"><span class="label">Class:</span><span class="val">${{char.class_name || 'Character'}}</span></div>
        <div class="pill"><span class="label">Spec:</span><span class="val">${{char.spec || 'Discipline'}}</span></div>
        <div class="pill"><span class="label">Level:</span><span class="val">${{char.level || 80}}</span></div>
        <div class="pill"><span class="label">Resource:</span><span class="val">${{char.resource_type || 'Energy'}}</span></div>
      `;
      document.getElementById('metaPills').innerHTML = pillsHtml;

      const kpis = [
        {{ label: 'Combat Duration', val: `${{summary.duration || 0.0}}s`, cls: '' }},
        {{ label: 'Pre-Pull', val: `${{(-(summary.t_start || 0)).toFixed(2)}}s`, cls: '' }},
        {{ label: 'DPS', val: (summary.dps || 0).toLocaleString(), cls: 'accent' }},
        {{ label: 'Total Damage', val: (summary.total_damage || 0).toLocaleString(), cls: 'success' }},
        {{ label: 'Total Hits', val: (summary.total_hits || 0).toLocaleString(), cls: '' }},
        {{ label: 'Crit %', val: `${{summary.crit_pct || 0}}%`, cls: 'warning' }},
        {{ label: 'APM', val: summary.apm || 0, cls: '' }},
        {{ label: 'Stall Time', val: `${{summary.total_stalled_time || 0.0}}s`, cls: summary.total_stalled_time > 0 ? 'warning' : '' }},
      ];

      document.getElementById('kpiBar').innerHTML = kpis.map(k => `
        <div class="kpi-card ${{k.cls}}">
          <div class="kpi-label">${{k.label}}</div>
          <div class="kpi-val">${{k.val}}</div>
        </div>
      `).join('');

      document.getElementById('passivesCountBadge').textContent = (TRACE.initial_state.passives || []).length;
      document.getElementById('treeLevelsCountBadge').textContent = (TRACE.initial_state.skill_tree || []).length || 8;
      document.getElementById('rotStepsCountBadge').textContent = (TRACE.initial_state.rotation || []).length;
      document.getElementById('decisionsCountBadge').textContent = (TRACE.rotation_decisions || []).length;
      document.getElementById('hitsCountBadge').textContent = (TRACE.hit_math_records || []).length;
      document.getElementById('eventsCountBadge').textContent = (TRACE.events || []).length;
    }}

    // Showcase: Tactical, Implants & Relics
    function renderGearShowcase() {{
      const st = TRACE.initial_state;
      const tactical = st.tactical;
      const legendaries = st.legendaries || [];
      const relics = st.relics || [];
      const cont = document.getElementById('gearShowcaseGrid');

      let html = '';

      // Tactical Card
      if (tactical) {{
        html += `
          <div class="gear-item-card" style="border-left: 4px solid var(--purple);">
            <div class="gear-header">
              <span class="badge-tag badge-crit">TACTICAL ITEM</span>
            </div>
            <div class="gear-title">${{tactical.name}}</div>
            <div class="mono" style="font-size: 11px; color: var(--text-dim);">${{tactical.fqn}}</div>
            ${{(TRACE.summary.tactical_swaps || []).map(sw => `
              <div class="mono" style="font-size: 11px; color: var(--warning); margin-top: 4px;">
                Pre-combat swap @ ${{sw.t.toFixed(2)}}s &rarr; ${{sw.to}}
              </div>`).join('')}}
          </div>
        `;
      }}

      // Legendary Implants Cards
      legendaries.forEach((leg, idx) => {{
        html += `
          <div class="gear-item-card" style="border-left: 4px solid var(--warning);">
            <div class="gear-header">
              <span class="badge-tag badge-warn">LEGENDARY IMPLANT #${{idx+1}}</span>
            </div>
            <div class="gear-title">${{leg.name}}</div>
            <div class="mono" style="font-size: 11px; color: var(--text-dim);">${{leg.fqn}}</div>
          </div>
        `;
      }});

      // Relics Cards
      relics.forEach((rel, idx) => {{
        html += `
          <div class="gear-item-card" style="border-left: 4px solid var(--accent);">
            <div class="gear-header">
              <span class="badge-tag">RELIC #${{idx+1}}</span>
            </div>
            <div class="gear-title">${{rel.name}}</div>
            <div class="mono" style="font-size: 11px; color: var(--text-dim);">${{rel.fqn}}</div>
          </div>
        `;
      }});

      cont.innerHTML = html || '<div style="color:var(--text-dim);">No special gear items loaded.</div>';
    }}

    // Tab 2: Derived Stats Table (Calculated After Passives & Buffs)
    function renderDerivedStats() {{
      const d = TRACE.initial_state.derived || {{}};
      const rows = [
        ['Effective GCD', `${{d.gcd || 1.5}}s`],
        ['Mastery', `${{(d.mastery || 0).toLocaleString()}} ${{(d.base_mastery && d.base_mastery !== d.mastery) ? `<span style="color:var(--text-dim); font-size:11px;">(Base: ${{d.base_mastery.toLocaleString()}})</span>` : ''}}`],
        ['Power', (d.power || 0).toLocaleString()],
      ];
      if (d.force_power > 0 && d.tech_power > 0) {{
        rows.push(['Force / Tech Power', `${{d.force_power.toLocaleString()}} / ${{d.tech_power.toLocaleString()}}`]);
      }} else if (d.force_power > 0) {{
        rows.push(['Force Power', d.force_power.toLocaleString()]);
      }} else if (d.tech_power > 0) {{
        rows.push(['Tech Power', d.tech_power.toLocaleString()]);
      }}
      rows.push(
        ['Critical Rating', (d.crit_rating || 0).toLocaleString()],
        ['Critical Chance %', `${{d.crit_chance || 0}}% ${{(d.base_crit_chance && d.base_crit_chance !== d.crit_chance) ? `<span style="color:var(--text-dim); font-size:11px;">(Base: ${{d.base_crit_chance}}% + ${{d.coord_bonus_pct}}% Coordination)</span>` : ''}}`],
        ['Critical Multiplier %', `${{d.crit_multiplier || 150}}%`],
        ['Alacrity Rating', (d.alacrity_rating || 0).toLocaleString()],
        ['Alacrity %', `${{d.alacrity_pct || 0}}%`],
        ['Accuracy Rating', (d.accuracy_rating || 0).toLocaleString()],
        ['Accuracy % (Main / Off)', `${{d.accuracy_pct || 100}}%`],
        ['Weapon Damage Range', d.weapon_range || '--']
      );
      if (d.bonus_damage_force > 0) rows.push(['Force Bonus Damage', d.bonus_damage_force.toLocaleString()]);
      if (d.bonus_damage_melee > 0) rows.push(['Melee Bonus Damage', d.bonus_damage_melee.toLocaleString()]);
      if (d.bonus_damage_tech > 0) rows.push(['Tech Bonus Damage', d.bonus_damage_tech.toLocaleString()]);
      if (d.bonus_damage_ranged > 0) rows.push(['Ranged Bonus Damage', d.bonus_damage_ranged.toLocaleString()]);
      if (d.armor_rating > 0) rows.push(['Armor Rating', d.armor_rating.toLocaleString()]);
      if (d.damage_reduction > 0) rows.push(['Damage Reduction %', `${{d.damage_reduction}}%`]);
      rows.push(['Standard Health', (d.standard_health || 19335).toLocaleString()]);
      if (d.max_health > 0) rows.push(['Max Health', d.max_health.toLocaleString()]);
      document.getElementById('derivedStatsTable').innerHTML = rows.map(r => `
        <tr>
          <td style="color: var(--text-muted); font-weight: 500;">${{r[0]}}</td>
          <td class="mono" style="font-weight: 700; color: #fff;">${{r[1]}}</td>
        </tr>
      `).join('');
    }}

    // Tab 3: Skill Tree & Tier Choices
    function renderSkillTree() {{
      const tree = TRACE.initial_state.skill_tree || [];
      const cont = document.getElementById('skillTreeContainer');
      if (!tree.length) {{
        cont.innerHTML = '<div style="color:var(--text-dim); padding:16px;">Skill tree structure not available in config.</div>';
        return;
      }}

      // Display in descending order (highest level top down to lowest)
      const sortedTree = [...tree].sort((a, b) => parseInt(b.level, 10) - parseInt(a.level, 10));

      cont.innerHTML = sortedTree.map(t => {{
        const optHtml = (t.options || []).map(o => `
          <div class="tree-option-card ${{o.is_selected ? 'selected' : ''}}">
            <div class="opt-title">
              <span>Option ${{o.idx}}: ${{o.name}}</span>
              ${{o.is_selected ? '<span class="badge-selected badge-tag">SELECTED</span>' : ''}}
            </div>
            <div class="mono" style="font-size: 10px; color: var(--text-dim); word-break: break-all;">${{o.fqn}}</div>
          </div>
        `).join('');

        return `
          <div class="tree-tier-row">
            <div class="tree-tier-header">
              <span style="font-weight: 700; font-size: 14px; color: var(--accent);">Tier Level ${{t.level}}</span>
              <span style="font-size: 12px; color: var(--text-muted);">Choice: Option ${{t.selected_idx || 'None'}}</span>
            </div>
            <div class="tree-options-grid">
              ${{optHtml}}
            </div>
          </div>
        `;
      }}).join('');
    }}

    // Tab 4: Rotation Profile Sequence
    function renderRotationProfile() {{
      const seq = TRACE.initial_state.rotation || [];
      const cont = document.getElementById('rotationSequenceContainer');
      if (!seq.length) {{
        cont.innerHTML = '<div style="color:var(--text-dim); padding:16px;">Rotation sequence not available in config.</div>';
        return;
      }}

      document.getElementById('rotationProfileTitle').textContent = `(${{seq.length}} Total Steps)`;

      cont.innerHTML = seq.map(s => {{
        let poolHtml = '';
        if (s.candidates && s.candidates.length) {{
          poolHtml = s.candidates.map((c, idx) => `
            <div class="rot-pool-item">
              <div>
                <span style="color:var(--text-dim); margin-right:8px; font-family:monospace;">#${{idx+1}}</span>
                <strong style="color:#fff;">${{c.name}}</strong>
                <span class="mono" style="color:var(--text-dim); margin-left:8px; font-size:11px;">(${{c.id}})</span>
              </div>
              <div class="mono" style="font-size:11px; color:var(--text-muted);">
                ${{Object.keys(c.rules || {{}}).length ? JSON.stringify(c.rules) : '<span style="color:var(--text-dim)">Default</span>'}}
              </div>
            </div>
          `).join('');
        }}

        let badgeType = 'badge-tag';
        if (s.type === 'priority_block') badgeType += ' badge-warn';
        else if (s.type === 'fixed') badgeType += ' badge-ok';

        return `
          <div class="rot-step-card">
            <div class="rot-step-header">
              <div>
                <span class="mono" style="font-weight:700; color:var(--accent); margin-right:8px;">Step ${{s.step_num}}</span>
                <strong style="font-size:14px; color:#fff;">${{s.name}}</strong>
                <span class="${{badgeType}}" style="margin-left:8px;">${{s.type}}</span>
              </div>
              <div class="mono" style="font-size:12px; color:var(--text-muted);">
                ${{s.lead_time ? `Lead Time: ${{s.lead_time}}s` : ''}}
              </div>
            </div>
            ${{poolHtml ? `<div style="margin-top:6px;">${{poolHtml}}</div>` : ''}}
          </div>
        `;
      }}).join('');
    }}

    // Tab 2: Target Debuffs
    function renderTargetDebuffs() {{
      const target = TRACE.initial_state.target || {{}};
      const debuffs = target.initial_debuffs || [];
      const cont = document.getElementById('targetDebuffsContainer');

      let html = `<div style="margin-bottom: 12px; font-size: 13px;">Target: <strong>${{target.name}}</strong> (Starting HP: <span class="mono">${{(target.starting_hp || 0).toLocaleString()}}</span>)</div>`;
      if (!debuffs.length) {{
        html += `<div style="color: var(--text-dim); font-size: 12px;">No active baseline target debuffs.</div>`;
      }} else {{
        html += `<div style="display: flex; flex-direction: column; gap: 8px;">`;
        debuffs.forEach(db => {{
          const mods = (db.modifiers || []).map(m => `<span class="badge-tag">${{m.stat}}: ${{m.value}}</span>`).join(' ');
          html += `
            <div style="background: #0f172a; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-subtle);">
              <div style="font-weight: 600; color: #fff; margin-bottom: 4px;">${{db.name}}</div>
              <div>${{mods || '<span style="color:var(--text-dim)">Baseline effect</span>'}}</div>
            </div>
          `;
        }});
        html += `</div>`;
      }}
      cont.innerHTML = html;
    }}

    // Tab 2: Passives Table
    function renderPassivesTable() {{
      const passives = TRACE.initial_state.passives || [];
      const tbody = document.querySelector('#passivesTable tbody');
      tbody.innerHTML = passives.map(p => {{
        const scHtml = (p.stat_changes || []).map(sc => {{
          const valStr = sc.is_percent ? `${{sc.value * 100}}%` : sc.value;
          return `<div class="mono" style="font-size: 11px; margin-bottom: 2px;">• <span style="color:var(--accent)">${{sc.stat}}</span>: <strong>${{valStr}}</strong></div>`;
        }}).join('');

        const effHtml = (p.effects || []).map(e => {{
          const trigs = (e.triggers || []).map(t => `<span class="badge-tag">${{t}}</span>`).join(' ');
          return `<div style="font-size: 11px; margin-bottom: 3px;">${{e.name || 'Effect'}} ${{trigs}}</div>`;
        }}).join('');

        let originBadge = 'badge-tag';
        if (p.origin.includes('Tactical')) originBadge += ' badge-crit';
        else if (p.origin.includes('Legendary')) originBadge += ' badge-warn';
        else if (p.origin.includes('Discipline')) originBadge += ' badge-ok';

        return `
          <tr>
            <td>
              <div style="font-weight: 600; color: #fff;">${{p.name}}</div>
              <div class="mono" style="font-size: 10px; color: var(--text-dim);">${{p.fqn}}</div>
            </td>
            <td><span class="${{originBadge}}">${{p.origin}}</span></td>
            <td>${{scHtml || '<span style="color:var(--text-dim)">None</span>'}}</td>
            <td>${{effHtml || '<span style="color:var(--text-dim)">None</span>'}}</td>
          </tr>
        `;
      }}).join('');
    }}

    function filterPassivesTable() {{
      const q = document.getElementById('passiveSearch').value.toLowerCase().trim();
      const rows = document.querySelectorAll('#passivesTable tbody tr');
      rows.forEach(r => {{
        const text = r.textContent.toLowerCase();
        r.style.display = text.includes(q) ? '' : 'none';
      }});
    }}

    // Tab 2: Active Abilities Table
    function renderActiveAbilitiesTable() {{
      const abls = TRACE.initial_state.active_abilities || [];
      const tbody = document.querySelector('#activeAbilitiesTable tbody');
      tbody.innerHTML = abls.map(a => `
        <tr>
          <td>
            <div style="font-weight: 600; color: #fff;">${{a.name}}</div>
            <div class="mono" style="font-size: 10px; color: var(--text-dim);">${{a.fqn}}</div>
          </td>
          <td><span class="badge-tag">${{a.origin}}</span></td>
          <td class="mono">${{a.cooldown > 0 ? `${{a.cooldown}}s` : 'None'}}</td>
          <td class="mono">${{a.energy_cost > 0 ? a.energy_cost : '0'}}</td>
          <td class="mono">${{a.channel_duration > 0 ? `Channel ${{a.channel_duration}}s` : (a.cast_time > 0 ? `Cast ${{a.cast_time}}s` : 'Instant')}}</td>
          <td>${{a.energy_type}}</td>
          <td>${{(a.tags || []).slice(0, 3).map(t => `<span class="badge-tag" style="font-size:10px;">${{t.split('.').pop()}}</span>`).join(' ')}}</td>
        </tr>
      `).join('');
    }}

    // Tab 2: Procs Table
    function renderProcsTable() {{
      const procs = TRACE.initial_state.procs || [];
      const tbody = document.querySelector('#procsTable tbody');
      tbody.innerHTML = procs.map(p => `
        <tr>
          <td style="font-weight: 600; color: #fff;">${{p.name}}</td>
          <td>
            <div>${{p.source_name}}</div>
            <div class="mono" style="font-size: 10px; color: var(--text-dim);">${{p.source_fqn}}</div>
          </td>
          <td class="mono" style="font-weight: 700; color: var(--accent);">${{p.icd}}s</td>
          <td><span class="badge-tag">${{p.kind}}</span></td>
        </tr>
      `).join('');
    }}

    // Tab 5: Live Rotation Decisions
    function renderRotationDecisions() {{
      const decisions = TRACE.rotation_decisions || [];
      const cont = document.getElementById('rotationListContainer');

      cont.innerHTML = decisions.map(d => {{
        const isStall = d.is_stall;
        const candidateItems = (d.candidates || []).map(c => `
          <div class="candidate-card ${{c.accepted ? 'accepted' : 'rejected'}}">
            <div>
              <span style="font-weight: 600; color: #fff;">${{c.ability}}</span>
              <span style="margin-left: 8px; font-size: 11px; color: var(--text-muted);">${{c.reason || (c.accepted ? 'Cast initiated' : 'Rejected')}}</span>
            </div>
            <div>
              ${{c.accepted ? '<span class="badge-ok badge-tag">CAST</span>' : '<span class="badge-fail badge-tag">SKIP</span>'}}
            </div>
          </div>
        `).join('');

        return `
          <div class="card decision-card" data-stall="${{isStall}}" style="margin-bottom: 12px; border-left: 4px solid ${{isStall ? 'var(--warning)' : (d.chosen ? 'var(--accent)' : 'var(--text-dim)')}};">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <div>
                <span class="mono" style="color: var(--accent); font-weight: 700;">[${{d.t.toFixed(2)}}s]</span>
                <span style="font-weight: 700; color: #fff; margin-left: 8px;">Step: ${{d.step_name}}</span>
                <span class="badge-tag" style="margin-left: 6px;">${{d.step_type}}</span>
              </div>
              <div>
                ${{isStall ? '<span class="badge-warn badge-tag">STALL / IDLE</span>' : (d.chosen ? `<span style="font-weight:700; color:var(--success);">Chosen: ${{d.chosen}}</span>` : '<span style="color:var(--text-dim);">No action</span>')}}
              </div>
            </div>
            <div style="margin-top: 6px;">
              ${{candidateItems}}
            </div>
          </div>
        `;
      }}).join('');
    }}

    function filterDecisionsType(type) {{
      selectedDecisionFilter = type;
      document.getElementById('chipAllDecisions').classList.toggle('active', type === 'all');
      document.getElementById('chipStalls').classList.toggle('active', type === 'stalls');
      filterRotationList();
    }}

    function filterRotationList() {{
      const q = document.getElementById('rotationSearch').value.toLowerCase().trim();
      const cards = document.querySelectorAll('.decision-card');
      cards.forEach(c => {{
        const isStall = c.getAttribute('data-stall') === 'true';
        if (selectedDecisionFilter === 'stalls' && !isStall) {{
          c.style.display = 'none';
          return;
        }}
        const text = c.textContent.toLowerCase();
        c.style.display = text.includes(q) ? '' : 'none';
      }});
    }}

    // Tab 6: Hit Math Auditor
    function renderMathHitsTable() {{
      const hits = TRACE.hit_math_records || [];
      const tbody = document.querySelector('#mathHitsTable tbody');
      tbody.innerHTML = hits.map((h, idx) => `
        <tr class="clickable-row" onclick="inspectHitMath(${{idx}})">
          <td class="mono" style="color: var(--accent);">${{h.t.toFixed(2)}}s</td>
          <td style="font-weight: 600; color: #fff;">${{h.ability}}</td>
          <td class="mono" style="font-weight: 700; color: ${{h.is_crit ? 'var(--purple)' : '#fff'}};">${{h.damage.toLocaleString()}}</td>
          <td>${{h.is_crit ? '<span class="badge-crit badge-tag">CRIT</span>' : '<span class="badge-tag">NORMAL</span>'}}</td>
          <td>${{h.attack_type}} / ${{h.damage_type}}</td>
          <td class="mono">${{h.target_hp.toLocaleString()}}</td>
          <td><button class="btn-chip" style="padding: 2px 8px;">Inspect Math</button></td>
        </tr>
      `).join('');
    }}

    function toggleMathCrits() {{
      showMathCritsOnly = !showMathCritsOnly;
      document.getElementById('chipMathCrits').classList.toggle('active', showMathCritsOnly);
      filterMathTable();
    }}

    function filterMathTable() {{
      const q = document.getElementById('mathSearch').value.toLowerCase().trim();
      const rows = document.querySelectorAll('#mathHitsTable tbody tr');
      rows.forEach(r => {{
        const isCrit = r.querySelector('.badge-crit') !== null;
        if (showMathCritsOnly && !isCrit) {{
          r.style.display = 'none';
          return;
        }}
        const text = r.textContent.toLowerCase();
        r.style.display = text.includes(q) ? '' : 'none';
      }});
    }}

    function inspectHitMath(index) {{
      const hit = TRACE.hit_math_records[index];
      if (!hit) return;

      const pane = document.getElementById('mathInspector');
      pane.classList.add('open');
      document.getElementById('mathInspectorTitle').innerHTML = `Hit #${{hit.hit_id}}: <strong>${{hit.ability}}</strong> at ${{hit.t.toFixed(2)}}s &mdash; ${{hit.damage.toLocaleString()}} damage ${{hit.is_crit ? '<span class="badge-crit badge-tag">CRITICAL!</span>' : ''}}`;

      const m = hit.math || {{}};
      const buckets = m.buckets || {{}};

      const bucketsHtml = Object.entries(buckets).map(([k, v]) => `
        <div class="math-row">
          <span>${{k}}</span>
          <span class="mono">${{typeof v === 'number' ? v.toFixed(4) : v}}</span>
        </div>
      `).join('') || '<div style="color:var(--text-dim); font-size:12px;">No active bucket multipliers.</div>';

      document.getElementById('mathInspectorBody').innerHTML = `
        <div class="math-tree">
          <!-- Block 1: Base Roll -->
          <div class="math-block">
            <h4>1. Base Damage</h4>
            <div class="math-row"><span>Base Calculated:</span><span class="mono">${{m.base_damage || '--'}}</span></div>
            <div class="math-row"><span>Post-Mitigation:</span><span class="mono">${{m.post_mit_damage || '--'}}</span></div>
          </div>

          <!-- Block 2: Empirical Buckets -->
          <div class="math-block">
            <h4>2. Modifier Buckets</h4>
            ${{bucketsHtml}}
            <div class="math-row"><span>Combined Multiplier:</span><span class="mono">${{m.total_multiplier || '1.0'}}</span></div>
          </div>

          <!-- Block 3: Critical & Final -->
          <div class="math-block">
            <h4>3. Critical & Final Damage</h4>
            <div class="math-row"><span>Bonus Crit Chance:</span><span class="mono">+${{((m.bonus_crit_chance || 0) * 100).toFixed(2)}}%</span></div>
            <div class="math-row"><span>Bonus Crit Multiplier:</span><span class="mono">+${{((m.bonus_crit_modifier || 0) * 100).toFixed(2)}}%</span></div>
            <div class="math-row"><span>Critical Hit Rolled?</span><span class="mono">${{hit.is_crit ? 'YES' : 'NO'}}</span></div>
            <div class="math-row"><span>Final Damage:</span><span class="mono" style="color:var(--accent);">${{hit.damage.toLocaleString()}}</span></div>
          </div>
        </div>
      `;
      pane.scrollIntoView({{ behavior: 'smooth' }});
    }}

    // Tab 7: Event Log Table
    function renderEventsTable() {{
      const events = TRACE.events || [];
      const tbody = document.querySelector('#eventsTable tbody');
      tbody.innerHTML = events.map(e => {{
        let typeBadge = 'badge-tag';
        let detailText = '';
        let valText = '';

        switch (e.type) {{
          case 'cast_start':
            typeBadge += ' badge-ok';
            detailText = `Casts <strong>${{e.ability}}</strong>${{e.is_channel ? ' (Channel)' : ''}}`;
            valText = e.duration > 0 ? `${{e.duration}}s` : 'Instant';
            break;
          case 'damage_hit':
            typeBadge += e.is_crit ? ' badge-crit' : ' badge-ok';
            detailText = `<strong>${{e.ability}}</strong> hit on ${{e.target}}`;
            valText = `${{e.damage.toLocaleString()}} dmg (${{e.target_hp.toLocaleString()}} HP rem)`;
            break;
          case 'buff_apply':
          case 'buff_refresh':
            typeBadge += ' badge-warn';
            detailText = `${{e.type === 'buff_apply' ? 'Applied' : 'Refreshed'}} <strong>${{e.effect}}</strong> on ${{e.entity}}`;
            valText = `x${{e.stacks}}${{e.duration > 0 ? ` (${{e.duration}}s)` : ''}}`;
            break;
          case 'buff_stack':
            typeBadge += ' badge-warn';
            detailText = `Stacks modified: <strong>${{e.effect}}</strong> on ${{e.entity}}`;
            valText = `${{e.old_stacks}} -> ${{e.new_stacks}}`;
            break;
          case 'buff_expire':
            typeBadge += '';
            detailText = `Expired: <strong>${{e.effect}}</strong> on ${{e.entity}}`;
            valText = 'Cleared';
            break;
          case 'resource':
            const isProcRes = e.reason && e.reason.startsWith('Proc');
            typeBadge += isProcRes ? ' badge-crit' : ' badge-tag';
            detailText = isProcRes
              ? `Resource (${{e.resource}}): <span style="color: var(--accent-crit); font-weight: 600;">${{e.reason}}</span>`
              : `Resource (${{e.resource}}): ${{e.reason}}`;
            valText = `${{e.current}} (${{e.delta >= 0 ? '+' : ''}}${{e.delta}})`;
            break;
          case 'rotation_eval':
            typeBadge += e.is_stall ? ' badge-fail' : '';
            detailText = `Evaluated step <strong>${{e.step_name}}</strong>`;
            valText = e.is_stall ? 'STALL' : (e.chosen ? `Chosen: ${{e.chosen}}` : 'No action');
            break;
          case 'proc_fire':
            typeBadge += ' badge-crit';
            detailText = `Proc trigger [${{e.trigger}}]: <strong>${{e.effect}}</strong>`;
            valText = e.source;
            break;
          case 'stall':
            typeBadge += ' badge-fail';
            detailText = `Rotation Stall: ${{e.step_info}}`;
            valText = `${{e.duration}}s idle`;
            break;
          case 'tactical_swap':
            typeBadge += ' badge-crit';
            detailText = `Tactical swap: <strong>${{e.ability}}</strong>`;
            valText = `${{e.from || '-'}} &rarr; ${{e.to}}`;
            break;
          default:
            detailText = e.type;
        }}

        return `
          <tr data-type="${{e.type}}">
            <td class="mono" style="color: var(--accent); font-weight: 600;">${{e.t.toFixed(2)}}s${{e.t < 0 ? ' <span class="badge-tag">PRE-PULL</span>' : ''}}</td>
            <td><span class="${{typeBadge}}">${{e.type}}</span></td>
            <td>${{detailText}}</td>
            <td class="mono" style="font-size: 12px;">${{valText}}</td>
          </tr>
        `;
      }}).join('');
    }}

    function filterEventsType(type) {{
      selectedEventFilter = type;
      document.querySelectorAll('#pane-events .btn-chip').forEach(c => {{
        c.classList.toggle('active', c.getAttribute('onclick').includes(`'${{type}}'`));
      }});
      filterEventsTable();
    }}

    function filterEventsTable() {{
      const q = document.getElementById('eventSearch').value.toLowerCase().trim();
      const rows = document.querySelectorAll('#eventsTable tbody tr');
      rows.forEach(r => {{
        const t = r.getAttribute('data-type');
        let typeMatch = (selectedEventFilter === 'all');
        if (selectedEventFilter === 'cast' && (t === 'cast_start' || t === 'cast_finish' || t === 'channel_tick')) typeMatch = true;
        if (selectedEventFilter === 'damage_hit' && t === 'damage_hit') typeMatch = true;
        if (selectedEventFilter === 'buff' && t.startsWith('buff_')) typeMatch = true;
        if (selectedEventFilter === 'resource' && t === 'resource') typeMatch = true;
        if (selectedEventFilter === 'rotation_eval' && t === 'rotation_eval') typeMatch = true;
        if (selectedEventFilter === 'proc' && t === 'proc_fire') typeMatch = true;
        if (selectedEventFilter === 'stall' && t === 'stall') typeMatch = true;

        if (!typeMatch) {{
          r.style.display = 'none';
          return;
        }}
        const text = r.textContent.toLowerCase();
        r.style.display = text.includes(q) ? '' : 'none';
      }});
    }}

    // Tab 1: Interactive SVG Timeline
    function renderTimeline() {{
      const svg = document.getElementById('timelineSvg');
      const container = document.getElementById('timelineContainer');
      const duration = Math.max(1.0, TRACE.summary.duration || 10.0);
      const tStart = Math.min(0, TRACE.summary.t_start || 0);
      const span = Math.max(1.0, duration - tStart);

      const baseWidth = Math.max(container.clientWidth - 20, 900);
      const totalWidth = baseWidth * timelineZoom;
      const totalHeight = 360;

      svg.setAttribute('width', totalWidth);
      svg.setAttribute('height', totalHeight);
      svg.innerHTML = '';

      const timeToX = (t) => ((t - tStart) / span) * (totalWidth - 60) + 40;

      // Draw background grid lines and time ruler
      let timeStep = 1.0;
      if (span > 30) timeStep = 5.0;
      if (span > 120) timeStep = 10.0;
      if (timelineZoom > 2.0) timeStep = Math.max(0.5, timeStep / 2);

      let gridHtml = '';
      for (let t = Math.ceil(tStart / timeStep) * timeStep; t <= duration; t += timeStep) {{
        const x = timeToX(t);
        gridHtml += `
          <line x1="${{x}}" y1="0" x2="${{x}}" y2="${{totalHeight - 30}}" stroke="rgba(255,255,255,0.04)" stroke-dasharray="2,2"/>
          <text x="${{x}}" y="${{totalHeight - 10}}" fill="var(--text-dim)" font-size="10" text-anchor="middle" font-family="monospace">${{t.toFixed(1)}}s</text>
        `;
      }}

      // Pre-pull shading, PULL marker (T0 = first damage) and tactical swap markers
      if (tStart < 0) {{
        const x0 = timeToX(tStart);
        const xPull = timeToX(0);
        gridHtml += `
          <rect x="${{x0}}" y="0" width="${{xPull - x0}}" height="${{totalHeight - 30}}" fill="rgba(148,163,184,0.10)"/>
          <text x="${{x0 + 4}}" y="12" fill="var(--text-dim)" font-size="10" font-weight="700">PRE-PULL</text>
        `;
      }}
      gridHtml += `
        <line x1="${{timeToX(0)}}" y1="0" x2="${{timeToX(0)}}" y2="${{totalHeight - 30}}" stroke="var(--danger)" stroke-width="1.5"/>
        <text x="${{timeToX(0) + 4}}" y="12" fill="var(--danger)" font-size="10" font-weight="700">PULL</text>
      `;
      (TRACE.summary.tactical_swaps || []).forEach(sw => {{
        const xs = timeToX(sw.t);
        const label = String(sw.to || '').split('.').pop();
        gridHtml += `
          <line x1="${{xs}}" y1="16" x2="${{xs}}" y2="${{totalHeight - 30}}" stroke="var(--warning)" stroke-width="1" stroke-dasharray="4,2"/>
          <text x="${{xs + 3}}" y="${{totalHeight - 34}}" fill="var(--warning)" font-size="9" font-weight="600">TAC: ${{label}}</text>
        `;
      }});

      // Track 1: Casts / Channels (y: 20 to 60)
      const casts = (TRACE.events || []).filter(e => e.type === 'cast_start');
      let castsHtml = '<text x="10" y="38" fill="var(--text-muted)" font-size="11" font-weight="700">CASTS</text>';
      casts.forEach((c, idx) => {{
        const x1 = timeToX(c.t);
        const castDur = Math.max(0.3, c.duration);
        const x2 = timeToX(Math.min(duration, c.t + castDur));
        const w = Math.max(12, x2 - x1);
        const fill = c.is_channel ? '#6366f1' : '#38bdf8';

        castsHtml += `
          <g class="clickable-row" onclick="inspectTimelineCast(${{idx}})" style="cursor: pointer;">
            <rect x="${{x1}}" y="24" width="${{w}}" height="22" rx="4" fill="${{fill}}" fill-opacity="0.85" stroke="#fff" stroke-width="0.5"/>
            <text x="${{x1 + 4}}" y="39" fill="#fff" font-size="10" font-weight="600">${{c.ability}}</text>
          </g>
        `;
      }});

      // Track 2: Resource Sparkline (y: 70 to 140)
      const resSamples = TRACE.resource_samples || [];
      let resPath = '';
      let resHtml = '<text x="10" y="105" fill="var(--text-muted)" font-size="11" font-weight="700">RESOURCE</text>';
      if (resSamples.length > 1) {{
        const maxRes = TRACE.initial_state.character.max_resource || 100;
        const resToY = (val) => 140 - ((val / maxRes) * 60);

        resPath = `M ${{timeToX(resSamples[0].t)}} ${{resToY(resSamples[0].v)}}`;
        for (let i = 1; i < resSamples.length; i++) {{
          resPath += ` L ${{timeToX(resSamples[i].t)}} ${{resToY(resSamples[i].v)}}`;
        }}
        resHtml += `
          <path d="${{resPath}}" fill="none" stroke="var(--warning)" stroke-width="2" opacity="0.9"/>
        `;
      }}

      // Track 3: Target HP curve (y: 155 to 215)
      const hpSamples = TRACE.target_hp_samples || [];
      let hpPath = '';
      let tHpHtml = '<text x="10" y="185" fill="var(--text-muted)" font-size="11" font-weight="700">TARGET HP</text>';
      if (hpSamples.length > 1) {{
        const hpToY = (pct) => 215 - ((pct / 100.0) * 50);
        hpPath = `M ${{timeToX(hpSamples[0].t)}} ${{hpToY(hpSamples[0].pct)}}`;
        for (let i = 1; i < hpSamples.length; i++) {{
          hpPath += ` L ${{timeToX(hpSamples[i].t)}} ${{hpToY(hpSamples[i].pct)}}`;
        }}
        tHpHtml += `
          <path d="${{hpPath}}" fill="none" stroke="var(--danger)" stroke-width="2" opacity="0.85"/>
        `;
      }}

      // Track 4: Buff Active Windows (y: 230 to 310)
      const buffWins = TRACE.active_buff_windows || [];
      let buffsHtml = '<text x="10" y="270" fill="var(--text-muted)" font-size="11" font-weight="700">BUFFS</text>';
      const topBuffs = buffWins.filter(b => !b.is_passive).slice(0, 5);
      topBuffs.forEach((b, idx) => {{
        const y = 230 + (idx * 16);
        const x1 = timeToX(b.start);
        const x2 = timeToX(b.end !== null ? b.end : duration);
        const w = Math.max(8, x2 - x1);
        buffsHtml += `
          <rect x="${{x1}}" y="${{y}}" width="${{w}}" height="12" rx="3" fill="var(--success)" fill-opacity="0.45" stroke="var(--success)" stroke-width="0.5"/>
          <text x="${{x1 + 4}}" y="${{y + 9}}" fill="#fff" font-size="9" font-weight="600">${{b.name}}</text>
        `;
      }});

      svg.innerHTML = gridHtml + castsHtml + resHtml + tHpHtml + buffsHtml;

      // Mouse scrubber interaction
      svg.onmousemove = (evt) => {{
        const rect = svg.getBoundingClientRect();
        const mouseX = evt.clientX - rect.left;
        const normT = Math.max(tStart, Math.min(duration, tStart + ((mouseX - 40) / (totalWidth - 60)) * span));

        document.getElementById('hudTime').textContent = `${{normT.toFixed(2)}}s`;

        // Update live resource & HP at scrubber position
        const closestRes = resSamples.reduce((prev, curr) => curr.t <= normT ? curr : prev, resSamples[0] || {{ v: 0 }});
        if (closestRes) document.getElementById('hudResource').textContent = closestRes.v;

        const closestHp = hpSamples.reduce((prev, curr) => curr.t <= normT ? curr : prev, hpSamples[0] || {{ pct: 100 }});
        if (closestHp) document.getElementById('hudHp').textContent = `${{closestHp.pct.toFixed(1)}}%`;

        const activeBuffsAtT = buffWins.filter(b => b.start <= normT && (b.end === null || b.end >= normT));
        document.getElementById('hudBuffs').textContent = activeBuffsAtT.length;
      }};
    }}

    function zoomTimeline(factor) {{
      timelineZoom = Math.max(0.5, Math.min(8.0, timelineZoom * factor));
      renderTimeline();
    }}

    function resetTimelineZoom() {{
      timelineZoom = 1.0;
      renderTimeline();
    }}

    function inspectTimelineCast(idx) {{
      const casts = (TRACE.events || []).filter(e => e.type === 'cast_start');
      const c = casts[idx];
      if (!c) return;

      const pane = document.getElementById('quickInspector');
      pane.classList.add('open');
      document.getElementById('quickInspectorTitle').textContent = `Cast: ${{c.ability}} at ${{c.t.toFixed(2)}}s`;
      document.getElementById('quickInspectorBody').innerHTML = `
        <div style="font-size: 13px;">
          <div><strong>FQN:</strong> <span class="mono">${{c.fqn}}</span></div>
          <div><strong>Duration:</strong> <span class="mono">${{c.duration}}s</span> ${{c.is_channel ? '(Channel)' : '(Instant/Cast)'}}</div>
          <div><strong>Target:</strong> ${{c.target || 'Current Target'}}</div>
        </div>
      `;
    }}

    function closeInspector() {{
      document.getElementById('quickInspector').classList.remove('open');
    }}
  </script>
</body>
</html>
"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    return str(output_file)

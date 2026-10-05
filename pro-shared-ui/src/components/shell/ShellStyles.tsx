/**
 * Global CSS the shell needs that inline styles can't express: keyframes, the
 * font import, scoped scrollbar/selection styling, and hover utility classes
 * (ported from the design's `style-hover` directives). Scoped under `.lf-shell`
 * so it doesn't leak into the host app. Rendered once by <WorkspaceShell>.
 */
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Chakra+Petch:ital,wght@0,400;0,500;0,600;0,700;1,500;1,600&family=JetBrains+Mono:ital,wght@0,400;0,500;0,700;1,400&family=Courier+Prime:ital,wght@0,400;0,700;1,400&display=swap');
.lf-shell, .lf-shell *{box-sizing:border-box;}
.lf-shell ::selection{background:rgba(76,194,255,.28);color:var(--strong);}
.lf-shell ::-webkit-scrollbar{width:7px;height:7px;}
.lf-shell ::-webkit-scrollbar-thumb{background:rgba(232,68,58,.32);}
.lf-shell ::-webkit-scrollbar-thumb:hover{background:rgba(232,68,58,.55);}
.lf-shell ::-webkit-scrollbar-track{background:transparent;}
.lf-shell :is(button,[role="button"],[role="separator"],input,textarea,select):focus-visible{outline:2px solid var(--accent)!important;outline-offset:2px;}
@keyframes lf-sweep{to{transform:rotate(360deg);}}
@keyframes lf-blink{0%,48%{opacity:1;}49%,100%{opacity:0;}}
@keyframes lf-pulse{0%,100%{opacity:.45;}50%{opacity:1;}}
@keyframes lf-scan{from{transform:translateY(-12%);}to{transform:translateY(112%);}}
@keyframes lf-glow{0%,100%{box-shadow:0 0 0 0 rgba(255,82,96,0);}50%{box-shadow:0 0 14px 1px rgba(255,82,96,.45);}}
@keyframes lf-flick{0%,93%,100%{opacity:1;}94%{opacity:.55;}96%{opacity:1;}97%{opacity:.7;}}
@keyframes lf-bars{0%,100%{transform:scaleY(.35);}50%{transform:scaleY(1);}}
@keyframes lf-halo{0%,100%{opacity:.3;transform:scale(1);}50%{opacity:.7;transform:scale(1.1);}}
@keyframes lf-dash{to{stroke-dashoffset:-30;}}
@keyframes lf-flow{to{stroke-dashoffset:-60;}}
@keyframes lf-spin{to{transform:rotate(360deg);}}
@keyframes lf-spinr{to{transform:rotate(-360deg);}}
@keyframes lf-ring{0%,100%{opacity:.4;transform:scale(1);}50%{opacity:.85;transform:scale(1.06);}}
/* hover utilities (from style-hover) */
.lf-shell .lf-nav:hover{background:rgba(76,194,255,.05);color:var(--txt);}
.lf-shell .lf-nav-q:hover{background:rgba(176,124,255,.07);color:var(--txt);}
.lf-shell .lf-hov:hover{color:var(--txt);}
.lf-shell .lf-cmd:hover{border-color:rgba(76,194,255,.4);box-shadow:0 0 16px rgba(76,194,255,.12);}
.lf-shell .lf-chip:hover{border-color:var(--accent);color:var(--txt2);}
.lf-shell .lf-block:hover{background:rgba(255,82,96,.12);}
.lf-shell .lf-warn:hover{background:rgba(255,180,84,.12);}
.lf-shell .lf-sug:hover{background:rgba(76,194,255,.12);}
.lf-shell .lf-opp:hover{background:rgba(98,217,154,.12);}
.lf-shell .lf-row:hover{background:var(--tint2);}
.lf-shell .lf-row2:hover{background:var(--tint2);}
/* Studio chrome stays on one cinematic row when space permits. At the desktop
   app's supported minimum width it becomes two deliberate rows instead of
   clipping the always-on command, adaptive, layout, or save-status controls. */
.lf-topbar{position:relative;z-index:30;display:flex;align-items:center;flex:none;height:46px;min-width:0;gap:14px;padding:0 14px;background:linear-gradient(180deg,var(--raised),var(--panel2));border-bottom:1px solid var(--line);}
.lf-topbar-brand,.lf-topbar-format,.lf-topbar-adaptive,.lf-topbar-layout,.lf-topbar-status{flex:none;}
.lf-topbar-command{min-width:0;}
.lf-topbar-command .lf-cmd{min-width:0;}
.lf-topbar-command-copy{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
/* Real Studio dock workspace. The panel layer uses display:contents so every
   opened panel keeps one stable DOM/React parent while its grid coordinates move. */
.lf-dock-workspace{position:relative;isolation:isolate;display:grid;flex:1;min-width:0;min-height:0;overflow:hidden;background:var(--base);}
.lf-dock-header{display:flex;align-items:stretch;min-width:0;min-height:0;border-bottom:1px solid var(--line2);background:var(--panel);z-index:4;}
.lf-dock-header-left{grid-column:1;grid-row:1;border-right:1px solid var(--line2);}
.lf-dock-header-center{grid-column:3;grid-row:1;}
.lf-dock-header-right{grid-column:5;grid-row:1;border-left:1px solid var(--line2);}
.lf-dock-header-bottom{grid-column:1 / 6;grid-row:4;border-top:1px solid var(--line2);}
.lf-dock-tabs{display:flex;align-items:stretch;min-width:0;overflow-x:auto;scrollbar-width:thin;}
.lf-dock-tab-group{display:flex;align-items:stretch;flex:none;border-right:1px solid var(--line2);}
.lf-dock-tab,.lf-dock-tab-action,.lf-dock-header-actions button{border:0;background:transparent;color:var(--txt2);font:inherit;font-size:9px;letter-spacing:.08em;cursor:pointer;}
.lf-dock-tab{padding:0 9px;border-bottom:2px solid transparent;text-transform:uppercase;}
.lf-dock-tab[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent);background:var(--tint2);}
.lf-dock-tab-action{width:24px;padding:0;color:var(--txt3);}
.lf-dock-tab-action:hover,.lf-dock-header-actions button:hover{color:var(--strong);background:var(--tint2);}
.lf-dock-tab:disabled,.lf-dock-tab-action:disabled,.lf-dock-header-actions button:disabled{cursor:wait;opacity:.55;}
.lf-dock-header-actions{display:flex;align-items:stretch;margin-left:auto;flex:none;border-left:1px solid var(--line2);}
.lf-dock-header-actions button{padding:0 10px;}
.lf-dock-panel-layer{display:contents;}
.lf-dock-panel{position:relative;min-width:0;min-height:0;overflow:auto;padding:12px;background:var(--base);}
.lf-dock-panel-content{min-width:0;min-height:0;height:100%;}
.lf-dock-panel-left{border-right:1px solid var(--line2);}
.lf-dock-panel-right{border-left:1px solid var(--line2);}
.lf-dock-panel-bottom{border-top:1px solid var(--line2);}
.lf-dock-panel-flush{padding:0;overflow:hidden;}
.lf-dock-panel[hidden]{display:none!important;}
.lf-dock-resizer{z-index:5;touch-action:none;display:flex;align-items:center;justify-content:center;background:transparent;}
.lf-dock-resizer::after{content:"";display:block;border-radius:3px;background:var(--line-cy);transition:background .12s,box-shadow .12s;}
.lf-dock-resizer:hover::after,.lf-dock-resizer:focus-visible::after{background:var(--accent);box-shadow:0 0 8px color-mix(in srgb,var(--accent) 55%,transparent);}
.lf-dock-resizer-left{grid-column:2;grid-row:1 / 3;cursor:col-resize;}
.lf-dock-resizer-right{grid-column:4;grid-row:1 / 3;cursor:col-resize;}
.lf-dock-resizer-left::after,.lf-dock-resizer-right::after{width:3px;height:42px;}
.lf-dock-resizer-bottom{grid-column:1 / 6;grid-row:3;cursor:row-resize;}
.lf-dock-resizer-bottom::after{width:42px;height:3px;}
.lf-dock-collapsed{z-index:4;border:0;background:var(--panel2);color:var(--accent);font:inherit;font-size:9px;letter-spacing:.12em;cursor:pointer;}
.lf-dock-collapsed-left{grid-column:1;grid-row:1 / 3;writing-mode:vertical-rl;transform:rotate(180deg);border-right:1px solid var(--line2);}
.lf-dock-collapsed-right{grid-column:5;grid-row:1 / 3;writing-mode:vertical-rl;border-left:1px solid var(--line2);}
.lf-dock-collapsed-bottom{grid-column:1 / 6;grid-row:4;border-top:1px solid var(--line2);}
.lf-dock-collapsed:hover{background:var(--tint2);color:var(--strong);}
/* Modeless tear-off panels remain in the stable panel layer. Bounds and stack
   order are supplied as inline layout state; these classes own their chrome. */
.lf-floating-panel{position:absolute!important;display:flex;flex-direction:column;min-width:220px;min-height:132px;max-width:calc(100% - 16px);max-height:calc(100% - 16px);padding:0;overflow:hidden;border:1px solid var(--line2);background:var(--panel);box-shadow:0 12px 36px rgba(0,0,0,.48),0 0 0 1px color-mix(in srgb,var(--accent) 8%,transparent);z-index:var(--lf-floating-z,20);}
.lf-floating-panel[hidden]{display:none!important;}
.lf-floating-panel-active,.lf-floating-panel:focus-within{border-color:color-mix(in srgb,var(--accent) 68%,var(--line2));box-shadow:0 14px 42px rgba(0,0,0,.56),0 0 14px color-mix(in srgb,var(--accent) 18%,transparent);}
.lf-floating-panel-minimized{display:none!important;}
.lf-floating-panel-titlebar{display:flex;align-items:center;flex:none;min-width:0;height:32px;border-bottom:1px solid var(--line2);background:var(--panel2);color:var(--txt2);cursor:move;touch-action:none;user-select:none;}
.lf-floating-panel-titlebar[hidden],.lf-floating-panel-resizer[hidden]{display:none!important;}
.lf-floating-panel-titlebar:hover{background:var(--tint2);}
.lf-floating-panel-title{min-width:0;flex:1;overflow:hidden;padding:0 9px;font-size:9px;font-weight:600;letter-spacing:.1em;text-overflow:ellipsis;text-transform:uppercase;white-space:nowrap;}
.lf-floating-panel-active .lf-floating-panel-title,.lf-floating-panel:focus-within .lf-floating-panel-title{color:var(--accent);}
.lf-floating-panel-actions{display:flex;align-self:stretch;flex:none;border-left:1px solid var(--line2);}
.lf-floating-panel-actions button{width:30px;min-width:30px;padding:0;border:0;border-left:1px solid var(--line2);background:transparent;color:var(--txt3);font:inherit;font-size:10px;cursor:pointer;}
.lf-floating-panel-actions button:first-child{border-left:0;}
.lf-floating-panel-actions button:hover{background:var(--tint2);color:var(--strong);}
.lf-floating-panel-actions button:disabled{cursor:wait;opacity:.55;}
.lf-floating-panel-content{position:relative;display:flex;flex:1;min-width:0;min-height:0;overflow:auto;padding:12px;background:var(--base);}
.lf-floating-panel-content>*{min-width:0;min-height:0;}
.lf-floating-panel.lf-dock-panel-flush .lf-floating-panel-content{overflow:hidden;padding:0;}
.lf-floating-panel-resizer{position:absolute;right:0;bottom:0;z-index:2;width:22px;height:22px;border:0;background:transparent;color:var(--txt3);cursor:nwse-resize;touch-action:none;}
.lf-floating-panel-resizer::before,.lf-floating-panel-resizer::after{content:"";position:absolute;right:4px;bottom:4px;width:10px;height:1px;background:currentColor;transform:rotate(-45deg);transform-origin:right center;}
.lf-floating-panel-resizer::before{right:7px;bottom:4px;width:6px;}
.lf-floating-panel-resizer:hover,.lf-floating-panel-resizer:focus-visible{color:var(--accent);background:color-mix(in srgb,var(--accent) 8%,transparent);}
.lf-floating-minimized-tray{position:absolute;left:50%;bottom:8px;z-index:1000;display:flex;align-items:stretch;max-width:calc(100% - 20px);min-height:30px;overflow-x:auto;transform:translateX(-50%);border:1px solid var(--line2);background:color-mix(in srgb,var(--panel2) 94%,transparent);box-shadow:0 8px 24px rgba(0,0,0,.4);backdrop-filter:blur(6px);}
.lf-floating-minimized-tray-label{display:flex;align-items:center;flex:none;padding:0 8px;border-right:1px solid var(--line2);color:var(--txt3);font-size:8px;letter-spacing:.12em;text-transform:uppercase;}
.lf-floating-minimized-tray-item{flex:none;max-width:190px;padding:0 10px;border:0;border-right:1px solid var(--line2);background:transparent;color:var(--txt2);font:inherit;font-size:9px;letter-spacing:.06em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer;}
.lf-floating-minimized-tray-item:last-child{border-right:0;}
.lf-floating-minimized-tray-item:hover{background:var(--tint2);color:var(--accent);}
.lf-floating-minimized-tray-item:disabled{cursor:wait;opacity:.55;}
/* Grid-layer drop targets do not intercept the pointer; the workspace drag
   controller chooses a region and only toggles the visual active state. */
.lf-dock-drop-target{position:relative;z-index:999;min-width:0;min-height:0;pointer-events:none;}
.lf-dock-drop-target::after{content:"";position:absolute;inset:6px;border:1px dashed var(--accent);background:color-mix(in srgb,var(--accent) 10%,transparent);box-shadow:inset 0 0 18px color-mix(in srgb,var(--accent) 10%,transparent);opacity:0;transform:scale(.985);transition:opacity .12s,transform .12s;}
.lf-dock-drop-target.is-active::after,.lf-dock-drop-target[data-drop-active="true"]::after{opacity:1;transform:scale(1);}
.lf-dock-drop-target-left{grid-column:1;grid-row:1 / 3;}
.lf-dock-drop-target-center{grid-column:3;grid-row:1 / 3;}
.lf-dock-drop-target-right{grid-column:5;grid-row:1 / 3;}
.lf-dock-drop-target-bottom{grid-column:1 / 6;grid-row:4 / 6;}
.lf-dock-drop-target-floating{position:absolute;inset:0;}
.lf-workspace-navigator{position:relative;display:flex;flex:none;min-width:0;min-height:0;border-right:1px solid var(--line2);background:var(--panel2);}
.lf-workspace-navigator-content{display:flex;flex:1;min-width:0;min-height:0;overflow:hidden;}
.lf-workspace-navigator-collapse{position:absolute;right:8px;top:4px;z-index:7;width:24px;height:24px;border:1px solid var(--line2);background:var(--panel);color:var(--txt2);font:inherit;cursor:pointer;}
.lf-workspace-navigator-collapse:hover{color:var(--accent);border-color:var(--line-cy);}
.lf-workspace-navigator-resizer{position:absolute;right:-5px;top:0;bottom:0;width:9px;z-index:6;display:flex;align-items:center;justify-content:center;cursor:col-resize;touch-action:none;}
.lf-workspace-navigator-resizer::after{content:"";width:3px;height:42px;border-radius:3px;background:var(--line-cy);}
.lf-workspace-navigator-resizer:hover::after,.lf-workspace-navigator-resizer:focus-visible::after{background:var(--accent);box-shadow:0 0 8px color-mix(in srgb,var(--accent) 55%,transparent);}
.lf-workspace-navigator-collapsed{width:34px;flex:none;display:flex;border-right:1px solid var(--line2);background:var(--panel2);}
.lf-workspace-navigator-collapsed button{width:100%;border:0;background:transparent;color:var(--accent);font:inherit;font-size:9px;letter-spacing:.12em;writing-mode:vertical-rl;cursor:pointer;}
.lf-workspace-navigator-collapsed button:hover{background:var(--tint2);color:var(--strong);}
/* Shared live scene index. It owns a bounded scroll region so a long manuscript
   never pushes the host's panel navigation out of reach. */
.lf-studio-scene-navigator{display:flex;flex:none;min-width:0;max-height:min(34vh,320px);flex-direction:column;margin:8px 10px;border:1px solid var(--line2);background:var(--tint);}
.lf-studio-scene-navigator-heading{display:flex;align-items:center;gap:7px;min-height:28px;padding:0 8px;border-bottom:1px solid var(--line2);color:var(--txt3);font-size:8px;letter-spacing:.16em;}
.lf-studio-scene-navigator-heading>span:nth-child(2){color:var(--accent);}
.lf-studio-structure-global-actions,.lf-studio-structure-group-actions{display:flex;align-items:center;gap:2px;}
.lf-studio-structure-global-actions{margin-left:auto;}
.lf-studio-structure-quiet-action{min-width:22px;padding:3px 4px;border:1px solid transparent;background:transparent;color:var(--txt3);font:inherit;font-size:7px;letter-spacing:.03em;cursor:pointer;}
.lf-studio-structure-quiet-action:hover,.lf-studio-structure-quiet-action:focus-visible{border-color:var(--line-cy);background:var(--tint2);color:var(--accent);outline:none;}
.lf-studio-structure-quiet-action[aria-disabled="true"]{cursor:default;opacity:.3;}
.lf-studio-scene-search-action{margin-left:auto;padding:3px 5px;border:1px solid var(--line2);background:transparent;color:var(--txt2);font:inherit;font-size:7px;letter-spacing:.04em;cursor:pointer;white-space:nowrap;}
.lf-studio-scene-search-action:hover{border-color:var(--line-cy);color:var(--accent);}
.lf-studio-scene-search-action[aria-disabled="true"]{cursor:wait;opacity:.58;}
.lf-studio-scene-filter{display:flex;align-items:center;gap:6px;padding:6px 7px;border-bottom:1px solid var(--line2);color:var(--txt3);font-size:7px;letter-spacing:.12em;}
.lf-studio-scene-filter input{width:100%;min-width:0;padding:4px 5px;border:1px solid var(--line2);background:var(--raised);color:var(--txt);font:inherit;font-size:9px;letter-spacing:0;outline:0;}
.lf-studio-scene-filter input::placeholder{color:var(--txt3);}
.lf-studio-structure-action-editor{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;padding:7px;border-bottom:1px solid var(--line-cy);background:var(--raised);color:var(--txt2);font-size:8px;}
.lf-studio-structure-action-editor>strong,.lf-studio-structure-action-editor>p,.lf-studio-structure-action-buttons{grid-column:1/-1;}
.lf-studio-structure-action-editor>strong{color:var(--accent);font-family:'Chakra Petch',sans-serif;font-size:9px;letter-spacing:.06em;text-transform:uppercase;}
.lf-studio-structure-action-editor>label{display:flex;min-width:0;flex-direction:column;gap:3px;color:var(--txt3);font-size:7px;letter-spacing:.08em;}
.lf-studio-structure-action-editor input,.lf-studio-structure-action-editor select{min-width:0;padding:4px 5px;border:1px solid var(--line2);background:var(--panel);color:var(--txt);font:inherit;font-size:9px;letter-spacing:0;outline:none;}
.lf-studio-structure-action-editor input:focus,.lf-studio-structure-action-editor select:focus{border-color:var(--line-cy);}
.lf-studio-structure-action-editor>p{margin:0;color:var(--txt2);font-size:8px;line-height:1.45;}
.lf-studio-structure-action-buttons{display:flex;justify-content:flex-end;gap:5px;}
.lf-studio-structure-action-buttons button{padding:4px 6px;border:1px solid var(--line2);background:transparent;color:var(--txt2);font:inherit;font-size:7px;cursor:pointer;}
.lf-studio-structure-action-buttons button[type="submit"]{border-color:var(--line-cy);color:var(--accent);}
.lf-studio-structure-action-buttons button:disabled{cursor:wait;opacity:.5;}
.lf-studio-structure-list{min-height:0;margin:0;padding:3px 0;overflow-y:auto;list-style:none;}
.lf-studio-structure-list ol{margin:0;padding:0;list-style:none;}
.lf-studio-structure-list li{margin:0;padding:0;}
.lf-studio-structure-list [hidden]{display:none;}
.lf-studio-structure-toggle{display:flex;width:100%;min-width:0;align-items:center;gap:6px;border:0;background:transparent;color:var(--txt2);font:inherit;text-align:left;cursor:pointer;}
.lf-studio-structure-toggle:hover{background:var(--tint2);color:var(--strong);}
.lf-studio-structure-toggle[aria-disabled="true"]{cursor:default;opacity:.68;}
.lf-studio-structure-group-row{display:flex;min-width:0;align-items:stretch;}
.lf-studio-structure-group-row>.lf-studio-structure-toggle{min-width:0;flex:1;}
.lf-studio-structure-group-actions{flex:none;padding-right:3px;opacity:.18;transition:opacity .12s ease;}
.lf-studio-structure-group-row:hover>.lf-studio-structure-group-actions,.lf-studio-structure-group-row:focus-within>.lf-studio-structure-group-actions{opacity:1;}
.lf-studio-structure-act-toggle{padding:6px 7px;border-bottom:1px solid color-mix(in srgb,var(--line2) 72%,transparent);font-family:'Chakra Petch',sans-serif;font-size:9px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;}
.lf-studio-structure-chapter-toggle{padding:5px 7px 5px 18px;font-size:8px;letter-spacing:.04em;}
.lf-studio-structure-number{min-width:25px;flex:none;color:var(--accent);font-family:'Chakra Petch',sans-serif;font-size:8px;text-align:right;}
.lf-studio-structure-name{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.lf-studio-structure-count{flex:none;color:var(--txt3);font-size:7px;}
.lf-studio-structure-scenes .lf-studio-scene-row{padding-left:27px;}
.lf-studio-structure-act>.lf-studio-structure-children>li>.lf-studio-scene-row{padding-left:17px;}
.lf-studio-scene-entry{position:relative;display:flex;min-width:0;align-items:stretch;}
.lf-studio-scene-entry[data-drag-source="true"]{opacity:.48;}
.lf-studio-scene-entry[data-drop-edge="before"]::before,.lf-studio-scene-entry[data-drop-edge="after"]::after{position:absolute;right:5px;left:5px;z-index:2;height:2px;background:var(--accent);box-shadow:0 0 7px color-mix(in srgb,var(--accent) 72%,transparent);content:"";pointer-events:none;}
.lf-studio-scene-entry[data-drop-edge="before"]::before{top:-1px;}
.lf-studio-scene-entry[data-drop-edge="after"]::after{bottom:-1px;}
.lf-studio-scene-row{display:flex;min-width:0;flex:1;align-items:center;gap:7px;padding:6px 7px;border:0;border-left:2px solid transparent;background:transparent;color:var(--txt2);font:inherit;text-align:left;cursor:pointer;}
.lf-studio-scene-row:hover{background:var(--tint2);color:var(--txt);}
.lf-studio-scene-row[aria-current="location"]{border-left-color:var(--accent);background:color-mix(in srgb,var(--accent) 10%,transparent);color:var(--strong);}
.lf-studio-scene-row[aria-disabled="true"]{cursor:wait;opacity:.58;}
.lf-studio-scene-move-handle{width:24px;flex:none;border:0;border-left:1px solid transparent;background:transparent;color:var(--txt3);font:inherit;font-size:10px;cursor:grab;}
.lf-studio-scene-move-handle:hover,.lf-studio-scene-move-handle:focus-visible,.lf-studio-scene-move-handle[aria-pressed="true"]{border-left-color:var(--line2);background:var(--tint2);color:var(--accent);outline:none;}
.lf-studio-scene-move-handle[aria-disabled="true"]{cursor:default;opacity:.35;}
.lf-studio-scene-move-handle:active{cursor:grabbing;}
.lf-studio-scene-delete-action{width:20px;flex:none;border-left-color:transparent;opacity:.15;}
.lf-studio-scene-entry:hover>.lf-studio-scene-delete-action,.lf-studio-scene-delete-action:focus-visible{opacity:1;}
.lf-studio-scene-placement-status{border-bottom:1px solid color-mix(in srgb,var(--accent) 32%,var(--line2));color:var(--txt2);line-height:1.45;}
.lf-studio-scene-position{width:22px;flex:none;color:var(--txt3);font-family:'Chakra Petch',sans-serif;font-size:9px;text-align:right;}
.lf-studio-scene-copy{display:flex;min-width:0;flex:1;flex-direction:column;gap:1px;}
.lf-studio-scene-title,.lf-studio-scene-meta{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.lf-studio-scene-title{font-size:10px;}
.lf-studio-scene-meta{color:var(--txt3);font-size:7.5px;}
.lf-studio-scene-state{width:10px;flex:none;color:var(--accent);font-size:8px;text-align:center;}
.lf-studio-scene-message{padding:9px;color:var(--txt3);font-size:8px;line-height:1.4;text-align:center;}
.lf-studio-scene-error{display:flex;align-items:center;gap:6px;border-bottom:1px solid color-mix(in srgb,var(--crimson) 45%,transparent);background:color-mix(in srgb,var(--crimson) 8%,transparent);color:var(--crimson);text-align:left;}
.lf-studio-scene-error span{min-width:0;flex:1;}
.lf-studio-scene-error button{padding:2px 4px;border:1px solid currentColor;background:transparent;color:inherit;font:inherit;font-size:7px;cursor:pointer;}
.lf-studio-scene-filter-notice{display:flex;align-items:center;gap:6px;border-bottom:1px solid var(--line2);background:var(--tint2);text-align:left;}
.lf-studio-scene-filter-notice span{min-width:0;flex:1;}
.lf-studio-scene-filter-notice button{padding:2px 4px;border:1px solid var(--line2);background:transparent;color:var(--accent);font:inherit;font-size:7px;cursor:pointer;}
@media (max-width:1280px){
  .lf-topbar{height:78px;display:grid;grid-template-columns:max-content max-content minmax(0,1fr);grid-template-rows:39px 39px;grid-template-areas:"brand format command" "adaptive layout status";column-gap:10px;row-gap:0;padding:0 10px;}
  .lf-topbar-brand{grid-area:brand;}
  .lf-topbar-format{grid-area:format;}
  .lf-topbar-command{grid-area:command;}
  .lf-topbar-adaptive{grid-area:adaptive;}
  .lf-topbar-layout{grid-area:layout;}
  .lf-topbar-status{grid-area:status;justify-self:end;}
}
@media (max-width:760px){
  .lf-floating-panel{min-width:min(220px,calc(100% - 16px));max-width:calc(100% - 8px);max-height:calc(100% - 8px);}
  .lf-floating-panel-titlebar{height:36px;}
  .lf-floating-panel-title{padding-inline:7px;}
  .lf-floating-panel-actions button{width:34px;min-width:34px;}
  .lf-floating-minimized-tray{right:4px;bottom:4px;left:4px;max-width:none;transform:none;}
  .lf-floating-minimized-tray-label{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0;}
}
@media (prefers-reduced-motion:reduce){
  .lf-shell *, .lf-shell *::before, .lf-shell *::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important;}
}
`;

export function ShellStyles() {
  return <style>{CSS}</style>;
}

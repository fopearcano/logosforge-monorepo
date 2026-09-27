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
/* Real Studio dock workspace. The panel layer uses display:contents so every
   opened panel keeps one stable DOM/React parent while its grid coordinates move. */
.lf-dock-workspace{position:relative;display:grid;flex:1;min-width:0;min-height:0;overflow:hidden;background:var(--base);}
.lf-dock-header{display:flex;align-items:stretch;min-width:0;min-height:0;border-bottom:1px solid var(--line2);background:var(--panel);z-index:4;}
.lf-dock-header-center{grid-column:1;grid-row:1;}
.lf-dock-header-right{grid-column:3;grid-row:1;border-left:1px solid var(--line2);}
.lf-dock-header-bottom{grid-column:1 / 4;grid-row:4;border-top:1px solid var(--line2);}
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
.lf-dock-panel-right{border-left:1px solid var(--line2);}
.lf-dock-panel-bottom{border-top:1px solid var(--line2);}
.lf-dock-panel-flush{padding:0;overflow:hidden;}
.lf-dock-panel[hidden]{display:none!important;}
.lf-dock-resizer{z-index:5;touch-action:none;display:flex;align-items:center;justify-content:center;background:transparent;}
.lf-dock-resizer::after{content:"";display:block;border-radius:3px;background:var(--line-cy);transition:background .12s,box-shadow .12s;}
.lf-dock-resizer:hover::after,.lf-dock-resizer:focus-visible::after{background:var(--accent);box-shadow:0 0 8px color-mix(in srgb,var(--accent) 55%,transparent);}
.lf-dock-resizer-right{grid-column:2;grid-row:1 / 3;cursor:col-resize;}
.lf-dock-resizer-right::after{width:3px;height:42px;}
.lf-dock-resizer-bottom{grid-column:1 / 4;grid-row:3;cursor:row-resize;}
.lf-dock-resizer-bottom::after{width:42px;height:3px;}
.lf-dock-collapsed{z-index:4;border:0;background:var(--panel2);color:var(--accent);font:inherit;font-size:9px;letter-spacing:.12em;cursor:pointer;}
.lf-dock-collapsed-right{grid-column:3;grid-row:1 / 3;writing-mode:vertical-rl;border-left:1px solid var(--line2);}
.lf-dock-collapsed-bottom{grid-column:1 / 4;grid-row:4;border-top:1px solid var(--line2);}
.lf-dock-collapsed:hover{background:var(--tint2);color:var(--strong);}
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
@media (prefers-reduced-motion:reduce){
  .lf-shell *, .lf-shell *::before, .lf-shell *::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important;}
}
`;

export function ShellStyles() {
  return <style>{CSS}</style>;
}

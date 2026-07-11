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
`;

export function ShellStyles() {
  return <style>{CSS}</style>;
}

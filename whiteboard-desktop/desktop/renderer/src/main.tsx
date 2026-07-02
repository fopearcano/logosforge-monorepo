import React from 'react';
import ReactDOM from 'react-dom/client';

import { App } from './App';
import './styles/app.css';
import { applyStoredTheme } from './styles/themes/customThemeStorage';
import { ThemeProvider } from './styles/themes/ThemeProvider';

// Apply the persisted theme before React renders → no theme flash on startup.
applyStoredTheme();

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);

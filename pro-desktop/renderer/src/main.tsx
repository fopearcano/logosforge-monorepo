import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { applySkinPreference, readSkinPreference } from './skinPreference';
import './styles.css';

// Apply before React mounts so a persisted Paper/Lamplit workspace never
// flashes the Forge palette during startup.
applySkinPreference(readSkinPreference());

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

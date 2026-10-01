import { useMemo } from 'react';
import {
  StudioOmnibox,
  createCommandRegistry,
  type CommandDescriptor,
  type CommandRegistry,
  type OmniboxPanel,
  type StudioNavigationOptions,
} from '@logosforge/pro-shared-ui';
import type { ProjectDTO } from '@logosforge/ui-contracts';

/** Backward-compatible name for App.tsx; new callers can import CommandDescriptor directly. */
export type Command = CommandDescriptor;

/** Desktop host adapter for the shared desktop/browser Studio omnibox. */
export function CommandPalette({
  open,
  onClose,
  onError,
  commands,
  registry,
  panels,
  projects,
  recentProjectIds,
  onNavigate,
  onSelectProject,
}: {
  open: boolean;
  onClose: () => void;
  onError?: (error: unknown, label: string) => void;
  /** Existing integration path. A registry is created from this array. */
  commands?: readonly CommandDescriptor[];
  /** Preferred integration path. When present, it takes precedence over commands. */
  registry?: CommandRegistry;
  panels: readonly OmniboxPanel[];
  projects: readonly ProjectDTO[];
  recentProjectIds?: readonly number[];
  onNavigate(panelId: string, options?: StudioNavigationOptions): Promise<boolean>;
  onSelectProject(projectId: number): Promise<boolean>;
}) {
  const activeRegistry = useMemo(
    () => registry ?? createCommandRegistry(commands ?? []),
    [commands, registry],
  );

  return (
    <StudioOmnibox
      open={open}
      onClose={onClose}
      onError={onError}
      registry={activeRegistry}
      panels={panels}
      projects={projects}
      recentProjectIds={recentProjectIds}
      onNavigate={onNavigate}
      onSelectProject={onSelectProject}
    />
  );
}

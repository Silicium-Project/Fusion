export type PackageChannel = 'dev' | 'prod';
export type PackageManager = 'apt' | 'dnf';
export interface RepositoryCommands {
  setup: string;
  install: string;
  update: string;
  diagnose: string;
  ca: string;
}
export const PACKAGE_BASES: Readonly<Record<PackageChannel, string>>;
export function repositoryCommands(
  manager: PackageManager,
  channel: PackageChannel,
  options?: { baseURL?: string; testTransport?: boolean },
): RepositoryCommands;

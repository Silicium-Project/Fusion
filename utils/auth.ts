import { jwtDecode } from 'jwt-decode';

// Only a UI expiry check. The API remains responsible for verifying the signature.
export function tokenExpiry(token: unknown, now = Date.now()): Date | undefined {
  if (typeof token !== 'string' || !token) return;
  try {
    const { exp } = jwtDecode<{ exp?: number }>(token);
    if (typeof exp !== 'number' || !Number.isFinite(exp)) return;
    const expires = new Date(exp * 1000);
    return Number.isFinite(expires.getTime()) && expires.getTime() > now ? expires : undefined;
  } catch { return; }
}

export function authErrorMessage(error: unknown): string {
  const failure = error as { data?: { message?: unknown }; status?: number; statusCode?: number };
  if (typeof failure?.data?.message === 'string') return failure.data.message;
  const status = failure?.statusCode ?? failure?.status;
  if (status === 401) return 'Identifiant ou mot de passe incorrect.';
  if (status === 409) return 'Cette adresse e-mail ou ce nom d’utilisateur est déjà utilisé.';
  if (status === 400) return 'Vérifiez les informations du formulaire.';
  return 'Le service est indisponible. Réessayez plus tard.';
}

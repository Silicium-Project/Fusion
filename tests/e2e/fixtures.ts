import type { Page } from '@playwright/test';

export const token = (exp = Math.floor(Date.now() / 1000) + 900) => `header.${Buffer.from(JSON.stringify({ exp, role: 'user' })).toString('base64url')}.signature`;

export const user = { id: 1, username: 'luis', firstName: 'Luis', lastName: 'Fernandes', email: 'luis@example.test', role: 'user', createdAt: '2026-09-01T10:00:00Z' };

export const job = {
  id: 1, title: 'Rendu architecture', description: 'Validation du mockup final', workload: 'raytracer', priority: 'normal',
  fragmentCount: 4, status: 'completed', siliciumJobId: 'site-render-functional-1', billableWorkUnits: 4200,
  computeReceiptHash: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', createdAt: '2026-09-06T08:00:00Z',
  startedAt: '2026-09-06T08:01:00Z', completedAt: '2026-09-06T08:03:00Z',
};

export const dashboard = {
  job, resultReady: false, resultUrl: '/jobs/1/result', diagnostics: {},
  summary: { success: true, stage: 'completed', fragmentCount: 4, image: { width: 1920, height: 1080 }, fragments: [0, 1, 2, 3].map(fragment_index => ({ fragment_index, status: 'verified', stage: 'verify', handled_by: `worker-${fragment_index % 2}` })), nodeRuns: [] },
  devnet: { enabled: true, ok: true, status: 'confirmed', programId: 'program-functional', rpc: 'https://api.devnet.solana.com', signatures: ['signature-functional'] },
};

export async function mockAPI(page: Page) {
  await page.route('**/downloads/update-manifest.json', route => route.fulfill({ json: { generated_utc: '2026-09-06T08:00:00Z', channels: { prod: { version: '1.0.0' }, dev: { version: '1.1.0-dev.2' } } } }));
  await page.route(/^https?:\/\/[^/]+\/api\/.*$/, route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/status')) return route.fulfill({ json: { status: 'operational', checkedAt: '2026-09-06T08:00:00Z', backend: { status: 'operational', database: 'operational' }, network: { status: 'operational', peers: 3, activePeers: 3, outdatedPeers: 1 }, blockchain: { status: 'operational', network: 'devnet', configured: true, programId: 'program-functional' } } });
    if (path.endsWith('/user')) return route.fulfill({ json: user });
    if (path.endsWith('/jobs/1/dashboard')) return route.fulfill({ json: dashboard });
    if (path.endsWith('/jobs/network/peers')) return route.fulfill({ json: { peers: [{ node_id: 'orchestrator-1', version_status: 'server', outdated: false }, { node_id: 'worker-1', node_roles: ['resource'], app_version: '1.0.0', release_channel: 'prod', version_status: 'current', outdated: false }, { node_id: 'worker-2', node_roles: ['verify'], app_version: '0.9.0', release_channel: 'prod', version_status: 'outdated', outdated: true }] } });
    if (path.endsWith('/jobs/network/tasks')) return route.fulfill({ json: { active: [], recent: [], workloads: [{ work_id: 'site-render-functional-1', workload: 'raytracer', status: 'completed', total: 4, completed: 4, failed: 0, active: 0, updated_at: '2026-09-06T08:03:00Z', subtasks: [] }] } });
    if (path.endsWith('/jobs') && request.method() === 'GET') return route.fulfill({ headers: { 'x-total-count': '1', 'x-page': '1', 'x-page-size': '20', 'access-control-expose-headers': 'x-total-count,x-page,x-page-size' }, json: [job] });
    if (path.endsWith('/jobs') && request.method() === 'POST') return route.fulfill({ status: 202, json: job });
    if (path.endsWith('/jobs/1/cancel')) return route.fulfill({ status: 202, json: { ...job, status: 'cancelled' } });
    return route.fulfill({ status: 404, json: { message: `No mock for ${request.method()} ${path}` } });
  });
}

export async function authenticate(page: Page) {
  await page.context().addCookies([
    { name: 'auth_token', value: token(), domain: '127.0.0.1', path: '/' },
    { name: 'refresh_token', value: token(Math.floor(Date.now() / 1000) + 86_400), domain: '127.0.0.1', path: '/' },
  ]);
}

import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { authenticate, dashboard, job, mockAPI } from './fixtures';

test.beforeEach(async ({ page }) => { await mockAPI(page); await authenticate(page); });

for (const pageCase of [
  { path: '/dashboard', heading: 'Accueil' }, { path: '/jobs', heading: 'Mes projets' },
  { path: '/jobs/new', heading: 'Lancer un calcul' }, { path: '/jobs/1', heading: 'Rendu architecture' },
  { path: '/network', heading: 'Santé du réseau' }, { path: '/nodes', heading: 'Machines' }, { path: '/workloads', heading: 'Types de calcul' }, { path: '/profile', heading: 'Paramètres' },
]) {
  test(`${pageCase.path} renders without browser errors`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pageCase.path);
    await expect(page.getByRole('heading', { name: pageCase.heading, exact: true }).first()).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test('a job can be submitted and opens its canonical detail route', async ({ page }) => {
  await page.goto('/jobs/new');
  const continueButton = page.getByRole('button', { name: 'Continuer' });
  await expect(continueButton).toBeVisible();
  await page.getByPlaceholder('Ex. Rendu intérieur — version 4').fill('Rendu architecture');
  // Raytracer jobs open on the scene editor; an existing .cfg is imported.
  await page.getByRole('radio', { name: /Importer un fichier/ }).click();
  await page.locator('input[type=file]').setInputFiles({
    name: 'demo-scene.cfg',
    mimeType: 'text/plain',
    buffer: Buffer.from(`# Site raytracer fixture
camera :
{
  resolution = { width = 32 height = 20 }
  position = { x = 0 y = 0 z = 0 }
}
`),
  });
  // Checked before sending: no object and no light are warnings, not errors.
  await expect(page.getByText('2 points à vérifier')).toBeVisible();
  await continueButton.click();
  await page.getByRole('button', { name: 'Continuer' }).click();
  const submit = page.getByRole('button', { name: 'Lancer le calcul' });
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(page).toHaveURL(url => url.pathname === '/jobs/1');
  await expect(page.getByRole('heading', { name: 'Rendu architecture' })).toBeVisible();
});

test('a scene composed in the editor is sent as a .cfg file', async ({ page }) => {
  let sent = '';
  await page.route('**/api/jobs', route => {
    if (route.request().method() !== 'POST') return route.fallback();
    sent = route.request().postData() || '';
    return route.fulfill({ status: 202, json: job });
  });
  await page.goto('/jobs/new');
  // Without a name, "Continue" is disabled and says why.
  await expect(page.getByRole('button', { name: 'Continuer' })).toBeDisabled();
  await expect(page.getByText('Donnez un nom à votre projet pour continuer.')).toBeVisible();
  await page.getByPlaceholder('Ex. Rendu intérieur — version 4').fill('Mon studio');
  await expect(page.getByRole('button', { name: 'Continuer' })).toBeEnabled();
  await page.getByRole('button', { name: /Studio/ }).click();
  await expect(page.getByText('Modèle « Studio » chargé.')).toBeVisible();
  await expect(page.getByRole('img', { name: /Aperçu de la scène/ })).toBeVisible();
  await page.getByRole('button', { name: 'Continuer' }).click();
  await page.getByRole('button', { name: 'Continuer' }).click();
  await expect(page.getByText('mon-studio.cfg')).toBeVisible();
  await expect(page.getByText('1080 × 1080 · 3 objets · 2 lumières')).toBeVisible();
  await page.getByRole('button', { name: 'Lancer le calcul' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/jobs/1');
  expect(sent).toContain('filename="mon-studio.cfg"');
  expect(sent).toContain('resolution = { width = 1080 height = 1080 }');
  expect(sent).toContain('sphere = {');
});

test('the photorealistic quality sends an engine-2 scene to the network', async ({ page }) => {
  let sent = '';
  await page.route('**/api/jobs', route => {
    if (route.request().method() !== 'POST') return route.fallback();
    sent = route.request().postData() || '';
    return route.fulfill({ status: 202, json: job });
  });
  await page.goto('/jobs/new');
  await page.getByPlaceholder('Ex. Rendu intérieur — version 4').fill('Miroirs photo');
  await page.getByRole('button', { name: /Miroirs/ }).click();
  await page.getByRole('tab', { name: 'Rendu' }).click();
  await page.getByLabel('Qualité du rendu final').selectOption('photo');
  await expect(page.getByText(/256 rayons par pixel, éclairage global/)).toBeVisible();
  await page.getByRole('button', { name: 'Continuer' }).click();
  await page.getByRole('button', { name: 'Continuer' }).click();
  await expect(page.getByText('1280 × 720 · 5 objets · 2 lumières · 256 rayons par pixel')).toBeVisible();
  await page.getByRole('button', { name: 'Lancer le calcul' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/jobs/1');
  expect(sent).toContain('mode = path');
  expect(sent).toContain('samples = 256');
  expect(sent).toContain('type = metal roughness = 0');
});

test('an imported scene with errors is blocked until it is fixed in the editor', async ({ page }) => {
  await page.goto('/jobs/new');
  await page.getByPlaceholder('Ex. Rendu intérieur — version 4').fill('Scène cassée');
  await page.getByRole('radio', { name: /Importer un fichier/ }).click();
  await page.locator('input[type=file]').setInputFiles({
    name: 'broken.cfg',
    mimeType: 'text/plain',
    buffer: Buffer.from('camera : {\n  resolution = { height = 32 width = 64 }\n};\nprimitives : {\n  sphere = { x = 5 radus = 1 }\n};\nlights : { point = { x = 1 } };\n'),
  });
  await expect(page.getByText('1 erreur à corriger')).toBeVisible();
  await expect(page.getByText('Vouliez-vous dire « radius » ?')).toBeVisible();
  const continueButton = page.getByRole('button', { name: 'Continuer' });
  await expect(continueButton).toBeDisabled();
  await page.getByRole('button', { name: 'Ouvrir dans l’éditeur' }).click();
  await expect(page.getByRole('img', { name: /Aperçu de la scène/ })).toBeVisible();
  await expect(continueButton).toBeEnabled();
});

test('an advanced scene is checked in the browser and sent as it is', async ({ page }) => {
  await page.goto('/jobs/new');
  await page.getByPlaceholder('Ex. Rendu intérieur — version 4').fill('Scène avancée');
  await page.getByRole('radio', { name: /Importer un fichier/ }).click();
  await page.locator('input[type=file]').setInputFiles({
    name: 'advanced.cfg',
    mimeType: 'text/plain',
    buffer: Buffer.from([
      'render : { mode = path samples = 64 }',
      'camera : { resolution = { width = 320 height = 180 } position = { x = 0 y = 0 z = 1 } look_at = { x = 5 y = 0 z = 0 } }',
      'materials : { material = { name = verre type = glass } }',
      'primitives : {',
      '  sphere = { x = 5 radius = 1 material = verre }',
      '  box = { translate = { x = 6 y = 2 } rotate = { z = 30 } type = metal roughness = 0.2 }',
      '  plane = { z = -1 type = diffuse }',
      '}',
      'lights : { area = { x = 2 y = -3 z = 4 radius = 0.5 intensity = 300 } }',
      'animation : { frames = 24 fps = 24 }',
    ].join('\n')),
  });
  await expect(page.getByText('Fichier de scène valide')).toBeVisible();
  await expect(page.getByText('320 × 180 · 2 objets · 1 lumière · 6 triangles · 64 rayons par pixel')).toBeVisible();
  await expect(page.getByText(/ne sait pas encore montrer les animations/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Ouvrir dans l’éditeur' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Continuer' })).toBeEnabled();
});

test('a scene with glass, boxes, area lights and an aimed camera opens in the editor', async ({ page }) => {
  let sent = '';
  await page.route('**/api/jobs', route => {
    if (route.request().method() !== 'POST') return route.fallback();
    sent = route.request().postData() || '';
    return route.fulfill({ status: 202, json: job });
  });
  await page.goto('/jobs/new');
  await page.getByPlaceholder('Ex. Rendu intérieur — version 4').fill('Scène verre');
  await page.getByRole('radio', { name: /Importer un fichier/ }).click();
  await page.locator('input[type=file]').setInputFiles({
    name: 'verre.cfg',
    mimeType: 'text/plain',
    buffer: Buffer.from([
      'render : { mode = path samples = 64 }',
      'camera : { resolution = { width = 320 height = 180 } position = { x = 0 y = 0 z = 1 } look_at = { x = 5 y = 0 z = 0 } }',
      'materials : { material = { name = verre type = glass } }',
      'primitives : {',
      '  sphere = { x = 5 radius = 1 material = verre }',
      '  box = { translate = { x = 6 y = 2 } rotate = { z = 30 } type = metal roughness = 0.2 }',
      '  plane = { z = -1 type = diffuse }',
      '}',
      'lights : { area = { x = 2 y = -3 z = 4 radius = 0.5 intensity = 300 } }',
    ].join('\n')),
  });
  await page.getByRole('button', { name: 'Ouvrir dans l’éditeur' }).click();
  await expect(page.getByRole('img', { name: /Aperçu de la scène/ })).toBeVisible();
  await expect(page.getByRole('tab', { name: /Objets/ })).toContainText('3');
  await expect(page.getByRole('button', { name: /^Boîte 1/ })).toBeVisible();
  await expect(page.getByText(/Aperçu terminé|Aperçu en cours/)).toBeVisible();
  await page.getByRole('button', { name: 'Continuer' }).click();
  await page.getByRole('button', { name: 'Continuer' }).click();
  await expect(page.getByText('320 × 180 · 3 objets · 1 lumière · 256 rayons par pixel')).toBeVisible();
  await page.getByRole('button', { name: 'Lancer le calcul' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/jobs/1');
  expect(sent).toContain('type = glass');
  expect(sent).toContain('box = {');
  expect(sent).toContain('area = {');
});

test('a failed job keeps the worker traceback visible', async ({ page }) => {
  await page.route('**/api/jobs/1/dashboard', route => route.fulfill({
    json: {
      ...dashboard,
      job: { ...job, status: 'failed', errorMessage: 'RuntimeError: worker failed\nTraceback (most recent call last):\n  worker.py:42\nValueError: bad scene' },
      summary: { ...dashboard.summary, success: false, stage: 'failed', failureDetail: 'RuntimeError: worker failed\nTraceback (most recent call last):\n  worker.py:42\nValueError: bad scene' },
    },
  }));
  await page.goto('/jobs/1');
  const notice = page.locator('.notice--danger');
  await expect(notice).toContainText('RuntimeError: worker failed');
  await expect(notice).toContainText('worker.py:42');
  await expect(notice).toContainText('ValueError: bad scene');
});

test('a SHA-256 job shows its chunks and its hash instead of an image', async ({ page }) => {
  const hashJob = { ...job, title: 'Empreinte archive', workload: 'calcul/integrity/sha256', fragmentCount: 2 };
  const fragments = [0, 1].map(fragment_index => ({ fragment_index, status: 'completed', handled_by: `worker-${fragment_index}` }));
  const report = {
    workload: 'calcul/integrity/sha256', algorithm: 'sha256', size_bytes: 10, chunk_count: 2, chunk_list_sha256: 'c'.repeat(64), input_hash: null,
    chunks: [{ index: 0, offset: 0, length: 5, sha256: 'a'.repeat(64) }, { index: 1, offset: 5, length: 5, sha256: 'b'.repeat(64) }],
  };
  await page.route('**/api/jobs/1/dashboard', route => route.fulfill({ json: { ...dashboard, job: hashJob, resultReady: true, summary: { success: true, fragmentCount: 2, fragments } } }));
  await page.route('**/api/jobs/1/result', route => route.fulfill({ json: report }));
  await page.goto('/jobs/1');
  await expect(page.getByText('Empreinte de la liste des morceaux')).toBeVisible();
  await expect(page.getByText('c'.repeat(64))).toBeVisible();
  await expect(page.getByText('b'.repeat(64))).toBeVisible();
  await expect(page.locator('.render-preview')).toHaveCount(0);
  await expect(page.getByText('2 terminés, 0 actifs, 0 en erreur.')).toBeVisible();
});

test('the project list exposes the submit path', async ({ page }) => {
  await page.goto('/jobs');
  const createLink = page.getByRole('main').getByRole('link', { name: 'Nouveau calcul' });
  await expect(createLink).toBeVisible();
  await createLink.click();
  await expect(page).toHaveURL(url => url.pathname === '/jobs/new');
});

test('connected mobile navigation remains usable and does not overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dashboard');
  const navigation = page.getByRole('navigation', { name: 'Navigation mobile de l’application' });
  await expect(navigation.getByRole('link', { name: 'Mes projets' })).toBeVisible();
  await navigation.getByRole('link', { name: 'Nouveau calcul' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/jobs/new');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('mobile navigation stays in flow instead of obscuring content', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/nodes');
  const layout = await page.evaluate(() => {
    const navigation = document.querySelector('.mobile-nav');
    const main = document.querySelector('.app-layout__main');
    if (!navigation || !main) return null;
    const navigationRect = navigation.getBoundingClientRect();
    const mainRect = main.getBoundingClientRect();
    return { position: getComputedStyle(navigation).position, navigationBottom: navigationRect.bottom, mainTop: mainRect.top };
  });
  expect(layout).not.toBeNull();
  expect(layout?.position).not.toBe('fixed');
  expect(layout?.navigationBottom).toBeLessThanOrEqual((layout?.mainTop || 0) + 1);
});

test('logout clears the session and returns to the public homepage', async ({ page }) => {
  await page.goto('/profile');
  await page.getByRole('button', { name: 'Déconnexion' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/');
  const cookies = await page.context().cookies();
  expect(cookies.some(cookie => cookie.name === 'auth_token' || cookie.name === 'refresh_token')).toBe(false);
});

test('documents are sent for a document search only after the sharing consent', async ({ page }) => {
  let sent = '';
  await page.route('**/api/jobs', route => {
    if (route.request().method() !== 'POST') return route.fallback();
    sent = route.request().postData() || '';
    return route.fulfill({ status: 202, json: { ...job, workload: 'ai/embedding/multilingual-e5-small' } });
  });
  await page.goto('/jobs/new?workload=documents');
  await page.getByPlaceholder('Ex. Rendu intérieur — version 4').fill('Cours de droit');
  await page.locator('input[type=file]').setInputFiles([
    { name: 'contrat.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 contrat') },
    { name: 'notes.md', mimeType: 'text/markdown', buffer: Buffer.from('# Notes') },
  ]);
  await expect(page.getByText('2 documents prêts')).toBeVisible();
  const continueButton = page.getByRole('button', { name: 'Continuer' });
  await expect(continueButton).toBeDisabled();
  await page.getByText('J’ai compris que les machines du réseau lisent le texte de mes documents.').click();
  await continueButton.click();
  await expect(page.locator('.advanced-options')).toHaveCount(0);
  await page.getByRole('button', { name: 'Continuer' }).click();
  await page.getByRole('button', { name: 'Lancer le calcul' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/jobs/1');
  expect(sent).toContain('ai/embedding/multilingual-e5-small');
  expect(sent).toContain('name="acknowledge_sharing"\r\n\r\n1');
  expect(sent).toContain('filename="contrat.pdf"');
  expect(sent).toContain('filename="notes.md"');
  expect(sent).not.toContain('name="fragment_count"');
});

test('a finished document search answers questions with the source of each passage', async ({ page }) => {
  const documentJob = { ...job, title: 'Cours de droit', workload: 'ai/embedding/multilingual-e5-small', collectionId: 'site-docs-1' };
  await page.route('**/api/jobs/1/dashboard', route => route.fulfill({ json: {
    ...dashboard, job: documentJob, resultReady: true,
    summary: { success: true, fragmentCount: 1, fragments: [{ fragment_index: 0, status: 'completed', items: 40 }] },
    documentIndex: { passageCount: 40, documents: [{ name: 'contrat.pdf', pages: 12, passages: 40 }], skipped: [{ name: 'scan.pdf', reason: 'no_text' }] },
  } }));
  let asked = '';
  await page.route('**/api/jobs/1/search?*', route => {
    asked = new URL(route.request().url()).searchParams.get('q') || '';
    return route.fulfill({ json: { query: asked, searchedJobs: 1, hits: [{ jobId: 1, passageId: 7, document: 'contrat.pdf', page: 12, section: 'Contrat › Article 6 - Résiliation', text: 'Le client peut demander la résiliation du contrat par lettre recommandée.', score: 0.87 }] } });
  });
  await page.goto('/jobs/1');
  await expect(page.getByText('1 document lu, 40 passages.', { exact: false })).toBeVisible();
  await expect(page.getByText('scan.pdf')).toBeVisible();
  await page.getByPlaceholder('Posez votre question, par exemple : comment résilier le contrat ?').fill('comment résilier le contrat ?');
  await page.getByRole('button', { name: 'Chercher' }).click();
  await expect(page.getByText('contrat.pdf — page 12')).toBeVisible();
  await expect(page.getByText('Contrat › Article 6 - Résiliation')).toBeVisible();
  await expect(page.locator('mark', { hasText: 'résiliation' })).toBeVisible();
  expect(asked).toBe('comment résilier le contrat ?');
  await expect(page.getByRole('link', { name: 'Ajouter des documents' })).toHaveAttribute('href', /collection=site-docs-1/);
  await expect(page.getByRole('button', { name: 'Télécharger', exact: true })).toHaveCount(0);
});

test('a document search lists the documents searched and scrolls past the first five passages', async ({ page }) => {
  const documentJob = { ...job, title: 'Cours de droit', workload: 'ai/embedding/multilingual-e5-small', collectionId: 'site-docs-1' };
  const collectionDocuments = Array.from({ length: 10 }, (_, index) => ({ jobId: 1, name: `dossier/chapitre-${String(index + 1).padStart(2, '0')}.pdf`, pages: index + 2, passages: 10 }));
  await page.route('**/api/jobs/1/dashboard', route => route.fulfill({ json: {
    ...dashboard, job: documentJob, resultReady: true,
    summary: { success: true, fragmentCount: 1, fragments: [{ fragment_index: 0, status: 'completed', items: 100 }] },
    documentIndex: { passageCount: 100, documents: collectionDocuments.slice(0, 1), skipped: [] },
    collectionDocuments,
  } }));
  const text = 'Le préavis est d’un mois pour un logement meublé. '.repeat(12);
  let asked = 0;
  await page.route('**/api/jobs/1/search?*', route => {
    asked = Number(new URL(route.request().url()).searchParams.get('k'));
    return route.fulfill({ json: { searchedJobs: 2, hits: Array.from({ length: 12 }, (_, index) => ({ jobId: 1, passageId: index, document: 'dossier/chapitre-01.pdf', page: index + 1, text, score: 0.9 - index / 100 })) } });
  });
  await page.goto('/jobs/1');
  const sources = page.getByRole('region', { name: /Recherche dans/ });
  await expect(sources).toContainText('10 documents');
  await expect(sources.getByRole('button')).toHaveCount(9); // 8 documents + "Voir les 10 documents"
  await sources.getByRole('button', { name: 'Voir les 10 documents' }).click();
  await expect(sources.getByRole('button', { name: /chapitre-10\.pdf/ })).toBeVisible();

  const before = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.getByPlaceholder('Posez votre question, par exemple : comment résilier le contrat ?').fill('quel est le préavis ?');
  await page.getByRole('button', { name: 'Chercher' }).click();
  const list = page.getByRole('list', { name: 'Passages trouvés' });
  await expect(list.getByRole('listitem')).toHaveCount(12);
  expect(asked).toBe(20);
  const box = await list.evaluate(element => ({ client: element.clientHeight, scroll: element.scrollHeight, overflow: getComputedStyle(element).overflowY }));
  expect(box.overflow).toBe('auto');
  expect(box.scroll).toBeGreaterThan(box.client);
  const fifth = await list.getByRole('listitem').nth(4).evaluate((item, ) => item.getBoundingClientRect().bottom - item.parentElement!.getBoundingClientRect().top);
  expect(Math.abs(fifth - box.client)).toBeLessThan(4);
  const after = await page.evaluate(() => document.documentElement.scrollHeight);
  expect(after - before).toBeLessThan(box.client + 200);
});

test('the site switches to English and German, and the API is asked in that language', async ({ page }) => {
  const languages: string[] = [];
  await page.route('**/api/jobs?*', async route => { languages.push(route.request().headers()['accept-language'] || ''); await route.fallback(); });
  await page.goto('/dashboard');
  await page.getByRole('button', { name: 'English' }).first().click();
  await expect(page.getByRole('heading', { name: 'Home', exact: true })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await page.goto('/jobs');
  await expect(page.getByRole('heading', { name: 'My projects', exact: true })).toBeVisible();
  await expect.poll(() => languages.at(-1)).toBe('en');
  await page.getByRole('button', { name: 'Deutsch' }).first().click();
  await expect(page.getByRole('heading', { name: 'Meine Projekte', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Meine Projekte', exact: true })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'de');
});

test('the job types page explains each type and offers its example file', async ({ page }) => {
  await page.goto('/workloads');
  for (const name of ['Rendu d’image', 'Empreinte SHA-256', 'Recherche dans mes documents']) {
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  }
  for (const file of ['silicium-demo-scene.cfg', 'silicium-hash-example.txt', 'silicium-documents-example.zip']) {
    const link = page.locator(`a[href="/examples/${file}"]`);
    await expect(link).toHaveAttribute('download', file);
    const response = await page.request.get(`/examples/${file}`);
    expect(response.ok()).toBe(true);
  }
  await page.locator('#sha256').getByRole('link', { name: 'Essayer avec ce type' }).click();
  await expect(page).toHaveURL(url => url.pathname === '/jobs/new' && url.searchParams.get('workload') === 'calcul/integrity/sha256');
  await expect(page.getByRole('combobox').first()).toHaveValue('calcul/integrity/sha256');
});

test('a completed job shows its blockchain trace and checks it against the chain', async ({ page }) => {
  // Trace written by the Go BackEnd; the browser recomputes it.
  const trace = JSON.parse(readFileSync(new URL('../fixtures/chain-trace.json', import.meta.url), 'utf8'));
  const signature = '5'.repeat(88);
  const devnet = {
    enabled: true, ok: true, status: 'anchored', programId: trace.program_id, rpc: 'https://api.devnet.solana.com', cluster: 'devnet',
    signatures: [signature], explorerUrl: `https://explorer.solana.com/tx/${signature}?cluster=devnet`,
    memo: trace.memo, merkleRoot: trace.merkle_root, finalSha256: trace.final_sha256, taskCount: trace.task_count, fragments: trace.fragments,
  };
  await page.route('**/api/jobs/1/dashboard', route => route.fulfill({ json: { ...dashboard, devnet } }));
  // The Solana RPC answers getTransaction with the anchored memo.
  await page.route('https://api.devnet.solana.com/**', route => route.fulfill({ json: { jsonrpc: '2.0', id: JSON.parse(route.request().postData() || '{}').id ?? 1, result: {
    slot: 1, blockTime: 1, version: 'legacy',
    meta: { err: null, fee: 5000, preBalances: [1, 1], postBalances: [1, 1], innerInstructions: [], logMessages: [], status: { Ok: null } },
    transaction: { signatures: [signature], message: {
      accountKeys: [{ pubkey: '11111111111111111111111111111111', signer: true, writable: true, source: 'transaction' }, { pubkey: trace.program_id, signer: false, writable: false, source: 'transaction' }],
      recentBlockhash: '11111111111111111111111111111111',
      instructions: [{ program: 'spl-memo', programId: trace.program_id, parsed: trace.memo, stackHeight: null }],
    } },
  } } }));
  await page.goto('/jobs/1');
  await expect(page.getByText('Ancrée sur Solana', { exact: true })).toBeVisible();
  await expect(page.getByText(trace.merkle_root)).toBeVisible();
  await expect(page.getByRole('link', { name: /5555/ })).toHaveAttribute('href', devnet.explorerUrl);
  await page.getByRole('button', { name: 'Vérifier depuis la blockchain' }).click();
  await expect(page.getByText('Trace intacte', { exact: true })).toBeVisible();
  await expect(page.getByText('La racine inscrite sur Solana correspond : 3 tâches vérifiées.')).toBeVisible();
  await expect(page.locator('.chain-trace__mark.is-valid')).toHaveCount(3);
});

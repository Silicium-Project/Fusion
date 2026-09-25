import assert from 'node:assert/strict';
import { setTimeout as wait } from 'node:timers/promises';
import { chromium } from '@playwright/test';

const baseURL = process.env.SILICIUM_INTEGRATION_URL || 'http://proxy';
const maxAttempts = 12;
let lastError;

for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const statusResponses = [];
  page.on('response', (response) => {
    try {
      if (new URL(response.url()).pathname === '/api/status') {
        statusResponses.push(`${response.status()} ${response.url()}`);
      }
    } catch {
      // Ignore malformed URLs reported by browser internals.
    }
  });

  try {
    const statusResponse = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/api/status' && response.status() === 200,
      { timeout: 15_000 },
    );
    await page.goto(baseURL, { waitUntil: 'domcontentloaded', timeout: 20_000 });
    await expectHomePage(page);
    const payload = await (await statusResponse).json();
    assert.equal(typeof payload.network, 'object', 'BackEnd /status must expose Network state');
    assert.equal(typeof payload.network.peers, 'number', 'Network state must originate from the Rust control API');
    console.log(`Integration path verified on attempt ${attempt}: browser -> proxy -> BackEnd -> Rust node.`);
    await browser.close();
    process.exit(0);
  } catch (error) {
    lastError = new Error(`attempt ${attempt}/${maxAttempts}: ${error.message}; /api/status responses: ${statusResponses.join(', ') || 'none'}`);
    await browser.close();
    if (attempt < maxAttempts) {
      await wait(2_000);
    }
  }
}

throw lastError;

async function expectHomePage(page) {
  await page.getByText('Calcul distribué, simplement').waitFor({ state: 'visible', timeout: 15_000 });
}

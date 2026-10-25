/** Render deployment configuration using disposable fixtures; never weaken production-required variables. */
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { root, run, readJson, Failure } from '../lib/process.mjs';
const temporary = mkdtempSync(resolve(tmpdir(), 'silicium-compose-fixture-'));
const channels = readJson(resolve(root, 'infra/release/channels.json')).channels;
const program = readFileSync(
  resolve(root, 'chain/solana/programs/solana-layer/src/lib.rs'),
  'utf8',
).match(/declare_id!\("([1-9A-HJ-NP-Za-km-z]+)"\)/)?.[1];
if (!program) throw new Failure('Fixture must use the declared public program ID');
let count = 0;
try {
  for (const [channel, meta] of Object.entries(channels)) {
    const config = resolve(temporary, channel);
    mkdirSync(config);
    for (const name of ['backend', 'frontend'])
      cpSync(resolve(root, `infra/env/${name}.example.env`), resolve(config, `${name}.env`));
    const images = Object.fromEntries(
      ['API', 'WEB', 'NETWORK'].map((name) => [
        `SILICIUM_${name}_IMAGE`,
        `ghcr.io/silicium-project/${name.toLowerCase()}@sha256:${'0'.repeat(64)}`,
      ]),
    );
    const env = {
      ...images,
      SILICIUM_CONFIG_DIR: config,
      SILICIUM_DATA_ROOT: resolve(config, 'data'),
      SILICIUM_COMPOSE_PROJECT_NAME: meta.compose_project,
      SILICIUM_RELEASE_CHANNEL: channel,
      SILICIUM_SOLANA_PROGRAM_ID: program,
      SILICIUM_RELEASE_ID: `${channel}-0.0.0-fixture`,
      SILICIUM_MANIFEST_DIGEST: '0'.repeat(64),
      SILICIUM_TURN_PASSWORD: 'fixture',
      SILICIUM_PROXY_BIND_ADDRESS: meta.proxy_bind_address,
      SILICIUM_PROXY_HTTP_PORT: String(meta.proxy_http_port),
      SILICIUM_PROXY_HTTPS_PORT: String(meta.proxy_https_port),
      SILICIUM_BACKEND_HTTP_PORT: String(meta.backend_http_port),
      SILICIUM_FRONTEND_HTTP_PORT: String(meta.frontend_http_port),
      SILICIUM_BACKEND_NETWORK_NAME: meta.backend_network_name,
      SILICIUM_FRONTEND_NETWORK_NAME: meta.frontend_network_name,
    };
    const rendered = JSON.parse(
      run(
        [
          ...(process.env.SILICIUM_COMPOSE_BINARY
            ? [process.env.SILICIUM_COMPOSE_BINARY]
            : ['docker', 'compose']),
          '--env-file',
          'infra/env/compose.example.env',
          '-f',
          'infra/compose/docker-compose.yml',
          'config',
          '--format',
          'json',
        ],
        { env },
      ).stdout,
    );
    if (
      rendered.name !== meta.compose_project ||
      Object.values(rendered.services).some((service) => service.build)
    )
      throw new Failure(
        'Deployment rendering reintroduced a build or changed its channel identity',
      );
    for (const [name, service] of [
      ['API', 'backend'],
      ['WEB', 'frontend'],
      ['NETWORK', 'reputation_bridge'],
    ])
      if (rendered.services[service].image !== images[`SILICIUM_${name}_IMAGE`])
        throw new Failure('Deployment must use explicit immutable images');
    if (
      Number(rendered.services.backend.ports[0].published) !== meta.backend_http_port ||
      Number(rendered.services.frontend.ports[0].published) !== meta.frontend_http_port
    )
      throw new Failure('Channel port isolation was lost');
    console.log(`ok ${++count} - isolated ${channel} Compose render, immutable images, no builds`);
  }
  console.log(`1..${count}\n# tests ${count}\n# pass ${count}`);
} finally {
  rmSync(temporary, { recursive: true, force: true });
}

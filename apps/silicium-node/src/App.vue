<template>
  <main class="shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Silicium Node</p>
        <h1>Votre PC rejoint le reseau</h1>
        <p class="subtitle">
          Une seule app pour installer le runtime, connecter la machine, suivre les travaux et garder
          l'historique local.
        </p>
      </div>
      <div class="status-pill" :class="{ online: status.running }">
        {{ status.running ? 'Node actif' : 'Node arrete' }}
      </div>
    </section>

    <section class="layout">
      <aside class="panel setup-panel">
        <div class="panel-head compact">
          <div>
            <h2>Installation</h2>
            <p>Beta locale, futur installateur autonome.</p>
          </div>
          <button class="ghost icon-button" @click="runChecks">Verifier</button>
        </div>

        <label>
          Dossier Silicium
          <input v-model="form.repoRoot" placeholder="C:\\Users\\...\\eipSilicium" />
        </label>
        <label>
          Orchestrateur
          <input v-model="form.orchestratorUrl" />
        </label>
        <label>
          Adresse annoncee
          <input v-model="form.advertiseHost" placeholder="IP locale ou publique" />
        </label>

        <div class="actions">
          <button @click="install">Installer / reparer</button>
          <button :disabled="status.running" @click="activateNode">Activer mon PC</button>
          <button class="ghost" :disabled="!status.running" @click="deactivateNode">Arreter</button>
        </div>

        <div class="check-list">
          <div v-for="check in checks" :key="check.name" class="check-row" :class="{ ok: check.ok }">
            <span>{{ check.ok ? 'ok' : 'x' }}</span>
            <div>
              <strong>{{ check.name }}</strong>
              <small>{{ check.detail || 'non disponible' }}</small>
            </div>
          </div>
        </div>
      </aside>

      <section class="main-stack">
        <section class="stats-grid">
          <article class="stat-card">
            <span>Mode actuel</span>
            <strong>{{ status.running ? 'Disponible' : 'Hors ligne' }}</strong>
            <small>{{ status.running ? 'Le reseau choisit calcul ou verification.' : 'Aucun travail accepte.' }}</small>
          </article>
          <article class="stat-card">
            <span>Roles reseau</span>
            <strong>{{ status.roles || 'compute,verify' }}</strong>
            <small>Selection automatique cote orchestration.</small>
          </article>
          <article class="stat-card">
            <span>Resultats locaux</span>
            <strong>{{ activity.knownResults }}</strong>
            <small>{{ activity.lastResult }}</small>
          </article>
          <article class="stat-card">
            <span>Stockage local</span>
            <strong>{{ formatBytes(activity.storageBytes) }}</strong>
            <small>Cache node et sorties de calcul.</small>
          </article>
        </section>

        <section class="panel">
          <div class="panel-head">
            <div>
              <h2>Travail en cours</h2>
              <p>Cette zone affichera la tache assignee, le fragment courant et la verification.</p>
            </div>
            <button class="ghost" @click="refreshAll">Rafraichir</button>
          </div>
          <div class="work-card">
            <div>
              <strong>{{ status.running ? 'En attente de mission reseau' : 'Node inactif' }}</strong>
              <p>
                {{ status.running
                  ? 'Le PC est joignable. Quand une tache arrive, le detail apparaitra ici.'
                  : 'Activez le PC pour rejoindre le pool de calcul.' }}
              </p>
            </div>
            <span class="work-state">{{ status.running ? 'ready' : 'offline' }}</span>
          </div>
        </section>

        <section class="split-grid">
          <section class="panel">
            <h2>Historique</h2>
            <div v-if="activity.history.length === 0" class="empty-state">
              Aucun fichier d'activite local trouve pour le moment.
            </div>
            <div v-else class="history-list">
              <div v-for="item in activity.history" :key="`${item.name}-${item.modifiedAt}`" class="history-row">
                <div>
                  <strong>{{ item.name }}</strong>
                  <small>{{ formatDate(item.modifiedAt) }}</small>
                </div>
                <span>{{ formatBytes(item.sizeBytes) }}</span>
              </div>
            </div>
          </section>

          <section class="panel">
            <h2>Compte node</h2>
            <div class="account-card">
              <strong>{{ form.nodeId }}</strong>
              <p>Identite locale beta. Ensuite, cette identite sera liee au compte Silicium et au wallet.</p>
            </div>
            <div class="account-grid">
              <span>Reputation initiale</span>
              <strong>{{ form.reputationScore }}</strong>
              <span>Taches vues</span>
              <strong>{{ activity.knownTasks }}</strong>
            </div>
          </section>
        </section>

        <section class="panel">
          <div class="panel-head">
            <div>
              <h2>Journal</h2>
              <p>Evenements locaux du launcher.</p>
            </div>
          </div>
          <pre class="logs">{{ logs.join('\n') }}</pre>
        </section>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import {
  checkEnvironment,
  installRuntime,
  nodeActivity,
  nodeStatus,
  startNode,
  stopNode,
  type CheckItem,
  type NodeActivity,
} from './tauri';

const defaultRepoRoot = localStorage.getItem('silicium.repoRoot') || '';

const form = reactive({
  repoRoot: defaultRepoRoot,
  orchestratorUrl: localStorage.getItem('silicium.orchestratorUrl') || 'http://213.32.68.67:46100',
  advertiseHost: localStorage.getItem('silicium.advertiseHost') || '',
  nodeId: localStorage.getItem('silicium.nodeId') || `silicium-${crypto.randomUUID().slice(0, 8)}`,
  reputationScore: Number(localStorage.getItem('silicium.reputationScore') || 100),
});

const status = reactive({ running: false, roles: 'compute,verify' });
const activity = reactive<NodeActivity>({
  knownResults: 0,
  knownTasks: 0,
  lastResult: 'Aucun resultat local pour le moment',
  storageBytes: 0,
  history: [],
});
const checks = ref<CheckItem[]>([]);
const logs = ref<string[]>(['Silicium Node pret. Lancez les checks puis activez votre PC.']);

function remember() {
  localStorage.setItem('silicium.repoRoot', form.repoRoot);
  localStorage.setItem('silicium.orchestratorUrl', form.orchestratorUrl);
  localStorage.setItem('silicium.advertiseHost', form.advertiseHost);
  localStorage.setItem('silicium.nodeId', form.nodeId);
  localStorage.setItem('silicium.reputationScore', String(form.reputationScore));
}

function pushLog(message: string) {
  logs.value = [`${new Date().toLocaleTimeString()}  ${message}`, ...logs.value].slice(0, 100);
}

async function refreshStatus() {
  const next = await nodeStatus();
  status.running = next.running;
  status.roles = next.roles;
}

async function refreshActivity() {
  if (!form.repoRoot.trim()) {
    return;
  }
  try {
    const next = await nodeActivity(form.repoRoot);
    Object.assign(activity, next);
  } catch (error) {
    pushLog(`Activite indisponible: ${String(error)}`);
  }
}

async function refreshAll() {
  try {
    await refreshStatus();
    await refreshActivity();
  } catch (error) {
    pushLog(`Rafraichissement impossible: ${String(error)}`);
  }
}

async function runChecks() {
  remember();
  try {
    checks.value = await checkEnvironment(form.repoRoot);
    pushLog('Checks systeme termines.');
  } catch (error) {
    pushLog(`Checks impossibles: ${String(error)}`);
  }
}

async function install() {
  remember();
  try {
    const message = await installRuntime(form.repoRoot);
    pushLog(message);
  } catch (error) {
    pushLog(`Installation impossible: ${String(error)}`);
  }
}

async function activateNode() {
  remember();
  try {
    const message = await startNode({
      repoRoot: form.repoRoot,
      orchestratorUrl: form.orchestratorUrl,
      advertiseHost: form.advertiseHost,
      nodeId: form.nodeId,
      reputationScore: form.reputationScore,
    });
    pushLog(message);
    await refreshAll();
  } catch (error) {
    pushLog(`Activation impossible: ${String(error)}`);
  }
}

async function deactivateNode() {
  try {
    const message = await stopNode();
    pushLog(message);
    await refreshAll();
  } catch (error) {
    pushLog(`Arret impossible: ${String(error)}`);
  }
}

function formatBytes(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(seconds: number) {
  if (!seconds) {
    return 'date inconnue';
  }
  return new Date(seconds * 1000).toLocaleString();
}

onMounted(async () => {
  await refreshAll();
  if (form.repoRoot.trim()) {
    await runChecks();
  }
  window.setInterval(refreshAll, 5000);
});
</script>

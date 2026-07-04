<template>
  <main class="shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Silicium Node</p>
        <h1>{{ status.running ? 'Votre PC aide le reseau' : 'Activez votre PC' }}</h1>
        <p class="subtitle">
          {{ status.running
            ? 'Silicium utilise votre machine quand une tache compatible est disponible.'
            : 'Un clic suffit. L app prepare le runtime, connecte votre machine et affiche ensuite son activite.' }}
        </p>
      </div>
      <div class="status-pill" :class="{ online: status.running }">
        {{ status.running ? 'Connecte' : 'Hors ligne' }}
      </div>
    </section>

    <section v-if="!status.running" class="activation-card">
      <div class="activation-copy">
        <h2>Rejoindre le reseau Silicium</h2>
        <p>
          Aucune notion technique necessaire. Silicium choisira automatiquement si votre PC calcule,
          verifie ou attend une meilleure tache.
        </p>
      </div>

      <button class="primary-action" :disabled="busy" @click="activateOneClick">
        {{ busy ? 'Activation en cours...' : 'Activer mon PC' }}
      </button>

      <details class="advanced">
        <summary>Options avancees</summary>
        <div class="advanced-grid">
          <label>
            Dossier Silicium
            <input v-model="form.repoRoot" placeholder="detecte automatiquement" />
          </label>
          <label>
            Orchestrateur
            <input v-model="form.orchestratorUrl" />
          </label>
          <label>
            Adresse annoncee
            <input v-model="form.advertiseHost" placeholder="detectee automatiquement" />
          </label>
        </div>
      </details>

      <p v-if="userMessage" class="user-message">{{ userMessage }}</p>
    </section>

    <section v-else-if="view === 'dashboard'" class="dashboard">
      <nav class="view-nav">
        <button class="ghost active-tab">Tableau de bord</button>
        <button class="ghost" @click="view = 'history'">Historique</button>
      </nav>

      <section class="stats-grid">
        <article class="stat-card">
          <span>Etat</span>
          <strong>{{ nodePhase.label }}</strong>
          <small>{{ nodePhase.description }}</small>
        </article>
        <article class="stat-card">
          <span>Travail actuel</span>
          <strong>{{ currentWorkLabel }}</strong>
          <small>Le reseau assigne les taches automatiquement.</small>
        </article>
        <article class="stat-card">
          <span>Resultats locaux</span>
          <strong>{{ activity.knownResults }}</strong>
          <small>{{ activity.lastResult }}</small>
        </article>
        <article class="stat-card">
          <span>Stockage utilise</span>
          <strong>{{ formatBytes(activity.storageBytes) }}</strong>
          <small>Cache et sorties du node.</small>
        </article>
      </section>

      <section class="panel current-panel">
        <div>
          <h2>Activite du PC</h2>
          <p>{{ nodePhase.detail }}</p>
        </div>
        <button class="danger" :disabled="busy" @click="deactivateNode">Retirer mon PC du reseau</button>
      </section>

      <section class="status-flow">
        <div
          v-for="step in flowSteps"
          :key="step.key"
          class="flow-step"
          :class="{ active: step.key === nodePhase.key, done: step.done }"
        >
          <span>{{ step.index }}</span>
          <strong>{{ step.label }}</strong>
        </div>
      </section>

      <section class="visual-grid">
        <section class="panel network-map">
          <div class="map-head">
            <div>
              <h2>Schema du node</h2>
              <p>Un seul PC, plusieurs capacites, attribution automatique par le reseau.</p>
            </div>
            <span class="map-badge">{{ status.running ? 'connecte' : 'hors ligne' }}</span>
          </div>

          <div class="node-graph" :class="{ active: status.running }">
            <div class="graph-node graph-network">Reseau</div>
            <div class="graph-line line-compute"></div>
            <div class="graph-line line-verify"></div>
            <div class="graph-line line-trace"></div>
            <div class="graph-node graph-pc">Votre PC</div>
            <div class="graph-node graph-compute">Calcul</div>
            <div class="graph-node graph-verify">Verification</div>
            <div class="graph-node graph-trace">Trace</div>
          </div>
        </section>

        <section class="panel role-policy">
          <h2>Regle de confiance</h2>
          <div class="policy-step ok">
            <strong>Ce PC peut calculer</strong>
            <span>Il recoit des fragments adaptes a sa reputation et sa disponibilite.</span>
          </div>
          <div class="policy-step ok">
            <strong>Ce PC peut verifier</strong>
            <span>Il controle des fragments produits par d autres machines.</span>
          </div>
          <div class="policy-step guard">
            <strong>Pas d auto-verification</strong>
            <span>Un node ne valide pas son propre calcul sur le meme fragment.</span>
          </div>
        </section>
      </section>

      <section class="split-grid">
        <section class="panel">
          <div class="panel-row">
            <div>
              <h2>Derniere activite</h2>
              <p>{{ friendlyLastActivity }}</p>
            </div>
            <button class="ghost" @click="view = 'history'">Voir l historique</button>
          </div>
        </section>

        <section class="panel">
          <h2>Mon node</h2>
          <div class="node-card">
            <strong>{{ form.nodeId }}</strong>
            <p>Identite locale de cette machine.</p>
          </div>
          <div class="account-grid">
            <span>Capacites</span>
            <strong>Calcul + verification</strong>
            <span>Reputation initiale</span>
            <strong>{{ form.reputationScore }}</strong>
            <span>Taches vues</span>
            <strong>{{ activity.knownTasks }}</strong>
          </div>
        </section>
      </section>

      <details class="diagnostics">
        <summary>Diagnostics</summary>
        <div class="diag-content">
          <button class="ghost" :disabled="busy" @click="refreshAll">Rafraichir</button>
          <div class="check-list">
            <div v-for="check in checks" :key="check.name" class="check-row" :class="{ ok: check.ok }">
              <span>{{ check.ok ? 'ok' : 'x' }}</span>
              <div>
                <strong>{{ check.name }}</strong>
                <small>{{ check.detail || 'non disponible' }}</small>
              </div>
            </div>
          </div>
          <pre class="logs">{{ logs.join('\n') }}</pre>
        </div>
      </details>
    </section>

    <section v-else class="dashboard">
      <nav class="view-nav">
        <button class="ghost" @click="view = 'dashboard'">Tableau de bord</button>
        <button class="ghost active-tab">Historique</button>
      </nav>

      <section class="panel history-page">
        <div class="panel-row history-header">
          <div>
            <h2>Historique de votre PC</h2>
            <p>Resume simple des derniers travaux vus par cette machine.</p>
          </div>
          <button class="ghost" :disabled="busy" @click="refreshAll">Rafraichir</button>
        </div>

        <div v-if="friendlyHistory.length === 0" class="empty-state">
          Aucun travail enregistre pour le moment. Votre PC est pret et attend une tache.
        </div>
        <div v-else class="friendly-history">
          <article v-for="item in friendlyHistory" :key="item.id" class="friendly-event">
            <div class="event-dot"></div>
            <div>
              <strong>{{ item.title }}</strong>
              <p>{{ item.description }}</p>
            </div>
            <span>{{ item.date }}</span>
          </article>
        </div>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import {
  appDefaults,
  checkEnvironment,
  installRuntime,
  nodeActivity,
  nodeStatus,
  startNode,
  stopNode,
  type CheckItem,
  type NodeActivity,
} from './tauri';

const form = reactive({
  repoRoot: localStorage.getItem('silicium.repoRoot') || '',
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
const logs = ref<string[]>(['Silicium Node pret.']);
const busy = ref(false);
const userMessage = ref('');
const view = ref<'dashboard' | 'history'>('dashboard');

const nodePhase = computed(() => {
  if (!status.running) {
    return {
      key: 'offline',
      label: 'Hors ligne',
      description: 'Votre PC ne participe pas encore.',
      detail: 'Activez votre PC pour rejoindre le reseau.',
    };
  }
  const names = activity.history.map((item) => item.name.toLowerCase());
  if (names.some((name) => name.startsWith('result.'))) {
    return {
      key: 'submitted',
      label: 'Resultat envoye',
      description: 'Un travail a ete termine localement.',
      detail: 'Le dernier resultat local a ete produit et rendu disponible au reseau.',
    };
  }
  if (names.some((name) => name.includes('verify') || name.includes('vote'))) {
    return {
      key: 'verify',
      label: 'Verification',
      description: 'Votre PC controle un resultat.',
      detail: 'Votre machine verifie un fragment calcule par un autre node.',
    };
  }
  if (names.some((name) => name.includes('task') || name.includes('queue'))) {
    return {
      key: 'compute',
      label: 'Calcul',
      description: 'Votre PC traite une tache.',
      detail: 'Votre machine travaille sur un fragment attribue par le reseau.',
    };
  }
  return {
    key: 'waiting',
    label: 'En attente',
    description: 'Votre PC est connecte et disponible.',
    detail: 'Votre PC est connecte au reseau. Il sera sollicite quand une tache compatible arrivera.',
  };
});

const currentWorkLabel = computed(() => {
  if (!status.running) {
    return 'Inactif';
  }
  return nodePhase.value.key === 'waiting' ? 'Pret' : nodePhase.value.label;
});

const flowOrder = ['waiting', 'compute', 'verify', 'submitted'];
const flowSteps = computed(() => {
  const currentIndex = Math.max(0, flowOrder.indexOf(nodePhase.value.key));
  return [
    { key: 'waiting', label: 'Connecte', index: '1', done: currentIndex > 0 },
    { key: 'compute', label: 'Calcul', index: '2', done: currentIndex > 1 },
    { key: 'verify', label: 'Verification', index: '3', done: currentIndex > 2 },
    { key: 'submitted', label: 'Resultat envoye', index: '4', done: nodePhase.value.key === 'submitted' },
  ];
});

const friendlyLastActivity = computed(() => {
  if (activity.history.length === 0) {
    return 'Aucune tache recue pour le moment. Le PC reste disponible.';
  }
  return `${friendlyEvent(activity.history[0]).title} - ${friendlyEvent(activity.history[0]).date}`;
});

const friendlyHistory = computed(() =>
  activity.history.slice(0, 12).map((item, index) => ({
    id: `${item.name}-${item.modifiedAt}-${index}`,
    ...friendlyEvent(item),
  })),
);

function remember() {
  localStorage.setItem('silicium.repoRoot', form.repoRoot);
  localStorage.setItem('silicium.orchestratorUrl', form.orchestratorUrl);
  localStorage.setItem('silicium.advertiseHost', form.advertiseHost);
  localStorage.setItem('silicium.nodeId', form.nodeId);
  localStorage.setItem('silicium.reputationScore', String(form.reputationScore));
}

function pushLog(message: string) {
  logs.value = [`${new Date().toLocaleTimeString()}  ${message}`, ...logs.value].slice(0, 80);
}

async function loadDefaults() {
  try {
    const defaults = await appDefaults();
    form.repoRoot ||= defaults.repoRoot;
    form.advertiseHost ||= defaults.advertiseHost;
    form.orchestratorUrl ||= defaults.orchestratorUrl;
    remember();
  } catch (error) {
    pushLog(`Detection automatique indisponible: ${String(error)}`);
  }
}

async function refreshStatus() {
  const next = await nodeStatus();
  status.running = next.running;
  status.roles = next.roles;
}

async function refreshActivity() {
  try {
    const next = await nodeActivity(form.repoRoot);
    Object.assign(activity, next);
  } catch {
    // No activity yet, or repo not available. Keep the dashboard quiet for non-technical users.
  }
}

async function refreshAll() {
  await refreshStatus();
  await refreshActivity();
}

async function runChecksQuietly() {
  checks.value = await checkEnvironment(form.repoRoot);
  const failed = checks.value.filter((check) => !check.ok);
  if (failed.length > 0) {
    pushLog(`${failed.length} verification(s) a revoir.`);
  } else {
    pushLog('Environnement pret.');
  }
}

async function activateOneClick() {
  busy.value = true;
  userMessage.value = 'Preparation de votre PC...';
  remember();
  try {
    await loadDefaults();
    await runChecksQuietly();
    userMessage.value = 'Installation et verification du runtime...';
    await installRuntime(form.repoRoot);
    userMessage.value = 'Connexion au reseau Silicium...';
    const message = await startNode({
      repoRoot: form.repoRoot,
      orchestratorUrl: form.orchestratorUrl,
      advertiseHost: form.advertiseHost,
      nodeId: form.nodeId,
      reputationScore: form.reputationScore,
    });
    pushLog(message);
    userMessage.value = '';
    await refreshAll();
  } catch (error) {
    userMessage.value = "L activation n a pas pu se terminer. Ouvrez Diagnostics si besoin.";
    pushLog(`Activation impossible: ${String(error)}`);
  } finally {
    busy.value = false;
  }
}

async function deactivateNode() {
  busy.value = true;
  try {
    const message = await stopNode();
    pushLog(message);
    await refreshAll();
  } catch (error) {
    pushLog(`Retrait impossible: ${String(error)}`);
  } finally {
    busy.value = false;
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

function friendlyEvent(item: { name: string; modifiedAt: number; sizeBytes: number }) {
  const lower = item.name.toLowerCase();
  if (lower.startsWith('result.')) {
    return {
      title: 'Resultat envoye',
      description: `Un resultat a ete produit par ce PC (${formatBytes(item.sizeBytes)}).`,
      date: formatDate(item.modifiedAt),
    };
  }
  if (lower.includes('verify') || lower.includes('vote')) {
    return {
      title: 'Verification effectuee',
      description: 'Ce PC a participe au controle d un resultat.',
      date: formatDate(item.modifiedAt),
    };
  }
  if (lower.includes('task') || lower.includes('queue')) {
    return {
      title: 'Tache recue',
      description: 'Le reseau a transmis un travail a cette machine.',
      date: formatDate(item.modifiedAt),
    };
  }
  return {
    title: 'Activite reseau',
    description: 'Un fichier local lie au node a ete mis a jour.',
    date: formatDate(item.modifiedAt),
  };
}

onMounted(async () => {
  await loadDefaults();
  await refreshAll();
  window.setInterval(refreshAll, 5000);
});
</script>

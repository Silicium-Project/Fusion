<template>
  <main class="shell compact-shell">
    <section class="hero compact-hero">
      <div>
        <p class="eyebrow">Silicium Node</p>
        <h1>{{ status.running ? 'Votre PC est dans le reseau' : 'Activez votre PC' }}</h1>
        <p class="subtitle">
          {{ status.running
            ? 'Votre machine reste disponible en arriere-plan. Silicium lui attribue automatiquement du calcul ou de la verification.'
            : 'Un clic suffit pour connecter ce PC au reseau Silicium.' }}
        </p>
      </div>
      <div class="status-pill" :class="{ online: status.running }">
        {{ status.running ? 'Connecte' : 'Hors ligne' }}
      </div>
    </section>

    <section v-if="!status.running" class="activation-card compact-activation">
      <div class="activation-copy">
        <h2>Rejoindre le reseau</h2>
        <p>
          Silicium prepare le runtime, connecte ce PC et affiche ensuite son activite. Aucun choix technique n est demande.
        </p>
      </div>

      <button class="primary-action" :disabled="busy" @click="activateOneClick">
        {{ busy ? 'Activation...' : 'Activer mon PC' }}
      </button>

      <details class="advanced">
        <summary>Parametres avances</summary>
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

    <section v-else class="dashboard compact-dashboard">
      <section class="stats-grid compact-stats">
        <article class="stat-card">
          <span>Statut</span>
          <strong>{{ nodePhase.label }}</strong>
          <small>{{ nodePhase.description }}</small>
        </article>
        <article class="stat-card">
          <span>Gains confirmes</span>
          <strong>{{ confirmedRewards }}</strong>
          <small>{{ rewardNote }}</small>
        </article>
        <article class="stat-card">
          <span>Taches traitees</span>
          <strong>{{ activity.knownResults }}</strong>
          <small>{{ activity.knownTasks }} evenement(s) vus par ce PC.</small>
        </article>
        <article class="stat-card">
          <span>Stockage local</span>
          <strong>{{ formatBytes(activity.storageBytes) }}</strong>
          <small>Cache, preuves et resultats temporaires.</small>
        </article>
      </section>

      <section class="panel current-panel">
        <div>
          <h2>Activite actuelle</h2>
          <p>{{ nodePhase.detail }}</p>
        </div>
        <button class="danger" :disabled="busy" @click="deactivateNode">Retirer ce PC</button>
      </section>

      <section class="split-grid compact-grid">
        <section class="panel">
          <div class="panel-row">
            <div>
              <h2>Suivi des travaux</h2>
              <p>{{ friendlyLastActivity }}</p>
            </div>
            <button class="ghost" :disabled="busy" @click="refreshAll">Rafraichir</button>
          </div>

          <div class="work-summary">
            <div class="work-step" :class="{ active: nodePhase.key === 'waiting' }">
              <strong>Disponible</strong>
              <span>En attente d une tache compatible</span>
            </div>
            <div class="work-step" :class="{ active: nodePhase.key === 'compute' }">
              <strong>Calcul</strong>
              <span>Execution d un fragment</span>
            </div>
            <div class="work-step" :class="{ active: nodePhase.key === 'verify' }">
              <strong>Verification</strong>
              <span>Controle d un resultat</span>
            </div>
            <div class="work-step" :class="{ active: nodePhase.key === 'submitted' }">
              <strong>Resultat</strong>
              <span>Sortie renvoyee au reseau</span>
            </div>
          </div>
        </section>

        <section class="panel">
          <h2>Votre PC</h2>
          <div class="account-grid">
            <span>Identite</span>
            <strong>{{ form.nodeId }}</strong>
            <span>Capacites</span>
            <strong>Calcul + verification</strong>
            <span>Reputation beta</span>
            <strong>{{ form.reputationScore }}</strong>
            <span>Dernier resultat</span>
            <strong>{{ shortResultName }}</strong>
          </div>
        </section>
      </section>

      <section class="panel history-page compact-history">
        <div class="panel-row history-header">
          <div>
            <h2>Historique</h2>
            <p>Les derniers travaux et fichiers produits par ce PC.</p>
          </div>
        </div>

        <div v-if="friendlyHistory.length === 0" class="empty-state">
          Aucun travail enregistre pour le moment. Votre PC est connecte et attend une tache.
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
  nodeActivity,
  nodeStatus,
  startNode,
  stopNode,
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
  lastResult: 'Aucun resultat local',
  storageBytes: 0,
  history: [],
});
const busy = ref(false);
const userMessage = ref('');

const nodePhase = computed(() => {
  if (!status.running) {
    return {
      key: 'offline',
      label: 'Hors ligne',
      description: 'Votre PC ne participe pas encore.',
      detail: 'Activez votre PC pour rejoindre le reseau.',
    };
  }
  const recentLimit = Date.now() / 1000 - 120;
  const names = activity.history
    .filter((item) => item.modifiedAt >= recentLimit)
    .map((item) => item.name.toLowerCase());
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
    description: 'Le service local est actif.',
    detail: 'Votre PC est connecte. Il sera sollicite quand une tache compatible arrivera.',
  };
});

const confirmedRewards = computed(() => '0.00 SOL');
const rewardNote = computed(() => 'Paiements reels a connecter au smart contract.');

const friendlyLastActivity = computed(() => {
  if (activity.history.length === 0) {
    return 'Aucune tache recue pour le moment. Le PC reste disponible.';
  }
  const event = friendlyEvent(activity.history[0]);
  return `${event.title} - ${event.date}`;
});

const friendlyHistory = computed(() =>
  activity.history.slice(0, 10).map((item, index) => ({
    id: `${item.name}-${item.modifiedAt}-${index}`,
    ...friendlyEvent(item),
  })),
);

const shortResultName = computed(() => {
  if (!activity.lastResult || activity.lastResult === 'Aucun resultat local') {
    return 'Aucun';
  }
  return activity.lastResult.length > 24 ? `${activity.lastResult.slice(0, 21)}...` : activity.lastResult;
});

function remember() {
  localStorage.setItem('silicium.repoRoot', form.repoRoot);
  localStorage.setItem('silicium.orchestratorUrl', form.orchestratorUrl);
  localStorage.setItem('silicium.advertiseHost', form.advertiseHost);
  localStorage.setItem('silicium.nodeId', form.nodeId);
  localStorage.setItem('silicium.reputationScore', String(form.reputationScore));
}

async function loadDefaults() {
  try {
    const defaults = await appDefaults();
    form.repoRoot ||= defaults.repoRoot;
    form.advertiseHost ||= defaults.advertiseHost;
    form.orchestratorUrl ||= defaults.orchestratorUrl;
    remember();
  } catch {
    // Keep the app silent for non-technical users; activation will show a simple message if needed.
  }
}

async function refreshStatus() {
  const next = await nodeStatus(form.repoRoot);
  status.running = next.running;
  status.roles = next.roles;
}

async function refreshActivity() {
  try {
    const next = await nodeActivity(form.repoRoot);
    Object.assign(activity, next);
  } catch {
    // No activity yet.
  }
}

async function refreshAll() {
  await refreshStatus();
  await refreshActivity();
}

async function activateOneClick() {
  busy.value = true;
  userMessage.value = 'Connexion du PC au reseau...';
  remember();
  try {
    await loadDefaults();
    await startNode({
      repoRoot: form.repoRoot,
      orchestratorUrl: form.orchestratorUrl,
      advertiseHost: form.advertiseHost,
      nodeId: form.nodeId,
      reputationScore: form.reputationScore,
    });
    userMessage.value = '';
    await refreshAll();
  } catch {
    userMessage.value = "L activation n a pas pu se terminer. Verifiez que l installation est a jour.";
  } finally {
    busy.value = false;
  }
}

async function deactivateNode() {
  busy.value = true;
  try {
    await stopNode(form.repoRoot);
    await refreshAll();
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
  if (lower.startsWith('failed.')) {
    return {
      title: 'Travail en erreur',
      description: 'Votre PC a rencontre une erreur sur un travail du reseau.',
      date: formatDate(item.modifiedAt),
    };
  }
  if (lower.startsWith('result.sent.')) {
    return {
      title: 'Resultat renvoye',
      description: `Le resultat a ete transmis au reseau (${formatDurationMs(item.sizeBytes)}).`,
      date: formatDate(item.modifiedAt),
    };
  }
  if (lower.startsWith('result.')) {
    return {
      title: 'Resultat produit',
      description: `Votre PC a termine un travail (${formatDurationMs(item.sizeBytes)}).`,
      date: formatDate(item.modifiedAt),
    };
  }
  if (lower.includes('verify') || lower.includes('vote')) {
    return {
      title: 'Verification effectuee',
      description: 'Votre PC a controle un resultat du reseau.',
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

function formatDurationMs(durationMs: number) {
  if (!durationMs) {
    return 'duree inconnue';
  }
  const seconds = Math.round(durationMs / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${String(remainingSeconds).padStart(2, '0')}s`;
}

onMounted(async () => {
  await loadDefaults();
  await refreshAll();
  window.setInterval(refreshAll, 5000);
});
</script>

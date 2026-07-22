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

    <p v-if="userMessage" class="app-banner info-banner">{{ userMessage }}</p>
    <p v-if="refreshError" class="app-banner error-banner">{{ refreshError }}</p>
    <section class="app-banner release-banner" :class="{ warning: updateInfo.updateAvailable, error: updateInfo.state === 'error' }">
      <div>
        <strong>{{ releaseBannerTitle }}</strong>
        <span>{{ releaseBannerDetail }}</span>
      </div>
      <span class="release-channel">{{ updateInfo.currentChannel }} · {{ updateInfo.currentVersion }}</span>
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
            <span>Version active</span>
            <strong>{{ updateInfo.currentVersion }} ({{ updateInfo.currentChannel }})</strong>
            <span>Dernier resultat</span>
            <strong>{{ shortResultName }}</strong>
          </div>
        </section>
      </section>

      <section class="panel network-directory">
        <div class="directory-heading">
          <div>
            <p class="eyebrow">Annuaire reseau connu</p>
            <h2>Nodes observes par ce PC</h2>
            <p>Presence, release, identite P2P, ICE et activite scheduler issues du dernier snapshot mesh.</p>
          </div>
          <div class="directory-metrics">
            <span><strong>{{ activity.machines.length }}</strong> connus</span>
            <span class="metric-online"><strong>{{ onlineMachineCount }}</strong> en ligne</span>
            <span :class="{ 'metric-warning': outdatedMachineCount > 0 }"><strong>{{ outdatedMachineCount }}</strong> a mettre a jour</span>
            <span><strong>{{ directCandidateMachineCount }}</strong> avec candidats ICE</span>
          </div>
        </div>

        <div class="directory-toolbar">
          <input v-model.trim="networkQuery" type="search" placeholder="Rechercher un node, role, endpoint, version..." />
          <span>{{ filteredMachines.length }} resultat(s)</span>
        </div>

        <div v-if="activity.machines.length === 0" class="empty-state">
          Aucun node dans l annuaire local. Les entrees apparaitront apres la prochaine synchronisation P2P.
        </div>
        <div v-else-if="filteredMachines.length === 0" class="empty-state">
          Aucun node ne correspond a cette recherche.
        </div>
        <div v-else class="directory-table">
          <div class="directory-columns" aria-hidden="true">
            <span>Node / identite</span>
            <span>Release</span>
            <span>P2P / ICE</span>
            <span>Scheduler</span>
            <span>Derniere presence</span>
          </div>

          <article v-for="machine in filteredMachines" :key="machine.nodeId" class="directory-node" :class="{ offline: !machine.online }">
            <div class="directory-summary">
              <div class="directory-identity">
                <span class="machine-light" :class="{ online: machine.online }"></span>
                <div>
                  <strong>{{ machine.nodeId }}</strong>
                  <small>{{ machine.selfNode ? 'Ce PC' : shortIdentity(machine.identityId) }}</small>
                </div>
              </div>

              <div class="directory-release">
                <strong :class="{ 'machine-version-warning': machineNeedsUpdate(machine) }">{{ machine.appVersion || 'version inconnue' }}</strong>
                <small>{{ machine.releaseChannel || 'canal inconnu' }}<template v-if="machine.releaseBuild"> · {{ machine.releaseBuild }}</template></small>
              </div>

              <div class="directory-p2p">
                <span class="p2p-badge" :class="p2pStatusClass(machine)">{{ p2pStatusLabel(machine) }}</span>
                <small>{{ candidateSummary(machine) }}</small>
              </div>

              <div class="directory-scheduler">
                <strong>{{ machineWorkLabel(machine) }}</strong>
                <small>{{ machine.schedulerActive ? 'poll actif' : 'poll inactif' }}</small>
              </div>

              <div class="directory-presence">
                <strong>{{ formatRelativeTime(machine.lastSeenUnix) }}</strong>
                <small>{{ machine.lastSeenUtc || 'date inconnue' }}</small>
              </div>
            </div>

            <details class="directory-details">
              <summary>Details techniques et candidats</summary>
              <div class="directory-detail-grid">
                <div><span>Roles</span><code>{{ machine.roles.join(', ') || 'aucun' }}</code></div>
                <div><span>Endpoint HTTP annonce</span><code>{{ machine.httpBaseUrl || 'non annonce' }}</code></div>
                <div><span>Endpoint mesh annonce</span><code>{{ machine.meshPostUrl || 'non annonce' }}</code></div>
                <div><span>Identite P2P</span><code>{{ machine.identityId || 'inconnue' }}</code></div>
                <div><span>Plateforme / CPU</span><code>{{ machine.platform || 'inconnue' }} · {{ machine.cpuCount || '?' }} coeur(s)</code></div>
                <div><span>Fonctions transport</span><code>{{ machine.features.join(', ') || 'non annoncees' }}</code></div>
                <div><span>Relay</span><code>{{ machine.relayCapable ? 'capable' : 'non annonce' }}</code></div>
                <div><span>Dernier claim</span><code>{{ machine.lastClaimPollUtc || 'aucun' }}</code></div>
                <div><span>Derniere reponse</span><code>{{ responseLabel(machine) }}<template v-if="machine.lastResponseItemId"> · {{ machine.lastResponseItemId }}</template></code></div>
              </div>
              <div v-if="machine.candidates.length" class="candidate-list">
                <div v-for="(candidate, index) in machine.candidates" :key="`${machine.nodeId}-${candidate.ip}-${candidate.port}-${index}`" class="candidate-card">
                  <strong>{{ candidate.candidateType || 'host' }} / {{ candidate.transport || 'udp' }}</strong>
                  <code>{{ candidate.ip }}:{{ candidate.port }}</code>
                  <small>{{ candidate.internetRoutable ? 'routable Internet' : 'adresse locale/NAT' }}<template v-if="candidate.source"> · {{ candidate.source }}</template></small>
                </div>
              </div>
              <p v-else class="candidate-empty">Aucun candidat ICE annonce par ce node.</p>
              <p v-if="machine.lastClaimError" class="directory-error">{{ machine.lastClaimError }}</p>
            </details>
          </article>
        </div>
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
          <article v-for="item in recentFriendlyHistory" :key="item.id" class="friendly-event">
            <div class="event-dot"></div>
            <div>
              <strong>{{ item.title }}</strong>
              <p>{{ item.description }}</p>
            </div>
            <span>{{ item.date }}</span>
          </article>
          <details v-if="olderFriendlyHistory.length > 0" class="history-more">
            <summary>Voir les anciens evenements ({{ olderFriendlyHistory.length }})</summary>
            <div class="friendly-history history-more-list">
              <article v-for="item in olderFriendlyHistory" :key="item.id" class="friendly-event">
                <div class="event-dot"></div>
                <div>
                  <strong>{{ item.title }}</strong>
                  <p>{{ item.description }}</p>
                </div>
                <span>{{ item.date }}</span>
              </article>
            </div>
          </details>
        </div>
      </section>
    </section>

    <details class="diagnostics compact-diagnostics">
      <summary>Diagnostics techniques</summary>
      <div class="diag-content">
        <div class="panel-row">
          <div>
            <h2>Etat local</h2>
            <p>Infos utiles si un PC ne recupere pas les taches ou si le runtime local echoue.</p>
          </div>
          <button class="ghost" :disabled="busy" @click="refreshDiagnostics">Verifier</button>
        </div>

        <div class="check-list">
          <div class="check-row" :class="{ ok: diagnostics.python.ok }">
            <span>{{ diagnostics.python.ok ? 'ok' : 'x' }}</span>
            <div>
              <strong>Python</strong>
              <small>{{ diagnostics.python.detail || 'non teste' }}</small>
            </div>
          </div>
          <div class="check-row" :class="{ ok: diagnostics.openssl.ok }">
            <span>{{ diagnostics.openssl.ok ? 'ok' : 'x' }}</span>
            <div>
              <strong>{{ diagnostics.openssl.name || 'Identite reseau' }}</strong>
              <small>{{ diagnostics.openssl.detail || 'non teste' }}</small>
            </div>
          </div>
          <div class="check-row" :class="{ ok: diagnostics.orchestrator.ok }">
            <span>{{ diagnostics.orchestrator.ok ? 'ok' : 'x' }}</span>
            <div>
              <strong>Orchestrateur</strong>
              <small>{{ diagnostics.orchestrator.detail || 'non teste' }}</small>
            </div>
          </div>
        </div>

        <div class="diag-grid">
          <span>Runtime</span>
          <code>{{ diagnostics.repoRoot || form.repoRoot || 'non detecte' }}</code>
          <span>CLI Silicium</span>
          <code>{{ diagnostics.siliciumCli || 'non detecte' }}</code>
          <span>Logs</span>
          <code>{{ diagnostics.logDir || 'non detecte' }}</code>
          <span>Node PID</span>
          <code>{{ diagnostics.nodePid || 'aucun' }}</code>
          <span>Supervisor PID</span>
          <code>{{ diagnostics.supervisorPid || 'aucun' }}</code>
          <span>Port local</span>
          <code>{{ diagnostics.portReady ? '46101 ouvert' : '46101 ferme' }}</code>
        </div>

        <pre class="logs">{{ diagnostics.logTail }}</pre>
      </div>
    </details>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import {
  appDefaults,
  nodeActivity,
  nodeDiagnostics,
  nodeStatus,
  startNode,
  stopNode,
  checkForUpdates,
  updateStatus,
  type NodeActivity,
  type NodeDiagnostics,
  type UpdateStatus,
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
  machines: [],
});
const diagnostics = reactive<NodeDiagnostics>({
  repoRoot: '',
  siliciumCli: '',
  logDir: '',
  nodePid: null,
  supervisorPid: null,
  nodeRunning: false,
  supervisorRunning: false,
  portReady: false,
  orchestrator: { name: 'Orchestrateur', ok: false, detail: 'non teste' },
  openssl: { name: 'Identite reseau', ok: false, detail: 'non teste' },
  python: { name: 'Python', ok: false, detail: 'non teste' },
  logTail: 'Ouvrez puis cliquez sur Verifier pour charger les diagnostics.',
});
const updateInfo = reactive<UpdateStatus>({
  currentVersion: 'inconnue',
  currentChannel: 'dev',
  currentBuild: '',
  latestVersion: '',
  state: 'unknown',
  updateAvailable: false,
  automatic: true,
  lastCheckedUtc: '',
  error: '',
  checkIntervalSeconds: 30,
});
const busy = ref(false);
const userMessage = ref('');
const refreshError = ref('');
const networkQuery = ref('');
let refreshTimer: number | undefined;
let refreshInFlight = false;

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
  activity.history.map((item, index) => ({
    id: `${item.name}-${item.modifiedAt}-${index}`,
    ...friendlyEvent(item),
  })),
);
const recentFriendlyHistory = computed(() => friendlyHistory.value.slice(0, 5));
const olderFriendlyHistory = computed(() => friendlyHistory.value.slice(5));
const onlineMachineCount = computed(() => activity.machines.filter((machine) => machine.online).length);
const outdatedMachineCount = computed(() => activity.machines.filter(machineNeedsUpdate).length);
const directCandidateMachineCount = computed(() => activity.machines.filter((machine) => machine.candidates.length > 0).length);
const filteredMachines = computed(() => {
  const query = networkQuery.value.toLowerCase();
  if (!query) return activity.machines;
  return activity.machines.filter((machine) => {
    const searchable = [
      machine.nodeId,
      machine.identityId,
      machine.appVersion,
      machine.releaseChannel,
      machine.releaseBuild,
      machine.httpBaseUrl,
      machine.platform,
      ...machine.roles,
      ...machine.features,
      ...machine.candidates.flatMap((candidate) => [candidate.candidateType, candidate.transport, candidate.ip, candidate.source]),
    ].join(' ').toLowerCase();
    return searchable.includes(query);
  });
});
const releaseBannerTitle = computed(() => {
  if (updateInfo.state === 'waiting_for_idle') return `Mise a jour ${updateInfo.latestVersion} en attente`;
  if (updateInfo.state === 'installing') return 'Installation de la mise a jour...';
  if (updateInfo.state === 'downloading') return 'Telechargement de la mise a jour...';
  if (updateInfo.updateAvailable) return `Mise a jour ${updateInfo.latestVersion} requise`;
  if (updateInfo.state === 'error') return 'Verification des mises a jour en erreur';
  return 'Mises a jour automatiques actives';
});
const releaseBannerDetail = computed(() => {
  if (updateInfo.state === 'waiting_for_idle') return 'Une tache est en cours. L installation demarrera automatiquement des que le node sera disponible.';
  if (updateInfo.updateAvailable) return 'Le node sera mis a jour et redemarre automatiquement des que le paquet est verifie.';
  if (updateInfo.state === 'error') return updateInfo.error || 'Le serveur de versions sera reinterroge automatiquement.';
  return `Canal ${updateInfo.currentChannel}; verification toutes les ${formatUpdateInterval(updateInfo.checkIntervalSeconds)}.`;
});

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
    if (defaults.repoRoot) {
      form.repoRoot = defaults.repoRoot;
    }
    form.advertiseHost ||= defaults.advertiseHost;
    form.orchestratorUrl ||= defaults.orchestratorUrl;
    if (defaults.nodeId) {
      form.nodeId = defaults.nodeId;
    }
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

async function refreshUpdateStatus() {
  try {
    Object.assign(updateInfo, await updateStatus());
  } catch {
    // Le superviseur continuera les verifications en arriere-plan.
  }
}

async function refreshAll() {
  if (refreshInFlight) return;
  refreshInFlight = true;
  try {
    await refreshStatus();
    await refreshActivity();
    await refreshUpdateStatus();
    refreshError.value = '';
  } catch (error) {
    refreshError.value = `Impossible de lire l etat local : ${friendlyError(error)}`;
  } finally {
    refreshInFlight = false;
  }
}

async function refreshDiagnostics() {
  try {
    const next = await nodeDiagnostics(form.repoRoot);
    Object.assign(diagnostics, next);
  } catch (error) {
    diagnostics.logTail = friendlyError(error);
  }
}

async function activateOneClick() {
  busy.value = true;
  userMessage.value = 'Connexion du PC au reseau...';
  remember();
  try {
    await loadDefaults();
    const message = await startNode({
      repoRoot: form.repoRoot,
      orchestratorUrl: form.orchestratorUrl,
      advertiseHost: form.advertiseHost,
      nodeId: form.nodeId,
      reputationScore: form.reputationScore,
    });
    userMessage.value = message;
    await refreshAll();
  } catch (error) {
    userMessage.value = `L activation n a pas pu se terminer : ${friendlyError(error)}`;
    await refreshDiagnostics();
  } finally {
    busy.value = false;
  }
}

async function deactivateNode() {
  busy.value = true;
  try {
    await stopNode(form.repoRoot);
    userMessage.value = 'Ce PC a ete retire du reseau.';
    await refreshAll();
  } catch (error) {
    userMessage.value = `Impossible de retirer ce PC : ${friendlyError(error)}`;
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

function friendlyEvent(item: NodeActivity['history'][number]) {
  const lower = item.name.toLowerCase();
  const fragment = item.fragmentIndex ? ` fragment #${item.fragmentIndex}` : '';
  const peer = item.peerId ? ` via ${item.peerId}` : '';
  if (item.kind === 'fragment_fetched') {
    return {
      title: `Fragment recupere${fragment}`,
      description: `Les donnees de calcul ont bien ete recues${peer}.`,
      date: formatDate(item.modifiedAt),
    };
  }
  if (item.kind === 'verification_input_fetched') {
    return {
      title: `Verification recue${fragment}`,
      description: `Le resultat a controler a bien ete recupere${peer}.`,
      date: formatDate(item.modifiedAt),
    };
  }
  if (item.kind === 'task_started') {
    return {
      title: item.role === 'verify' ? `Verification demarree${fragment}` : `Calcul demarre${fragment}`,
      description: `La machine traite ${item.itemId || 'une tache du reseau'}.`,
      date: formatDate(item.modifiedAt),
    };
  }
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

function machineWorkLabel(machine: NodeActivity['machines'][number]) {
  const task = machine.activeTasks[0];
  if (!machine.online) return 'Inactive';
  if (task) {
    if (task.role === 'verify' || task.activity === 'verification') return 'Verification en cours';
    if (task.activity === 'fragment') return 'Fragment en cours';
    return 'Tache en cours';
  }
  if (!machine.schedulerActive) return 'En attente du scheduler';
  return 'Disponible';
}

function machineWorkDetail(machine: NodeActivity['machines'][number]) {
  const task = machine.activeTasks[0];
  if (machine.lastClaimError) return machine.lastClaimError;
  if (task) {
    const fragment = task.fragmentIndex !== null && task.fragmentIndex !== undefined
      ? `fragment #${task.fragmentIndex}`
      : task.workload;
    return `${task.itemId}${fragment ? ` - ${fragment}` : ''}`;
  }
  if (machine.online && !machine.schedulerActive) {
    return machine.lastClaimPollUtc
      ? `Derniere demande: ${machine.lastClaimPollUtc}`
      : 'Aucune demande de tache recente';
  }
  return machine.roles.length ? machine.roles.join(' + ') : 'aucun role annonce';
}

function machinePresenceLabel(machine: NodeActivity['machines'][number]) {
  if (!machine.online) return 'Hors ligne ou heartbeat expire';
  if (machine.activeTasks.length > 0) return 'Connectee et en cours de travail';
  if (!machine.schedulerActive) return 'Connectee, mais ne reclame plus de tache';
  return 'Connectee et disponible pour le scheduler';
}

function responseLabel(machine: NodeActivity['machines'][number]) {
  if (machine.lastResponseOk === true) return 'Reponse OK';
  if (machine.lastResponseOk === false) return 'Reponse en erreur';
  return 'Pas encore de retour';
}

function responseClass(machine: NodeActivity['machines'][number]) {
  if (machine.lastResponseOk === true) return 'ok';
  if (machine.lastResponseOk === false) return 'failed';
  return '';
}

function machineNeedsUpdate(machine: NodeActivity['machines'][number]) {
  if (!machine.appVersion) return true;
  return machine.releaseChannel === updateInfo.currentChannel
    && Boolean(updateInfo.latestVersion)
    && machine.appVersion !== updateInfo.latestVersion;
}

function machineVersionLabel(machine: NodeActivity['machines'][number]) {
  if (!machine.appVersion) return 'Version inconnue - mise a jour requise';
  const channel = machine.releaseChannel || 'canal inconnu';
  return machineNeedsUpdate(machine)
    ? `${machine.appVersion} (${channel}) - mise a jour requise`
    : `${machine.appVersion} (${channel})`;
}

function shortIdentity(identity: string) {
  if (!identity) return 'identite non annoncee';
  return identity.length > 22 ? `${identity.slice(0, 10)}...${identity.slice(-8)}` : identity;
}

function candidateSummary(machine: NodeActivity['machines'][number]) {
  if (!machine.candidates.length) return 'aucun candidat annonce';
  const types = [...new Set(machine.candidates.map((candidate) => candidate.candidateType || 'host'))];
  return `${machine.candidates.length} candidat(s) · ${types.join(', ')}`;
}

function p2pStatusLabel(machine: NodeActivity['machines'][number]) {
  if (!machine.online) return 'Hors ligne';
  if (!machine.candidates.length) return 'Aucun candidat';
  if (machine.candidates.some((candidate) => candidate.internetRoutable)) return 'ICE routable';
  return 'ICE local / NAT';
}

function p2pStatusClass(machine: NodeActivity['machines'][number]) {
  if (!machine.online) return 'offline';
  if (!machine.candidates.length) return 'warning';
  if (machine.candidates.some((candidate) => candidate.internetRoutable)) return 'ok';
  return 'nat';
}

function formatRelativeTime(seconds: number) {
  if (!seconds) return 'jamais';
  const age = Math.max(0, Math.round(Date.now() / 1000 - seconds));
  if (age < 5) return 'a l instant';
  if (age < 60) return `il y a ${age}s`;
  if (age < 3600) return `il y a ${Math.floor(age / 60)} min`;
  if (age < 86400) return `il y a ${Math.floor(age / 3600)} h`;
  return `il y a ${Math.floor(age / 86400)} j`;
}

function formatUpdateInterval(seconds: number) {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds / 3600)} h`;
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

function friendlyError(error: unknown) {
  const raw = error instanceof Error ? error.message : String(error);
  const messages: Record<string, string> = {
    managed_runtime_not_found: 'le runtime Silicium est absent; reinstallez l application',
    orchestrator_url_missing: 'l adresse de l orchestrateur est vide',
    orchestrator_url_invalid_scheme: 'l adresse doit commencer par http:// ou https://',
    orchestrator_url_invalid_host: 'l adresse de l orchestrateur est invalide',
  };
  return messages[raw] || raw;
}

function scheduleRefresh() {
  refreshTimer = window.setTimeout(async () => {
    await refreshAll();
    scheduleRefresh();
  }, 5000);
}

onMounted(async () => {
  await loadDefaults();
  try {
    Object.assign(updateInfo, await checkForUpdates());
  } catch {
    // Une nouvelle tentative sera faite par le superviseur.
  }
  await refreshAll();
  scheduleRefresh();
});

onBeforeUnmount(() => {
  if (refreshTimer !== undefined) window.clearTimeout(refreshTimer);
});
</script>

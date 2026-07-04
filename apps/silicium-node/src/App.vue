<template>
  <main class="shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Silicium Node</p>
        <h1>Rejoindre le reseau</h1>
        <p class="subtitle">
          Lancez votre PC comme worker, verifier, ou les deux, sans manipuler les scripts a la main.
        </p>
      </div>
      <div class="status-pill" :class="{ online: status.worker || status.verifier }">
        {{ status.worker || status.verifier ? 'Node actif' : 'Node arrete' }}
      </div>
    </section>

    <section class="grid">
      <form class="panel" @submit.prevent>
        <h2>Configuration</h2>
        <label>
          Dossier du repo Silicium
          <input v-model="form.repoRoot" placeholder="C:\\Users\\...\\eipSilicium" />
        </label>
        <label>
          Orchestrateur public
          <input v-model="form.orchestratorUrl" />
        </label>
        <label>
          IP annoncee par ce PC
          <input v-model="form.advertiseHost" placeholder="192.168.1.20 ou IP publique" />
        </label>
        <p class="hint">
          En beta, l'app pilote les scripts du repo. Le prochain package embarquera l'installation.
        </p>
      </form>

      <section class="panel">
        <h2>Roles</h2>
        <div class="role-card">
          <div>
            <strong>Worker</strong>
            <p>Calcule les fragments envoyes par le reseau.</p>
          </div>
          <button :disabled="status.worker" @click="start('worker')">
            {{ status.worker ? 'Actif' : 'Demarrer' }}
          </button>
          <button class="ghost" :disabled="!status.worker" @click="stop('worker')">Arreter</button>
        </div>
        <div class="role-card">
          <div>
            <strong>Verifier</strong>
            <p>Verifie les fragments avant reassemblage.</p>
          </div>
          <button :disabled="status.verifier" @click="start('verifier')">
            {{ status.verifier ? 'Actif' : 'Demarrer' }}
          </button>
          <button class="ghost" :disabled="!status.verifier" @click="stop('verifier')">Arreter</button>
        </div>
      </section>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>Journal local</h2>
          <p>Les evenements importants du launcher apparaissent ici.</p>
        </div>
        <button class="ghost" @click="refreshStatus">Rafraichir</button>
      </div>
      <pre class="logs">{{ logs.join('\n') }}</pre>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { nodeStatus, startNode, stopNode, type NodeRole } from './tauri';

const form = reactive({
  repoRoot: localStorage.getItem('silicium.repoRoot') || '',
  orchestratorUrl: localStorage.getItem('silicium.orchestratorUrl') || 'http://213.32.68.67:46100',
  advertiseHost: localStorage.getItem('silicium.advertiseHost') || '',
});

const status = reactive({ worker: false, verifier: false });
const logs = ref<string[]>(['Silicium Node pret. Configurez le repo et demarrez un role.']);

function remember() {
  localStorage.setItem('silicium.repoRoot', form.repoRoot);
  localStorage.setItem('silicium.orchestratorUrl', form.orchestratorUrl);
  localStorage.setItem('silicium.advertiseHost', form.advertiseHost);
}

function pushLog(message: string) {
  logs.value = [`${new Date().toLocaleTimeString()}  ${message}`, ...logs.value].slice(0, 80);
}

async function refreshStatus() {
  try {
    const next = await nodeStatus();
    status.worker = next.worker;
    status.verifier = next.verifier;
  } catch (error) {
    pushLog(`Status indisponible: ${String(error)}`);
  }
}

async function start(role: NodeRole) {
  remember();
  try {
    const nodeId = role === 'worker' ? 'worker-desktop-1' : 'verifier-desktop-1';
    const reputationScore = role === 'worker' ? 120 : 90;
    const message = await startNode({
      role,
      repoRoot: form.repoRoot,
      orchestratorUrl: form.orchestratorUrl,
      advertiseHost: form.advertiseHost,
      nodeId,
      reputationScore,
    });
    pushLog(message);
    await refreshStatus();
  } catch (error) {
    pushLog(`Erreur start ${role}: ${String(error)}`);
  }
}

async function stop(role: NodeRole) {
  try {
    const message = await stopNode(role);
    pushLog(message);
    await refreshStatus();
  } catch (error) {
    pushLog(`Erreur stop ${role}: ${String(error)}`);
  }
}

onMounted(refreshStatus);
</script>

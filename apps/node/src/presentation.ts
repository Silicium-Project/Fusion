/** Pure presentation of observed node activity; no runtime calls or persisted state. */
import type { NodeActivity } from './tauri';

export function formatBytes(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDate(seconds: number) {
  if (!seconds) {
    return 'date inconnue';
  }
  return new Date(seconds * 1000).toLocaleString();
}

export function friendlyEvent(item: NodeActivity['history'][number]) {
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
      title:
        item.role === 'verify' ? `Verification demarree${fragment}` : `Calcul demarre${fragment}`,
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

export function machineWorkLabel(machine: NodeActivity['machines'][number]) {
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

export function taskRoleLabel(role: string) {
  if (role === 'verify') return 'Verification';
  if (role === 'compute') return 'Calcul';
  if (role === 'storage') return 'Stockage';
  if (role === 'audit') return 'Audit';
  return role || 'Tache';
}

export function machineWorkDetail(machine: NodeActivity['machines'][number]) {
  const task = machine.activeTasks[0];
  if (machine.lastClaimError) return machine.lastClaimError;
  if (task) {
    const fragment =
      task.fragmentIndex !== null && task.fragmentIndex !== undefined
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

export function machinePresenceLabel(machine: NodeActivity['machines'][number]) {
  if (!machine.online) return 'Hors ligne ou heartbeat expire';
  if (machine.activeTasks.length > 0) return 'Connectee et en cours de travail';
  if (!machine.schedulerActive) return 'Connectee, mais ne reclame plus de tache';
  return 'Connectee et disponible pour le scheduler';
}

export function responseLabel(machine: NodeActivity['machines'][number]) {
  if (machine.lastResponseOk === true) return 'Reponse OK';
  if (machine.lastResponseOk === false) return 'Reponse en erreur';
  return 'Pas encore de retour';
}

export function responseClass(machine: NodeActivity['machines'][number]) {
  if (machine.lastResponseOk === true) return 'ok';
  if (machine.lastResponseOk === false) return 'failed';
  return '';
}

export function shortIdentity(identity: string) {
  if (!identity) return 'identite non annoncee';
  return identity.length > 22 ? `${identity.slice(0, 10)}...${identity.slice(-8)}` : identity;
}

export function candidateSummary(machine: NodeActivity['machines'][number]) {
  if (!machine.candidates.length) return 'aucun candidat annonce';
  const types = [
    ...new Set(machine.candidates.map((candidate) => candidate.candidateType || 'host')),
  ];
  return `${machine.candidates.length} candidat(s) · ${types.join(', ')}`;
}

export function latestTransportProof(machine: NodeActivity['machines'][number]) {
  return machine.transportAttestations[0];
}

export function transportProofSummary(machine: NodeActivity['machines'][number]) {
  const proof = latestTransportProof(machine);
  if (!proof) return `${candidateSummary(machine)} · aucune preuve de chemin`;
  return `${transportScopeLabel(proof.proofScope)} · ${proof.peerProofVerified ? 'preuve distante signee' : 'observation locale signee'}`;
}

export function p2pStatusLabel(machine: NodeActivity['machines'][number]) {
  if (!machine.online) return 'Hors ligne';
  const proof = latestTransportProof(machine);
  if (!proof) return machine.candidates.length ? 'ICE non atteste' : 'Aucune preuve P2P';
  return transportRouteLabel(proof.route, proof.transportBackend);
}

export function p2pStatusClass(machine: NodeActivity['machines'][number]) {
  if (!machine.online) return 'offline';
  const proof = latestTransportProof(machine);
  if (!proof) return 'warning';
  if (proof.route === 'direct' && proof.success) return 'ok';
  if (proof.route === 'relay') return 'relay';
  if (proof.route === 'central') return 'central';
  return 'warning';
}

export function transportRouteLabel(route: string, backend: string) {
  if (route === 'direct' && backend === 'ice') return 'Direct ICE prouve';
  if (route === 'direct') return 'Direct pair observe';
  if (route === 'relay') return 'Relay observe';
  if (route === 'central') return 'Flux central observe';
  if (route === 'failed') return 'Connexion directe echouee';
  return 'Chemin inconnu';
}

export function transportScopeLabel(scope: string) {
  if (scope === 'payload_transfer') return 'transfert de contenu';
  if (scope === 'task_delivery') return 'livraison de tache';
  return 'test de connectivite';
}

export function shortProof(value: string) {
  if (!value) return 'hash indisponible';
  return value.length > 24 ? `${value.slice(0, 12)}...${value.slice(-8)}` : value;
}

export function formatRelativeTime(seconds: number) {
  if (!seconds) return 'jamais';
  const age = Math.max(0, Math.round(Date.now() / 1000 - seconds));
  if (age < 5) return 'a l instant';
  if (age < 60) return `il y a ${age}s`;
  if (age < 3600) return `il y a ${Math.floor(age / 60)} min`;
  if (age < 86400) return `il y a ${Math.floor(age / 3600)} h`;
  return `il y a ${Math.floor(age / 86400)} j`;
}

export function formatUpdateInterval(seconds: number) {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds / 3600)} h`;
}

export function formatDurationMs(durationMs: number) {
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

export function friendlyError(error: unknown) {
  const raw = error instanceof Error ? error.message : String(error);
  const messages: Record<string, string> = {
    managed_runtime_not_found: 'le runtime Silicium est absent; reinstallez l application',
    orchestrator_url_missing: 'l adresse de l orchestrateur est vide',
    orchestrator_url_invalid_scheme: 'l adresse doit commencer par http:// ou https://',
    orchestrator_url_invalid_host: 'l adresse de l orchestrateur est invalide',
    node_not_ready_after_supervisor_start:
      'le service local met trop de temps a demarrer; une nouvelle verification sera faite automatiquement',
    supervisor_exited_before_ready:
      'le superviseur local s est arrete avant que le reseau soit disponible',
  };
  const knownPrefix = Object.keys(messages).find((key) => raw.startsWith(key));
  return knownPrefix ? messages[knownPrefix] : raw;
}

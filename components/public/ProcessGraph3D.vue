<template>
  <div
    ref="root"
    class="process-graph-3d"
    :data-active-node="activeNodeId"
    data-camera-moving="false"
    :data-camera-target="activeNodeId"
    data-camera-position="0,0,0"
    role="img"
    :aria-label="t('graph3d.aria', { node: activeNodeLabel })"
    @pointermove="handlePointerMove"
    @pointerleave="handlePointerLeave"
  >
    <canvas ref="canvas" class="process-graph-3d__canvas" aria-hidden="true"></canvas>

    <div class="process-graph-3d__labels" aria-hidden="true">
      <span
        v-for="node in nodes"
        :key="node.id"
        class="process-graph-3d__label"
        :data-node-label="node.id"
      >
        <i></i>
        {{ node.label }}
      </span>
    </div>

    <div class="process-graph-3d__readout" aria-hidden="true">
      <span class="process-graph-3d__readout-dot"></span>
      <span>
        <small>{{ t('graph3d.target') }}</small>
        <strong>{{ activeNodeLabel }}</strong>
      </span>
    </div>

    <div v-if="!ready" class="process-graph-3d__loading" aria-hidden="true">
      <span class="process-graph-3d__loading-orbit"></span>
      <span>{{ t('graph3d.loading') }}</span>
    </div>

    <div v-if="fallback" class="process-graph-3d__fallback">
      <strong>{{ t('graph3d.unsupported') }}</strong>
      <span>{{ t('graph3d.fallback') }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import * as THREE from 'three';

export type ProcessGraphNode = {
  id: string;
  label: string;
  phase: number;
  x: number;
  y: number;
  z: number;
  tone: 'mint' | 'violet' | 'blue' | 'amber';
};

const props = defineProps<{
  nodes: readonly ProcessGraphNode[];
  activeNodeId: string;
  activePhase: number;
}>();

const { t } = useI18n();
const root = ref<HTMLElement | null>(null);
const canvas = ref<HTMLCanvasElement | null>(null);
const ready = ref(false);
const fallback = ref(false);

const activeNodeLabel = computed(() => {
  return props.nodes.find(node => node.id === props.activeNodeId)?.label || t('graph3d.network');
});

type NodeRuntime = {
  group: THREE.Group;
  body: THREE.Mesh<THREE.BoxGeometry, THREE.MeshStandardMaterial>;
  ring: THREE.Mesh<THREE.TorusGeometry, THREE.MeshBasicMaterial>;
  position: THREE.Vector3;
  color: number;
};

type EdgeRuntime = {
  phase: number;
  curve: THREE.LineCurve3;
  tube: THREE.Mesh<THREE.TubeGeometry, THREE.MeshBasicMaterial>;
};

const palette: Record<ProcessGraphNode['tone'], number> = {
  mint: 0x13bfae,
  violet: 0x7669e8,
  blue: 0x4c86dc,
  amber: 0xd89a45,
};

const edgeDefinitions: Array<[string, string, number]> = [
  ['source', 'relay-a', 0],
  ['source', 'relay-b', 1],
  ['relay-a', 'compute-a', 2],
  ['relay-a', 'compute-b', 2],
  ['relay-b', 'compute-a', 2],
  ['relay-b', 'compute-b', 2],
  ['compute-a', 'result', 3],
  ['compute-b', 'result', 3],
];

const nodeRuntimes = new Map<string, NodeRuntime>();
const edgeRuntimes: EdgeRuntime[] = [];
const particles: Array<{ mesh: THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>; edge: EdgeRuntime; phase: number; speed: number }> = [];
const labelElements = new Map<string, HTMLElement>();

let scene: THREE.Scene | null = null;
let renderer: THREE.WebGLRenderer | null = null;
let camera: THREE.PerspectiveCamera | null = null;
let graphRoot: THREE.Group | null = null;
let resizeObserver: ResizeObserver | null = null;
let animationFrame = 0;
let lastFrame = 0;
let reducedMotion = false;

const currentCameraPosition = new THREE.Vector3(8.6, 5.8, 11.8);
const desiredCameraPosition = new THREE.Vector3();
const currentCameraLook = new THREE.Vector3();
const desiredCameraLook = new THREE.Vector3();
const pointer = new THREE.Vector2();
const pointerTarget = new THREE.Vector2();
const projectedPoint = new THREE.Vector3();

function nodePosition(node: ProcessGraphNode) {
  return new THREE.Vector3(node.x, node.y, node.z);
}

function createNode(node: ProcessGraphNode) {
  if (!graphRoot) return;

  const color = palette[node.tone];
  const group = new THREE.Group();
  const position = nodePosition(node);
  group.position.copy(position);
  group.userData.nodeId = node.id;

  const bodyMaterial = new THREE.MeshStandardMaterial({
    color: 0xe7f7f3,
    emissive: color,
    emissiveIntensity: 0.1,
    metalness: 0.12,
    roughness: 0.22,
    transparent: true,
    opacity: 0.93,
  });
  const body = new THREE.Mesh(new THREE.BoxGeometry(1.04, 0.78, 0.9), bodyMaterial);
  group.add(body);

  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(0.78, 0.018, 8, 48),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.5 }),
  );
  ring.rotation.x = Math.PI / 2;
  ring.position.y = -0.02;
  group.add(ring);

  nodeRuntimes.set(node.id, { group, body, ring, position, color });
  graphRoot.add(group);
}

function createEdge(fromId: string, toId: string, phase: number) {
  if (!graphRoot) return;
  const from = nodeRuntimes.get(fromId)?.position;
  const to = nodeRuntimes.get(toId)?.position;
  if (!from || !to) return;

  const curve = new THREE.LineCurve3(from, to);
  const geometry = new THREE.TubeGeometry(curve, 18, 0.021, 6, false);
  const tube = new THREE.Mesh(
    geometry,
    new THREE.MeshBasicMaterial({ color: 0x6ca9a3, transparent: true, opacity: 0.24 }),
  );
  graphRoot.add(tube);
  edgeRuntimes.push({ phase, curve, tube });
}

function createParticle(edge: EdgeRuntime, index: number) {
  if (!graphRoot) return;
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(index % 2 ? 0.045 : 0.06, 8, 8),
    new THREE.MeshBasicMaterial({ color: index % 3 ? 0x13bfae : 0x7669e8, transparent: true, opacity: 0.92 }),
  );
  graphRoot.add(mesh);
  particles.push({ mesh, edge, phase: (index * 0.17) % 1, speed: 0.055 + (index % 3) * 0.014 });
}

function setupScene() {
  if (!canvas.value || !root.value) return;

  try {
    reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0xeaf5f2, 10, 24);

    camera = new THREE.PerspectiveCamera(34, 1, 0.1, 60);
    camera.position.copy(currentCameraPosition);

    renderer = new THREE.WebGLRenderer({ canvas: canvas.value, antialias: true, alpha: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;
    const hemisphere = new THREE.HemisphereLight(0xffffff, 0x9bc7c0, 1.7);
    scene.add(hemisphere);
    const key = new THREE.DirectionalLight(0xffffff, 2.25);
    key.position.set(-4, 8, 8);
    scene.add(key);
    const fill = new THREE.PointLight(0x7669e8, 1.35, 16, 2);
    fill.position.set(4, 1, -5);
    scene.add(fill);

    graphRoot = new THREE.Group();
    scene.add(graphRoot);

    const grid = new THREE.GridHelper(15, 15, 0x61a99e, 0xa4cac4);
    grid.position.y = -3.85;
    const gridMaterial = grid.material as THREE.LineBasicMaterial;
    gridMaterial.transparent = true;
    gridMaterial.opacity = 0.16;
    graphRoot.add(grid);

    const hub = new THREE.Group();
    const hubMaterial = new THREE.MeshStandardMaterial({
      color: 0xe9fbf7,
      emissive: 0x13bfae,
      emissiveIntensity: 0.28,
      metalness: 0.22,
      roughness: 0.18,
      transparent: true,
      opacity: 0.98,
    });
    const hubBody = new THREE.Mesh(new THREE.SphereGeometry(0.92, 24, 16), hubMaterial);
    hub.add(hubBody);
    const hubRing = new THREE.Mesh(
      new THREE.TorusGeometry(1.24, 0.018, 8, 64),
      new THREE.MeshBasicMaterial({ color: 0x7669e8, transparent: true, opacity: 0.35 }),
    );
    hubRing.rotation.x = Math.PI / 2.2;
    hub.add(hubRing);
    graphRoot.add(hub);

    props.nodes.forEach(createNode);
    edgeDefinitions.forEach(([from, to, phase]) => createEdge(from, to, phase));
    edgeRuntimes.forEach((edge, edgeIndex) => {
      createParticle(edge, edgeIndex);
    });

    props.nodes.forEach(node => {
      const element = root.value?.querySelector<HTMLElement>(`[data-node-label="${node.id}"]`);
      if (element) labelElements.set(node.id, element);
    });

    updateCameraTarget();
    resize();
    ready.value = true;
    animationFrame = requestAnimationFrame(animate);
  } catch (error) {
    console.warn('[Silicium] Impossible d’initialiser le graphe WebGL.', error);
    fallback.value = true;
  }
}

function updateCameraTarget() {
  if (!camera || !root.value) return;
  const selected = nodeRuntimes.get(props.activeNodeId);
  const target = selected?.position || new THREE.Vector3(0, 0, 0);
  const direction = target.clone();
  if (direction.lengthSq() < 0.01) direction.set(0, 0, 1);
  direction.normalize();

  // The destination is derived from the selected node. There is no authored
  // camera path: jumping to another step simply recomputes this XYZ target.
  desiredCameraLook.copy(target);
  desiredCameraPosition.copy(target).add(direction.multiplyScalar(4.65));
  desiredCameraPosition.y += 1.15;
  root.value.dataset.cameraTarget = props.activeNodeId;
}

function resize() {
  if (!renderer || !camera || !root.value) return;
  const { width, height } = root.value.getBoundingClientRect();
  if (!width || !height) return;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function updateLabels() {
  if (!camera || !root.value) return;
  const { width, height } = root.value.getBoundingClientRect();
  labelElements.forEach((element, id) => {
    const runtime = nodeRuntimes.get(id);
    if (!runtime) return;
    projectedPoint.copy(runtime.position).project(camera!);
    const visible = projectedPoint.z > -1 && projectedPoint.z < 1 && Math.abs(projectedPoint.x) < 1.08 && Math.abs(projectedPoint.y) < 1.08;
    const x = (projectedPoint.x * 0.5 + 0.5) * width;
    const y = (-projectedPoint.y * 0.5 + 0.5) * height;
    element.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%)`;
    element.style.opacity = visible ? (id === props.activeNodeId ? '1' : '0.62') : '0';
    element.dataset.depth = projectedPoint.z.toFixed(3);
  });
}

function updateMaterials() {
  edgeRuntimes.forEach(edge => {
    const active = edge.phase === props.activePhase;
    const reached = edge.phase < props.activePhase;
    edge.tube.material.opacity = active ? 0.72 : reached ? 0.4 : 0.17;
    edge.tube.material.color.set(active ? 0x13bfae : reached ? 0x6ca9a3 : 0x8ab5b0);
  });

  nodeRuntimes.forEach((node, id) => {
    const active = id === props.activeNodeId;
    const phase = props.nodes.find(item => item.id === id)?.phase ?? Number.POSITIVE_INFINITY;
    const reached = phase < props.activePhase;
    node.body.material.emissiveIntensity = active ? 0.46 : reached ? 0.2 : 0.07;
    node.body.material.opacity = active ? 1 : reached ? 0.95 : 0.78;
    node.ring.material.opacity = active ? 0.68 : 0.04;
  });
}

function animate(timestamp: number) {
  if (!renderer || !scene || !camera || !root.value) return;
  const delta = Math.min(0.05, (timestamp - lastFrame) / 1000 || 0.016);
  lastFrame = timestamp;
  const easing = reducedMotion ? 1 : 1 - Math.pow(0.0008, delta);

  currentCameraPosition.lerp(desiredCameraPosition, easing);
  currentCameraLook.lerp(desiredCameraLook, easing);
  if (reducedMotion) {
    pointer.set(0, 0);
    pointerTarget.set(0, 0);
  } else {
    pointer.lerp(pointerTarget, Math.min(1, delta * 5.4));
  }

  camera.position.copy(currentCameraPosition);
  camera.position.x += pointer.x * 0.34;
  camera.position.y -= pointer.y * 0.22;
  camera.position.z += Math.abs(pointer.x) * 0.08;
  camera.lookAt(currentCameraLook);

  const distance = currentCameraPosition.distanceTo(desiredCameraPosition);
  const moving = !reducedMotion && (distance > 0.07 || currentCameraLook.distanceTo(desiredCameraLook) > 0.07 || pointer.length() > 0.018);
  root.value.dataset.cameraMoving = moving ? 'true' : 'false';
  root.value.dataset.cameraPosition = [currentCameraPosition.x, currentCameraPosition.y, currentCameraPosition.z].map(value => value.toFixed(2)).join(',');
  root.value.dataset.cameraX = currentCameraPosition.x.toFixed(2);
  root.value.dataset.cameraY = currentCameraPosition.y.toFixed(2);
  root.value.dataset.cameraZ = currentCameraPosition.z.toFixed(2);
  root.value.dataset.cameraDistance = distance.toFixed(3);
  const hub = graphRoot?.children.find(child => child.type === 'Group' && child.userData.nodeId === undefined);
  if (hub) {
    const ring = hub.children.find(child => child instanceof THREE.Mesh && child.geometry instanceof THREE.TorusGeometry);
    if (ring) ring.rotation.z += delta * 0.18;
  }
  particles.forEach((particle, index) => {
    const t = (timestamp * 0.001 * particle.speed + particle.phase) % 1;
    particle.edge.curve.getPointAt(t, particle.mesh.position);
    particle.mesh.material.opacity = 0.36 + Math.sin((t + index) * Math.PI) * 0.36;
  });
  updateMaterials();
  updateLabels();
  renderer.render(scene, camera);
  animationFrame = requestAnimationFrame(animate);
}

function handlePointerMove(event: PointerEvent) {
  if (!root.value || reducedMotion) return;
  const bounds = root.value.getBoundingClientRect();
  pointerTarget.x = ((event.clientX - bounds.left) / bounds.width - 0.5) * 2;
  pointerTarget.y = ((event.clientY - bounds.top) / bounds.height - 0.5) * 2;
}

function handlePointerLeave() {
  pointerTarget.set(0, 0);
}

watch(() => props.activeNodeId, updateCameraTarget);

onMounted(() => {
  setupScene();
  resizeObserver = new ResizeObserver(resize);
  if (root.value) resizeObserver.observe(root.value);
});

onBeforeUnmount(() => {
  cancelAnimationFrame(animationFrame);
  resizeObserver?.disconnect();
  renderer?.dispose();
  scene?.traverse(object => {
    if (object instanceof THREE.Mesh) {
      object.geometry.dispose();
      if (Array.isArray(object.material)) object.material.forEach(material => material.dispose());
      else object.material.dispose();
    }
  });
  nodeRuntimes.clear();
  edgeRuntimes.splice(0);
  particles.splice(0);
  labelElements.clear();
});
</script>

<style scoped>
.process-graph-3d{position:relative;width:100%;height:100%;min-height:31rem;overflow:hidden;border:1px solid rgba(255,255,255,.82);border-radius:2rem;background:radial-gradient(circle at 50% 42%,rgba(255,255,255,.96),rgba(224,245,240,.48) 46%,rgba(212,224,246,.36) 100%);box-shadow:inset 0 1px 0 rgba(255,255,255,.98),inset 0 0 0 1px rgba(25,51,73,.06),0 32px 62px rgba(25,51,73,.14);isolation:isolate}.process-graph-3d::before{position:absolute;inset:0;z-index:-1;background:radial-gradient(circle at 22% 78%,rgba(118,105,232,.12),transparent 28%),radial-gradient(circle at 78% 20%,rgba(19,191,174,.16),transparent 32%);content:'';pointer-events:none}.process-graph-3d__canvas{position:absolute;inset:0;display:block;width:100%;height:100%;outline:none;transition:filter .25s ease}.process-graph-3d__labels{position:absolute;inset:0;pointer-events:none}.process-graph-3d__label{position:absolute;top:0;left:0;display:flex;align-items:center;gap:.38rem;padding:.36rem .56rem;border:1px solid rgba(255,255,255,.86);border-radius:999px;background:rgba(255,255,255,.67);box-shadow:inset 0 1px 0 rgba(255,255,255,.96),0 9px 24px rgba(25,51,73,.12);color:#244055;font-family:var(--font-mono);font-size:.836rem;font-weight:650;letter-spacing:.025em;white-space:nowrap;backdrop-filter:blur(14px);transform:translate(-50%,-50%);transition:opacity .22s ease}.process-graph-3d__label i{width:.38rem;height:.38rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 .22rem rgba(19,191,174,.11)}.process-graph-3d__label[data-node-label=relay-a] i,.process-graph-3d__label[data-node-label=compute-b] i{background:var(--violet-500);box-shadow:0 0 0 .22rem rgba(118,105,232,.11)}.process-graph-3d__label[data-node-label=compute-a] i{background:#4c86dc;box-shadow:0 0 0 .22rem rgba(76,134,220,.11)}.process-graph-3d__label[data-node-label=result] i{background:#d89a45;box-shadow:0 0 0 .22rem rgba(216,154,69,.13)}.process-graph-3d__readout{position:absolute;right:1.1rem;bottom:1rem;display:flex;align-items:center;gap:.55rem;padding:.55rem .7rem;border:1px solid rgba(255,255,255,.74);border-radius:1rem;background:rgba(255,255,255,.58);box-shadow:inset 0 1px 0 rgba(255,255,255,.92),0 12px 28px rgba(25,51,73,.1);backdrop-filter:blur(16px)}.process-graph-3d__readout-dot{width:.48rem;height:.48rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 .28rem rgba(19,191,174,.12);animation:graph-pulse 1.8s ease-in-out infinite}.process-graph-3d__readout small,.process-graph-3d__readout strong{display:block}.process-graph-3d__readout small{color:#6f7f87;font-family:var(--font-mono);font-size:.812rem;letter-spacing:.06em;text-transform:uppercase}.process-graph-3d__readout strong{margin-top:.15rem;color:#244055;font-size:.891rem;letter-spacing:-.025em}.process-graph-3d__loading,.process-graph-3d__fallback{position:absolute;inset:0;display:grid;place-content:center;justify-items:center;gap:.6rem;color:#5d747d;font-family:var(--font-mono);font-size:.857rem;text-align:center}.process-graph-3d__loading-orbit{width:2rem;height:2rem;border:1px solid rgba(19,191,174,.2);border-top-color:var(--mint-500);border-radius:50%;animation:graph-spin 1.1s linear infinite}.process-graph-3d__fallback{padding:2rem;color:#516a75}.process-graph-3d__fallback strong{font-family:var(--font-sans);font-size:.966rem}.process-graph-3d__fallback span{max-width:18rem;line-height:1.6}@keyframes graph-spin{to{transform:rotate(360deg)}}@keyframes graph-pulse{0%,100%{opacity:.48;transform:scale(.85)}50%{opacity:1;transform:scale(1.12)}}@media(max-width:760px){.process-graph-3d{min-height:22rem;border-radius:1.45rem}.process-graph-3d__readout{right:.65rem;bottom:.65rem;padding:.45rem .55rem}.process-graph-3d__readout small{font-size:.812rem}.process-graph-3d__readout strong{font-size:.857rem}.process-graph-3d__label{padding:.27rem .42rem;font-size:.812rem}.process-graph-3d__label i{width:.31rem;height:.31rem}}@media(max-width:420px){.process-graph-3d{min-height:18rem}.process-graph-3d__label{font-size:.812rem}.process-graph-3d__readout{display:none}}@media(prefers-reduced-motion:reduce){.process-graph-3d__canvas{filter:none!important}.process-graph-3d__readout-dot,.process-graph-3d__loading-orbit{animation:none}}
.process-graph-3d{contain:layout paint;border-color:var(--glass-edge);border-radius:var(--radius-lg);background:var(--glass-card);box-shadow:var(--glass-inset),var(--glass-shadow)}.process-graph-3d::before{background:radial-gradient(circle at 22% 78%,rgba(118,105,232,.08),transparent 28%),radial-gradient(circle at 78% 20%,rgba(19,191,174,.1),transparent 32%)}.process-graph-3d__canvas{transition:none}.process-graph-3d__labels{contain:layout paint}.process-graph-3d__label{border-color:var(--glass-edge);background:rgba(255,255,255,.66);box-shadow:var(--shadow-xs);color:var(--ink-800);backdrop-filter:blur(10px)}.process-graph-3d__readout{border-color:var(--glass-edge);background:rgba(255,255,255,.58);box-shadow:var(--shadow-xs);backdrop-filter:blur(12px)}.process-graph-3d__readout small{color:var(--ink-500)}.process-graph-3d__readout strong{color:var(--ink-800)}@media(max-width:760px){.process-graph-3d{border-radius:var(--radius-lg)}}
</style>

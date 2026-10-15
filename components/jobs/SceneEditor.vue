<template>
  <div class="scene-editor">
    <div class="scene-templates" role="group" :aria-label="t('sceneEditor.templatesTitle')">
      <span class="field-label">{{ t('sceneEditor.templatesTitle') }}</span>
      <div class="scene-templates__list">
        <button v-for="name in SCENE_TEMPLATES" :key="name" type="button" class="scene-template" :class="{ 'scene-template--active': template === name }" @click="loadTemplate(name)">
          <span class="scene-template__thumb" :style="{ backgroundImage: thumbnails[name] ? `url(${thumbnails[name]})` : undefined }"></span>
          <span>{{ t(`sceneEditor.templates.${name}`) }}</span>
        </button>
      </div>
      <p v-if="undoScene && cfg === loadedCfg" class="scene-templates__undo" role="status">{{ t('sceneEditor.loaded', { name: t(`sceneEditor.templates.${template}`) }) }} <button type="button" @click="undo">{{ t('sceneEditor.undo') }}</button></p>
    </div>

    <figure class="scene-preview">
      <canvas ref="canvas" :width="canvasSize.width" :height="canvasSize.height" :style="{ aspectRatio: `${scene.width} / ${scene.height}` }" :aria-label="t('sceneEditor.previewAria')" role="img" @click="pick"></canvas>
      <figcaption><span><UiIcon name="sparkle"/>{{ t('sceneEditor.previewCaption') }}</span><span class="scene-preview__size">{{ scene.width }} × {{ scene.height }}</span></figcaption>
    </figure>

    <div class="scene-panels">
      <section class="scene-panel" aria-labelledby="scene-image">
        <h3 id="scene-image">{{ t('sceneEditor.image') }}</h3>
        <label class="field"><span>{{ t('sceneEditor.resolution') }}</span>
          <select class="select" :value="resolutionId" @change="setResolution(($event.target as HTMLSelectElement).value)">
            <option v-for="preset in RESOLUTION_PRESETS" :key="preset.id" :value="preset.id">{{ t(`sceneEditor.resolutions.${preset.id}`) }}</option>
            <option v-if="resolutionId === 'custom'" value="custom">{{ t('sceneEditor.resolutions.custom', { width: scene.width, height: scene.height }) }}</option>
          </select>
          <small>{{ t('sceneEditor.pixels', { pixels: pixelLabel }) }}</small>
        </label>
        <SceneSlider v-model="scene.fov" :label="t('sceneEditor.fov')" :hint="t('sceneEditor.fovHint')" :min="20" :max="120" :step="1" />
        <SceneSlider v-model="scene.camera.z" :label="t('sceneEditor.cameraHeight')" :min="-2" :max="4" :step="0.1" />
      </section>

      <section class="scene-panel" aria-labelledby="scene-objects">
        <div class="scene-panel__head"><h3 id="scene-objects">{{ t('sceneEditor.objects') }}</h3>
          <div class="scene-panel__add"><button type="button" @click="addObject('sphere')"><UiIcon name="plus"/>{{ t('sceneEditor.addSphere') }}</button><button type="button" @click="addObject('plane')"><UiIcon name="plus"/>{{ t('sceneEditor.addPlane') }}</button></div>
        </div>
        <p v-if="!scene.objects.length" class="scene-panel__empty">{{ t('sceneEditor.noObjects') }}</p>
        <ul class="scene-items">
          <li v-for="item in scene.objects" :key="item.id" :ref="(element) => itemRefs.set(item.id, element as HTMLElement)" class="scene-item" :class="{ 'scene-item--open': selected === item.id }">
            <div class="scene-item__row">
              <button type="button" class="scene-item__toggle" :aria-expanded="selected === item.id" @click="select(item.id)">
                <span class="scene-item__swatch" :class="`scene-item__swatch--${item.kind}`" :style="{ background: toHex(item.material.color) }"></span>
                <strong>{{ objectName(item) }}</strong>
                <small>{{ item.kind === 'sphere' ? t(`sceneEditor.materials.${materialPreset(item.material)}`) : t(`sceneEditor.orientations.${planeOrientation(item)}`) }}</small>
                <UiIcon name="chevron" class="scene-item__chevron"/>
              </button>
              <button type="button" class="scene-item__remove" :aria-label="t('sceneEditor.remove', { name: objectName(item) })" @click="removeObject(item.id)"><UiIcon name="x"/></button>
            </div>
            <div v-if="selected === item.id" class="scene-item__body">
              <template v-if="item.kind === 'sphere'">
                <SceneSlider v-model="item.x" :label="t('sceneEditor.distance')" :hint="t('sceneEditor.distanceHint')" :min="1" :max="30" />
                <SceneSlider :model-value="-item.y" :label="t('sceneEditor.side')" :min="-10" :max="10" @update:model-value="item.y = -$event" />
                <SceneSlider v-model="item.z" :label="t('sceneEditor.height')" :min="-5" :max="8" />
                <SceneSlider v-model="item.radius" :label="t('sceneEditor.radius')" :min="0.1" :max="5" :step="0.05" />
              </template>
              <template v-else>
                <label class="field"><span>{{ t('sceneEditor.orientation') }}</span>
                  <select class="select" :value="planeOrientation(item)" @change="setOrientation(item, ($event.target as HTMLSelectElement).value)">
                    <option v-for="(_, name) in PLANE_ORIENTATIONS" :key="name" :value="name">{{ t(`sceneEditor.orientations.${name}`) }}</option>
                    <option v-if="planeOrientation(item) === 'custom'" value="custom">{{ t('sceneEditor.orientations.custom') }}</option>
                  </select>
                </label>
                <SceneSlider v-if="planeOrientation(item) === 'back'" v-model="item.x" :label="t('sceneEditor.distance')" :min="2" :max="40" />
                <SceneSlider v-else v-model="item.z" :label="t('sceneEditor.height')" :min="-5" :max="10" />
              </template>
              <div class="scene-item__look">
                <label class="scene-color"><span>{{ t('sceneEditor.color') }}</span><input type="color" :value="toHex(item.material.color)" @input="item.material.color = fromHex(($event.target as HTMLInputElement).value)"></label>
                <label class="field"><span>{{ t('sceneEditor.material') }}</span>
                  <select class="select" :value="materialPreset(item.material)" @change="setMaterial(item.material, ($event.target as HTMLSelectElement).value)">
                    <option v-for="(_, name) in MATERIAL_PRESETS" :key="name" :value="name">{{ t(`sceneEditor.materials.${name}`) }}</option>
                    <option v-if="materialPreset(item.material) === 'custom'" value="custom">{{ t('sceneEditor.materials.custom') }}</option>
                  </select>
                </label>
              </div>
              <details class="scene-item__fine">
                <summary>{{ t('sceneEditor.fine') }}</summary>
                <SceneSlider v-model="item.material.reflection" :label="t('sceneEditor.reflection')" :min="0" :max="0.95" :step="0.01" />
                <SceneSlider v-model="item.material.specular" :label="t('sceneEditor.specular')" :min="0" :max="2" :step="0.05" />
                <SceneSlider v-model="item.material.shininess" :label="t('sceneEditor.shininess')" :min="1" :max="512" :step="1" />
              </details>
            </div>
          </li>
        </ul>
      </section>

      <section class="scene-panel" aria-labelledby="scene-lights">
        <div class="scene-panel__head"><h3 id="scene-lights">{{ t('sceneEditor.lights') }}</h3>
          <div class="scene-panel__add"><button type="button" @click="addLight"><UiIcon name="plus"/>{{ t('sceneEditor.addLight') }}</button></div>
        </div>
        <p v-if="!scene.lights.length" class="scene-panel__empty">{{ t('sceneEditor.noLights') }}</p>
        <ul class="scene-items">
          <li v-for="(light, index) in scene.lights" :key="light.id" class="scene-item" :class="{ 'scene-item--open': selected === light.id }">
            <div class="scene-item__row">
              <button type="button" class="scene-item__toggle" :aria-expanded="selected === light.id" @click="select(light.id)">
                <span class="scene-item__swatch scene-item__swatch--light" :style="{ background: toHex(light.color) }"></span>
                <strong>{{ t('sceneEditor.light', { index: index + 1 }) }}</strong>
                <small>{{ t('sceneEditor.intensityValue', { value: Math.round(light.intensity) }) }}</small>
                <UiIcon name="chevron" class="scene-item__chevron"/>
              </button>
              <button type="button" class="scene-item__remove" :aria-label="t('sceneEditor.remove', { name: t('sceneEditor.light', { index: index + 1 }) })" @click="removeLight(light.id)"><UiIcon name="x"/></button>
            </div>
            <div v-if="selected === light.id" class="scene-item__body">
              <SceneSlider v-model="light.x" :label="t('sceneEditor.distance')" :hint="t('sceneEditor.distanceHint')" :min="-10" :max="30" />
              <SceneSlider :model-value="-light.y" :label="t('sceneEditor.side')" :min="-15" :max="15" @update:model-value="light.y = -$event" />
              <SceneSlider v-model="light.z" :label="t('sceneEditor.height')" :min="-5" :max="15" />
              <SceneSlider v-model="light.intensity" :label="t('sceneEditor.intensity')" :min="0" :max="1500" :step="10" />
              <label class="scene-color"><span>{{ t('sceneEditor.color') }}</span><input type="color" :value="toHex(light.color)" @input="light.color = fromHex(($event.target as HTMLInputElement).value)"></label>
            </div>
          </li>
        </ul>
      </section>
    </div>

    <details class="scene-file">
      <summary><UiIcon name="code"/>{{ t('sceneEditor.file') }}</summary>
      <p>{{ t('sceneEditor.fileHint') }} <a :href="downloadUrl" :download="fileName" class="scene-file__download">{{ t('sceneEditor.download') }}</a></p>
      <pre>{{ cfg }}</pre>
    </details>
  </div>
</template>

<script setup lang="ts">
// Visual editor of a raytracer scene: templates, a live preview rendered with
// a port of the engine, and forms for the camera, objects and lights. The
// parent gets the scene through `v-model` and writes the `.cfg` with
// `sceneToCfg` when the job is sent.
import { cloneScene, MATERIAL_PRESETS, materialPreset, newLight, newPlane, newSphere, parseSceneText, PLANE_ORIENTATIONS, planeOrientation, RESOLUTION_PRESETS, sceneFileName, sceneToCfg, type Rgb, type SceneMaterial, type SceneModel, type SceneObject, type ScenePlane } from '~/utils/scene';
import { pickPrimitive, previewSize, renderScene, toRgba } from '~/utils/sceneRender';
import { SCENE_TEMPLATES, sceneTemplate, type SceneTemplate } from '~/utils/sceneTemplates';

const props = withDefaults(defineProps<{ title?: string }>(), { title: '' });
const scene = defineModel<SceneModel>({ required: true });
const { t } = useI18n();

const template = ref<SceneTemplate | ''>('');
const undoScene = ref<SceneModel | null>(null);
/** `.cfg` right after a template was loaded: "Undo" is offered until the scene changes. */
const loadedCfg = ref('');
const selected = ref<number | null>(null);
const canvas = ref<HTMLCanvasElement | null>(null);
const itemRefs = new Map<number, HTMLElement>();
const thumbnails = reactive<Partial<Record<SceneTemplate, string>>>({});

const cfg = computed(() => sceneToCfg(scene.value, props.title));
const fileName = computed(() => sceneFileName(props.title));
const downloadUrl = computed(() => `data:text/plain;charset=utf-8,${encodeURIComponent(cfg.value)}`);
const resolutionId = computed(() => RESOLUTION_PRESETS.find((preset) => preset.width === scene.value.width && preset.height === scene.value.height)?.id || 'custom');
const pixelLabel = computed(() => (scene.value.width * scene.value.height).toLocaleString());

// ------------------------------------------------------------ preview
// Rendered small while the user drags a slider, sharper once they stop.
const FAST_WIDTH = 200;
const FULL_WIDTH = 480;
const quality = ref<'fast' | 'full'>('full');
const canvasSize = computed(() => previewSize(scene.value, quality.value === 'fast' ? FAST_WIDTH : FULL_WIDTH, quality.value === 'fast' ? 140 : 340));
let fastTimer: ReturnType<typeof setTimeout> | undefined;
let fullTimer: ReturnType<typeof setTimeout> | undefined;

function draw() {
  const element = canvas.value;
  if (!element) return;
  const context = element.getContext('2d');
  if (!context) return;
  const { width, height } = canvasSize.value;
  element.width = width;
  element.height = height;
  const pixels = renderScene(parseSceneText(cfg.value), width, height);
  context.putImageData(new ImageData(toRgba(pixels), width, height), 0, 0);
}

function schedule() {
  clearTimeout(fastTimer);
  clearTimeout(fullTimer);
  fastTimer = setTimeout(() => { quality.value = 'fast'; nextTick(draw); }, 16);
  fullTimer = setTimeout(() => { quality.value = 'full'; nextTick(draw); }, 260);
}

watch(cfg, schedule);
onMounted(() => {
  draw();
  // Template thumbnails, one per frame so the page stays responsive.
  SCENE_TEMPLATES.forEach((name, index) => setTimeout(() => {
    const model = sceneTemplate(name);
    const size = previewSize(model, 96, 60);
    const pixels = renderScene(parseSceneText(sceneToCfg(model)), size.width, size.height);
    const thumbnail = document.createElement('canvas');
    thumbnail.width = size.width;
    thumbnail.height = size.height;
    thumbnail.getContext('2d')?.putImageData(new ImageData(toRgba(pixels), size.width, size.height), 0, 0);
    thumbnails[name] = thumbnail.toDataURL();
  }, 120 * (index + 1)));
});
onBeforeUnmount(() => { clearTimeout(fastTimer); clearTimeout(fullTimer); });

/** Click on the preview: open the object under the cursor. */
function pick(event: MouseEvent) {
  const element = canvas.value;
  if (!element) return;
  const box = element.getBoundingClientRect();
  const index = pickPrimitive(parseSceneText(cfg.value), (event.clientX - box.left) / box.width, (event.clientY - box.top) / box.height);
  // The engine lists every sphere before the planes.
  const spheres = scene.value.objects.filter((item) => item.kind === 'sphere');
  const planes = scene.value.objects.filter((item) => item.kind === 'plane');
  const item = index === undefined ? undefined : index < spheres.length ? spheres[index] : planes[index - spheres.length];
  if (!item) return;
  selected.value = item.id;
  nextTick(() => itemRefs.get(item.id)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }));
}

// ------------------------------------------------------------ editing
function loadTemplate(name: SceneTemplate) {
  undoScene.value = cloneScene(scene.value);
  // `scene.value` still holds the old scene until the parent updates it.
  const next = sceneTemplate(name);
  scene.value = next;
  loadedCfg.value = sceneToCfg(next, props.title);
  template.value = name;
  selected.value = null;
}

function undo() {
  if (!undoScene.value) return;
  scene.value = undoScene.value;
  undoScene.value = null;
  template.value = '';
}

function setResolution(id: string) {
  const preset = RESOLUTION_PRESETS.find((item) => item.id === id);
  if (!preset) return;
  scene.value.width = preset.width;
  scene.value.height = preset.height;
}

function select(id: number) {
  selected.value = selected.value === id ? null : id;
}

function objectName(item: SceneObject): string {
  const index = scene.value.objects.filter((other) => other.kind === item.kind).indexOf(item) + 1;
  return t(`sceneEditor.${item.kind}`, { index });
}

const PALETTE: Rgb[] = [[18, 191, 174], [255, 120, 90], [121, 109, 240], [255, 200, 70], [70, 160, 255], [240, 240, 245]];

function addObject(kind: 'sphere' | 'plane') {
  const count = scene.value.objects.length;
  const item = kind === 'sphere'
    ? newSphere({ x: 5 + (count % 3), y: ((count % 5) - 2) * -1.1, z: 0, material: { color: PALETTE[count % PALETTE.length]!, ...MATERIAL_PRESETS.glossy } })
    : newPlane({ z: -1 });
  scene.value.objects.push(item);
  selected.value = item.id;
}

function removeObject(id: number) {
  scene.value.objects = scene.value.objects.filter((item) => item.id !== id);
}

function addLight() {
  const light = newLight({ x: 2, y: scene.value.lights.length % 2 ? 3 : -3, z: 5 });
  scene.value.lights.push(light);
  selected.value = light.id;
}

function removeLight(id: number) {
  scene.value.lights = scene.value.lights.filter((light) => light.id !== id);
}

function setMaterial(material: SceneMaterial, name: string) {
  const preset = MATERIAL_PRESETS[name as keyof typeof MATERIAL_PRESETS];
  if (preset) Object.assign(material, preset);
}

function setOrientation(plane: ScenePlane, name: string) {
  const normal = PLANE_ORIENTATIONS[name as keyof typeof PLANE_ORIENTATIONS];
  if (!normal) return;
  plane.normal = [...normal];
  if (name === 'back') { plane.x = Math.max(plane.x, 10); plane.z = 0; }
  if (name === 'ceiling') { plane.z = Math.max(plane.z, 4); plane.x = 0; }
  if (name === 'floor') { plane.z = Math.min(plane.z, -1); plane.x = 0; }
}

const toHex = (rgb: Rgb) => `#${rgb.map((value) => Math.round(Math.min(255, Math.max(0, value))).toString(16).padStart(2, '0')).join('')}`;
const fromHex = (hex: string): Rgb => [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16) || 0) as Rgb;
</script>

<style scoped>
.scene-editor{display:grid;min-width:0;gap:1rem}.scene-editor>*{min-width:0}
.scene-templates{display:grid;gap:.5rem}.scene-templates__list{display:grid;grid-template-columns:repeat(auto-fill,minmax(88px,1fr));gap:.5rem}
.scene-template{display:grid;gap:.35rem;padding:.35rem;border:1px solid var(--border);border-radius:.7rem;background:white;color:var(--ink-800);font:inherit;font-size:.82rem;font-weight:650;text-align:left;cursor:pointer;transition:border-color .15s,box-shadow .15s}
.scene-template:hover{border-color:var(--mint-500)}.scene-template--active{border-color:var(--mint-600);box-shadow:0 0 0 3px var(--mint-100)}
.scene-template__thumb{display:block;aspect-ratio:16/10;border-radius:.45rem;background:linear-gradient(180deg,#5e8ad6,#a9c0e8) center/cover no-repeat}
.scene-templates__undo{margin:0;color:var(--ink-600);font-size:.84rem}.scene-templates__undo button{padding:0;border:0;background:none;color:var(--mint-700);font:inherit;font-weight:750;text-decoration:underline;cursor:pointer}
.scene-preview{margin:0;overflow:hidden;border:1px solid var(--border);border-radius:var(--radius-md);background:#0b1523}
.scene-preview canvas{display:block;width:100%;max-height:420px;object-fit:contain;cursor:crosshair}
.scene-preview figcaption{display:flex;justify-content:space-between;gap:.75rem;padding:.55rem .8rem;background:var(--surface-soft);color:var(--ink-600);font-size:.82rem;line-height:1.4}
.scene-preview figcaption span{display:inline-flex;align-items:center;gap:.4rem}.scene-preview figcaption svg{width:.85rem;flex:none;color:var(--mint-700)}.scene-preview__size{flex:none;font-family:var(--font-mono)}
.scene-panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:.8rem;align-items:start}
.scene-panel{display:grid;gap:.75rem;padding:.9rem;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}
.scene-panel h3{margin:0;color:var(--ink-950);font-size:.95rem}.scene-panel__head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.5rem}
.scene-panel__add{display:flex;gap:.35rem}.scene-panel__add button{display:inline-flex;align-items:center;gap:.3rem;padding:.35rem .55rem;border:1px solid var(--border-strong);border-radius:.5rem;background:white;color:var(--ink-800);font:inherit;font-size:.8rem;font-weight:700;cursor:pointer}.scene-panel__add button:hover{border-color:var(--mint-500);color:var(--mint-700)}.scene-panel__add svg{width:.7rem}
.scene-panel__empty{margin:0;color:var(--ink-600);font-size:.84rem;line-height:1.45}
.scene-panel .field small{color:var(--ink-500);font-size:.8rem}
.scene-items{display:grid;gap:.4rem;margin:0;padding:0;list-style:none}
.scene-item{border:1px solid var(--border);border-radius:.65rem;background:white}.scene-item--open{border-color:rgba(18,191,174,.45)}
.scene-item__row{display:grid;grid-template-columns:1fr auto;align-items:center}
.scene-item__toggle{display:grid;grid-template-columns:auto auto 1fr auto;align-items:center;gap:.5rem;min-width:0;padding:.5rem .6rem;border:0;background:none;color:var(--ink-900);font:inherit;text-align:left;cursor:pointer}
.scene-item__toggle strong{font-size:.86rem}.scene-item__toggle small{overflow:hidden;color:var(--ink-500);font-size:.8rem;text-overflow:ellipsis;white-space:nowrap}
.scene-item__chevron{width:.7rem;color:var(--ink-400);transition:transform .15s}.scene-item--open .scene-item__chevron{transform:rotate(90deg)}
.scene-item__swatch{width:1rem;height:1rem;border:1px solid rgba(11,21,35,.2);border-radius:50%}.scene-item__swatch--plane{border-radius:.2rem;transform:skewX(-20deg)}.scene-item__swatch--light{box-shadow:0 0 0 3px rgba(255,200,70,.35)}
.scene-item__remove{display:grid;width:1.8rem;height:1.8rem;margin-right:.35rem;place-items:center;border:0;border-radius:.4rem;background:none;color:var(--ink-500);cursor:pointer}.scene-item__remove:hover{background:var(--red-100);color:var(--red-600)}.scene-item__remove svg{width:.7rem}
.scene-item__body{display:grid;gap:.7rem;padding:.2rem .7rem .8rem}
.scene-item__look{display:grid;grid-template-columns:auto 1fr;align-items:start;gap:.7rem}.scene-item__look .field{gap:.25rem}.scene-item__look .field>span{color:var(--ink-700);font-size:.84rem;font-weight:650}
.scene-color{display:grid;gap:.25rem;color:var(--ink-700);font-size:.84rem;font-weight:650}.scene-color input{width:3rem;height:2.2rem;padding:.15rem;border:1px solid var(--border-strong);border-radius:.45rem;background:white;cursor:pointer}
.scene-item__fine{display:grid;gap:.6rem}.scene-item__fine summary{color:var(--ink-600);font-size:.82rem;font-weight:700;cursor:pointer}.scene-item__fine[open]{gap:.7rem}
.scene-file{min-width:0;overflow:hidden;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}
.scene-file summary{display:flex;align-items:center;gap:.5rem;padding:.75rem 1rem;color:var(--ink-800);font-size:.88rem;font-weight:720;cursor:pointer}.scene-file summary svg{width:.9rem}
.scene-file p{margin:0;padding:0 1rem .6rem;color:var(--ink-600);font-size:.84rem;line-height:1.5}.scene-file__download{color:var(--mint-700);font-weight:750;text-decoration:underline;text-underline-offset:2px}
.scene-file pre{max-height:260px;margin:0 1rem 1rem;padding:.75rem;overflow:auto;border-radius:.6rem;background:#0f1d2e;color:#d6e4f0;font-family:var(--font-mono);font-size:.76rem;line-height:1.5;tab-size:2}
@media(max-width:620px){.scene-preview figcaption{flex-direction:column}}
</style>

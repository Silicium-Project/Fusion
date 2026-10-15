<template>
  <div class="scene-editor">
    <div class="scene-templates" role="group" :aria-label="t('sceneEditor.templatesTitle')">
      <span class="field-label">{{ t('sceneEditor.templatesTitle') }}</span>
      <div class="scene-templates__list">
        <button v-for="name in SCENE_TEMPLATES" :key="name" type="button" class="scene-template" :class="{ 'scene-template--active': template === name }" @click="loadTemplate(name)">
          <span class="scene-template__thumb" :style="{ backgroundImage: thumbnails[name] ? `url(${thumbnails[name]})` : undefined }"></span>
          <span class="scene-template__name">{{ t(`sceneEditor.templates.${name}`) }}</span>
        </button>
      </div>
      <p v-if="undoScene && cfg === loadedCfg" class="scene-templates__undo" role="status">{{ t('sceneEditor.loaded', { name: t(`sceneEditor.templates.${template}`) }) }} <button type="button" @click="undo">{{ t('sceneEditor.undo') }}</button></p>
    </div>

    <div class="scene-workspace">
      <figure class="scene-preview">
        <div class="scene-preview__frame">
          <canvas ref="canvas" :aria-label="t('sceneEditor.previewAria')" role="img" @click="pick"></canvas>
          <span v-if="previewError" class="scene-preview__error" role="alert">{{ t('sceneEditor.previewError', { message: previewError }) }}</span>
        </div>
        <div class="scene-preview__progress" :style="{ width: `${progress * 100}%` }" :class="{ 'is-done': progress >= 1 }"></div>
        <figcaption>
          <span class="scene-preview__status" role="status">
            <UiIcon :name="progress >= 1 ? 'check' : 'sparkle'"/>
            {{ progress >= 1 ? t('sceneEditor.previewDone', { samples: previewSamples }) : t('sceneEditor.previewRunning', { samples: previewSamples, target: previewTarget }) }}
          </span>
          <span class="scene-preview__size">{{ scene.width }} × {{ scene.height }}</span>
          <small>{{ t('sceneEditor.previewCaption') }}<template v-if="networkSamples > previewTarget">{{ ` ${t('sceneEditor.previewNetwork', { samples: networkSamples })}` }}</template></small>
        </figcaption>
      </figure>

      <div class="scene-controls">
        <div class="scene-tabs" role="tablist" :aria-label="t('sceneEditor.tabsAria')">
          <button v-for="name in TABS" :id="`scene-tab-${name}`" :key="name" type="button" role="tab" class="scene-tab" :class="{ 'scene-tab--active': tab === name }" :aria-selected="tab === name" :aria-controls="`scene-panel-${name}`" @click="tab = name">
            {{ t(`sceneEditor.tabs.${name}`) }}<span v-if="name === 'objects'" class="scene-tab__count">{{ scene.objects.length }}</span><span v-else-if="name === 'lights'" class="scene-tab__count">{{ scene.lights.length }}</span>
          </button>
        </div>

        <!-- Objects -->
        <section v-show="tab === 'objects'" id="scene-panel-objects" class="scene-panel" role="tabpanel" aria-labelledby="scene-tab-objects">
          <div class="scene-add" role="group" :aria-label="t('sceneEditor.addObject')">
            <button v-for="kind in (['sphere', 'box', 'plane', 'panel'] as const)" :key="kind" type="button" @click="addObject(kind)"><UiIcon name="plus"/>{{ t(`sceneEditor.kinds.${kind}`) }}</button>
            <details ref="modelMenu" class="scene-add__menu">
              <summary><UiIcon name="cube"/>{{ t('sceneEditor.kinds.mesh') }}</summary>
              <div class="scene-add__list">
                <button v-for="name in BUILTIN_MODELS" :key="name" type="button" @click="addModel(name)">{{ t(`sceneEditor.models.${name}`) }}</button>
                <button type="button" @click="objInput?.click()"><UiIcon name="upload"/>{{ t('sceneEditor.importObj') }}</button>
              </div>
            </details>
            <input ref="objInput" type="file" accept=".obj,text/plain" hidden @change="importObj">
          </div>
          <p v-if="objError" class="scene-panel__error" role="alert">{{ objError }}</p>
          <p v-if="!scene.objects.length" class="scene-panel__empty">{{ t('sceneEditor.noObjects') }}</p>
          <ul class="scene-items">
            <li v-for="item in scene.objects" :key="item.id" :ref="(element) => itemRefs.set(item.id, element as HTMLElement)" class="scene-item" :class="{ 'scene-item--open': selected === item.id }">
              <div class="scene-item__row">
                <button type="button" class="scene-item__toggle" :aria-expanded="selected === item.id" @click="select(item.id)">
                  <span class="scene-item__swatch" :class="`scene-item__swatch--${item.kind}`" :style="{ background: toHex(item.material.color) }"></span>
                  <strong>{{ objectName(item) }}</strong>
                  <small>{{ objectDetail(item) }}</small>
                  <UiIcon name="chevron" class="scene-item__chevron"/>
                </button>
                <button type="button" class="scene-item__remove" :aria-label="t('sceneEditor.duplicate', { name: objectName(item) })" :title="t('sceneEditor.duplicate', { name: objectName(item) })" @click="duplicateObject(item)"><UiIcon name="layers"/></button>
                <button type="button" class="scene-item__remove" :aria-label="t('sceneEditor.remove', { name: objectName(item) })" @click="removeObject(item.id)"><UiIcon name="x"/></button>
              </div>
              <div v-if="selected === item.id" class="scene-item__body">
                <template v-if="item.kind === 'plane'">
                  <label class="field"><span>{{ t('sceneEditor.orientation') }}</span>
                    <select class="select" :value="planeOrientation(item)" @change="setOrientation(item, ($event.target as HTMLSelectElement).value)">
                      <option v-for="(_, name) in PLANE_ORIENTATIONS" :key="name" :value="name">{{ t(`sceneEditor.orientations.${name}`) }}</option>
                      <option v-if="planeOrientation(item) === 'custom'" value="custom">{{ t('sceneEditor.orientations.custom') }}</option>
                    </select>
                  </label>
                  <SceneSlider v-if="planeOrientation(item) === 'back'" v-model="item.x" :label="t('sceneEditor.distance')" :min="1" :max="40" />
                  <SceneSlider v-else-if="planeOrientation(item) === 'left' || planeOrientation(item) === 'right'" :model-value="-item.y" :label="t('sceneEditor.side')" :min="-15" :max="15" @update:model-value="item.y = -$event" />
                  <SceneSlider v-else v-model="item.z" :label="t('sceneEditor.height')" :min="-5" :max="10" />
                </template>
                <template v-else>
                  <SceneSlider v-model="item.x" :label="t('sceneEditor.distance')" :hint="t('sceneEditor.distanceHint')" :min="0.5" :max="30" />
                  <SceneSlider :model-value="-item.y" :label="t('sceneEditor.side')" :min="-10" :max="10" @update:model-value="item.y = -$event" />
                  <SceneSlider v-model="item.z" :label="t('sceneEditor.height')" :min="-5" :max="8" />
                </template>
                <SceneSlider v-if="item.kind === 'sphere'" v-model="item.radius" :label="t('sceneEditor.radius')" :min="0.05" :max="5" :step="0.05" />
                <template v-if="item.kind === 'box'">
                  <SceneSlider v-model="item.size[1]" :label="t('sceneEditor.width')" :min="0.05" :max="10" :step="0.05" />
                  <SceneSlider v-model="item.size[0]" :label="t('sceneEditor.depth')" :min="0.05" :max="10" :step="0.05" />
                  <SceneSlider v-model="item.size[2]" :label="t('sceneEditor.tall')" :min="0.05" :max="10" :step="0.05" />
                </template>
                <template v-if="item.kind === 'panel'">
                  <SceneSlider v-model="item.width" :label="t('sceneEditor.width')" :min="0.05" :max="20" :step="0.05" />
                  <SceneSlider v-model="item.height" :label="t('sceneEditor.panelHeight')" :min="0.05" :max="20" :step="0.05" />
                  <SceneSlider v-model="item.rotation[1]" :label="t('sceneEditor.tilt')" :hint="t('sceneEditor.tiltHint')" :min="-90" :max="90" :step="1" />
                </template>
                <template v-if="item.kind === 'mesh'">
                  <SceneSlider v-model="item.size" :label="t('sceneEditor.size')" :min="0.05" :max="10" :step="0.05" />
                  <SceneSlider v-model="item.rotation[0]" :label="t('sceneEditor.roll')" :min="-180" :max="180" :step="1" />
                </template>
                <SceneSlider v-if="item.kind === 'box' || item.kind === 'panel' || item.kind === 'mesh'" v-model="item.rotation[2]" :label="t('sceneEditor.turn')" :min="-180" :max="180" :step="1" />

                <div class="scene-item__look">
                  <label class="scene-color"><span>{{ t('sceneEditor.color') }}</span><input type="color" :value="toHex(item.material.color)" @input="item.material.color = fromHex(($event.target as HTMLInputElement).value)"></label>
                  <label class="field"><span>{{ t('sceneEditor.material') }}</span>
                    <select class="select" :value="materialPreset(item.material)" @change="setMaterial(item.material, ($event.target as HTMLSelectElement).value)">
                      <option v-for="(_, name) in MATERIAL_PRESETS" :key="name" :value="name">{{ t(`sceneEditor.materials.${name}`) }}</option>
                      <option v-if="materialPreset(item.material) === 'custom'" value="custom">{{ t('sceneEditor.materials.custom') }}</option>
                    </select>
                  </label>
                </div>
                <p class="scene-item__hint">{{ t(`sceneEditor.materialHints.${item.material.type}`) }}</p>
                <details class="scene-item__fine">
                  <summary>{{ t('sceneEditor.fine') }}</summary>
                  <label class="field"><span>{{ t('sceneEditor.materialType') }}</span>
                    <select v-model="item.material.type" class="select">
                      <option v-for="name in MATERIAL_TYPES" :key="name" :value="name">{{ t(`sceneEditor.materialTypes.${name}`) }}</option>
                    </select>
                  </label>
                  <template v-if="item.material.type === 'phong'">
                    <SceneSlider v-model="item.material.reflection" :label="t('sceneEditor.reflection')" :min="0" :max="0.95" :step="0.01" />
                    <SceneSlider v-model="item.material.specular" :label="t('sceneEditor.specular')" :min="0" :max="2" :step="0.05" />
                    <SceneSlider v-model="item.material.shininess" :label="t('sceneEditor.shininess')" :min="1" :max="512" :step="1" />
                  </template>
                  <SceneSlider v-if="item.material.type === 'phong' || item.material.type === 'metal'" v-model="item.material.roughness" :label="t('sceneEditor.roughness')" :hint="t('sceneEditor.roughnessHint')" :min="0" :max="1" :step="0.01" />
                  <SceneSlider v-if="item.material.type === 'glass'" v-model="item.material.ior" :label="t('sceneEditor.ior')" :hint="t('sceneEditor.iorHint')" :min="1" :max="3" :step="0.01" />
                  <SceneSlider v-if="item.material.type === 'emissive'" v-model="item.material.strength" :label="t('sceneEditor.strength')" :min="0" :max="30" :step="0.1" />
                </details>
              </div>
            </li>
          </ul>
        </section>

        <!-- Lights -->
        <section v-show="tab === 'lights'" id="scene-panel-lights" class="scene-panel" role="tabpanel" aria-labelledby="scene-tab-lights">
          <div class="scene-add" role="group" :aria-label="t('sceneEditor.addLight')">
            <button v-for="kind in (['point', 'area'] as const)" :key="kind" type="button" @click="addLight(kind)"><UiIcon name="plus"/>{{ t(`sceneEditor.lightKinds.${kind}`) }}</button>
          </div>
          <p v-if="!scene.lights.length" class="scene-panel__empty">{{ renderQuality === 'photo' ? t('sceneEditor.noLightsPath') : t('sceneEditor.noLights') }}</p>
          <ul class="scene-items">
            <li v-for="(light, index) in scene.lights" :key="light.id" :ref="(element) => itemRefs.set(light.id, element as HTMLElement)" class="scene-item" :class="{ 'scene-item--open': selected === light.id }">
              <div class="scene-item__row">
                <button type="button" class="scene-item__toggle" :aria-expanded="selected === light.id" @click="select(light.id)">
                  <span class="scene-item__swatch scene-item__swatch--light" :style="{ background: toHex(light.color) }"></span>
                  <strong>{{ t('sceneEditor.light', { index: index + 1 }) }}</strong>
                  <small>{{ t(`sceneEditor.lightKinds.${light.kind}`) }} · {{ t('sceneEditor.intensityValue', { value: Math.round(light.intensity) }) }}</small>
                  <UiIcon name="chevron" class="scene-item__chevron"/>
                </button>
                <button type="button" class="scene-item__remove" :aria-label="t('sceneEditor.remove', { name: t('sceneEditor.light', { index: index + 1 }) })" @click="removeLight(light.id)"><UiIcon name="x"/></button>
              </div>
              <div v-if="selected === light.id" class="scene-item__body">
                <label class="field"><span>{{ t('sceneEditor.lightKind') }}</span>
                  <select v-model="light.kind" class="select">
                    <option v-for="kind in (['point', 'area'] as const)" :key="kind" :value="kind">{{ t(`sceneEditor.lightKinds.${kind}`) }}</option>
                  </select>
                  <small>{{ t(`sceneEditor.lightHints.${light.kind}`) }}</small>
                </label>
                <SceneSlider v-model="light.x" :label="t('sceneEditor.distance')" :hint="t('sceneEditor.distanceHint')" :min="-10" :max="30" />
                <SceneSlider :model-value="-light.y" :label="t('sceneEditor.side')" :min="-15" :max="15" @update:model-value="light.y = -$event" />
                <SceneSlider v-model="light.z" :label="t('sceneEditor.height')" :min="-5" :max="15" />
                <SceneSlider v-model="light.intensity" :label="t('sceneEditor.intensity')" :min="0" :max="1500" :step="10" />
                <SceneSlider v-if="light.kind === 'area'" v-model="light.radius" :label="t('sceneEditor.lightSize')" :hint="t('sceneEditor.lightSizeHint')" :min="0.05" :max="3" :step="0.05" />
                <label class="scene-color"><span>{{ t('sceneEditor.color') }}</span><input type="color" :value="toHex(light.color)" @input="light.color = fromHex(($event.target as HTMLInputElement).value)"></label>
              </div>
            </li>
          </ul>
        </section>

        <!-- Camera -->
        <section v-show="tab === 'camera'" id="scene-panel-camera" class="scene-panel" role="tabpanel" aria-labelledby="scene-tab-camera">
          <SceneSlider v-model="scene.camera.x" :label="t('sceneEditor.cameraForward')" :min="-10" :max="10" />
          <SceneSlider :model-value="-scene.camera.y" :label="t('sceneEditor.side')" :min="-10" :max="10" @update:model-value="scene.camera.y = -$event" />
          <SceneSlider v-model="scene.camera.z" :label="t('sceneEditor.cameraHeight')" :min="-2" :max="8" />
          <SceneSlider v-model="scene.camera.yaw" :label="t('sceneEditor.yaw')" :hint="t('sceneEditor.yawHint')" :min="-90" :max="90" :step="1" />
          <SceneSlider v-model="scene.camera.pitch" :label="t('sceneEditor.pitch')" :hint="t('sceneEditor.pitchHint')" :min="-60" :max="60" :step="1" />
          <SceneSlider v-model="scene.fov" :label="t('sceneEditor.fov')" :hint="t('sceneEditor.fovHint')" :min="15" :max="110" :step="1" />
          <SceneSlider v-model="scene.camera.aperture" :label="t('sceneEditor.aperture')" :hint="t('sceneEditor.apertureHint')" :min="0" :max="0.3" :step="0.005" />
          <SceneSlider v-if="scene.camera.aperture > 0" v-model="scene.camera.focus" :label="t('sceneEditor.focus')" :hint="t('sceneEditor.focusHint')" :min="0.5" :max="30" />
        </section>

        <!-- Render -->
        <section v-show="tab === 'render'" id="scene-panel-render" class="scene-panel" role="tabpanel" aria-labelledby="scene-tab-render">
          <label class="field"><span>{{ t('sceneEditor.quality') }}</span>
            <select class="select" :value="renderQuality" @change="setQuality(($event.target as HTMLSelectElement).value as RenderQuality)">
              <option v-for="name in QUALITIES" :key="name" :value="name">{{ t(`sceneEditor.qualities.${name}`) }}</option>
            </select>
            <small>{{ t(`sceneEditor.qualityHints.${renderQuality}`) }} {{ t('sceneEditor.cost', { rays: costLabel }) }}</small>
          </label>
          <label class="field"><span>{{ t('sceneEditor.resolution') }}</span>
            <select class="select" :value="resolutionId" @change="setResolution(($event.target as HTMLSelectElement).value)">
              <option v-for="preset in RESOLUTION_PRESETS" :key="preset.id" :value="preset.id">{{ t(`sceneEditor.resolutions.${preset.id}`) }}</option>
              <option v-if="resolutionId === 'custom'" value="custom">{{ t('sceneEditor.resolutions.custom', { width: scene.width, height: scene.height }) }}</option>
            </select>
            <small>{{ t('sceneEditor.pixels', { pixels: pixelLabel }) }}</small>
          </label>
          <SceneSlider :model-value="scene.sky ?? 1" :label="t('sceneEditor.sky')" :hint="t('sceneEditor.skyHint')" :min="0" :max="2" :step="0.05" @update:model-value="scene.sky = $event" />
          <SceneSlider :model-value="scene.exposure ?? 1" :label="t('sceneEditor.exposure')" :min="0.2" :max="3" :step="0.05" @update:model-value="scene.exposure = $event" />
        </section>
      </div>
    </div>

    <details class="scene-file">
      <summary><UiIcon name="code"/>{{ t('sceneEditor.file') }}</summary>
      <p>{{ t('sceneEditor.fileHint') }} <a :href="downloadUrl" :download="fileName" class="scene-file__download">{{ t('sceneEditor.download') }}</a></p>
      <pre>{{ cfg }}</pre>
    </details>
  </div>
</template>

<script setup lang="ts">
// Visual editor of a raytracer scene: templates, a live preview rendered in
// the browser by a port of the network's engine (progressively, in a
// worker), and tabs for the objects, lights, camera and render settings.
// The parent gets the scene through `v-model` and writes the `.cfg` with
// `sceneToCfg` when the job is sent.
import { intlLocale } from '~/utils/i18n';
import { buildScene, pickShape, previewSize } from '~/utils/engine';
import { BUILTIN_MODELS, builtinModel, fit, parseObj, yUpToZUp, type BuiltinModel } from '~/utils/engine/models';
import { cloneScene, look, MATERIAL_PRESETS, MATERIAL_TYPES, materialPreset, newBox, newId, newLight, newMesh, newPanel, newPlane, newSphere, PLANE_ORIENTATIONS, planeOrientation, RENDER_QUALITIES, renderCost, type RenderQuality, RESOLUTION_PRESETS, sceneFileName, sceneToCfg, type Rgb, type SceneMaterial, type SceneObject, type SceneModel, type ScenePlane } from '~/utils/scene';
import { createScenePreview, type PreviewReply } from '~/utils/scenePreview';
import { SCENE_TEMPLATES, sceneTemplate, type SceneTemplate } from '~/utils/sceneTemplates';

const props = withDefaults(defineProps<{ title?: string }>(), { title: '' });
const scene = defineModel<SceneModel>({ required: true });
const { t } = useI18n();

const TABS = ['objects', 'lights', 'camera', 'render'] as const;
type Tab = (typeof TABS)[number];
const tab = ref<Tab>('objects');
const template = ref<SceneTemplate | ''>('');
const undoScene = ref<SceneModel | null>(null);
/** `.cfg` right after a template was loaded: "Undo" is offered until the scene changes. */
const loadedCfg = ref('');
const selected = ref<number | null>(null);
const canvas = ref<HTMLCanvasElement | null>(null);
const modelMenu = ref<HTMLDetailsElement | null>(null);
const objInput = ref<HTMLInputElement | null>(null);
const objError = ref('');
const itemRefs = new Map<number, HTMLElement>();
const thumbnails = reactive<Partial<Record<SceneTemplate, string>>>({});

const cfg = computed(() => sceneToCfg(scene.value, props.title));
const fileName = computed(() => sceneFileName(props.title));
const downloadUrl = computed(() => `data:text/plain;charset=utf-8,${encodeURIComponent(cfg.value)}`);
const resolutionId = computed(() => RESOLUTION_PRESETS.find((preset) => preset.width === scene.value.width && preset.height === scene.value.height)?.id || 'custom');
const QUALITIES: RenderQuality[] = ['draft', 'smooth', 'photo'];
const renderQuality = computed<RenderQuality>(() => scene.value.quality || 'draft');
const costLabel = computed(() => new Intl.NumberFormat(intlLocale(), { notation: 'compact', maximumFractionDigits: 1 }).format(renderCost(scene.value)));
const pixelLabel = computed(() => (scene.value.width * scene.value.height).toLocaleString(intlLocale()));
function setQuality(value: RenderQuality) {
  if (value === 'draft') delete scene.value.quality;
  else scene.value.quality = value;
}

// ------------------------------------------------------------ preview
// The preview is the network's render, smaller and with fewer rays per pixel
// for path tracing (refined pass after pass).
const PREVIEW_MAX_SAMPLES = 64;
const networkSamples = computed(() => RENDER_QUALITIES[renderQuality.value].samples);
const pathTraced = computed(() => RENDER_QUALITIES[renderQuality.value].mode === 'path');
const previewTarget = computed(() => Math.min(networkSamples.value, PREVIEW_MAX_SAMPLES));
const previewSamples = ref(0);
const previewError = ref('');
const progress = computed(() => (previewTarget.value ? Math.min(1, previewSamples.value / previewTarget.value) : 0));
let preview: ReturnType<typeof createScenePreview> | undefined;
let thumbnailRenderer: ReturnType<typeof createScenePreview> | undefined;
let timer: ReturnType<typeof setTimeout> | undefined;

function draw(reply: PreviewReply) {
  if (reply.kind === 'error') {
    previewError.value = reply.message;
    return;
  }
  previewError.value = '';
  const element = canvas.value;
  const context = element?.getContext('2d');
  if (!element || !context) return;
  if (element.width !== reply.width || element.height !== reply.height) {
    element.width = reply.width;
    element.height = reply.height;
  }
  context.putImageData(new ImageData(reply.pixels, reply.width, reply.height), 0, 0);
  // The first, smaller image of a live edit does not count as a pass.
  previewSamples.value = reply.quick ? 0 : reply.samples;
}

function renderPreview() {
  const size = previewSize(scene.value, pathTraced.value ? 360 : 560, pathTraced.value ? 240 : 380);
  previewSamples.value = 0;
  preview?.render({ text: cfg.value, ...size, target: previewTarget.value, quick: true });
}

watch(cfg, () => {
  clearTimeout(timer);
  timer = setTimeout(renderPreview, 30);
});

const THUMB_WIDTH = 128;
const THUMB_HEIGHT = 80;
function renderThumbnails(index = 0) {
  const name = SCENE_TEMPLATES[index];
  if (!name || !thumbnailRenderer) return;
  const model = sceneTemplate(name);
  const path = RENDER_QUALITIES[model.quality || 'draft'].mode === 'path';
  // Every thumbnail has the frame of the cards (16:10), whatever the image size of the template.
  const text = sceneToCfg(model).replace(/resolution = \{ width = \d+ height = \d+ \}/, `resolution = { width = ${THUMB_WIDTH} height = ${THUMB_HEIGHT} }`);
  thumbnailRenderer.render({ text, width: THUMB_WIDTH, height: THUMB_HEIGHT, target: path ? 6 : 1 });
  pendingThumbnail = name;
}
let pendingThumbnail: SceneTemplate | undefined;

onMounted(() => {
  if (canvas.value) Object.assign(canvas.value, previewSize(scene.value, 560, 380));
  preview = createScenePreview(draw);
  renderPreview();
  thumbnailRenderer = createScenePreview((reply) => {
    const name = pendingThumbnail;
    if (!name) return;
    if (reply.kind === 'image' && reply.samples >= reply.target) {
      const thumbnail = document.createElement('canvas');
      thumbnail.width = reply.width;
      thumbnail.height = reply.height;
      thumbnail.getContext('2d')?.putImageData(new ImageData(reply.pixels, reply.width, reply.height), 0, 0);
      thumbnails[name] = thumbnail.toDataURL();
    }
    if (reply.kind === 'error' || reply.samples >= reply.target) renderThumbnails(SCENE_TEMPLATES.indexOf(name) + 1);
  });
  // After the first preview, so the page shows the scene first.
  setTimeout(() => renderThumbnails(), 400);
});
onBeforeUnmount(() => {
  clearTimeout(timer);
  preview?.stop();
  thumbnailRenderer?.stop();
});

/** Click on the preview: open the object (or the light) under the cursor. */
function pick(event: MouseEvent) {
  const element = canvas.value;
  if (!element) return;
  const box = element.getBoundingClientRect();
  let source: number | undefined;
  try {
    const built = buildScene(cfg.value);
    const shape = pickShape(built, (event.clientX - box.left) / box.width, (event.clientY - box.top) / box.height);
    source = shape === undefined ? undefined : built.shapeSource[shape];
  } catch {
    return;
  }
  if (source === undefined) return;
  // The engine numbers objects in file order, then the lights.
  const objects = scene.value.objects;
  const item = source < objects.length ? objects[source] : scene.value.lights[source - objects.length];
  if (!item) return;
  tab.value = source < objects.length ? 'objects' : 'lights';
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
  return t('sceneEditor.itemName', { kind: t(`sceneEditor.kinds.${item.kind}`), index });
}

function objectDetail(item: SceneObject): string {
  const preset = materialPreset(item.material);
  const material = preset === 'custom' ? t(`sceneEditor.materialTypes.${item.material.type}`) : t(`sceneEditor.materials.${preset}`);
  if (item.kind === 'plane') return `${t(`sceneEditor.orientations.${planeOrientation(item)}`)} · ${material}`;
  if (item.kind === 'mesh') return `${t('sceneEditor.triangles', { count: item.faces.length / 3 })} · ${material}`;
  return material;
}

const PALETTE: Rgb[] = [[18, 191, 174], [255, 120, 90], [121, 109, 240], [255, 200, 70], [70, 160, 255], [240, 240, 245]];
const nextColor = () => [...PALETTE[scene.value.objects.length % PALETTE.length]!] as Rgb;
/** Somewhere in view that is not on top of the last objects. */
function freeSpot() {
  const count = scene.value.objects.length;
  return { x: 5 + (count % 3), y: ((count % 5) - 2) * -1.1 };
}

function addObject(kind: 'sphere' | 'plane' | 'box' | 'panel') {
  const spot = freeSpot();
  const item = kind === 'sphere' ? newSphere({ ...spot, z: 0, material: look(nextColor(), 'glossy') })
    : kind === 'box' ? newBox({ ...spot, z: -0.5, material: look(nextColor(), 'satin') })
      : kind === 'panel' ? newPanel()
        : newPlane({ z: -1 });
  scene.value.objects.push(item);
  selected.value = item.id;
}

function addModel(name: BuiltinModel) {
  if (modelMenu.value) modelMenu.value.open = false;
  const item = newMesh({ ...freeSpot(), z: -1, ...builtinModel(name), material: look(nextColor(), 'glossy') });
  scene.value.objects.push(item);
  selected.value = item.id;
}

const OBJ_LIMIT = 50_000;
async function importObj(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (modelMenu.value) modelMenu.value.open = false;
  if (!file) return;
  objError.value = '';
  try {
    const model = fit(yUpToZUp(parseObj(await file.text())), 1);
    if (model.faces.length / 3 > OBJ_LIMIT) {
      objError.value = t('sceneEditor.objTooLarge', { count: model.faces.length / 3, max: OBJ_LIMIT });
      return;
    }
    const item = newMesh({ ...freeSpot(), z: -1, size: 1.5, ...model, material: look(nextColor(), 'glossy') });
    scene.value.objects.push(item);
    selected.value = item.id;
  } catch (error) {
    objError.value = t('sceneEditor.objError', { name: file.name, message: error instanceof Error ? error.message : String(error) });
  }
}

function duplicateObject(item: SceneObject) {
  const copy = { ...(JSON.parse(JSON.stringify(item)) as SceneObject), id: newId() };
  if (copy.kind !== 'plane') copy.y -= 1.2;
  scene.value.objects.splice(scene.value.objects.indexOf(item) + 1, 0, copy);
  selected.value = copy.id;
}

function removeObject(id: number) {
  scene.value.objects = scene.value.objects.filter((item) => item.id !== id);
}

function addLight(kind: 'point' | 'area') {
  const light = newLight({ kind, x: 2, y: scene.value.lights.length % 2 ? 3 : -3, z: 5, intensity: kind === 'area' ? 300 : 400 });
  scene.value.lights.push(light);
  selected.value = light.id;
}

function removeLight(id: number) {
  scene.value.lights = scene.value.lights.filter((light) => light.id !== id);
}

function setMaterial(material: SceneMaterial, name: string) {
  const preset = MATERIAL_PRESETS[name as keyof typeof MATERIAL_PRESETS];
  if (preset) Object.assign(material, look(material.color, preset));
}

function setOrientation(plane: ScenePlane, name: string) {
  const normal = PLANE_ORIENTATIONS[name as keyof typeof PLANE_ORIENTATIONS];
  if (!normal) return;
  plane.normal = [...normal];
  if (name === 'back') { plane.x = Math.max(plane.x, 10); plane.y = 0; plane.z = 0; }
  if (name === 'ceiling') { plane.z = Math.max(plane.z, 4); plane.x = 0; plane.y = 0; }
  if (name === 'floor') { plane.z = Math.min(plane.z, -1); plane.x = 0; plane.y = 0; }
  if (name === 'left') { plane.y = Math.max(plane.y, 4); plane.x = 0; plane.z = 0; }
  if (name === 'right') { plane.y = Math.min(plane.y, -4); plane.x = 0; plane.z = 0; }
}

const toHex = (rgb: Rgb) => `#${rgb.map((value) => Math.round(Math.min(255, Math.max(0, value))).toString(16).padStart(2, '0')).join('')}`;
const fromHex = (hex: string): Rgb => [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16) || 0) as Rgb;
</script>

<style scoped>
.scene-editor{display:grid;min-width:0;gap:1rem;container-type:inline-size}.scene-editor>*{min-width:0}
.scene-templates{display:grid;gap:.5rem}.scene-templates__list{display:grid;grid-template-columns:repeat(auto-fill,minmax(92px,1fr));gap:.5rem}
.scene-template{display:grid;grid-template-rows:auto 1fr;align-content:start;gap:.35rem;min-width:0;padding:.35rem;border:1px solid var(--border);border-radius:.7rem;background:white;color:var(--ink-800);font:inherit;font-size:.82rem;font-weight:650;text-align:left;cursor:pointer;transition:border-color .15s,box-shadow .15s}
.scene-template:hover{border-color:var(--mint-500)}.scene-template--active{border-color:var(--mint-600);box-shadow:0 0 0 3px var(--mint-100)}
.scene-template__thumb{display:block;width:100%;aspect-ratio:16/10;border-radius:.45rem;background:linear-gradient(180deg,#5e8ad6,#a9c0e8) center/cover no-repeat}
.scene-template__name{display:-webkit-box;min-height:2.4em;overflow:hidden;line-height:1.2;-webkit-box-orient:vertical;-webkit-line-clamp:2}
.scene-templates__undo{margin:0;color:var(--ink-600);font-size:.84rem}.scene-templates__undo button{padding:0;border:0;background:none;color:var(--mint-700);font:inherit;font-weight:750;text-decoration:underline;cursor:pointer}

.scene-workspace{display:grid;gap:1rem;align-items:start}.scene-workspace>*{min-width:0}
@container (min-width: 760px){.scene-workspace{grid-template-columns:minmax(0,1.2fr) minmax(300px,1fr)}.scene-preview{position:sticky;top:6rem}}

.scene-preview{margin:0;overflow:hidden;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}
.scene-preview__frame{position:relative;background:#0b1523}
.scene-preview canvas{display:block;width:100%;height:auto;max-height:70vh;object-fit:contain;cursor:crosshair}
.scene-preview__error{position:absolute;inset:auto .6rem .6rem;padding:.45rem .6rem;border-radius:.5rem;background:rgba(180,30,30,.9);color:white;font-size:.8rem;line-height:1.4}
.scene-preview__progress{height:3px;background:var(--mint-500);transition:width .25s}.scene-preview__progress.is-done{background:var(--mint-700)}
.scene-preview figcaption{display:grid;grid-template-columns:1fr auto;gap:.3rem .75rem;padding:.55rem .8rem;color:var(--ink-600);font-size:.82rem;line-height:1.4}
.scene-preview figcaption small{grid-column:1/-1;color:var(--ink-500);font-size:.78rem}
.scene-preview__status{display:inline-flex;align-items:center;gap:.4rem;color:var(--ink-800);font-weight:650}.scene-preview figcaption svg{width:.85rem;flex:none;color:var(--mint-700)}.scene-preview__size{font-family:var(--font-mono)}

.scene-controls{display:grid;gap:.6rem;min-width:0}
.scene-tabs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.25rem;padding:.25rem;border:1px solid var(--border);border-radius:.7rem;background:var(--surface-soft)}
.scene-tab{display:inline-flex;align-items:center;justify-content:center;gap:.35rem;min-width:0;padding:.45rem .3rem;border:0;border-radius:.5rem;background:none;color:var(--ink-600);font:inherit;font-size:.84rem;font-weight:700;white-space:nowrap;cursor:pointer}
.scene-tab:hover{color:var(--ink-900)}.scene-tab--active{background:white;color:var(--mint-700);box-shadow:0 1px 3px rgba(11,21,35,.12)}
.scene-tab__count{min-width:1.2rem;padding:0 .3rem;border-radius:1rem;background:var(--mint-100);color:var(--mint-700);font-size:.72rem;line-height:1.2rem}
.scene-panel{display:grid;gap:.75rem;padding:.9rem;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}
.scene-panel .field small{color:var(--ink-500);font-size:.8rem}
.scene-panel__empty{margin:0;color:var(--ink-600);font-size:.84rem;line-height:1.45}.scene-panel__error{margin:0;color:var(--red-600);font-size:.84rem;line-height:1.45}
.scene-add{display:flex;flex-wrap:wrap;gap:.35rem}
.scene-add button,.scene-add summary{display:inline-flex;align-items:center;gap:.3rem;padding:.35rem .55rem;border:1px solid var(--border-strong);border-radius:.5rem;background:white;color:var(--ink-800);font:inherit;font-size:.8rem;font-weight:700;cursor:pointer;list-style:none}
.scene-add summary::-webkit-details-marker{display:none}
.scene-add button:hover,.scene-add summary:hover{border-color:var(--mint-500);color:var(--mint-700)}.scene-add svg{width:.75rem}
.scene-add__menu{position:relative}.scene-add__list{position:absolute;z-index:5;top:calc(100% + .3rem);left:0;display:grid;min-width:12rem;gap:.15rem;padding:.3rem;border:1px solid var(--border);border-radius:.6rem;background:white;box-shadow:0 10px 30px rgba(11,21,35,.15)}
.scene-add__list button{justify-content:flex-start;border-color:transparent}
.scene-items{display:grid;gap:.4rem;margin:0;padding:0;list-style:none}
.scene-item{border:1px solid var(--border);border-radius:.65rem;background:white}.scene-item--open{border-color:rgba(18,191,174,.45)}
.scene-item__row{display:grid;grid-template-columns:1fr auto auto;align-items:center}
.scene-item__toggle{display:grid;grid-template-columns:auto auto 1fr auto;align-items:center;gap:.5rem;min-width:0;padding:.5rem .6rem;border:0;background:none;color:var(--ink-900);font:inherit;text-align:left;cursor:pointer}
.scene-item__toggle strong{font-size:.86rem;white-space:nowrap}.scene-item__toggle small{overflow:hidden;color:var(--ink-500);font-size:.8rem;text-overflow:ellipsis;white-space:nowrap}
.scene-item__chevron{width:.7rem;color:var(--ink-400);transition:transform .15s}.scene-item--open .scene-item__chevron{transform:rotate(90deg)}
.scene-item__swatch{width:1rem;height:1rem;border:1px solid rgba(11,21,35,.2);border-radius:50%}.scene-item__swatch--plane{border-radius:.2rem;transform:skewX(-20deg)}.scene-item__swatch--box{border-radius:.15rem}.scene-item__swatch--panel{height:.6rem;border-radius:.1rem}.scene-item__swatch--mesh{border-radius:.15rem;clip-path:polygon(50% 0,100% 100%,0 100%)}.scene-item__swatch--light{box-shadow:0 0 0 3px rgba(255,200,70,.35)}
.scene-item__remove{display:grid;width:1.8rem;height:1.8rem;margin-right:.2rem;place-items:center;border:0;border-radius:.4rem;background:none;color:var(--ink-500);cursor:pointer}.scene-item__remove:hover{background:var(--surface-soft);color:var(--ink-900)}.scene-item__remove:last-child{margin-right:.35rem}.scene-item__remove:last-child:hover{background:var(--red-100);color:var(--red-600)}.scene-item__remove svg{width:.75rem}
.scene-item__body{display:grid;gap:.7rem;padding:.2rem .7rem .8rem}
.scene-item__look{display:grid;grid-template-columns:auto 1fr;align-items:start;gap:.7rem}.scene-item__look .field{gap:.25rem}.scene-item__look .field>span{color:var(--ink-700);font-size:.84rem;font-weight:650}
.scene-item__hint{margin:-.3rem 0 0;color:var(--ink-500);font-size:.8rem;line-height:1.4}
.scene-color{display:grid;gap:.25rem;color:var(--ink-700);font-size:.84rem;font-weight:650}.scene-color input{width:3rem;height:2.2rem;padding:.15rem;border:1px solid var(--border-strong);border-radius:.45rem;background:white;cursor:pointer}
.scene-item__fine{display:grid;gap:.6rem}.scene-item__fine summary{color:var(--ink-600);font-size:.82rem;font-weight:700;cursor:pointer}.scene-item__fine[open]{gap:.7rem}
.scene-file{min-width:0;overflow:hidden;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}
.scene-file summary{display:flex;align-items:center;gap:.5rem;padding:.75rem 1rem;color:var(--ink-800);font-size:.88rem;font-weight:720;cursor:pointer}.scene-file summary svg{width:.9rem}
.scene-file p{margin:0;padding:0 1rem .6rem;color:var(--ink-600);font-size:.84rem;line-height:1.5}.scene-file__download{color:var(--mint-700);font-weight:750;text-decoration:underline;text-underline-offset:2px}
.scene-file pre{max-height:260px;margin:0 1rem 1rem;padding:.75rem;overflow:auto;border-radius:.6rem;background:#0f1d2e;color:#d6e4f0;font-family:var(--font-mono);font-size:.76rem;line-height:1.5;tab-size:2}
</style>

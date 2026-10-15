// Ready-made scenes offered by the editor. Each call returns a fresh copy
// (new ids), so editing one never changes the template.

import { MATERIAL_PRESETS, newLight, newPlane, newSphere, type SceneModel } from './scene';

export const SCENE_TEMPLATES = ['demo', 'mirrors', 'studio', 'sunset', 'blank'] as const;
export type SceneTemplate = (typeof SCENE_TEMPLATES)[number];

const camera = { x: 0, y: 0, z: 0 };

export function sceneTemplate(name: SceneTemplate): SceneModel {
  switch (name) {
    case 'mirrors':
      return {
        width: 1280, height: 720, fov: 60, camera: { x: 0, y: 0, z: 0.4 },
        objects: [
          newSphere({ x: 6, y: 2.4, z: -0.2, radius: 0.8, material: { color: [255, 120, 150], ...MATERIAL_PRESETS.mirror } }),
          newSphere({ x: 6, y: 0, z: 0, radius: 1, material: { color: [235, 240, 255], ...MATERIAL_PRESETS.mirror } }),
          newSphere({ x: 6, y: -2.4, z: -0.2, radius: 0.8, material: { color: [120, 220, 255], ...MATERIAL_PRESETS.mirror } }),
          newSphere({ x: 4.2, y: 0.9, z: -0.65, radius: 0.35, material: { color: [255, 200, 70], ...MATERIAL_PRESETS.glossy } }),
          newPlane({ z: -1, material: { color: [40, 48, 66], reflection: 0.45, specular: 0.6, shininess: 64 } }),
        ],
        lights: [
          newLight({ x: 2, y: 3, z: 5, intensity: 420, color: [255, 190, 220] }),
          newLight({ x: 2, y: -3, z: 5, intensity: 420, color: [170, 220, 255] }),
        ],
      };
    case 'studio':
      return {
        width: 1080, height: 1080, fov: 45, camera,
        objects: [
          newSphere({ x: 6, y: 0, z: 0, radius: 1.1, material: { color: [18, 191, 174], ...MATERIAL_PRESETS.glossy } }),
          newPlane({ z: -1.1, material: { color: [190, 196, 204], reflection: 0.08, specular: 0.2, shininess: 16 } }),
          newPlane({ x: 9, normal: [-1, 0, 0], material: { color: [120, 136, 156], reflection: 0, specular: 0.1, shininess: 8 } }),
        ],
        lights: [
          newLight({ x: 3, y: 2.5, z: 4, intensity: 260 }),
          newLight({ x: 1, y: -3, z: 1.5, intensity: 120, color: [200, 220, 255] }),
        ],
      };
    case 'sunset':
      return {
        width: 1920, height: 1080, fov: 65, camera: { x: 0, y: 0, z: 0.2 },
        objects: [
          newSphere({ x: 14, y: -3, z: 2.2, radius: 2.4, material: { color: [255, 150, 70], ...MATERIAL_PRESETS.matte } }),
          newSphere({ x: 6, y: 1.6, z: -0.4, radius: 0.6, material: { color: [90, 70, 160], ...MATERIAL_PRESETS.metal } }),
          newSphere({ x: 5, y: -0.6, z: -0.7, radius: 0.3, material: { color: [255, 255, 255], ...MATERIAL_PRESETS.mirror } }),
          newPlane({ z: -1, material: { color: [60, 90, 140], reflection: 0.6, specular: 1, shininess: 128 } }),
        ],
        lights: [
          newLight({ x: 10, y: -2, z: 2.5, intensity: 600, color: [255, 170, 110] }),
          newLight({ x: 1, y: 2, z: 4, intensity: 90, color: [150, 160, 255] }),
        ],
      };
    case 'blank':
      return {
        width: 1280, height: 720, fov: 55, camera,
        objects: [
          newSphere({ x: 5, y: 0, z: 0 }),
          newPlane({ z: -1, material: { color: [170, 180, 195], reflection: 0.15, specular: 0.4, shininess: 48 } }),
        ],
        lights: [newLight({ x: 3, y: 2, z: 5, intensity: 300 })],
      };
    case 'demo':
    default:
      // Network/crates/raytracer/scenes/demo-scene.cfg
      return {
        width: 320, height: 200, fov: 55, camera,
        objects: [
          newSphere({ x: 5, y: -1.4, z: 0, radius: 0.8, material: { color: [0, 127, 255], reflection: 0.38, specular: 0.8, shininess: 96 } }),
          newSphere({ x: 5, y: 1.4, z: 0, radius: 0.8, material: { color: [255, 64, 64], reflection: 0.38, specular: 0.8, shininess: 96 } }),
          newSphere({ x: 4.4, y: 0, z: 0.6, radius: 0.7, material: { color: [255, 255, 255], reflection: 0.62, specular: 1, shininess: 160 } }),
          newPlane({ x: 1, y: 1, z: -1, material: { color: [225, 245, 255], reflection: 0.18, specular: 0.45, shininess: 48 } }),
        ],
        lights: [
          newLight({ x: 4, y: 0, z: 5, intensity: 450 }),
          newLight({ x: 2, y: -3, z: 3, intensity: 120 }),
        ],
      };
  }
}

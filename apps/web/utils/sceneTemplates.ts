// Ready-made scenes offered by the editor. Each call returns a fresh copy
// (new ids), so editing one never changes the template.
//
// `showcase` is also the example file of the job types page
// (public/examples/silicium-demo-scene.cfg, checked by the tests).

import { builtinModel } from './engine/models';
import {
  look,
  newBox,
  newCamera,
  newLight,
  newMesh,
  newPanel,
  newPlane,
  newSphere,
  type SceneModel,
} from './scene';

export const SCENE_TEMPLATES = [
  'showcase',
  'cornell',
  'demo',
  'mirrors',
  'studio',
  'sunset',
  'blank',
] as const;
export type SceneTemplate = (typeof SCENE_TEMPLATES)[number];

/** Title of the showcase scene, as written in the example file. */
export const SHOWCASE_TITLE = 'Silicium — scène vitrine du moteur de rendu';

export function sceneTemplate(name: SceneTemplate): SceneModel {
  switch (name) {
    case 'showcase': {
      const torus = builtinModel('torus');
      const gem = builtinModel('gem');
      return {
        width: 1280,
        height: 720,
        fov: 42,
        quality: 'photo',
        sky: 0.35,
        exposure: 1.15,
        camera: newCamera({ x: 0, y: 0, z: 1.1, pitch: -9, aperture: 0.035, focus: 6.2 }),
        objects: [
          newPlane({
            z: -1,
            material: look([214, 206, 196], 'satin', { reflection: 0.12, roughness: 0.15 }),
          }),
          newPlane({ x: 13, normal: [-1, 0, 0], material: look([96, 112, 140], 'matte') }),
          newSphere({
            x: 6.2,
            y: 0.15,
            z: -0.1,
            radius: 0.9,
            material: look([235, 248, 255], 'glass'),
          }),
          newSphere({
            x: 8,
            y: 2.3,
            z: -0.15,
            radius: 0.85,
            material: look([255, 196, 92], 'metal', { roughness: 0.22 }),
          }),
          newSphere({
            x: 5,
            y: -1.75,
            z: -0.55,
            radius: 0.45,
            material: look([240, 244, 250], 'mirror'),
          }),
          newBox({
            x: 8.4,
            y: -2.3,
            z: -0.3,
            size: [1.3, 1.3, 1.4],
            rotation: [0, 0, 28],
            material: look([18, 191, 174], 'matte'),
          }),
          newMesh({
            x: 4.7,
            y: 1.35,
            z: -1,
            size: 1,
            rotation: [0, 0, 20],
            ...torus,
            material: look([255, 110, 90], 'glossy'),
          }),
          newMesh({
            x: 5.1,
            y: -0.55,
            z: -1,
            size: 0.55,
            rotation: [0, 0, 15],
            ...gem,
            material: look([170, 210, 255], 'diamond'),
          }),
          newPanel({
            x: 6.5,
            y: 0,
            z: 3.4,
            width: 4,
            height: 1.6,
            rotation: [0, 90, 0],
            material: look([255, 236, 210], 'light', { strength: 5 }),
          }),
        ],
        lights: [
          newLight({
            kind: 'area',
            x: 2.5,
            y: -3.5,
            z: 3,
            radius: 0.6,
            intensity: 320,
            color: [190, 215, 255],
          }),
        ],
      };
    }
    case 'cornell':
      return {
        width: 1080,
        height: 1080,
        fov: 46,
        quality: 'photo',
        sky: 0,
        camera: newCamera({ x: 0.2, y: 0, z: 0 }),
        objects: [
          newPlane({ z: -1.5, material: look([235, 235, 230], 'matte') }),
          newPlane({ z: 1.5, normal: [0, 0, -1], material: look([235, 235, 230], 'matte') }),
          newPlane({ x: 6, normal: [-1, 0, 0], material: look([235, 235, 230], 'matte') }),
          newPlane({ y: 1.5, z: 0, normal: [0, -1, 0], material: look([210, 40, 40], 'matte') }),
          newPlane({ y: -1.5, z: 0, normal: [0, 1, 0], material: look([40, 190, 70], 'matte') }),
          newPanel({
            x: 4.4,
            y: 0,
            z: 1.49,
            width: 1.1,
            height: 1.1,
            rotation: [0, 90, 0],
            material: look([255, 240, 220], 'light', { strength: 9 }),
          }),
          newBox({
            x: 5,
            y: -0.55,
            z: -0.6,
            size: [0.85, 0.85, 1.8],
            rotation: [0, 0, 22],
            material: look([235, 235, 230], 'matte'),
          }),
          newSphere({
            x: 4,
            y: 0.65,
            z: -1.05,
            radius: 0.45,
            material: look([240, 250, 255], 'glass'),
          }),
        ],
        lights: [],
      };
    case 'mirrors':
      return {
        width: 1280,
        height: 720,
        fov: 60,
        camera: newCamera({ z: 0.4 }),
        objects: [
          newSphere({
            x: 6,
            y: 2.4,
            z: -0.2,
            radius: 0.8,
            material: look([255, 120, 150], 'mirror'),
          }),
          newSphere({ x: 6, y: 0, z: 0, radius: 1, material: look([235, 240, 255], 'mirror') }),
          newSphere({
            x: 6,
            y: -2.4,
            z: -0.2,
            radius: 0.8,
            material: look([120, 220, 255], 'mirror'),
          }),
          newSphere({
            x: 4.2,
            y: 0.9,
            z: -0.65,
            radius: 0.35,
            material: look([255, 200, 70], 'glossy'),
          }),
          newPlane({
            z: -1,
            material: look([40, 48, 66], { reflection: 0.45, specular: 0.6, shininess: 64 }),
          }),
        ],
        lights: [
          newLight({ x: 2, y: 3, z: 5, intensity: 420, color: [255, 190, 220] }),
          newLight({ x: 2, y: -3, z: 5, intensity: 420, color: [170, 220, 255] }),
        ],
      };
    case 'studio':
      return {
        width: 1080,
        height: 1080,
        fov: 45,
        camera: newCamera(),
        objects: [
          newSphere({ x: 6, y: 0, z: 0, radius: 1.1, material: look([18, 191, 174], 'glossy') }),
          newPlane({
            z: -1.1,
            material: look([190, 196, 204], { reflection: 0.08, specular: 0.2, shininess: 16 }),
          }),
          newPlane({
            x: 9,
            normal: [-1, 0, 0],
            material: look([120, 136, 156], { reflection: 0, specular: 0.1, shininess: 8 }),
          }),
        ],
        lights: [
          newLight({ x: 3, y: 2.5, z: 4, intensity: 260 }),
          newLight({ x: 1, y: -3, z: 1.5, intensity: 120, color: [200, 220, 255] }),
        ],
      };
    case 'sunset':
      return {
        width: 1920,
        height: 1080,
        fov: 65,
        camera: newCamera({ z: 0.2 }),
        objects: [
          newSphere({ x: 14, y: -3, z: 2.2, radius: 2.4, material: look([255, 150, 70], 'matte') }),
          newSphere({ x: 6, y: 1.6, z: -0.4, radius: 0.6, material: look([90, 70, 160], 'metal') }),
          newSphere({
            x: 5,
            y: -0.6,
            z: -0.7,
            radius: 0.3,
            material: look([255, 255, 255], 'mirror'),
          }),
          newPlane({
            z: -1,
            material: look([60, 90, 140], { reflection: 0.6, specular: 1, shininess: 128 }),
          }),
        ],
        lights: [
          newLight({ x: 10, y: -2, z: 2.5, intensity: 600, color: [255, 170, 110] }),
          newLight({ x: 1, y: 2, z: 4, intensity: 90, color: [150, 160, 255] }),
        ],
      };
    case 'blank':
      return {
        width: 1280,
        height: 720,
        fov: 55,
        camera: newCamera(),
        objects: [
          newSphere({ x: 5, y: 0, z: 0 }),
          newPlane({
            z: -1,
            material: look([170, 180, 195], { reflection: 0.15, specular: 0.4, shininess: 48 }),
          }),
        ],
        lights: [newLight({ x: 3, y: 2, z: 5, intensity: 300 })],
      };
    case 'demo':
    default:
      // Network/crates/raytracer/scenes/demo-scene.cfg
      return {
        width: 320,
        height: 200,
        fov: 55,
        camera: newCamera(),
        objects: [
          newSphere({
            x: 5,
            y: -1.4,
            z: 0,
            radius: 0.8,
            material: look([0, 127, 255], { reflection: 0.38, specular: 0.8, shininess: 96 }),
          }),
          newSphere({
            x: 5,
            y: 1.4,
            z: 0,
            radius: 0.8,
            material: look([255, 64, 64], { reflection: 0.38, specular: 0.8, shininess: 96 }),
          }),
          newSphere({
            x: 4.4,
            y: 0,
            z: 0.6,
            radius: 0.7,
            material: look([255, 255, 255], { reflection: 0.62, specular: 1, shininess: 160 }),
          }),
          newPlane({
            x: 1,
            y: 1,
            z: -1,
            material: look([225, 245, 255], { reflection: 0.18, specular: 0.45, shininess: 48 }),
          }),
        ],
        lights: [
          newLight({ x: 4, y: 0, z: 5, intensity: 450 }),
          newLight({ x: 2, y: -3, z: 3, intensity: 120 }),
        ],
      };
  }
}

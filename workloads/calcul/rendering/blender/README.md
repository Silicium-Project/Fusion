# Calcul · Rendering

- **Objectif** : calculer des frames (PNG/EXR) à partir d'une scène Blender/USD.
- **Entrées** : `scene.blend` + `frame_schedule.txt`.
- **Sorties** : `frame_<id>.png` + `frame_<id>.hash`.
- **Vérification** : `verification/rendering-spotcheck` pour rerender des frames aléatoires + `verification/hash-audit`.

# raytracer (`silicium-raytracer`)

Moteur de rendu natif, **utilisé en production** par tous les nœuds de calcul.
Rendu déterministe, parallélisé par lignes (moteur version 2, voir
[Format des scènes](#format-des-scènes)) : anticrénelage, caméra libre, matières Phong,
mates, métal, verre et lumineuses, lumières ponctuelles et à surface, éclairage
classique (Whitted) ou path tracing, sphères, plans, boîtes, triangles, maillages
(import `.obj`), transformations et animations.

Sans bloc `render`, une scène est rendue avec un rayon par pixel et l'éclairage
classique : les scènes écrites pour la première version du moteur donnent la même image
(au pixel près dans la plupart des cas).

## Utilisation

```bash
silicium-raytracer <scene.cfg> --output <rendu.ppm> \
  [--x-start N --x-end N --y-start N --y-end N] \
  [--threads N] [--progress-file progress.json] [--frame N]
```

- Sortie : PPM binaire (P6).
- `--x-*` / `--y-*` : ne rend qu'une tuile rectangulaire.
- `--frame` : image d'une animation.
- `--threads` ou `SILICIUM_RAYTRACER_THREADS` : nombre de threads (défaut : nombre
  de CPU logiques).
- Scènes d'exemple : `scenes/` (`demo-scene.cfg`, `silicium-test-scene.cfg`,
  `silicium-multi-fragment-scene.cfg`, utilisée par `ci/e2e.sh`).

Le déterminisme est une exigence : deux nœuds doivent produire les mêmes octets
pour qu'une vérification par un autre pair fonctionne.

## Organisation du code

La crate fournit une bibliothèque (`silicium_raytracer`) et le binaire
`silicium-raytracer` qui l'utilise.

| Fichier | Contenu |
| --- | --- |
| `src/lib.rs` | Constante `EPSILON` et liste des modules |
| `src/math.rs` | `Vec3`, `Ray` |
| `src/engine/` | Le moteur : `syntax` (lecture en arbre), `scene` (caméra, matières, objets, lumières, images clés), `geometry` (formes, transformations, BVH), `integrator` (Whitted et path tracing, tone mapping), `random` (aléatoire déterministe, `libm`), `obj` (import), `check` (règles de `check`) |
| `src/check.rs` | Rapport de `check` : clés inconnues ou mal écrites, valeurs hors limites, résolution que le découpage lirait autrement, etc. Les mêmes règles tournent dans le site (`FrontEnd/utils/sceneCheck.ts`) ; `tests/fixtures/check_cases.json` est partagé avec lui |
| `src/render.rs` | `RenderOptions`, rendu multi-thread d'une tuile, progression |
| `src/pipeline/` | Chaîne des tuiles : `tiles` (découpage centre → bords), `milestones` (engagement par blocs de lignes), `sampling` (vérification probabiliste), `reassemble`, `png`, `ppm` |
| `src/main.rs`, `src/commands/` | Binaire : rendu, ou une étape de la chaîne (sortie JSON) |

## Étapes de la chaîne (binaire)

```bash
silicium-raytracer split scene.cfg [--fragments N] [--target-pixels N] [--max-fragments N] [--output plan.json]
silicium-raytracer milestones tuile.ppm --x-start X --y-start Y [--batch-rows 20]
silicium-raytracer verify tuile.ppm --manifest jalons.json --seed S [--reputation 50]   # code 2 si échec
silicium-raytracer reassemble --fragment a.ppm --x-start 0 --y-start 0 --fragment b.ppm ... --output rendu.ppm [--png rendu.png]
silicium-raytracer validate tuile.ppm [--task-id ID] [--width W] [--height H] [--expected-hash H]
silicium-raytracer png tuile.ppm --output apercu.png        # code 1 si la tuile est invalide
silicium-raytracer resolution scene.cfg                     # {"width", "height"} (1920x1080 par défaut)
silicium-raytracer check scene.cfg                          # problèmes de la scène avec leur ligne (code 2 si erreur)
silicium-raytracer version                                  # {"engine": 2, "features": [...]}
silicium-raytracer import-obj modele.obj [--material nom] [--fit 2] [--up y|z] [--output bloc.txt]
silicium-raytracer frames scene.cfg --output-dir images/ [--first N --last N]   # une scène par image
```

Chaque étape affiche un objet JSON. C'est la **seule** implémentation de la
chaîne des tuiles : le nœud (`crates/p2p-node`, workload `raytracer`) l'utilise
comme bibliothèque, et le `compute_daemon` lance le binaire
(`SILICIUM_RAYTRACER_BIN`) pour rendre une tuile. Le code de ces étapes est dans
`src/commands/` (un fichier par groupe d'étapes).

Les résultats ne doivent pas changer : des nœuds de versions différentes
comparent les hash de jalons. `tests/fixtures/python_parity.json` fige les
résultats enregistrés depuis l'ancien code Python (supprimé) ; il est lu par
`tests/python_parity.rs`. Ne pas le régénérer.

`tests/milestone_rules.rs` teste les règles elles-mêmes : regroupement des
lignes en jalons, jalon modifié par un pixel altéré, taux d'échantillonnage selon
la réputation, escalade en cas d'échec.

## Format des scènes

`clé = valeur` et `nom = { … }` (`:` vaut `=`), commentaires `#` et `//`, mots
(`mode = path`, `"texte avec espaces"`), listes de nombres, listes libconfig
(`point = ( { … }, { … } )`) et images clés. Tous les blocs sont optionnels sauf
`camera.resolution`. Exemple complet : `tests/engine.rs` (`PATH_SCENE`).

```
render : {
  engine = 2          # version demandée : un moteur plus ancien refuse la scène
  mode = path         # whitted (classique, défaut) | path (path tracing)
  samples = 256       # rayons par pixel (anticrénelage), 1 par défaut
  bounces = 6         # rebonds max (3 en whitted, 8 en path par défaut)
  tonemap = aces      # clamp (défaut en whitted) | reinhard | aces (défaut en path)
  exposure = 1.0      sky = 1.0      clamp = 2.0      seed = 0
}

camera : {
  resolution = { width = 1920 height = 1080 }   # obligatoire, largeur en premier
  position = { x = 0 y = 0 z = 1 }
  look_at = { x = 5 y = 0 z = 0 }      # ou direction = {…}, ou rotation = { x y z } en degrés
  up = { x = 0 y = 0 z = 1 }
  fieldOfView = 55                     # angle vertical, en degrés
  aperture = 0.05  focus_distance = 5  # profondeur de champ (optionnel)
}

materials : {
  material = { name = verre  type = glass  ior = 1.5 }
  material = { name = or     type = metal  roughness = 0.2  color = { r = 255 g = 190 b = 90 } }
  material = { name = lampe  type = emissive  strength = 6 }
  # type = phong (défaut : reflection, specular, shininess) | diffuse
}

primitives : {
  sphere = { x = 5 y = 0 z = 0 radius = 1 material = verre }
  plane  = { z = -1 type = diffuse color = { r = 200 g = 200 b = 200 } }
  box    = { min = { x = -1 y = -1 z = 0 } max = { x = 1 y = 1 z = 1 } material = or }
  triangle = { a = {…} b = {…} c = {…} }
  quad   = { corner = {…} u = {…} v = {…} material = lampe }    # parallélogramme
  mesh   = { vertices = { 0 0 0  1 0 0  0 1 0 } faces = { 0 1 2 } }   # sommets numérotés depuis 0
  # tout objet : translate = {…}  rotate = { x y z } (degrés)  scale = 2 ou {…}
  # matière : material = nom, ou directement type, color, roughness… sur l'objet
}

lights : {
  point = { x = 4 y = 0 z = 5 intensity = 450 }
  area  = { x = 2 y = -3 z = 4 radius = 0.5 intensity = 300 r = 255 g = 220 b = 200 }   # ombres douces
}

animation : { frames = 48 fps = 24 }
# toute valeur numérique peut être animée : x = { 0 = -2  47 = 2  ease = smooth }
```

**Déterminisme.** Chaque nombre aléatoire dépend uniquement du pixel, du numéro
d'échantillon, de l'image et de `seed` (`src/engine/random.rs`), jamais des threads.
Les fonctions `sin`, `cos`, `tan`, `pow` viennent de la crate `libm` (Rust pur), pour
donner les mêmes bits sous Windows, Linux et macOS. Une tuile est donc identique à la
même zone de l'image entière, quel que soit le nombre de threads, et la vérification
par jalons fonctionne sans changement. `tests/engine.rs` fige des empreintes de rendu :
la changer revient à changer les pixels, ce qui impose d'incrémenter
`engine::ENGINE_VERSION`.

**Réseau.** Le nœud envoie un seul fichier de scène par job : un modèle `.obj` est donc
intégré à la scène (`import-obj`), et une animation devient une scène par image
(`frames`), chacune envoyée comme un job ordinaire. Un nœud dont le binaire est
antérieur à ce moteur ne connaît ni le bloc `render` ni les nouvelles formes, et ses
pixels diffèrent parfois de quelques niveaux même sur une scène simple : tous les nœuds
doivent être mis à jour ensemble, sinon leurs tuiles se rejettent mutuellement.

**Lumière en mode path.** `intensity` garde l'échelle du mode classique (450 à 5 unités
éclaire une surface blanche à peu près comme en mode `whitted`). Les objets `emissive` éclairent la
scène, le ciel aussi (`sky`). Les lumières très intenses vues à travers du verre ou un
miroir après une surface mate sont plafonnées à `clamp` (2 par défaut) pour éviter les
points blancs isolés.

## Construire et tester

```bash
cargo build --release -p silicium-raytracer   # binaire dans Network/target/release/
cargo test -p silicium-raytracer
```

L'app desktop (`Fusion/apps/silicium-node/scripts/prepare-runtime*`) construit ce
binaire et l'installe dans `Network/bin/raytracer/`.

## Évolution prévue

Les reçus de calcul signés de l'ancien nœud Python n'ont pas été portés ; la
facturation est dérivée du journal de tâches du nœud.

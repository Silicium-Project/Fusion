# TODO Splitter/Worker

- [x] Aligner le calcul de hash binaire entre splitter et fragment_executor (vérifier algo par défaut, longueur et encodage).
- [x] Rendre BinaryExtractor plus robuste sur les petits binaires (sections manquantes, segments vides) et gérer un hash stable en absence de bytes.
- [x] Nettoyage gcov automatique avant les tests (cible `test-clean` ou purge `build/tests`).
- [x] Améliorer la CLI/README: log de l'algo de hash utilisé, option démo pour choisir l'algorithme.
- [ ] Ajouter un test d’intégration léger comparant le hash calculé côté splitter et le worker (binaire minimal/stub).

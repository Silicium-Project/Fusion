# Calcul · Video encoding

- **Objectif** : transcoder des segments vidéo (H.264/H.265/AV1) envoyés par le scheduler.
- **Entrées** : `input.mp4` + `encoding.json` (codec, bitrate, preset, identifiant du segment).
- **Sorties** : `segment_<id>.mp4` + `segment_<id>.hash`.
- **Certification attendue** : hash SHA-256, contrôle FFprobe, redondance aléatoire (voir profils `verification/hash-audit` et `verification/rendering-spotcheck`).

## Commande de référence

```bash
ffmpeg -y -i input.mp4 \
  -c:v libx265 -preset medium -crf 24 \
  -c:a copy \
  "segment_${FRAGMENT_ID}.mp4"
sha256sum "segment_${FRAGMENT_ID}.mp4" > "segment_${FRAGMENT_ID}.hash"
```

## Matériel recommandé

| Profil | CPU | GPU | RAM |
| --- | --- | --- | --- |
| Basique | 4 cœurs | Optionnel | 4 GiB |
| Avancé | 8 cœurs | NVENC/AMF/QSV | 8 GiB |

Réduisez `preset` (ultrafast) sur mobile/SoC peu puissants. Le manifest associe chaque fragment à un coût estimatif (0,001 token Silicium).***

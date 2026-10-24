package catalog

import "testing"

// goldenDigest is the digest of the image classifier fixture. The node
// checks the same manifest in `workload/hf/manifest.rs` (test
// `digest_matches_the_backend`): change both together.
const goldenDigest = "0ff8e2804e7f301e0048936ce90e42a221f52eb5e9bc5b34e5ba74f59e8da9ff"

func TestManifestDigestIsSharedWithTheNode(t *testing.T) {
	decision := Admit(decode(t, vitInfo), vitTree(), DefaultPolicy())
	if decision.Manifest.Digest != goldenDigest || decision.Manifest.Key != "google--vit-base-patch16-224-0ff8e2804e7f" {
		t.Fatalf("digest %s key %s: update the node's test too", decision.Manifest.Digest, decision.Manifest.Key)
	}
}

func TestStringsFromTheHubAreLimited(t *testing.T) {
	info := decode(t, vitInfo)
	info.TransformersInfo.AutoModel = "Auto<script>"
	info.Config.Architectures = []string{"ViT Model", "ViTForImageClassification"}
	tree := append(vitTree(), small("tokenizer .json", "1111111111111111111111111111111111111111"))
	decision := Admit(info, tree, DefaultPolicy())
	m := decision.Manifest
	if m.Loader.AutoModel != "" || len(m.Loader.Architectures) != 1 || len(m.Files) != 3 {
		t.Fatalf("loader %+v files %v", m.Loader, paths(m))
	}
}

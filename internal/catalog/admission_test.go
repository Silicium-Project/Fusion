package catalog

import (
	"encoding/json"
	"strings"
	"testing"
)

// The fixtures copy what the Hub answered on 2026-10-20 for four unrelated
// models (`/api/models/<id>` and `/tree/<commit>`); the trees are shortened
// to the files that matter and the hashes not shown by the Hub are made up.

func lfs(path string, size int64, sha string) TreeEntry {
	entry := TreeEntry{Type: "file", Path: path, Size: size, OID: strings.Repeat("a", 40)}
	entry.LFS = &struct {
		OID  string `json:"oid"`
		Size int64  `json:"size"`
	}{OID: sha, Size: size}
	return entry
}

func small(path string, oid string) TreeEntry {
	return TreeEntry{Type: "file", Path: path, Size: 1983, OID: oid}
}

func sha(seed string) string { return strings.Repeat(seed, 64)[:64] }

func decode(t *testing.T, raw string) ModelInfo {
	t.Helper()
	var info ModelInfo
	if err := json.Unmarshal([]byte(raw), &info); err != nil {
		t.Fatal(err)
	}
	return info
}

const vitInfo = `{
  "id": "google/vit-base-patch16-224", "pipeline_tag": "image-classification",
  "library_name": "transformers", "sha": "3f49326eb077187dfe1c2a2bb15fbd74e6ab91e3",
  "tags": ["transformers","pytorch","tf","jax","safetensors","vit"], "gated": false,
  "disabled": false, "private": false, "downloads": 4776905, "likes": 991,
  "widgetData": [{"src": "https://huggingface.co/datasets/mishig/sample_images/resolve/main/tiger.jpg", "example_title": "Tiger"}],
  "config": {"architectures": ["ViTForImageClassification"], "model_type": "vit"},
  "cardData": {"license": "apache-2.0"},
  "transformersInfo": {"auto_model": "AutoModelForImageClassification", "pipeline_tag": "image-classification", "processor": "AutoImageProcessor"},
  "safetensors": {"parameters": {"F32": 86567656}, "total": 86567656}
}`

func vitTree() []TreeEntry {
	return []TreeEntry{
		small(".gitattributes", strings.Repeat("1", 40)),
		small("README.md", strings.Repeat("2", 40)),
		small("config.json", strings.Repeat("3", 40)),
		lfs("flax_model.msgpack", 346_000_000, sha("4")),
		lfs("model.safetensors", 346_293_852, sha("5")),
		small("preprocessor_config.json", strings.Repeat("6", 40)),
		lfs("pytorch_model.bin", 346_351_599, sha("7")),
		lfs("tf_model.h5", 346_000_000, sha("8")),
	}
}

func paths(m *Manifest) []string {
	var out []string
	for _, f := range m.Files {
		out = append(out, f.Path)
	}
	return out
}

func TestImageClassifierIsAdmittedWithSafetensorsOnly(t *testing.T) {
	decision := Admit(decode(t, vitInfo), vitTree(), DefaultPolicy())
	if decision.Status != StatusAdmitted {
		t.Fatalf("status %s, reasons %v", decision.Status, decision.Reasons)
	}
	m := decision.Manifest
	if got := strings.Join(paths(m), ","); got != "config.json,model.safetensors,preprocessor_config.json" {
		t.Fatalf("files %s", got)
	}
	if m.Runtime != RuntimePython || m.Library != "transformers" || m.HardwareClass != ClassA {
		t.Fatalf("manifest %+v", m)
	}
	if m.Loader.AutoModel != "AutoModelForImageClassification" || m.Loader.Processor != "AutoImageProcessor" {
		t.Fatalf("loader %+v", m.Loader)
	}
	if m.Files[1].SHA256 != sha("5") || m.Files[0].GitOID != strings.Repeat("3", 40) {
		t.Fatalf("hashes %+v", m.Files)
	}
	if !strings.HasPrefix(m.Key, "google--vit-base-patch16-224-") || len(m.Digest) != 64 {
		t.Fatalf("key %s digest %s", m.Key, m.Digest)
	}
	if !m.Verify() {
		t.Fatal("a sealed manifest must verify")
	}
	m.Files[1].SHA256 = sha("9")
	if m.Verify() {
		t.Fatal("a changed file must break the digest")
	}
}

func TestSpeechRecognizerLeavesPickleWeightsOut(t *testing.T) {
	info := decode(t, `{
	  "id": "openai/whisper-tiny", "pipeline_tag": "automatic-speech-recognition", "library_name": "transformers",
	  "sha": "169d4a4341b33bc18d8881c4b69c2e104e1cc0af",
	  "config": {"architectures": ["WhisperForConditionalGeneration"], "model_type": "whisper"},
	  "transformersInfo": {"auto_model": "AutoModelForSpeechSeq2Seq", "pipeline_tag": "automatic-speech-recognition", "processor": "AutoProcessor"},
	  "safetensors": {"parameters": {"F32": 37760640}, "total": 37760640},
	  "gated": false, "cardData": {"license": "apache-2.0"}
	}`)
	tree := []TreeEntry{
		small("config.json", "417aa9de49a132dd3eb6a56d3be2718b15f08917"),
		small("merges.txt", strings.Repeat("b", 40)),
		lfs("model.safetensors", 151061672, "7ebd0e69e78190ffe1438491fa05cc1f5c1aa3a4c4db3bc1723adbb551ea2395"),
		lfs("pytorch_model.bin", 151097819, sha("c")),
		small("tokenizer.json", strings.Repeat("d", 40)),
		small("normalizer.json", strings.Repeat("e", 40)),
	}
	decision := Admit(info, tree, DefaultPolicy())
	if decision.Status != StatusAdmitted {
		t.Fatalf("status %s %v", decision.Status, decision.Reasons)
	}
	for _, p := range paths(decision.Manifest) {
		if strings.HasSuffix(p, ".bin") {
			t.Fatalf("pickle file kept: %v", paths(decision.Manifest))
		}
	}
}

func sdxlInfo(licence string) string {
	return `{
	  "id": "stabilityai/sdxl-turbo", "pipeline_tag": "text-to-image", "library_name": "diffusers",
	  "sha": "71153311d3dbb46851df1931d3ca6e939de83304", "gated": false,
	  "tags": ["diffusers","onnx","safetensors","text-to-image","license:other"],
	  "config": {"diffusers": {"_class_name": "StableDiffusionXLPipeline"}},
	  "cardData": {"pipeline_tag": "text-to-image", "license": "other", "license_name": "` + licence + `"},
	  "safetensors": {"parameters": {"F32": 2567463684}, "total": 2567463684}
	}`
}

func sdxlTree() []TreeEntry {
	return []TreeEntry{
		small("model_index.json", strings.Repeat("1", 40)),
		lfs("sd_xl_turbo_1.0.safetensors", 13_900_000_000, sha("2")),
		lfs("sd_xl_turbo_1.0_fp16.safetensors", 6_900_000_000, sha("3")),
		small("scheduler/scheduler_config.json", strings.Repeat("4", 40)),
		small("text_encoder/config.json", strings.Repeat("5", 40)),
		lfs("text_encoder/model.safetensors", 492_000_000, sha("6")),
		lfs("text_encoder/model.fp16.safetensors", 246_000_000, sha("7")),
		small("unet/config.json", strings.Repeat("8", 40)),
		lfs("unet/diffusion_pytorch_model.safetensors", 10_270_000_000, sha("9")),
		lfs("unet/diffusion_pytorch_model.fp16.safetensors", 5_135_000_000, sha("a")),
		small("vae/config.json", strings.Repeat("b", 40)),
		lfs("vae/diffusion_pytorch_model.safetensors", 335_000_000, sha("c")),
		lfs("vae/diffusion_pytorch_model.fp16.safetensors", 167_000_000, sha("d")),
		lfs("unet/model.onnx", 10_000_000_000, sha("e")),
		lfs("onnx/unet/model.onnx", 10_000_000_000, sha("f")),
		small("onnx/unet/config.json", strings.Repeat("c", 40)),
	}
}

func TestNonCommercialLicenceNameIsRejected(t *testing.T) {
	decision := Admit(decode(t, sdxlInfo("sai-nc-community")), sdxlTree(), DefaultPolicy())
	if decision.Status != StatusRejected || !contains(decision.Reasons, "licence.non_commercial") {
		t.Fatalf("status %s reasons %v", decision.Status, decision.Reasons)
	}
}

func TestDiffusionPipelineKeepsComponentsInFP16(t *testing.T) {
	policy := DefaultPolicy()
	policy.Licences["silicium-test"] = true
	info := decode(t, sdxlInfo(""))
	info.CardData.License = Licences{"silicium-test"}
	decision := Admit(info, sdxlTree(), policy)
	if decision.Status != StatusAdmitted {
		t.Fatalf("status %s %v", decision.Status, decision.Reasons)
	}
	m := decision.Manifest
	got := strings.Join(paths(m), ",")
	want := "model_index.json,scheduler/scheduler_config.json,text_encoder/config.json,text_encoder/model.fp16.safetensors," +
		"unet/config.json,unet/diffusion_pytorch_model.fp16.safetensors,vae/config.json,vae/diffusion_pytorch_model.fp16.safetensors"
	if got != want {
		t.Fatalf("files\n got %s\nwant %s", got, want)
	}
	if m.Loader.Variant != "fp16" || m.Loader.PipelineClass != "StableDiffusionXLPipeline" {
		t.Fatalf("loader %+v", m.Loader)
	}
	if m.HardwareClass != ClassB {
		t.Fatalf("class %s for %d bytes", m.HardwareClass, m.TotalBytes)
	}
}

func TestCustomCodeOfANativeArchitectureIsAdmitted(t *testing.T) {
	info := decode(t, `{
	  "id": "microsoft/Phi-3-mini-4k-instruct", "pipeline_tag": "text-generation", "library_name": "transformers",
	  "sha": "0a67737cc96d2554230f90338b163bc6380a2a85",
	  "tags": ["transformers","safetensors","phi3","text-generation","custom_code","license:mit"],
	  "config": {"architectures": ["Phi3ForCausalLM"], "model_type": "phi3",
	    "auto_map": {"AutoConfig": "configuration_phi3.Phi3Config", "AutoModelForCausalLM": "modeling_phi3.Phi3ForCausalLM"}},
	  "transformersInfo": {"auto_model": "AutoModelForCausalLM", "pipeline_tag": "text-generation", "processor": "AutoTokenizer"},
	  "cardData": {"license": "mit"}, "safetensors": {"total": 3821079552}
	}`)
	tree := []TreeEntry{
		small("config.json", strings.Repeat("1", 40)),
		small("configuration_phi3.py", strings.Repeat("2", 40)),
		small("modeling_phi3.py", strings.Repeat("3", 40)),
		lfs("model-00001-of-00002.safetensors", 4_972_489_328, sha("4")),
		lfs("model-00002-of-00002.safetensors", 2_669_692_552, sha("5")),
		small("model.safetensors.index.json", strings.Repeat("6", 40)),
		lfs("tokenizer.model", 499_723, sha("7")),
		small("tokenizer.json", strings.Repeat("8", 40)),
	}
	decision := Admit(info, tree, DefaultPolicy())
	if decision.Status != StatusAdmitted || !contains(decision.Notes, "code.custom_declared_loaded_natively") {
		t.Fatalf("status %s reasons %v notes %v", decision.Status, decision.Reasons, decision.Notes)
	}
	for _, p := range paths(decision.Manifest) {
		if strings.HasSuffix(p, ".py") {
			t.Fatalf("code file kept: %v", paths(decision.Manifest))
		}
	}
	if !decision.Manifest.CustomCodeDeclared || decision.Manifest.HardwareClass != ClassB {
		t.Fatalf("manifest %+v", decision.Manifest)
	}
}

func TestCustomCodeWithoutNativeArchitectureGoesToReview(t *testing.T) {
	info := decode(t, vitInfo)
	info.Tags = append(info.Tags, "custom_code")
	info.Config.ModelType = ""
	decision := Admit(info, vitTree(), DefaultPolicy())
	if decision.Status != StatusReview || !contains(decision.Reasons, "code.custom") {
		t.Fatalf("status %s %v", decision.Status, decision.Reasons)
	}
}

func TestRulesRefuseUnsafeOrRestrictedModels(t *testing.T) {
	cases := []struct {
		name   string
		change func(*ModelInfo, *[]TreeEntry)
		status Status
		reason string
	}{
		{"pickle only", func(_ *ModelInfo, tree *[]TreeEntry) {
			*tree = []TreeEntry{small("config.json", strings.Repeat("1", 40)), lfs("pytorch_model.bin", 10, sha("2"))}
		}, StatusRejected, "format.pickle_only"},
		{"gated", func(info *ModelInfo, _ *[]TreeEntry) { info.Gated = true }, StatusRejected, "access.gated"},
		{"non commercial", func(info *ModelInfo, _ *[]TreeEntry) { info.CardData.License = Licences{"cc-by-nc-4.0"} }, StatusRejected, "licence.non_commercial"},
		{"unknown licence", func(info *ModelInfo, _ *[]TreeEntry) { info.CardData.License = Licences{"llama3.1"} }, StatusReview, "licence.unknown"},
		{"no licence", func(info *ModelInfo, _ *[]TreeEntry) { info.CardData = nil }, StatusReview, "licence.missing"},
		{"no task", func(info *ModelInfo, _ *[]TreeEntry) { info.PipelineTag = "" }, StatusReview, "task.missing"},
		{"unknown task", func(info *ModelInfo, _ *[]TreeEntry) { info.PipelineTag = "image-to-sound" }, StatusUnsupported, "task.unknown"},
		{"library not runnable", func(info *ModelInfo, _ *[]TreeEntry) { info.LibraryName = "espnet" }, StatusUnsupported, "library.unsupported"},
		{"too large", func(_ *ModelInfo, tree *[]TreeEntry) { (*tree)[4] = lfs("model.safetensors", 30<<30, sha("5")) }, StatusRejected, "size.too_large"},
		{"no commit", func(info *ModelInfo, _ *[]TreeEntry) { info.SHA = "main" }, StatusReview, "revision.missing"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			info, tree := decode(t, vitInfo), vitTree()
			c.change(&info, &tree)
			decision := Admit(info, tree, DefaultPolicy())
			if decision.Status != c.status || !contains(decision.Reasons, c.reason) {
				t.Fatalf("status %s reasons %v, want %s %s", decision.Status, decision.Reasons, c.status, c.reason)
			}
		})
	}
}

func TestUnsafePathsAreNeverPinned(t *testing.T) {
	tree := append(vitTree(),
		small("../escape.json", strings.Repeat("1", 40)),
		small(".git/config.json", strings.Repeat("2", 40)),
		small("a/./b.json", strings.Repeat("3", 40)),
		small(`a\b.json`, strings.Repeat("4", 40)),
	)
	decision := Admit(decode(t, vitInfo), tree, DefaultPolicy())
	if decision.Status != StatusAdmitted || !contains(decision.Notes, "files.unsafe_paths_ignored") {
		t.Fatalf("status %s notes %v", decision.Status, decision.Notes)
	}
	if len(decision.Manifest.Files) != 3 {
		t.Fatalf("files %v", paths(decision.Manifest))
	}
}

func TestGGUFRepositoryPinsOneQuantizationAndItsProjector(t *testing.T) {
	info := decode(t, `{
	  "id": "someone/vision-model-GGUF", "pipeline_tag": "image-text-to-text",
	  "sha": "1111111111111111111111111111111111111111", "tags": ["gguf"], "cardData": {"license": "apache-2.0"}
	}`)
	tree := []TreeEntry{
		lfs("model-Q8_0.gguf", 3_000_000_000, sha("1")),
		lfs("model-Q4_K_M.gguf", 1_800_000_000, sha("2")),
		lfs("model-F16.gguf", 6_000_000_000, sha("3")),
		lfs("mmproj-model-f16.gguf", 600_000_000, sha("4")),
		small("README.md", strings.Repeat("5", 40)),
	}
	decision := Admit(info, tree, DefaultPolicy())
	if decision.Status != StatusAdmitted {
		t.Fatalf("status %s %v", decision.Status, decision.Reasons)
	}
	m := decision.Manifest
	if got := strings.Join(paths(m), ","); got != "mmproj-model-f16.gguf,model-Q4_K_M.gguf" {
		t.Fatalf("files %s", got)
	}
	if m.Runtime != RuntimeOllama || m.Library != "gguf" || m.HardwareClass != ClassB {
		t.Fatalf("manifest %+v", m)
	}
}

func TestLibraryIsInferredFromTheFiles(t *testing.T) {
	info := decode(t, `{
	  "id": "someone/sentence-model", "pipeline_tag": "sentence-similarity",
	  "sha": "2222222222222222222222222222222222222222", "cardData": {"license": "mit"},
	  "config": {"architectures": ["BertModel"], "model_type": "bert"}
	}`)
	tree := []TreeEntry{
		small("config.json", strings.Repeat("1", 40)),
		small("modules.json", strings.Repeat("2", 40)),
		small("config_sentence_transformers.json", strings.Repeat("3", 40)),
		lfs("model.safetensors", 90_000_000, sha("4")),
		small("1_Pooling/config.json", strings.Repeat("5", 40)),
	}
	decision := Admit(info, tree, DefaultPolicy())
	if decision.Status != StatusAdmitted || decision.Manifest.Library != "sentence-transformers" {
		t.Fatalf("status %s %v library %s", decision.Status, decision.Reasons, decision.Manifest.Library)
	}
	if !contains(paths(decision.Manifest), "1_Pooling/config.json") {
		t.Fatalf("files %v", paths(decision.Manifest))
	}
}

func TestEveryTaskOfTheHubPageIsKnown(t *testing.T) {
	if len(Tasks()) != 52 {
		t.Fatalf("%d tasks", len(Tasks()))
	}
	seen := map[string]bool{}
	for _, task := range Tasks() {
		if seen[task.ID] || task.Label == "" || task.Metric == "" || task.Category == "" {
			t.Fatalf("task %+v", task)
		}
		seen[task.ID] = true
	}
	tasks := WithHubLibraries(map[string][]string{"text-to-image": {"diffusers", "a-new-library"}})
	for _, task := range tasks {
		if task.ID == "text-to-image" && strings.Join(task.Libraries, ",") != "a-new-library,diffusers" {
			t.Fatalf("libraries %v", task.Libraries)
		}
	}
}

func contains(values []string, value string) bool {
	for _, v := range values {
		if v == value {
			return true
		}
	}
	return false
}

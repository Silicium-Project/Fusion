// Admission: the rules that turn the Hub's description of a model (its info
// and its file tree at one commit) into a pinned manifest, or refuse it.
//
// Nothing here names a model. The rules read the task (`pipeline_tag`), the
// library (`library_name`, or the files when it is missing), how to load it
// (`transformersInfo`, `config`), the licence, the access, and the files with
// their hashes. A model is:
//
//   - admitted: every rule passes; the network may run it (after the load
//     test on the workers);
//   - review: nothing unsafe, but the Hub does not say enough (no task, no
//     licence we know, custom code without a native architecture…);
//   - unsupported: safe, but its task or library is not runnable yet;
//   - rejected: unsafe or not allowed (pickle only, gated, non-commercial
//     licence, too large…).

package catalog

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"path"
	"regexp"
	"sort"
	"strings"
)

// ManifestFormat identifies a model manifest.
const ManifestFormat = "silicium-model/1"

// Status of a model in the catalogue.
type Status string

const (
	StatusAdmitted    Status = "admitted"
	StatusReview      Status = "review"
	StatusUnsupported Status = "unsupported"
	StatusRejected    Status = "rejected"
	// StatusQuarantined: was admitted, then the Hub contradicted the pinned
	// files (set by the sync, never by Admit).
	StatusQuarantined Status = "quarantined"
)

func (s Status) severity() int {
	switch s {
	case StatusReview:
		return 1
	case StatusUnsupported:
		return 2
	case StatusRejected:
		return 3
	default:
		return 0
	}
}

// Runtime that runs a model on the workers.
type Runtime string

const (
	// RuntimePython: the isolated Silicium AI runtime (transformers,
	// diffusers…).
	RuntimePython Runtime = "python"
	// RuntimeOllama: GGUF language models, as the existing batch AI workload.
	RuntimeOllama Runtime = "ollama"
)

// Library names that are not `library_name` values of the Hub.
const libraryGGUF = "gguf"

// Policy holds the rules that are settings rather than code.
type Policy struct {
	// Licences allowed (lowercase SPDX-like identifiers of the Hub).
	Licences map[string]bool
	// MaxModelBytes: larger models are refused (the largest hardware class).
	MaxModelBytes int64
	// Libraries the runtimes can run, with the runtime of each.
	Libraries map[string]Runtime
}

// DefaultLicences are licences that allow running the model for a paid
// service. Licences with a non-commercial clause are refused; licences the
// list does not know go to review.
var DefaultLicences = []string{
	"apache-2.0", "mit", "bsd", "bsd-2-clause", "bsd-3-clause", "bsd-3-clause-clear",
	"isc", "unlicense", "cc0-1.0", "cc-by-2.0", "cc-by-3.0", "cc-by-4.0",
	"cc-by-sa-3.0", "cc-by-sa-4.0", "mpl-2.0", "artistic-2.0", "ecl-2.0",
	"afl-3.0", "bsl-1.0", "zlib", "pddl", "odc-by", "odbl", "wtfpl",
	"gpl-2.0", "gpl-3.0", "lgpl-2.1", "lgpl-3.0", "agpl-3.0", "epl-2.0",
	"openrail", "openrail++", "creativeml-openrail-m", "bigscience-openrail-m",
	"bigscience-bloom-rail-1.0", "bigcode-openrail-m",
}

// DefaultLibraries: what the Silicium AI runtime loads.
var DefaultLibraries = map[string]Runtime{
	"transformers":          RuntimePython,
	"sentence-transformers": RuntimePython,
	"diffusers":             RuntimePython,
	"timm":                  RuntimePython,
	"sklearn":               RuntimePython,
	"lerobot":               RuntimePython,
	libraryGGUF:             RuntimeOllama,
}

// DefaultMaxModelBytes is the largest model: what a 24 GB GPU can hold.
const DefaultMaxModelBytes int64 = 24 << 30

// DefaultPolicy returns the default rules.
func DefaultPolicy() Policy {
	licences := make(map[string]bool, len(DefaultLicences))
	for _, licence := range DefaultLicences {
		licences[licence] = true
	}
	libraries := make(map[string]Runtime, len(DefaultLibraries))
	for name, runtime := range DefaultLibraries {
		libraries[name] = runtime
	}
	return Policy{Licences: licences, MaxModelBytes: DefaultMaxModelBytes, Libraries: libraries}
}

// ManifestFile is a file of the model and how a node checks it: the
// SHA-256 of its content (large files) or its git blob hash (small files,
// which the Hub stores without a SHA-256).
type ManifestFile struct {
	Path   string `json:"path"`
	Size   int64  `json:"size"`
	SHA256 string `json:"sha256,omitempty"`
	GitOID string `json:"git_oid,omitempty"`
}

// Loader is how the runtime loads the model, from the Hub's metadata.
type Loader struct {
	AutoModel     string   `json:"auto_model,omitempty"`
	Processor     string   `json:"processor,omitempty"`
	PipelineClass string   `json:"pipeline_class,omitempty"`
	ModelType     string   `json:"model_type,omitempty"`
	Architectures []string `json:"architectures,omitempty"`
	// Variant of the weights (`fp16`), when the repository has one for
	// every component.
	Variant string `json:"variant,omitempty"`
}

// Manifest pins a model: the node downloads exactly these files at this
// commit and checks their hashes. `Key` and `Digest` derive from the rest:
// another commit or another file is another model.
type Manifest struct {
	Format             string         `json:"format"`
	Key                string         `json:"key"`
	Digest             string         `json:"digest"`
	Repository         string         `json:"repository"`
	Revision           string         `json:"revision"`
	Task               string         `json:"task"`
	Library            string         `json:"library"`
	Runtime            Runtime        `json:"runtime"`
	Loader             Loader         `json:"loader"`
	Files              []ManifestFile `json:"files"`
	TotalBytes         int64          `json:"total_bytes"`
	Parameters         int64          `json:"parameters,omitempty"`
	HardwareClass      HardwareClass  `json:"hardware_class"`
	Licence            string         `json:"licence"`
	CustomCodeDeclared bool           `json:"custom_code_declared,omitempty"`
}

// Decision is the outcome of Admit. Reasons are stable codes (the site
// translates them); Notes do not change the status.
type Decision struct {
	Status   Status    `json:"status"`
	Reasons  []string  `json:"reasons"`
	Notes    []string  `json:"notes"`
	Manifest *Manifest `json:"manifest,omitempty"`
}

func (d *Decision) mark(status Status, reason string) {
	if status.severity() > d.Status.severity() {
		d.Status = status
	}
	d.Reasons = append(d.Reasons, reason)
}

// Extensions of files the runtime reads besides the weights: configuration,
// tokenizers, vocabularies. Never code (`.py`).
var supportExtensions = map[string]bool{
	".json": true, ".txt": true, ".model": true, ".tiktoken": true,
	".vocab": true, ".bpe": true, ".spm": true, ".yaml": true, ".yml": true,
	".jinja": true,
}

// maxSupportFileBytes bounds a configuration or tokenizer file.
const maxSupportFileBytes = 64 << 20

// Formats whose loading runs code (Python pickle).
var pickleExtensions = map[string]bool{
	".bin": true, ".pt": true, ".pth": true, ".pkl": true, ".pickle": true,
	".joblib": true, ".ckpt": true,
}

// Directories of other frameworks' exports, never read by the runtime.
var foreignDirectories = map[string]bool{
	"onnx": true, "openvino": true, "coreml": true, "tflite": true, "flax": true,
	"jax": true, "tf": true, "mlx": true, "runs": true, "logs": true,
}

// GGUF quantizations by preference (balanced size and quality first).
var ggufPreference = []string{"q4_k_m", "q4_k_s", "q5_k_m", "q4_0", "q5_0", "q6_k", "q8_0", "q3_k_m", "f16"}

var ggufShard = regexp.MustCompile(`-\d{5}-of-\d{5}\.gguf$`)

const gib = int64(1) << 30

// Admit applies the rules to a model and its tree at `info.SHA`.
func Admit(info ModelInfo, tree []TreeEntry, policy Policy) Decision {
	decision := Decision{Status: StatusAdmitted, Reasons: []string{}, Notes: []string{}}

	if !repoID.MatchString(info.ID) {
		decision.mark(StatusRejected, "repository.invalid")
		return decision
	}
	if !commitSHA.MatchString(info.SHA) {
		decision.mark(StatusReview, "revision.missing")
		return decision
	}
	if info.Private || info.Disabled {
		decision.mark(StatusRejected, "access.unavailable")
	}
	if info.Gated {
		decision.mark(StatusRejected, "access.gated")
	}

	task, taskKnown := FindTask(info.PipelineTag)
	switch {
	case info.PipelineTag == "":
		decision.mark(StatusReview, "task.missing")
	case !taskKnown:
		decision.mark(StatusUnsupported, "task.unknown")
	}

	licence := admitLicence(info, policy, &decision)

	files := safeFiles(tree, &decision)
	library := info.LibraryName
	if hasExtension(files, ".gguf") && (library == "" || library == "transformers" || library == libraryGGUF || info.HasTag("gguf")) {
		library = libraryGGUF
	}
	if library == "" {
		library = inferLibrary(files)
		if library != "" {
			decision.Notes = append(decision.Notes, "library.inferred_from_files")
		}
	}
	runtime, runnable := policy.Libraries[library]
	switch {
	case library == "":
		decision.mark(StatusReview, "library.missing")
	case !runnable:
		decision.mark(StatusUnsupported, "library.unsupported")
	case library == libraryGGUF && taskKnown && task.ID != "text-generation" && task.ID != "image-text-to-text":
		decision.mark(StatusUnsupported, "library.unsupported_for_task")
	}

	loader := admitLoader(info, library, &decision)

	selected, variant := selectFiles(files, library, &decision)
	loader.Variant = variant
	if len(selected) == 0 {
		return decision
	}

	var total int64
	for _, file := range selected {
		total += file.Size
	}
	if policy.MaxModelBytes > 0 && total > policy.MaxModelBytes {
		decision.mark(StatusRejected, "size.too_large")
	}

	class := classForSize(total, library)
	if taskKnown {
		class = maxClass(class, task.MinClass)
	}

	var parameters int64
	if info.Safetensors != nil {
		parameters = info.Safetensors.Total
	}
	manifest := &Manifest{
		Format:             ManifestFormat,
		Repository:         info.ID,
		Revision:           info.SHA,
		Task:               info.PipelineTag,
		Library:            library,
		Runtime:            runtime,
		Loader:             loader,
		Files:              selected,
		TotalBytes:         total,
		Parameters:         parameters,
		HardwareClass:      class,
		Licence:            licence,
		CustomCodeDeclared: declaresCustomCode(info),
	}
	manifest.seal()
	decision.Manifest = manifest
	return decision
}

func admitLicence(info ModelInfo, policy Policy, decision *Decision) string {
	var licences []string
	if info.CardData != nil {
		for _, licence := range info.CardData.License {
			if licence = strings.ToLower(strings.TrimSpace(licence)); licence != "" {
				licences = append(licences, licence)
			}
		}
	}
	if len(licences) == 0 {
		for _, tag := range info.Tags {
			if strings.HasPrefix(tag, "license:") {
				licences = append(licences, strings.ToLower(strings.TrimPrefix(tag, "license:")))
			}
		}
	}
	if len(licences) == 0 {
		decision.mark(StatusReview, "licence.missing")
		return ""
	}
	named := licences
	if info.CardData != nil && info.CardData.LicenseName != "" {
		named = append(append([]string(nil), licences...), strings.ToLower(info.CardData.LicenseName))
	}
	for _, licence := range named {
		if strings.Contains(licence, "-nc") || strings.Contains(licence, "noncommercial") || strings.Contains(licence, "non-commercial") {
			decision.mark(StatusRejected, "licence.non_commercial")
			return identifierOrEmpty(licence)
		}
	}
	for _, licence := range licences {
		if policy.Licences[licence] {
			return licence
		}
	}
	decision.mark(StatusReview, "licence.unknown")
	return identifierOrEmpty(licences[0])
}

// admitLoader reads how to load the model; custom code is never run, so a
// model that declares some must also have an architecture the library
// knows (the runtime refuses an unknown one at the load test).
func admitLoader(info ModelInfo, library string, decision *Decision) Loader {
	loader := Loader{}
	if info.Config != nil {
		loader.ModelType = identifierOrEmpty(info.Config.ModelType)
		for _, architecture := range info.Config.Architectures {
			if identifier.MatchString(architecture) {
				loader.Architectures = append(loader.Architectures, architecture)
			}
		}
		if info.Config.Diffusers != nil {
			loader.PipelineClass = identifierOrEmpty(info.Config.Diffusers.ClassName)
		}
	}
	if info.TransformersInfo != nil {
		loader.AutoModel = identifierOrEmpty(info.TransformersInfo.AutoModel)
		loader.Processor = identifierOrEmpty(info.TransformersInfo.Processor)
		if tag := info.TransformersInfo.PipelineTag; tag != "" && info.PipelineTag != "" && tag != info.PipelineTag {
			decision.Notes = append(decision.Notes, "task.differs_from_transformers_info")
		}
	}
	switch library {
	case "transformers":
		if loader.AutoModel == "" && len(loader.Architectures) == 0 {
			decision.mark(StatusReview, "loader.unknown")
		}
	case "diffusers":
		if loader.PipelineClass == "" {
			decision.mark(StatusReview, "loader.unknown")
		}
	}
	if declaresCustomCode(info) {
		if loader.ModelType != "" && (loader.AutoModel != "" || len(loader.Architectures) > 0) {
			decision.Notes = append(decision.Notes, "code.custom_declared_loaded_natively")
		} else {
			decision.mark(StatusReview, "code.custom")
		}
	}
	return loader
}

func declaresCustomCode(info ModelInfo) bool {
	if info.HasTag("custom_code") {
		return true
	}
	if info.Config == nil {
		return false
	}
	raw := strings.TrimSpace(string(info.Config.AutoMap))
	return raw != "" && raw != "null" && raw != "{}"
}

// safeFiles keeps the files of the tree whose path is safe to write under a
// model directory, without other frameworks' exports.
func safeFiles(tree []TreeEntry, decision *Decision) []TreeEntry {
	var files []TreeEntry
	unsafe := false
	for _, entry := range tree {
		if entry.Type != "file" {
			continue
		}
		if !safePath(entry.Path) {
			unsafe = true
			continue
		}
		if first, _, found := strings.Cut(entry.Path, "/"); found && foreignDirectories[strings.ToLower(first)] {
			continue
		}
		files = append(files, entry)
	}
	if unsafe {
		decision.Notes = append(decision.Notes, "files.unsafe_paths_ignored")
	}
	sort.Slice(files, func(i, j int) bool { return files[i].Path < files[j].Path })
	return files
}

// pathCharacters: what a pinned path may hold (printable ASCII without
// quotes, backslash or colon), the same for every OS and every encoder.
var pathCharacters = regexp.MustCompile(`^[A-Za-z0-9 ._+()\[\]{}@=,~!#$%&^'/-]+$`)

// identifier: a class, model type or licence name from the Hub. Anything
// else is dropped (and the model goes to review when it was needed).
var identifier = regexp.MustCompile(`^[A-Za-z0-9_.+-]{1,100}$`)

func identifierOrEmpty(value string) string {
	if identifier.MatchString(value) {
		return value
	}
	return ""
}

func safePath(p string) bool {
	if p == "" || len(p) > 300 || !pathCharacters.MatchString(p) || strings.ContainsAny(p, "\\:\x00\"") || strings.HasPrefix(p, "/") {
		return false
	}
	for _, part := range strings.Split(p, "/") {
		if part == "" || part == "." || part == ".." || strings.HasPrefix(part, ".") {
			return false
		}
	}
	return path.Clean(p) == p
}

func hasExtension(files []TreeEntry, extension string) bool {
	for _, file := range files {
		if strings.EqualFold(path.Ext(file.Path), extension) {
			return true
		}
	}
	return false
}

func hasFile(files []TreeEntry, name string) bool {
	for _, file := range files {
		if file.Path == name {
			return true
		}
	}
	return false
}

// inferLibrary names the library from the files when the Hub does not.
func inferLibrary(files []TreeEntry) string {
	switch {
	case hasFile(files, "model_index.json"):
		return "diffusers"
	case hasFile(files, "modules.json") && hasFile(files, "config_sentence_transformers.json"):
		return "sentence-transformers"
	case hasExtension(files, ".skops"):
		return "sklearn"
	case hasFile(files, "config.json") && hasExtension(files, ".safetensors"):
		return "transformers"
	}
	return ""
}

// selectFiles picks the files the runtime needs, and the weights variant.
func selectFiles(files []TreeEntry, library string, decision *Decision) ([]ManifestFile, string) {
	switch library {
	case libraryGGUF:
		return selectGGUF(files, decision), ""
	case "sklearn":
		return selectWeights(files, ".skops", false, decision)
	case "diffusers":
		return selectWeights(files, ".safetensors", true, decision)
	default:
		return selectWeights(files, ".safetensors", false, decision)
	}
}

// selectWeights keeps every file with the weights extension and the
// support files (configuration, tokenizer). For diffusers, weights at the
// root are single-file checkpoints the pipeline does not read. When every
// weights directory has an `fp16` variant, only that variant is kept.
func selectWeights(files []TreeEntry, weightsExtension string, componentsOnly bool, decision *Decision) ([]ManifestFile, string) {
	var weights, support []TreeEntry
	hasPickle := false
	for _, file := range files {
		extension := strings.ToLower(path.Ext(file.Path))
		switch {
		case extension == weightsExtension:
			if componentsOnly && !strings.Contains(file.Path, "/") {
				continue
			}
			weights = append(weights, file)
		case pickleExtensions[extension]:
			hasPickle = true
		case supportExtensions[extension] && file.Size <= maxSupportFileBytes:
			support = append(support, file)
		}
	}
	if len(weights) == 0 {
		if hasPickle {
			decision.mark(StatusRejected, "format.pickle_only")
		} else {
			decision.mark(StatusReview, "format.no_weights")
		}
		return nil, ""
	}

	variant := ""
	directories := map[string]bool{}
	withFP16 := map[string]bool{}
	for _, file := range weights {
		directory := path.Dir(file.Path)
		directories[directory] = true
		if isFP16(file.Path) {
			withFP16[directory] = true
		}
	}
	if len(withFP16) == len(directories) && len(withFP16) > 0 {
		variant = "fp16"
	}
	var kept []TreeEntry
	for _, file := range weights {
		if (variant == "fp16") == isFP16(file.Path) || (variant == "" && !hasPlainSibling(weights, file)) {
			kept = append(kept, file)
		}
	}
	kept = append(kept, support...)
	return manifestFiles(kept, decision), variant
}

func isFP16(p string) bool {
	return strings.Contains(path.Base(p), ".fp16.")
}

// hasPlainSibling: an fp16 file whose directory also has non-variant
// weights is left out (the variant is not used).
func hasPlainSibling(weights []TreeEntry, file TreeEntry) bool {
	if !isFP16(file.Path) {
		return false
	}
	directory := path.Dir(file.Path)
	for _, other := range weights {
		if path.Dir(other.Path) == directory && !isFP16(other.Path) {
			return true
		}
	}
	return false
}

// selectGGUF keeps one GGUF file (the preferred quantization), its vision
// projector when there is one, and the support files.
func selectGGUF(files []TreeEntry, decision *Decision) []ManifestFile {
	var models, projectors, support []TreeEntry
	sharded := false
	for _, file := range files {
		name := strings.ToLower(path.Base(file.Path))
		switch {
		case strings.HasSuffix(name, ".gguf") && ggufShard.MatchString(name):
			sharded = true
		case strings.HasSuffix(name, ".gguf") && strings.Contains(name, "mmproj"):
			projectors = append(projectors, file)
		case strings.HasSuffix(name, ".gguf"):
			models = append(models, file)
		case supportExtensions[path.Ext(name)] && file.Size <= maxSupportFileBytes && !strings.Contains(file.Path, "/"):
			support = append(support, file)
		}
	}
	if len(models) == 0 {
		if sharded {
			decision.mark(StatusReview, "format.gguf_sharded")
		} else {
			decision.mark(StatusReview, "format.no_weights")
		}
		return nil
	}
	chosen := models[0]
	found := false
	for _, quantization := range ggufPreference {
		for _, file := range models {
			if strings.Contains(strings.ToLower(path.Base(file.Path)), quantization) {
				chosen, found = file, true
				break
			}
		}
		if found {
			break
		}
	}
	if !found {
		for _, file := range models[1:] {
			if file.Size < chosen.Size {
				chosen = file
			}
		}
	}
	kept := []TreeEntry{chosen}
	if len(projectors) > 0 {
		projector := projectors[0]
		for _, file := range projectors[1:] {
			if file.Size < projector.Size {
				projector = file
			}
		}
		kept = append(kept, projector)
	}
	kept = append(kept, support...)
	return manifestFiles(kept, decision)
}

var hexSHA256 = regexp.MustCompile(`^[0-9a-f]{64}$`)
var hexSHA1 = regexp.MustCompile(`^[0-9a-f]{40}$`)

func manifestFiles(entries []TreeEntry, decision *Decision) []ManifestFile {
	out := make([]ManifestFile, 0, len(entries))
	for _, entry := range entries {
		file := ManifestFile{Path: entry.Path, Size: entry.Size}
		switch {
		case entry.LFS != nil && hexSHA256.MatchString(entry.LFS.OID):
			file.SHA256 = entry.LFS.OID
			if entry.LFS.Size > 0 {
				file.Size = entry.LFS.Size
			}
		case hexSHA1.MatchString(entry.OID):
			file.GitOID = entry.OID
		default:
			decision.mark(StatusReview, "files.hash_missing")
			continue
		}
		out = append(out, file)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Path < out[j].Path })
	return out
}

// classForSize: the hardware a model of `bytes` needs. A GGUF model runs on
// a CPU up to a larger size than a PyTorch one.
func classForSize(bytes int64, library string) HardwareClass {
	limitA, limitB := 2*gib, 10*gib
	if library == libraryGGUF {
		limitA, limitB = 5*gib, 12*gib
	}
	switch {
	case bytes <= limitA:
		return ClassA
	case bytes <= limitB:
		return ClassB
	default:
		return ClassC
	}
}

// seal computes Digest (SHA-256 of the manifest without Key and Digest)
// and Key (`<repository slug>-<digest prefix>`).
//
// The node recomputes the digest (crate p2p-node, `workload/hf/manifest.rs`)
// from the same JSON: fields in declaration order, empty optional fields
// left out, no HTML escaping. Every string is limited to characters both
// encoders write the same way (see safePath and identifier).
func (m *Manifest) seal() {
	m.Key, m.Digest = "", ""
	sum := sha256.Sum256(canonicalJSON(m))
	m.Digest = hex.EncodeToString(sum[:])
	m.Key = slug(m.Repository) + "-" + m.Digest[:12]
}

// canonicalJSON encodes a manifest as the node does.
func canonicalJSON(m *Manifest) []byte {
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	_ = encoder.Encode(m)
	return bytes.TrimSuffix(buffer.Bytes(), []byte("\n"))
}

// Verify reports whether Key and Digest match the rest of the manifest.
func (m Manifest) Verify() bool {
	copied := m
	copied.Files = append([]ManifestFile(nil), m.Files...)
	copied.seal()
	return copied.Key == m.Key && copied.Digest == m.Digest
}

var slugInvalid = regexp.MustCompile(`[^a-z0-9._-]+`)

func slug(repository string) string {
	value := strings.ReplaceAll(strings.ToLower(repository), "/", "--")
	value = slugInvalid.ReplaceAllString(value, "-")
	if len(value) > 80 {
		value = value[:80]
	}
	return strings.Trim(value, "-.")
}

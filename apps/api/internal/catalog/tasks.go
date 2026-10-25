// Package catalog is the catalogue of Hugging Face models the network can
// run ("Catalogue IA"): the user picks a task, then a model admitted for it.
//
// The code knows the tasks and the libraries, never a model. Everything
// specific to a model comes from the Hub API (`/api/models`,
// `/api/models/<id>/tree/<commit>`) and is checked against the Silicium rules
// before the model is admitted:
//
//   - tasks.go: the tasks of the Hub, with what Silicium needs to know about
//     each one (category, minimal hardware, how a result is checked);
//   - hub.go: the Hub client (read only, no token needed);
//   - admission.go: the rules that turn the Hub's description of a model into
//     a pinned manifest (`silicium-model/1`), or refuse it with reasons;
//   - store.go and sync.go: the catalogue kept in the database and its
//     periodic refresh, which keeps serving the last copy when the Hub is
//     down and quarantines a model whose pinned files changed on the Hub.
//
// The Hub is a partial source of truth: it decides what is tried, never what
// is accepted. The node checks the files again (hash) and the admission test
// (loading the model, running its examples) has the last word.
package catalog

import "sort"

// Category groups tasks as on the Hub's model page.
type Category string

const (
	Multimodal    Category = "multimodal"
	Vision        Category = "computer-vision"
	NLP           Category = "natural-language-processing"
	Audio         Category = "audio"
	Tabular       Category = "tabular"
	Reinforcement Category = "reinforcement-learning"
	Other         Category = "other"
)

// HardwareClass is the least hardware a task or a model needs:
// A runs on a CPU, B wants a GPU with 6 GB or more, C one with 16–24 GB.
type HardwareClass string

const (
	ClassA HardwareClass = "A"
	ClassB HardwareClass = "B"
	ClassC HardwareClass = "C"
)

func (c HardwareClass) rank() int {
	switch c {
	case ClassB:
		return 1
	case ClassC:
		return 2
	default:
		return 0
	}
}

// maxClass is the more demanding of two classes.
func maxClass(a, b HardwareClass) HardwareClass {
	if b.rank() > a.rank() {
		return b
	}
	return a
}

// Verification is how the network checks a result of the task (shown to the
// user before they submit a job).
type Verification string

const (
	// VerifyExact: a recomputed sample must give the same answer (labels,
	// predictions).
	VerifyExact Verification = "exact"
	// VerifySimilar: a recomputed sample is compared by a similarity
	// (ROUGE-L, cosine, IoU, WER…) above a threshold.
	VerifySimilar Verification = "similarity"
	// VerifyPerceptual: generated media are compared by perceptual
	// similarity, by a verifier of the same hardware class.
	VerifyPerceptual Verification = "perceptual"
	// VerifyFull: the whole result is computed again (price ×2).
	VerifyFull Verification = "full-recompute"
)

// Task is one task of the Hub (`pipeline_tag`).
type Task struct {
	ID       string   `json:"id"`
	Label    string   `json:"label"`
	Category Category `json:"category"`
	// MinClass is the least hardware of the task, whatever the model.
	MinClass     HardwareClass `json:"minClass"`
	Verification Verification  `json:"verification"`
	// Metric names the comparison used by the verifiers.
	Metric string `json:"metric"`
	// HubSchema: the Hub publishes input/output JSON schemas for the task
	// (package `@huggingface/tasks`); otherwise Silicium writes its own.
	HubSchema bool `json:"hubSchema"`
	// Libraries that run the task according to the Hub (`/api/tasks`); the
	// defaults below are refreshed by the sync.
	Libraries []string `json:"libraries"`
}

// tasks lists the 52 tasks of the Hub's model page. Libraries are those of
// `@huggingface/tasks` 0.21.61 (`TASKS_MODEL_LIBRARIES`).
var tasks = []Task{
	// Multimodal.
	{"audio-text-to-text", "Audio-Text-to-Text", Multimodal, ClassB, VerifySimilar, "rouge-l", false, []string{"transformers"}},
	{"image-text-to-text", "Image-Text-to-Text", Multimodal, ClassB, VerifySimilar, "rouge-l", false, []string{"transformers"}},
	{"image-text-to-image", "Image-Text-to-Image", Multimodal, ClassC, VerifyPerceptual, "clip+ssim", true, []string{"diffusers"}},
	{"image-text-to-video", "Image-Text-to-Video", Multimodal, ClassC, VerifyFull, "clip-keyframes", true, []string{"diffusers"}},
	{"visual-question-answering", "Visual Question Answering", Multimodal, ClassB, VerifySimilar, "exact-or-rouge-l", true, []string{"transformers", "transformers.js"}},
	{"document-question-answering", "Document Question Answering", Multimodal, ClassA, VerifySimilar, "exact-match+span", true, []string{"transformers", "transformers.js"}},
	{"video-text-to-text", "Video-Text-to-Text", Multimodal, ClassC, VerifySimilar, "rouge-l", false, []string{"transformers"}},
	{"visual-document-retrieval", "Visual Document Retrieval", Multimodal, ClassB, VerifySimilar, "cosine", false, []string{"transformers"}},
	{"any-to-any", "Any-to-Any", Multimodal, ClassC, VerifySimilar, "by-output-modality", false, []string{"transformers"}},
	// Computer vision.
	{"depth-estimation", "Depth Estimation", Vision, ClassA, VerifySimilar, "mean-relative-error", true, []string{"transformers", "transformers.js"}},
	{"image-classification", "Image Classification", Vision, ClassA, VerifyExact, "top-1", true, []string{"keras", "timm", "transformers", "transformers.js"}},
	{"object-detection", "Object Detection", Vision, ClassA, VerifySimilar, "iou+label", true, []string{"transformers", "transformers.js", "ultralytics"}},
	{"image-segmentation", "Image Segmentation", Vision, ClassB, VerifySimilar, "mask-iou", true, []string{"transformers", "transformers.js"}},
	{"text-to-image", "Text-to-Image", Vision, ClassB, VerifyPerceptual, "clip+ssim", true, []string{"diffusers"}},
	{"image-to-text", "Image-to-Text", Vision, ClassA, VerifySimilar, "rouge-l", true, []string{"transformers", "transformers.js"}},
	{"image-to-image", "Image-to-Image", Vision, ClassB, VerifyPerceptual, "ssim+clip", true, []string{"diffusers", "transformers", "transformers.js"}},
	{"image-to-video", "Image-to-Video", Vision, ClassC, VerifyFull, "clip-keyframes", true, []string{"diffusers"}},
	{"unconditional-image-generation", "Unconditional Image Generation", Vision, ClassB, VerifyPerceptual, "clip+ssim", false, []string{"diffusers"}},
	{"video-classification", "Video Classification", Vision, ClassB, VerifyExact, "top-1", true, []string{"transformers"}},
	{"text-to-video", "Text-to-Video", Vision, ClassC, VerifyFull, "clip-keyframes", true, []string{"diffusers"}},
	{"zero-shot-image-classification", "Zero-Shot Image Classification", Vision, ClassA, VerifyExact, "top-1", true, []string{"transformers", "transformers.js"}},
	{"mask-generation", "Mask Generation", Vision, ClassB, VerifySimilar, "mask-iou", false, []string{"transformers"}},
	{"zero-shot-object-detection", "Zero-Shot Object Detection", Vision, ClassB, VerifySimilar, "iou+label", true, []string{"transformers", "transformers.js"}},
	{"text-to-3d", "Text-to-3D", Vision, ClassC, VerifyFull, "render-similarity", false, []string{"diffusers"}},
	{"image-to-3d", "Image-to-3D", Vision, ClassC, VerifyFull, "render-similarity", false, []string{"diffusers"}},
	{"image-feature-extraction", "Image Feature Extraction", Vision, ClassA, VerifySimilar, "cosine", false, []string{"timm", "transformers"}},
	{"keypoint-detection", "Keypoint Detection", Vision, ClassA, VerifySimilar, "keypoint-distance", false, []string{"transformers"}},
	{"video-to-video", "Video-to-Video", Vision, ClassC, VerifyPerceptual, "ssim+clip-per-segment", false, []string{"diffusers"}},
	// Natural language processing.
	{"text-classification", "Text Classification", NLP, ClassA, VerifyExact, "label", true, []string{"adapter-transformers", "setfit", "spacy", "transformers", "transformers.js"}},
	{"token-classification", "Token Classification", NLP, ClassA, VerifySimilar, "entity-f1", true, []string{"adapter-transformers", "flair", "spacy", "span-marker", "stanza", "transformers", "transformers.js"}},
	{"table-question-answering", "Table Question Answering", NLP, ClassA, VerifyExact, "exact-match", true, []string{"transformers"}},
	{"question-answering", "Question Answering", NLP, ClassA, VerifySimilar, "exact-match+f1", true, []string{"adapter-transformers", "allennlp", "transformers", "transformers.js"}},
	{"zero-shot-classification", "Zero-Shot Classification", NLP, ClassA, VerifyExact, "label", true, []string{"transformers", "transformers.js"}},
	{"translation", "Translation", NLP, ClassA, VerifySimilar, "chrf", true, []string{"transformers", "transformers.js"}},
	{"summarization", "Summarization", NLP, ClassA, VerifySimilar, "rouge-l", true, []string{"transformers", "transformers.js"}},
	{"feature-extraction", "Feature Extraction", NLP, ClassA, VerifySimilar, "cosine", true, []string{"sentence-transformers", "transformers", "transformers.js"}},
	{"text-generation", "Text Generation", NLP, ClassA, VerifySimilar, "rouge-l", true, []string{"transformers", "transformers.js"}},
	{"fill-mask", "Fill-Mask", NLP, ClassA, VerifyExact, "top-1", true, []string{"transformers", "transformers.js"}},
	{"sentence-similarity", "Sentence Similarity", NLP, ClassA, VerifySimilar, "score-delta", true, []string{"sentence-transformers", "spacy", "transformers.js"}},
	{"text-ranking", "Text Ranking", NLP, ClassA, VerifySimilar, "kendall-tau", true, []string{"sentence-transformers", "transformers"}},
	// Audio.
	{"text-to-speech", "Text-to-Speech", Audio, ClassB, VerifyPerceptual, "audio-embedding+wer", true, []string{"espnet", "tensorflowtts", "transformers", "transformers.js"}},
	{"text-to-audio", "Text-to-Audio", Audio, ClassB, VerifyPerceptual, "clap", true, []string{"transformers", "transformers.js"}},
	{"automatic-speech-recognition", "Automatic Speech Recognition", Audio, ClassA, VerifySimilar, "wer", true, []string{"espnet", "nemo", "speechbrain", "transformers", "transformers.js"}},
	{"audio-to-audio", "Audio-to-Audio", Audio, ClassB, VerifySimilar, "spectral-similarity", false, []string{"asteroid", "fairseq", "speechbrain"}},
	{"audio-classification", "Audio Classification", Audio, ClassA, VerifyExact, "top-1", true, []string{"speechbrain", "transformers", "transformers.js"}},
	{"voice-activity-detection", "Voice Activity Detection", Audio, ClassA, VerifySimilar, "segment-overlap", false, nil},
	// Tabular.
	{"tabular-classification", "Tabular Classification", Tabular, ClassA, VerifyExact, "prediction", false, []string{"sklearn"}},
	{"tabular-regression", "Tabular Regression", Tabular, ClassA, VerifyExact, "prediction-delta", false, []string{"sklearn"}},
	{"time-series-forecasting", "Time Series Forecasting", Tabular, ClassA, VerifySimilar, "relative-error", false, nil},
	// Reinforcement learning.
	{"reinforcement-learning", "Reinforcement Learning", Reinforcement, ClassA, VerifySimilar, "episode-return", false, []string{"transformers", "stable-baselines3", "ml-agents", "sample-factory"}},
	{"robotics", "Robotics", Reinforcement, ClassB, VerifySimilar, "episode-return", false, nil},
	// Other.
	{"graph-ml", "Graph Machine Learning", Other, ClassA, VerifyExact, "prediction", false, []string{"transformers"}},
}

var tasksByID = func() map[string]*Task {
	byID := make(map[string]*Task, len(tasks))
	for i := range tasks {
		byID[tasks[i].ID] = &tasks[i]
	}
	return byID
}()

// Tasks returns a copy of every task, in the Hub's order.
func Tasks() []Task {
	out := make([]Task, len(tasks))
	for i, task := range tasks {
		task.Libraries = append([]string(nil), task.Libraries...)
		out[i] = task
	}
	return out
}

// FindTask returns the task `id`.
func FindTask(id string) (Task, bool) {
	task, ok := tasksByID[id]
	if !ok {
		return Task{}, false
	}
	copied := *task
	copied.Libraries = append([]string(nil), task.Libraries...)
	return copied, true
}

// networkReady lists the tasks the network runs now: those of the node's
// `ai/hf` workload and of the Silicium AI runtime (step 1 of the plan, tasks
// that run on a CPU). The existing AI workloads (batch AI, document search)
// keep their own pages.
var networkReady = map[string]bool{
	"text-classification": true, "token-classification": true, "question-answering": true,
	"zero-shot-classification": true, "translation": true, "summarization": true,
	"feature-extraction": true, "text-generation": true, "fill-mask": true,
	"sentence-similarity": true, "text-ranking": true, "table-question-answering": true,
	"image-classification": true, "zero-shot-image-classification": true, "object-detection": true,
	"image-to-text": true, "image-feature-extraction": true, "automatic-speech-recognition": true,
	"audio-classification": true,
}

// NetworkReady reports whether the network runs task `id` now.
func NetworkReady(id string) bool { return networkReady[id] }

// WithHubLibraries returns the tasks with the libraries the Hub lists now
// (`/api/tasks`); a task the Hub no longer lists keeps the defaults.
func WithHubLibraries(hub map[string][]string) []Task {
	out := Tasks()
	for i := range out {
		if libraries, ok := hub[out[i].ID]; ok && len(libraries) > 0 {
			sorted := append([]string(nil), libraries...)
			sort.Strings(sorted)
			out[i].Libraries = sorted
		}
	}
	return out
}

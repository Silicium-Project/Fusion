// The quote of a job of the catalogue: cheaper when workers already have
// the model ("warm"), dearer when it must be installed on workers ("cold").
//
// Prices are in credits and only shown for now: the credit balance and the
// payments to workers come in the next step of the plan (they will use the
// same quote, written in the job's chain proof).

package catalog

import (
	"math"
	"strings"
)

// Credits per item by hardware class.
var itemCredits = map[HardwareClass]float64{ClassA: 1, ClassB: 4, ClassC: 16}

const (
	// Items per fragment (the node's default).
	itemsPerFragment = 16
	// Fragments run at once by different workers, at most.
	maxParallelWorkers = 4
	// Credits per GB of model installed on one worker.
	installCreditsPerGB = 2.0
	// Share added for the verifiers' recomputation (a sample of each
	// fragment), or the whole job again for full-recompute tasks.
	sampleVerification = 0.25
)

// Availability counts the online workers, and those holding a model.
type Availability struct {
	OnlineWorkers int `json:"onlineWorkers"`
	WarmWorkers   int `json:"warmWorkers"`
}

// AvailabilityFromPeers reads the node's `/v1/peers` payload: online
// workers (not the server itself), and those announcing `key` in
// `capacity.ai_models`.
func AvailabilityFromPeers(payload map[string]any, key string) Availability {
	var availability Availability
	peers, _ := payload["peers"].([]any)
	for _, item := range peers {
		peer, ok := item.(map[string]any)
		if !ok {
			continue
		}
		online, _ := peer["online"].(bool)
		self, _ := peer["self"].(bool)
		if !online || self || !hasRole(peer, "compute") {
			continue
		}
		availability.OnlineWorkers++
		capacity, _ := peer["capacity"].(map[string]any)
		models, _ := capacity["ai_models"].([]any)
		for _, model := range models {
			if model == key {
				availability.WarmWorkers++
				break
			}
		}
	}
	return availability
}

func hasRole(peer map[string]any, role string) bool {
	roles, ok := peer["roles"].([]any)
	if !ok {
		return true // Older peers do not say: compute and verify.
	}
	for _, value := range roles {
		if text, _ := value.(string); strings.EqualFold(text, role) {
			return true
		}
	}
	return false
}

// Quote is the estimated price of a job.
type Quote struct {
	Items            int     `json:"items"`
	Fragments        int     `json:"fragments"`
	WorkersNeeded    int     `json:"workersNeeded"`
	WarmWorkers      int     `json:"warmWorkers"`
	OnlineWorkers    int     `json:"onlineWorkers"`
	Warm             bool    `json:"warm"`
	ComputeCredits   float64 `json:"computeCredits"`
	VerifyCredits    float64 `json:"verifyCredits"`
	InstallCredits   float64 `json:"installCredits"`
	TotalCredits     float64 `json:"totalCredits"`
	InstallGigabytes float64 `json:"installGigabytes"`
	Verification     string  `json:"verification"`
	EstimateOnly     bool    `json:"estimateOnly"`
}

// QuoteFor prices `items` items of `model` given the availability.
func QuoteFor(model Model, items int, availability Availability) Quote {
	items = max(items, 1)
	class := HardwareClass(model.HardwareClass)
	unit, ok := itemCredits[class]
	if !ok {
		unit = itemCredits[ClassA]
	}
	fragments := int(math.Ceil(float64(items) / itemsPerFragment))
	needed := min(fragments, maxParallelWorkers)
	missing := max(needed-availability.WarmWorkers, 0)
	gigabytes := float64(model.TotalBytes) / float64(gib)

	verification := sampleVerification
	method := string(VerifySimilar)
	if task, found := FindTask(model.Task); found {
		method = string(task.Verification)
		if task.Verification == VerifyFull {
			verification = 1
		}
	}
	quote := Quote{
		Items: items, Fragments: fragments, WorkersNeeded: needed,
		WarmWorkers: availability.WarmWorkers, OnlineWorkers: availability.OnlineWorkers,
		Warm:             missing == 0,
		ComputeCredits:   round2(float64(items) * unit),
		InstallCredits:   round2(float64(missing) * math.Max(gigabytes, 0.1) * installCreditsPerGB),
		InstallGigabytes: round2(float64(missing) * gigabytes),
		Verification:     method,
		EstimateOnly:     true,
	}
	quote.VerifyCredits = round2(quote.ComputeCredits * verification)
	quote.TotalCredits = round2(quote.ComputeCredits + quote.VerifyCredits + quote.InstallCredits)
	return quote
}

func round2(value float64) float64 {
	return math.Round(value*100) / 100
}

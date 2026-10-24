// Brute-force protection of the login: after maxLoginFailures failed
// attempts on the same identifier within loginWindow, further attempts are
// refused until the window ends. A successful login clears the count.
//
// The count is per identifier (email or username, normalized), not per IP:
// behind the site's reverse proxy every request has the same address. The
// price is that someone can lock an account for 15 minutes by failing on
// purpose, which is acceptable here.

package handler

import (
	"strings"
	"sync"
	"time"
)

const (
	maxLoginFailures = 10
	loginWindow      = 15 * time.Minute
	// maxTrackedLogins bounds the memory used by the table.
	maxTrackedLogins = 10_000
)

type loginFailures struct {
	count int
	since time.Time
}

type loginThrottle struct {
	mu       sync.Mutex
	failures map[string]loginFailures
}

func newLoginThrottle() *loginThrottle {
	return &loginThrottle{failures: make(map[string]loginFailures)}
}

func throttleKey(identifier string) string { return strings.ToLower(strings.TrimSpace(identifier)) }

// blockedFor is how long logins on `identifier` are still refused; 0 when
// they are allowed.
func (t *loginThrottle) blockedFor(identifier string, now time.Time) time.Duration {
	if t == nil {
		return 0
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	entry, ok := t.failures[throttleKey(identifier)]
	if !ok || now.Sub(entry.since) >= loginWindow {
		return 0
	}
	if entry.count < maxLoginFailures {
		return 0
	}
	return loginWindow - now.Sub(entry.since)
}

// fail counts a failed login on `identifier`.
func (t *loginThrottle) fail(identifier string, now time.Time) {
	if t == nil {
		return
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	key := throttleKey(identifier)
	entry, ok := t.failures[key]
	if !ok || now.Sub(entry.since) >= loginWindow {
		if len(t.failures) >= maxTrackedLogins {
			t.forgetExpired(now)
		}
		entry = loginFailures{since: now}
	}
	entry.count++
	t.failures[key] = entry
}

// succeed clears the failures of `identifier`.
func (t *loginThrottle) succeed(identifier string) {
	if t == nil {
		return
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	delete(t.failures, throttleKey(identifier))
}

func (t *loginThrottle) forgetExpired(now time.Time) {
	for key, entry := range t.failures {
		if now.Sub(entry.since) >= loginWindow {
			delete(t.failures, key)
		}
	}
	if len(t.failures) >= maxTrackedLogins {
		// Still full of recent entries: start over rather than grow.
		t.failures = make(map[string]loginFailures)
	}
}

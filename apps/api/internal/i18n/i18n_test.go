package i18n

import (
	"net/http/httptest"
	"sort"
	"testing"
)

func TestEveryLanguageHasEveryMessage(t *testing.T) {
	reference := Keys(French)
	sort.Strings(reference)
	for _, lang := range []Lang{English, German} {
		if len(Keys(lang)) != len(reference) {
			t.Fatalf("%s has %d messages, French has %d", lang, len(Keys(lang)), len(reference))
		}
		for _, key := range reference {
			if _, ok := catalog[lang][key]; !ok {
				t.Fatalf("%s misses %q", lang, key)
			}
		}
	}
}

func TestTheLanguageComesFromAcceptLanguage(t *testing.T) {
	for header, want := range map[string]Lang{
		"":                     French,
		"en":                   English,
		"de-DE,de;q=0.9":       German,
		"es-ES, en-US;q=0.8":   English,
		"it":                   French,
		"EN-gb":                English,
		"fr-CA,fr;q=0.9,en;q=": French,
	} {
		request := httptest.NewRequest("GET", "/", nil)
		request.Header.Set("Accept-Language", header)
		if got := FromRequest(request); got != want {
			t.Fatalf("%q → %s, want %s", header, got, want)
		}
	}
}

func TestMessagesAreFormattedAndFallBack(t *testing.T) {
	if got := T(English, "password.too_short", 8); got != "The password must be at least 8 characters long." {
		t.Fatalf("got %q", got)
	}
	if got := T(German, "unknown.key"); got != "unknown.key" {
		t.Fatalf("got %q", got)
	}
}

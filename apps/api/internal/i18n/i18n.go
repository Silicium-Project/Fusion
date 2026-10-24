// Package i18n holds the messages the API shows to users, in French (the
// default), English and German.
//
// The site sends the language chosen by the user in `Accept-Language`;
// `FromRequest` picks the first supported language of that header and `T`
// returns a message of the catalog in that language. A key missing from a
// language falls back to French, then to the key itself, so a forgotten
// translation never shows an empty message.
package i18n

import (
	"fmt"
	"net/http"
	"strings"
)

// Lang is a supported language code.
type Lang string

const (
	French  Lang = "fr"
	English Lang = "en"
	German  Lang = "de"
)

// Default is the language used when the request names no supported one.
const Default = French

// Parse returns the supported language of a language tag ("en-US" → en),
// or false when the tag names another language.
func Parse(tag string) (Lang, bool) {
	tag = strings.ToLower(strings.TrimSpace(tag))
	if i := strings.IndexAny(tag, "-_"); i >= 0 {
		tag = tag[:i]
	}
	switch Lang(tag) {
	case French, English, German:
		return Lang(tag), true
	}
	return "", false
}

// FromHeader returns the first supported language of an `Accept-Language`
// header, in the order written (the site sends a single language; quality
// weights of browsers list the preferred one first in practice).
func FromHeader(header string) Lang {
	for _, part := range strings.Split(header, ",") {
		tag, _, _ := strings.Cut(part, ";")
		if lang, ok := Parse(tag); ok {
			return lang
		}
	}
	return Default
}

// FromRequest returns the language of a request.
func FromRequest(r *http.Request) Lang {
	if r == nil {
		return Default
	}
	return FromHeader(r.Header.Get("Accept-Language"))
}

// T returns the message `key` in `lang`, formatted with `args` (fmt verbs).
func T(lang Lang, key string, args ...any) string {
	message, ok := catalog[lang][key]
	if !ok {
		message, ok = catalog[Default][key]
	}
	if !ok {
		return key
	}
	if len(args) == 0 {
		return message
	}
	return fmt.Sprintf(message, args...)
}

// R is T in the language of the request.
func R(r *http.Request, key string, args ...any) string {
	return T(FromRequest(r), key, args...)
}

// Keys lists the keys of a language (used by the tests to check that every
// language has every message).
func Keys(lang Lang) []string {
	keys := make([]string, 0, len(catalog[lang]))
	for key := range catalog[lang] {
		keys = append(keys, key)
	}
	return keys
}

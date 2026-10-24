// Validation of the text users type: account fields (email, username, names,
// password) and the name and description of a job.
//
// Each function returns the cleaned value and the i18n key of the refusal,
// "" when the value is accepted. The site checks the same rules before
// sending; these are the ones that count.

package handler

import (
	"net/mail"
	"regexp"
	"strings"
	"unicode"
	"unicode/utf8"
)

const (
	maxEmailLength       = 254
	maxEmailLocalLength  = 64
	minPasswordRunes     = 8
	maxPasswordBytes     = 72 // bcrypt ignores what follows.
	maxPersonNameRunes   = 50
	maxJobTitleRunes     = 120
	maxJobDescriptionLen = 1000
)

// emailPattern is a plain address: no display name, no quoted local part,
// no IP literal, a domain with at least one dot.
var emailPattern = regexp.MustCompile(`^[a-z0-9.!#$%&'*+/=?^_{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$`)

// usernamePattern: 3 to 30 ASCII letters, digits, dots, hyphens or
// underscores. No "@", so a username never looks like an email address.
var usernamePattern = regexp.MustCompile(`^[A-Za-z0-9._-]{3,30}$`)

// reservedUsernames could be mistaken for the team or the system.
var reservedUsernames = map[string]bool{
	"admin": true, "administrator": true, "root": true, "silicium": true,
	"support": true, "system": true, "moderator": true, "staff": true,
}

// validEmail normalizes an email address (trimmed, lower case) and checks it.
func validEmail(value string) (string, string) {
	email := strings.ToLower(strings.TrimSpace(value))
	local, _, _ := strings.Cut(email, "@")
	if len(email) > maxEmailLength || len(local) > maxEmailLocalLength || !emailPattern.MatchString(email) {
		return "", "email.invalid"
	}
	if address, err := mail.ParseAddress(email); err != nil || address.Address != email {
		return "", "email.invalid"
	}
	return email, ""
}

// validUsername checks an optional username: nil when it is left empty.
func validUsername(value *string) (*string, string) {
	if value == nil || strings.TrimSpace(*value) == "" {
		return nil, ""
	}
	username := strings.TrimSpace(*value)
	if !usernamePattern.MatchString(username) || reservedUsernames[strings.ToLower(username)] || strings.Trim(username, "._-") == "" {
		return nil, "username.invalid"
	}
	return &username, ""
}

// validPersonName checks an optional first or last name: letters (any
// alphabet), spaces, hyphens, apostrophes and dots; nil when left empty.
func validPersonName(value *string) (*string, string) {
	if value == nil || strings.TrimSpace(*value) == "" {
		return nil, ""
	}
	name := strings.Join(strings.Fields(*value), " ")
	if utf8.RuneCountInString(name) > maxPersonNameRunes || !utf8.ValidString(name) {
		return nil, "name.invalid"
	}
	letters := 0
	for _, r := range name {
		switch {
		case unicode.IsLetter(r):
			letters++
		case unicode.Is(unicode.Mn, r), r == ' ', r == '-', r == '\'', r == '’', r == '.':
		default:
			return nil, "name.invalid"
		}
	}
	if letters == 0 {
		return nil, "name.invalid"
	}
	return &name, ""
}

// validNewPassword checks a password being set (never one being checked at
// login, so older short passwords still work until they are changed). The
// second value is the argument of the message (the minimum length).
func validNewPassword(password string) (string, []any) {
	switch {
	case utf8.RuneCountInString(password) < minPasswordRunes:
		return "password.too_short", []any{minPasswordRunes}
	case len(password) > maxPasswordBytes:
		return "password.too_long", nil
	}
	return "", nil
}

// validJobTitle trims a job title and checks it: 1 to 120 characters,
// without control or bidirectional-override characters.
func validJobTitle(value, fallback string) (string, string) {
	title := strings.Join(strings.Fields(value), " ")
	if title == "" {
		title = fallback
	}
	if utf8.RuneCountInString(title) > maxJobTitleRunes || hasHiddenCharacters(title, false) {
		return "", "job.title_invalid"
	}
	return title, ""
}

// validJobDescription trims a job description and checks it: at most 1,000
// characters; line breaks and tabs are kept.
func validJobDescription(value string) (string, string) {
	description := strings.TrimSpace(strings.ReplaceAll(value, "\r\n", "\n"))
	if utf8.RuneCountInString(description) > maxJobDescriptionLen || hasHiddenCharacters(description, true) {
		return "", "job.description_long"
	}
	return description, ""
}

// jobPriorities are the priorities a job can have.
var jobPriorities = map[string]bool{"low": true, "normal": true, "high": true, "urgent": true}

// validJobPriority checks a priority; empty means the default.
func validJobPriority(value, fallback string) (string, string) {
	priority := strings.ToLower(strings.TrimSpace(value))
	if priority == "" {
		return fallback, ""
	}
	if !jobPriorities[priority] {
		return "", "job.priority_invalid"
	}
	return priority, ""
}

// hasHiddenCharacters reports control characters (line breaks and tabs
// allowed when multiline) and the invisible characters that reorder or hide
// text (bidirectional overrides, zero-width characters), which can make a
// name read differently from what it is.
func hasHiddenCharacters(value string, multiline bool) bool {
	if !utf8.ValidString(value) {
		return true
	}
	for _, r := range value {
		if multiline && (r == '\n' || r == '\t') {
			continue
		}
		if unicode.IsControl(r) || isInvisibleFormat(r) {
			return true
		}
	}
	return false
}

func isInvisibleFormat(r rune) bool {
	return (r >= 0x200B && r <= 0x200F) || (r >= 0x202A && r <= 0x202E) || (r >= 0x2060 && r <= 0x2069) || r == 0xFEFF
}

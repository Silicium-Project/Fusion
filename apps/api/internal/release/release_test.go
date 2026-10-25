package release

import "testing"

func TestCurrentDefaultsToDevelopment(t *testing.T) {
	t.Setenv("SILICIUM_RELEASE_CHANNEL", "")
	t.Setenv("SILICIUM_RELEASE_VERSION", "")
	t.Setenv("SILICIUM_APP_VERSION", "")
	t.Setenv("SILICIUM_RELEASE_BUILD", "")

	got := Current()
	if got.Channel != Dev || got.Version != "unknown" || got.Build != "local" {
		t.Fatalf("unexpected development defaults: %#v", got)
	}
}

func TestCurrentNormalizesProductionMetadata(t *testing.T) {
	t.Setenv("SILICIUM_RELEASE_CHANNEL", " PROD ")
	t.Setenv("SILICIUM_RELEASE_VERSION", "1.2.3")
	t.Setenv("SILICIUM_RELEASE_BUILD", "abc123")

	got := Current()
	if got.Channel != Prod || got.Version != "1.2.3" || got.Build != "abc123" {
		t.Fatalf("unexpected production metadata: %#v", got)
	}
}

func TestValidateRejectsUnknownChannel(t *testing.T) {
	if err := Validate("staging"); err == nil {
		t.Fatal("expected unknown release channel to be rejected")
	}
}

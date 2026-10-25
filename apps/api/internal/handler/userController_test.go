package handler

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/silicium/internal/auth"
	"github.com/silicium/internal/contextkeys"
	"github.com/silicium/internal/models"
	"gorm.io/gorm"
)

// accountTestHandler is a handler on a fresh in-memory database of users.
func accountTestHandler(t *testing.T, name string) (Handler, *gorm.DB) {
	t.Helper()
	database, err := gorm.Open(sqlite.Open("file:"+name+"?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := database.AutoMigrate(&models.User{}, &models.Job{}); err != nil {
		t.Fatal(err)
	}
	sqlDB, _ := database.DB()
	sqlDB.SetMaxOpenConns(1)
	t.Cleanup(func() { _ = sqlDB.Close() })
	return New(database), database
}

// call sends a JSON request to `handle` as `userID` ("" for none) in `lang`.
func call(handle http.HandlerFunc, method, body, userID, lang string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, "/", strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	if lang != "" {
		request.Header.Set("Accept-Language", lang)
	}
	if userID != "" {
		request = request.WithContext(context.WithValue(request.Context(), contextkeys.UserIDKey, userID))
	}
	response := httptest.NewRecorder()
	handle(response, request)
	return response
}

func message(response *httptest.ResponseRecorder) string {
	var payload map[string]string
	_ = json.Unmarshal(response.Body.Bytes(), &payload)
	return payload["message"]
}

func TestAnAccountIsCreatedThenSignsIn(t *testing.T) {
	h, _ := accountTestHandler(t, "account-flow")
	created := call(h.Register, "POST", `{"email":"Ada@Example.test","password":"correct horse","username":"ada"}`, "", "en")
	if created.Code != http.StatusCreated || message(created) != "Account created. You can now sign in." {
		t.Fatalf("register: %d %s", created.Code, created.Body.String())
	}
	login := call(h.Login, "POST", `{"identifier":"ada@example.test","password":"correct horse"}`, "", "")
	var tokens map[string]string
	_ = json.Unmarshal(login.Body.Bytes(), &tokens)
	if login.Code != http.StatusOK || tokens["token"] == "" || tokens["refresh_token"] == "" {
		t.Fatalf("login: %d %s", login.Code, login.Body.String())
	}
	if _, err := auth.ParseAccess(tokens["token"]); err != nil {
		t.Fatal("the access token is not an access token")
	}
	refreshed := call(h.RefreshToken, "POST", `{"refresh_token":"`+tokens["token"]+`"}`, "", "")
	if refreshed.Code != http.StatusUnauthorized {
		t.Fatalf("an access token renewed the session: %d", refreshed.Code)
	}
	refreshed = call(h.RefreshToken, "POST", `{"refresh_token":"`+tokens["refresh_token"]+`"}`, "", "")
	if refreshed.Code != http.StatusOK {
		t.Fatalf("refresh: %d %s", refreshed.Code, refreshed.Body.String())
	}
}

func TestUsernamesAreUniqueIgnoringCase(t *testing.T) {
	h, _ := accountTestHandler(t, "account-username")
	call(h.Register, "POST", `{"email":"a@example.test","password":"password1","username":"Thom"}`, "", "")
	second := call(h.Register, "POST", `{"email":"b@example.test","password":"password1","username":"thom"}`, "", "de")
	if second.Code != http.StatusConflict || message(second) != "Dieser Benutzername wird bereits verwendet." {
		t.Fatalf("register: %d %s", second.Code, second.Body.String())
	}
	call(h.Register, "POST", `{"email":"c@example.test","password":"password1","username":"other"}`, "", "")
	update := call(h.UpdateUser, "PATCH", `{"username":"THOM"}`, "2", "")
	if update.Code != http.StatusConflict {
		t.Fatalf("update to a taken username: %d %s", update.Code, update.Body.String())
	}
}

func TestTheProfileIsCheckedBeforeBeingSaved(t *testing.T) {
	h, database := accountTestHandler(t, "account-profile")
	call(h.Register, "POST", `{"email":"a@example.test","password":"password1","username":"alice"}`, "", "")
	for _, body := range []string{
		`{"firstName":"` + strings.Repeat("x", 51) + `"}`,
		`{"lastName":"<img src=x>"}`,
		`{"username":"a b"}`,
		`{"username":"x"}`,
		`{"firstName":"ok"} trailing`,
	} {
		if response := call(h.UpdateUser, "PATCH", body, "1", ""); response.Code != http.StatusBadRequest {
			t.Fatalf("%s accepted: %d", body, response.Code)
		}
	}
	saved := call(h.UpdateUser, "PATCH", `{"firstName":" Zoë ","username":""}`, "1", "")
	var user models.User
	database.First(&user, 1)
	if saved.Code != http.StatusOK || user.FirstName == nil || *user.FirstName != "Zoë" || user.Username != nil {
		t.Fatalf("profile: %d %+v", saved.Code, user)
	}
}

func TestAPasswordChangeChecksTheCurrentOneWithoutEndingTheSession(t *testing.T) {
	h, _ := accountTestHandler(t, "account-password")
	call(h.Register, "POST", `{"email":"a@example.test","password":"password1"}`, "", "")
	wrong := call(h.ChangePassword, "PUT", `{"currentPassword":"nope-nope","newPassword":"password2"}`, "1", "")
	if wrong.Code != http.StatusBadRequest {
		t.Fatalf("wrong current password: %d (a 401 would sign the user out)", wrong.Code)
	}
	short := call(h.ChangePassword, "PUT", `{"currentPassword":"password1","newPassword":"short"}`, "1", "")
	if short.Code != http.StatusBadRequest {
		t.Fatalf("short new password: %d", short.Code)
	}
	ok := call(h.ChangePassword, "PUT", `{"currentPassword":"password1","newPassword":"password2"}`, "1", "")
	if ok.Code != http.StatusOK {
		t.Fatalf("change: %d %s", ok.Code, ok.Body.String())
	}
	if call(h.Login, "POST", `{"identifier":"a@example.test","password":"password2"}`, "", "").Code != http.StatusOK {
		t.Fatal("the new password does not sign in")
	}
}

func TestRepeatedFailedLoginsAreThrottled(t *testing.T) {
	h, _ := accountTestHandler(t, "account-throttle")
	call(h.Register, "POST", `{"email":"a@example.test","password":"password1"}`, "", "")
	for i := 0; i < maxLoginFailures; i++ {
		if response := call(h.Login, "POST", `{"identifier":"a@example.test","password":"guess"}`, "", ""); response.Code != http.StatusUnauthorized {
			t.Fatalf("attempt %d: %d", i, response.Code)
		}
	}
	blocked := call(h.Login, "POST", `{"identifier":" A@example.test ","password":"password1"}`, "", "en")
	if blocked.Code != http.StatusTooManyRequests || blocked.Header().Get("Retry-After") == "" || !strings.Contains(message(blocked), "Too many") {
		t.Fatalf("after %d failures: %d %s", maxLoginFailures, blocked.Code, blocked.Body.String())
	}
}

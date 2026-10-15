package session

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

func TestCookieRoundTrip(t *testing.T) {
	m := NewManager("secret", false)
	id := uuid.New()
	rec := httptest.NewRecorder()
	m.Set(rec, id)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	for _, c := range rec.Result().Cookies() {
		req.AddCookie(c)
	}
	got, ok := m.UserID(req)
	if !ok || got != id {
		t.Fatalf("got %v %v, want %v", got, ok, id)
	}
}

func TestTamperedCookieIsRejected(t *testing.T) {
	m := NewManager("secret", false)
	rec := httptest.NewRecorder()
	m.Set(rec, uuid.New())
	c := rec.Result().Cookies()[0]
	other := NewManager("other", false)
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.AddCookie(c)
	if _, ok := other.UserID(req); ok {
		t.Fatal("cookie signed with another secret must be rejected")
	}
	req = httptest.NewRequest(http.MethodGet, "/", nil)
	req.AddCookie(&http.Cookie{Name: CookieName, Value: "abc.def"})
	if _, ok := m.UserID(req); ok {
		t.Fatal("garbage cookie must be rejected")
	}
}

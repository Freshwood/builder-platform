// Package session keeps the guest user id in an HMAC-signed cookie.
package session

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
)

// CookieName is the name of the session cookie.
const CookieName = "hw_session"

// MaxAge is how long a guest session lives without a visit (180 days).
const MaxAge = 180 * 24 * time.Hour

// Manager signs and verifies session cookies.
type Manager struct {
	secret []byte
	secure bool
}

// NewManager returns a manager; secure cookies require HTTPS (production).
func NewManager(secret string, secure bool) *Manager {
	return &Manager{secret: []byte(secret), secure: secure}
}

// UserID returns the user id of a valid session cookie.
func (m *Manager) UserID(r *http.Request) (uuid.UUID, bool) {
	c, err := r.Cookie(CookieName)
	if err != nil {
		return uuid.Nil, false
	}
	payload, signature, ok := strings.Cut(c.Value, ".")
	if !ok || !hmac.Equal([]byte(signature), []byte(m.sign(payload))) {
		return uuid.Nil, false
	}
	raw, err := base64.RawURLEncoding.DecodeString(payload)
	if err != nil {
		return uuid.Nil, false
	}
	id, err := uuid.ParseBytes(raw)
	if err != nil {
		return uuid.Nil, false
	}
	return id, true
}

// Set writes the session cookie for a user.
func (m *Manager) Set(w http.ResponseWriter, id uuid.UUID) {
	payload := base64.RawURLEncoding.EncodeToString([]byte(id.String()))
	http.SetCookie(w, &http.Cookie{
		Name:     CookieName,
		Value:    payload + "." + m.sign(payload),
		Path:     "/",
		MaxAge:   int(MaxAge.Seconds()),
		HttpOnly: true,
		Secure:   m.secure,
		SameSite: http.SameSiteLaxMode,
	})
}

func (m *Manager) sign(payload string) string {
	mac := hmac.New(sha256.New, m.secret)
	mac.Write([]byte(payload))
	return base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

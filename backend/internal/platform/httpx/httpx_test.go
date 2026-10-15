package httpx

import (
	"compress/gzip"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"testing/fstest"
)

func TestGzipCompressesJSONButNotEventStreams(t *testing.T) {
	h := Gzip(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/stream" {
			w.Header().Set("Content-Type", "text/event-stream")
		} else {
			w.Header().Set("Content-Type", "application/json")
		}
		_, _ = w.Write([]byte(`{"a": 1}`))
	}))
	for path, want := range map[string]string{"/json": "gzip", "/stream": ""} {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		req.Header.Set("Accept-Encoding", "gzip")
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if got := rec.Header().Get("Content-Encoding"); got != want {
			t.Errorf("%s: Content-Encoding = %q, want %q", path, got, want)
		}
		if want == "gzip" {
			zr, err := gzip.NewReader(rec.Body)
			if err != nil {
				t.Fatal(err)
			}
			body, _ := io.ReadAll(zr)
			if string(body) != `{"a": 1}` {
				t.Errorf("body = %q", body)
			}
		}
	}
}

func TestSPAFallsBackToIndex(t *testing.T) {
	files := fstest.MapFS{
		"index.html":    {Data: []byte("<html>app</html>")},
		"assets/app.js": {Data: []byte("js")},
	}
	h := SPA(files)
	for path, want := range map[string]string{"/": "<html>app</html>", "/projects/123": "<html>app</html>", "/assets/app.js": "js"} {
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, path, nil))
		if rec.Body.String() != want {
			t.Errorf("%s: body = %q, want %q", path, rec.Body.String(), want)
		}
	}
}

func TestSecurityHeaders(t *testing.T) {
	rec := httptest.NewRecorder()
	SecurityHeaders(http.NotFoundHandler()).ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/", nil))
	if rec.Header().Get("X-Frame-Options") != "DENY" || rec.Header().Get("X-Content-Type-Options") != "nosniff" {
		t.Fatal(rec.Header())
	}
}

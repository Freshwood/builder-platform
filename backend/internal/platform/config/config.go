// Package config reads the application settings from environment variables (12-factor).
package config

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
)

// DevSecret is the session secret outside production; production refuses to start with it.
const DevSecret = "dev-only-insecure-session-secret"

// Settings holds every configuration value of the server. Names follow the environment
// variables (DATABASE_URL, LLM_MODE, ...).
type Settings struct {
	Environment      string // development | test | production
	Port             int
	DatabaseURL      string
	SessionSecret    string
	CORSOrigins      []string
	AutoCreateSchema bool
	StaticDir        string // optional directory with a built SPA; empty uses the embedded one

	LLMMode               string // test | openai
	LLMBaseURL            string
	LLMModel              string
	LLMModelFast          string
	LLMAPIKey             string
	LLMReasoning          string // off | minimal | low | medium | high
	LLMMaxOutputTokens    int
	LLMTemperature        float64
	AgentRequestLimit     int
	AgentTotalTokensLimit int
}

// SecureCookies is true in production, where the session cookie requires HTTPS.
func (s Settings) SecureCookies() bool { return s.Environment == "production" }

// FromEnv loads the settings from the environment, with a `.env` file as fallback for unset
// variables.
func FromEnv() (Settings, error) {
	return Load(os.Getenv)
}

// Load builds the settings from a lookup function (os.Getenv in production, a map in tests).
func Load(getenv func(string) string) (Settings, error) {
	dotenv := readDotEnv(".env")
	get := func(key, fallback string) string {
		if v := getenv(key); v != "" {
			return v
		}
		if v, ok := dotenv[key]; ok && v != "" {
			return v
		}
		return fallback
	}
	var errs []error
	integer := func(key string, fallback int) int {
		raw := get(key, strconv.Itoa(fallback))
		v, err := strconv.Atoi(raw)
		if err != nil {
			errs = append(errs, fmt.Errorf("%s: %q ist keine Zahl", key, raw))
		}
		return v
	}
	s := Settings{
		Environment:           get("ENVIRONMENT", "development"),
		Port:                  integer("API_PORT", 8000),
		DatabaseURL:           get("DATABASE_URL", "sqlite:///./var/homeworking.db"),
		SessionSecret:         get("SESSION_SECRET", DevSecret),
		CORSOrigins:           splitList(get("CORS_ORIGINS", "http://localhost:3000")),
		AutoCreateSchema:      get("AUTO_CREATE_SCHEMA", "") == "true",
		StaticDir:             get("STATIC_DIR", ""),
		LLMMode:               get("LLM_MODE", "test"),
		LLMBaseURL:            get("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
		LLMModel:              get("LLM_MODEL", ""),
		LLMModelFast:          get("LLM_MODEL_FAST", ""),
		LLMAPIKey:             get("LLM_API_KEY", ""),
		LLMReasoning:          get("LLM_REASONING", "low"),
		LLMMaxOutputTokens:    integer("LLM_MAX_OUTPUT_TOKENS", 12_000),
		AgentRequestLimit:     integer("AGENT_REQUEST_LIMIT", 12),
		AgentTotalTokensLimit: integer("AGENT_TOTAL_TOKENS_LIMIT", 1_000_000),
	}
	temperature, err := strconv.ParseFloat(get("LLM_TEMPERATURE", "0.2"), 64)
	if err != nil {
		errs = append(errs, fmt.Errorf("LLM_TEMPERATURE: %w", err))
	}
	s.LLMTemperature = temperature
	errs = append(errs, s.check()...)
	return s, errors.Join(errs...)
}

func (s Settings) check() []error {
	var errs []error
	switch s.Environment {
	case "development", "test", "production":
	default:
		errs = append(errs, fmt.Errorf("ENVIRONMENT: unbekannter Wert %q", s.Environment))
	}
	switch s.LLMMode {
	case "test", "openai":
	default:
		errs = append(errs, fmt.Errorf("LLM_MODE: unbekannter Wert %q", s.LLMMode))
	}
	switch s.LLMReasoning {
	case "off", "minimal", "low", "medium", "high":
	default:
		errs = append(errs, fmt.Errorf("LLM_REASONING: unbekannter Wert %q", s.LLMReasoning))
	}
	if s.Environment == "production" {
		if s.SessionSecret == DevSecret {
			errs = append(errs, errors.New("SESSION_SECRET must be set in production"))
		}
		if s.LLMMode == "test" {
			errs = append(errs, errors.New("LLM_MODE=test is not allowed in production"))
		}
	}
	if s.LLMMode == "openai" && s.LLMModel == "" {
		errs = append(errs, errors.New("LLM_MODEL is required when LLM_MODE=openai"))
	}
	return errs
}

func splitList(raw string) []string {
	var out []string
	for _, part := range strings.Split(raw, ",") {
		if p := strings.TrimSpace(part); p != "" {
			out = append(out, p)
		}
	}
	return out
}

// readDotEnv parses a simple KEY=VALUE file; a missing file yields no values.
func readDotEnv(path string) map[string]string {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	values := map[string]string{}
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, value, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		value = strings.TrimSpace(value)
		if len(value) >= 2 && (value[0] == '"' || value[0] == '\'') && value[len(value)-1] == value[0] {
			value = value[1 : len(value)-1]
		}
		values[strings.TrimPrefix(strings.TrimSpace(key), "export ")] = value
	}
	return values
}

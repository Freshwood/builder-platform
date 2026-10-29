import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const config = [
  ...nextVitals,
  ...nextTs,
  {
    // Playwright fixtures call their `use` callback; it is not a React hook.
    files: ["tests/**/*.ts"],
    rules: { "react-hooks/rules-of-hooks": "off" },
  },
  { ignores: [".next/**", "playwright-report/**", "test-results/**", "tests/bdd/.features-gen/**", "src/api/gen/**", "next-env.d.ts"] },
];

export default config;

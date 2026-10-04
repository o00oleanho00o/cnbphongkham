import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    ".next/**",
    "out/**",
    "node_modules/**",
    "next-env.d.ts",
    "src/lib/api/schema.d.ts",
    "shots/**",
  ]),
  {
    rules: {
      "no-console": "error",
      // React 19 compiler lint. The ported dashboard resets derived state in effects on purpose (list
      // pointer back to the first match when the filter changes, form fields when another record is
      // opened); rewriting those effects would change behaviour the original tests rely on.
      "react-hooks/set-state-in-effect": "off",
      // The Vietnamese UI copy of the ported dashboard uses straight quotes inside JSX text ("sửa", "Gán");
      // they are valid and escaping them would diverge from the original strings.
      "react/no-unescaped-entities": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
]);

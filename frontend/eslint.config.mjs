import js from "@eslint/js";
import tanstackRouter from "@tanstack/eslint-plugin-router";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import { defineConfig, globalIgnores } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig([
  js.configs.recommended,
  ...tseslint.configs.recommended,
  react.configs.flat.recommended,
  react.configs.flat["jsx-runtime"],
  reactHooks.configs.flat["recommended-latest"],
  ...tanstackRouter.configs["flat/recommended"],
  {
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    settings: { react: { version: "detect" } },
    plugins: { "jsx-a11y": jsxA11y },
    rules: {
      "jsx-a11y/alt-text": "warn",
      "jsx-a11y/aria-props": "warn",
      "jsx-a11y/aria-proptypes": "warn",
      "jsx-a11y/aria-unsupported-elements": "warn",
      "jsx-a11y/role-has-required-aria-props": "warn",
      "jsx-a11y/role-supports-aria-props": "warn",
    },
  },
  globalIgnores([
    ".output/**",
    "dist/**",
    "node_modules/**",
    "src/routeTree.gen.ts",
    "src/lib/api/schema.d.ts",
    "shots/**",
  ]),
  {
    rules: {
      "no-console": "error",
      // The props of the screens are typed by TypeScript.
      "react/prop-types": "off",
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

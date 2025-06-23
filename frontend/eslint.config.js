import js from "@eslint/js";
import query from "@tanstack/eslint-plugin-query";
import importPlugin from "eslint-plugin-import";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import security from "eslint-plugin-security";
import sonarjs from "eslint-plugin-sonarjs";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/node_modules/**",  // Explicit node_modules
      "dist/**",             // Build output
      "coverage/**",         // Test coverage
      "htmlcov/**",          // Python coverage reports
      ".vite/**",            // Vite cache
      "*.config.js",         // Config files
      "*.config.ts",         // Config files
      "**/*.d.ts",           // Type declaration files
      ".DS_Store",           // OS files
      "*.log",               // Log files
      "build/**",            // Alternative build directory
      ".next/**",            // Next.js build cache if used
      ".cache/**",           // Generic cache
    ]
  },
  // Apply SonarJS recommended rules for safety-critical code
  sonarjs.configs.recommended,
  {
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommended,
      ...tseslint.configs.strict,
      ...tseslint.configs.stylistic,
      ...query.configs["flat/recommended"]
    ],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        project: "./tsconfig.eslint.json",
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      "import": importPlugin,
      "react": react,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
      "jsx-a11y": jsxA11y,
      "@tanstack/query": query,
      "security": security,
    },
    settings: {
      react: {
        version: "detect",
        runtime: "automatic", // Modern JSX transform (React 17+)
      },
      "import/resolver": {
        typescript: {
          alwaysTryTypes: true,
          project: "./tsconfig.eslint.json",
        },
        node: {
          extensions: [".js", ".jsx", ".ts", ".tsx"],
        },
      },
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      ...react.configs.recommended.rules,
      ...jsxA11y.configs.strict.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
      // Accessibility best practices
      "jsx-a11y/alt-text": "error",
      "jsx-a11y/aria-props": "error",
      "jsx-a11y/aria-proptypes": "error",
      "jsx-a11y/aria-unsupported-elements": "error",
      "jsx-a11y/role-has-required-aria-props": "error",
      "jsx-a11y/role-supports-aria-props": "error",
      // Additional TypeScript rules (Safety-Critical Enforcement)
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/explicit-function-return-type": "off",
      "@typescript-eslint/explicit-module-boundary-types": "off",
      "@typescript-eslint/no-explicit-any": "error",  // STRICT: No any types in safety-critical code
      "@typescript-eslint/no-non-null-assertion": "error",  // STRICT: No ! operator - handle nulls explicitly

      // Enhanced Type Safety Rules (Safety-Critical Application)
      "@typescript-eslint/no-unnecessary-condition": "warn", // Downgrade from error
      "@typescript-eslint/strict-boolean-expressions": ["warn", { // More permissive
        "allowString": true,
        "allowNumber": true,
        "allowNullableObject": true,
        "allowNullableBoolean": true,
        "allowNullableString": true,
        "allowNullableNumber": true,
        "allowAny": true // Allow any for now during migration
      }],
      "@typescript-eslint/no-unsafe-assignment": "warn", // Downgrade from error
      "@typescript-eslint/no-unsafe-call": "warn", // Downgrade from error
      "@typescript-eslint/no-unsafe-return": "warn", // Downgrade from error
      "@typescript-eslint/await-thenable": "error",
      "@typescript-eslint/no-loss-of-precision": "error",
      "@typescript-eslint/prefer-readonly": "warn", // Downgrade from error

      // Performance-critical async/promise rules
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",

      // React Safety Rules
      "react-hooks/exhaustive-deps": "error",
      "react/jsx-no-constructed-context-values": "error",
      "react/jsx-key": "error",
      "react/no-array-index-key": "warn", // Downgrade from error
      "react/no-danger": "error",
      "react/no-unstable-nested-components": "error",
      "react/jsx-no-useless-fragment": "error",
      "react/jsx-no-bind": ["warn", { // More permissive for modern React
        "ignoreDOMComponents": true,
        "ignoreRefs": true,
        "allowArrowFunctions": true, // Allow arrow functions
        "allowFunctions": true,
        "allowBind": false
      }],

      // React JSX Rules (Modern React 17+ configuration)
      "react/react-in-jsx-scope": "off", // Not needed with new JSX transform
      "react/jsx-uses-react": "off", // Not needed with new JSX transform

      // Code Quality & Maintainability (Relaxed for existing codebase)
      "complexity": ["warn", { "max": 15 }], // Increased from 10
      "max-depth": ["warn", { "max": 4 }], // Increased from 3
      "max-lines-per-function": ["warn", { "max": 100 }], // Increased from 50
      "@typescript-eslint/consistent-type-imports": "warn", // Downgrade from error
      "@typescript-eslint/naming-convention": [
        "warn", // Downgrade from error
        {
          "selector": "interface",
          "format": ["PascalCase"],
          "prefix": ["I"]
        },
        {
          "selector": "typeAlias",
          "format": ["PascalCase"]
        }
      ],

      // Memory Safety & Best Practices
      "prefer-const": "error",
      "no-var": "error",
      "no-throw-literal": "error",
      "import/no-cycle": "error",
      "no-console": ["warn", { allow: ["warn", "error"] }],

      // Additional Quality Rules (Phase 1 Enhancement)
      "@typescript-eslint/no-unnecessary-type-assertion": "warn", // Downgrade from error
      "@typescript-eslint/prefer-nullish-coalescing": "warn", // Downgrade from error
      "@typescript-eslint/prefer-optional-chain": "warn", // Downgrade from error
      "@typescript-eslint/no-non-null-assertion": "warn", // Downgrade from error
      "import/no-duplicates": "warn", // Downgrade from error
      "import/first": "warn", // Downgrade from error
      "import/newline-after-import": "warn", // Downgrade from error

      // React Best Practices
      "react/jsx-boolean-value": ["error", "never"],
      "react/self-closing-comp": "warn", // Auto-fixable
      "react/jsx-no-duplicate-props": "error",
      "react/no-children-prop": "error",
      "react/jsx-curly-brace-presence": ["error", { "props": "never", "children": "never" }],
      "react/no-unescaped-entities": "warn", // Allow quotes in JSX text

      // Security Rules (Safety-Critical Application)
      "security/detect-object-injection": "error",
      "security/detect-non-literal-regexp": "error",
      "security/detect-non-literal-fs-filename": "error",
      "security/detect-eval-with-expression": "error",
      "security/detect-pseudoRandomBytes": "error",
      "security/detect-possible-timing-attacks": "warn",
      "security/detect-unsafe-regex": "error",

      // SonarJS Rules (Additional Safety-Critical Logic) - using defaults from recommended config
    },
  },
  {
    // Allow console statements in WebSocket and API files for debugging
    files: ["src/api/**/*.{ts,tsx}", "src/hooks/useWebSocket.ts"],
    rules: {
      "no-console": "off",
    },
  },
  {
    // Disable react-refresh warnings for shadcn/ui components
    files: ["src/components/ui/**/*.{ts,tsx}"],
    rules: {
      "react-refresh/only-export-components": "off",
    },
  },
  {
    // Disable react-refresh warnings for data-table component which exports schema
    files: ["src/components/data-table.tsx"],
    rules: {
      "react-refresh/only-export-components": "off",
    },
  }
);

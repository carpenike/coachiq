# ESLint and TypeScript Configuration

This document details the ESLint and TypeScript configuration used in the rvc2api project's React frontend.

## ESLint Configuration

### Flat Configuration Format

The project uses ESLint v9+ with the new flat configuration format, which provides better performance and more flexibility:

- `frontend/eslint.config.js`: Main configuration file
- `frontend/eslint.config.mjs`: Alternative format for module support

### Key ESLint Rules

```javascript
{
  // General formatting rules
  "quotes": ["error", "double"],
  "semi": ["error", "always"],
  "comma-dangle": ["error", "never"],
  "no-trailing-spaces": "error",
  "eol-last": ["error", "always"]
}
```

### Plugins

The ESLint configuration uses several plugins:

- `typescript-eslint`: For TypeScript linting
- `eslint-plugin-react-hooks`: For React hooks linting rules
- `eslint-plugin-react-refresh`: For React Fast Refresh compatibility
- `eslint-plugin-jsdoc`: For JSDoc comment validation

## TypeScript Configuration

### Project References

The TypeScript configuration uses project references to separate concerns:

- `tsconfig.json`: Root configuration that references the specific configuration files
- `tsconfig.app.json`: Configuration for the main application code
- `tsconfig.node.json`: Configuration for Node.js specific code
- `tsconfig.test.json`: Configuration for tests

### Common Issues and Solutions

#### Interface Parsing Errors

ESLint may produce parsing errors for TypeScript files that have standalone interfaces but no imports. This occurs because ESLint treats files with no imports/exports as script files rather than modules.

**Solution**: Ensure all TypeScript files with interfaces have at least one import statement. We provide a utility script to fix this automatically:

```bash
npm run fix:interfaces
```

This script adds a React import to interface files that don't have any imports.

#### Trailing Commas

ESLint is configured to disallow trailing commas in objects, arrays, and function parameters. We provide a utility script to fix trailing comma issues:

```bash
npm run fix:style
```

## Pre-commit Hook Configuration

The pre-commit hook is configured to run ESLint automatically with the `--fix` option:

```yaml
- repo: https://github.com/pre-commit/mirrors-eslint
  rev: v8.56.0
  hooks:
    - id: eslint
      files: \.(js|ts|tsx)$
      types: [file]
      args: ["--fix", "--config", "frontend/eslint.config.js"]
      additional_dependencies:
        - eslint@9.25.0
        - eslint-plugin-react-hooks@5.2.0
        - eslint-plugin-react-refresh@0.4.19
        - typescript@5.8.3
        - typescript-eslint@8.30.1
        - "@eslint/js@9.26.0"
        - globals@16.0.0
        - eslint-plugin-jsdoc@50.6.17
      exclude: ^frontend/(dist|node_modules)/
```

## Fix Scripts

### fix-typescript-interfaces.sh

This script ensures that all TypeScript files with interface definitions have proper imports:

```bash
#!/bin/bash
# Fix TypeScript parsing issues with interfaces

echo "Ensuring TypeScript imports are properly handled..."

# Make sure imports are properly formatted for TypeScript files with interfaces
for file in $(find ./src -name "*.ts" -o -name "*.tsx"); do
  # Skip compiled JS files
  if [[ $file == *".js" ]]; then
    continue
  fi

  # Fix interface definitions causing parsing errors by ensuring proper imports
  if grep -q "interface " "$file"; then
    # Check if the file is using imports already
    if ! grep -q "import " "$file"; then
      echo "Adding import to $file"
      # Create a temporary file with the import added at the top
      TMP_FILE=$(mktemp)
      echo '// Ensure file is treated as a module' > "$TMP_FILE"
      echo 'import type { FC } from "react";' >> "$TMP_FILE"
      echo '' >> "$TMP_FILE"
      cat "$file" >> "$TMP_FILE"
      # Replace original file with temporary file
      mv "$TMP_FILE" "$file"
    fi
  fi

  # Fix trailing commas in objects and arrays
  if grep -q ",$" "$file"; then
    echo "Fixing trailing commas in $file"
    TMP_FILE=$(mktemp)
    sed 's/,[ \t]*$//' "$file" > "$TMP_FILE"
    mv "$TMP_FILE" "$file"
  fi
done

# Also check JS config files
for file in $(find . -maxdepth 2 -name "*.js" -o -name "*.config.js" -o -name "*.config.ts"); do
  # Fix trailing commas in objects and arrays
  if grep -q ",$" "$file"; then
    echo "Fixing trailing commas in $file"
    TMP_FILE=$(mktemp)
    sed 's/,[ \t]*$//' "$file" > "$TMP_FILE"
    mv "$TMP_FILE" "$file"
  fi
done

echo "TypeScript interface fixes applied!"
```

### fix-eslint-issues.sh

This script runs multiple fixes in sequence:

```bash
#!/bin/bash
# Fix common ESLint issues in JS/TS files

# Fix TypeScript interface issues first
echo "Fixing TypeScript interface issues..."
./scripts/fix-typescript-interfaces.sh || true

# Apply standard ESLint fixes
echo "Applying ESLint fixes with new config..."
npx eslint --config eslint.config.js . --ext .ts,.tsx --fix || true

echo "Fixing trailing commas in configuration files..."

# Fix specific files
FILES_TO_CHECK=(
  "postcss.config.js"
  "tailwind.config.js"
  "vite.config.ts"
  "jest.config.ts"
  "jest.config.js"
  "src/utils/config.ts"
)

for file in "${FILES_TO_CHECK[@]}"; do
  echo "Checking $file..."
  if [ -f "$file" ]; then
    # Generic fix for trailing commas at end of lines before closing brackets or braces
    TMP_FILE=$(mktemp)
    sed 's/,[ \t]*\([\]}]\)/\1/g' "$file" > "$TMP_FILE"
    mv "$TMP_FILE" "$file"
    echo "Fixed $file"
  fi
done

echo "Fixes applied!"
```

## Available NPM Scripts

The following scripts are available in `package.json`:

```json
{
  "scripts": {
    "lint": "eslint --config eslint.config.js . --ext .ts,.tsx",
    "lint:fix": "eslint --config eslint.config.js . --ext .ts,.tsx --fix",
    "fix:style": "./scripts/fix-eslint-issues.sh",
    "fix:interfaces": "./scripts/fix-typescript-interfaces.sh",
    "typecheck": "tsc -p tsconfig.app.json --noEmit"
  }
}
```

## Troubleshooting

If you continue to experience ESLint or TypeScript issues:

1. Run `npm run fix:interfaces` to add imports to standalone interface files
2. Run `npm run fix:style` to fix trailing commas and other common issues
3. Check that your file is included in the appropriate tsconfig.json
4. Ensure you're properly importing dependencies in each file
5. For persistent issues, check GitHub issue #30

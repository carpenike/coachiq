// Root ESLint Flat Config for rvc2api monorepo
// This file provides ignore patterns for the entire repository
// Frontend-specific linting is handled in web_ui/eslint.config.js

export default [
  // Global ignores (covers all build/output/generated/cache files everywhere)
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/dist-ssr/**",
      "**/.vite/**",
      "**/.vite-temp/**",
      "**/.cache/**",
      "**/build/**",
      "**/site/**", // MkDocs and documentation output
      "**/docs/_build/**", // Sphinx or other doc builds
      "**/*.tsbuildinfo",
      "**/*.log",
      "**/.eslintcache",
      "**/.parcel-cache/**",
      "**/.turbo/**",
      "**/.next/**",
      "**/.output/**",
      "**/.storybook-static/**",
      "**/coverage/**",
      "**/assets/javascripts/workers/*.min.js", // Minified/generated JS (e.g., search workers)
      "web_ui/scripts/generate-api-types.js", // Exclude Node.js utility script from linting
      "**/CNAME",
      "**/objects.inv",
      "**/sitemap.xml*",
      "**/index.html",
      "**/404.html",
      "**/.venv/**",
      "**/venv/**",
      "**/.env/**",
      "**/.mypy_cache/**",
      "**/.pytest_cache/**",
      "**/.ruff_cache/**",
      "**/.tox/**",
      "**/.nox/**",
      "**/.eggs/**",
      "**/_deprecated/**",
      "**/.idea/**",
      "**/.vscode/**",
      "**/.devcontainer/**",
      "**/devcontainer/**",
      "**/.devcontainer/home-cache/**",
      "**/lib/**",
      "**/bin/**",
      "**/site-packages/**",
      "**/usr/**",
      "**/opt/**",
      "**/lib64/**",
      "**/include/**",
      "**/share/**",
      "**/pyvenv.cfg",
      "**/*.pyc",
      "**/*.pyo",
      "**/__pycache__/**",
      "**/virtualenv/**",
      "**/env/**",
      "**/ENV/**",
      "**/tmp/**",
      "**/temp/**",
      "**/log/**",
      "**/logs/**",
      "**/output/**",
      "**/.history/**",
      "**/.DS_Store",
      "**/Thumbs.db",
      "**/desktop.ini",
      "**/npm-debug.log",
      "**/yarn-error.log",
      "**/pnpm-debug.log",
      "**/pip-log.txt",
      "**/pip-delete-this-directory.txt"
    ]
  }
];

# GitHub Actions Configuration

This page explains the GitHub Actions workflows used in the rvc2api project for continuous integration, documentation building, and package deployment.

## Workflow Overview

```mermaid
flowchart TD
    Push[Push to Main Branch] --> CheckDocs{Changes to docs?}
    Tag[Push Tag] --> BuildDeb[Build Deb Packages]
    CheckDocs -->|Yes| BuildDocs[Build Documentation]
    CheckDocs -->|No| End[End]
    BuildDocs --> DeployPages[Deploy to GitHub Pages]
    BuildDeb --> DeployDebs[Add to Deb Repository]
    DeployDebs --> DeployPages

    classDef trigger fill:#bbdefb,stroke:#1976d2,color:#212121;
    classDef check fill:#fff9c4,stroke:#fbc02d,color:#212121;
    classDef build fill:#c8e6c9,stroke:#388e3c,color:#212121;
    classDef deploy fill:#ffecb3,stroke:#ffa000,color:#212121;
    classDef end fill:#f5f5f5,stroke:#bdbdbd,color:#212121;

    class Push,Tag trigger;
    class CheckDocs check;
    class BuildDocs,BuildDeb build;
    class DeployPages,DeployDebs deploy;
    class End end;
```

## Available Workflows

The project includes the following GitHub Actions workflows:

1. **Documentation Deployment** (`deploy-docs.yml`):

   - Triggered on changes to documentation files or manual dispatch
   - Builds MkDocs documentation
   - Deploys to GitHub Pages

2. **Debian Repository** (`deploy-deb-repo.yml`):

   - Template for future Debian package repository deployment
   - Currently disabled by default
   - Will be triggered by new version tags when enabled

3. **Combined Deployment** (`deploy-combined.yml`):
   - Handles both documentation and Debian packages
   - Documentation is built on every push to main
   - Debian packages are built when a version tag is pushed
   - Both are deployed to appropriate locations on GitHub Pages

## GitHub Pages Structure

The GitHub Pages deployment has the following structure:

```
username.github.io/rvc2api/
├── index.html               # Documentation home page
├── assets/                  # Documentation assets
├── api/                     # API documentation
├── architecture/            # Architecture documentation
└── debian-repo/             # Debian package repository
    ├── dists/               # Distribution information
    └── pool/                # Package files
```

## Setting Up GitHub Pages

To enable GitHub Pages deployment:

1. Go to your GitHub repository settings
2. Navigate to "Pages" in the left sidebar
3. Under "Build and deployment", select "GitHub Actions" as the source
4. The first successful workflow run will deploy your site

## Manual Workflow Dispatch

You can manually trigger workflows from the GitHub Actions tab:

1. Go to the "Actions" tab in your repository
2. Select the workflow you want to run
3. Click "Run workflow" and select the branch

## Custom Domain Configuration

If you want to use a custom domain:

1. Add your custom domain in the GitHub repository settings under "Pages"
2. Create a CNAME file in the docs directory with your domain
3. Add the following DNS records for your domain:
   - A record: `185.199.108.153`
   - A record: `185.199.109.153`
   - A record: `185.199.110.153`
   - A record: `185.199.111.153`
   - CNAME record: Subdomain pointing to `username.github.io`

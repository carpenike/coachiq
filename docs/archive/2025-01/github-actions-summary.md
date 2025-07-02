# GitHub Actions Summary

This document provides a summary of the GitHub Actions workflows implemented for the rvc2api project.

## Implemented Workflows

### Documentation Deployment (`deploy-docs.yml`)

This workflow automates the building and deploying of the project documentation to GitHub Pages.

- **Triggers**:
  - Push to `main` branch that changes docs or mkdocs.yml
  - Manual trigger via workflow_dispatch
- **Steps**:
  - Checkout code
  - Set up Python and Poetry
  - Install dependencies
  - Generate OpenAPI schema
  - Build MkDocs documentation
  - Deploy to GitHub Pages
- **Features**:
  - Adds .nojekyll file to prevent Jekyll processing
  - Preserves custom domain configuration (CNAME)
  - Uses GitHub's built-in Pages deployment

### Debian Repository Deployment (`deploy-deb-repo.yml`)

This workflow template is prepared for building and deploying a Debian package repository.

- **Triggers**:
  - Currently disabled, will be enabled for version tags when ready
  - Manual trigger via workflow_dispatch for testing
- **Steps**:
  - Create Debian repository structure
  - (Placeholder for package building)
  - Generate Packages and Release files
  - Sign the repository with GPG
  - Deploy to GitHub Pages under `/debian-repo/` path

### Combined Deployment (`deploy-combined.yml`)

This workflow handles both documentation and Debian repository deployment in one job.

- **Triggers**:
  - Push to `main` branch
  - Push of version tags
  - Manual trigger
- **Components**:
  - Documentation build job (always runs)
  - Debian repository build job (only runs for tags)
  - Deployment job that combines outputs

### Documentation Testing (`test-docs.yml`)

This workflow tests the documentation build process without deployment.

- **Triggers**:
  - Pull requests that change docs files
  - Manual trigger
- **Features**:
  - Validates that documentation builds successfully
  - Performs basic link checking
  - Identifies TODO comments

## Setting Up GitHub Pages

1. Go to your repository settings on GitHub
2. Navigate to "Pages" in the left sidebar
3. Under "Build and deployment", select "GitHub Actions"
4. The first successful workflow run will deploy your site

## Debian Repository Signing

To enable GPG signing for the Debian repository:

1. Generate a GPG key using the provided script:

   ```bash
   ./scripts/generate_repo_key.sh
   ```

2. Add the key to GitHub secrets:
   - Base64 encode the private key as instructed by the script
   - Add it as a repository secret named `GPG_SIGNING_KEY`

## Custom Domain Configuration

To use a custom domain with GitHub Pages:

1. Uncomment and fill in the domain in the `docs/CNAME` file
2. Configure your domain's DNS settings:
   - Add A records pointing to GitHub Pages IP addresses
   - Or add a CNAME record for a subdomain

## Manual Workflow Dispatch

All workflows can be manually triggered from the Actions tab in the GitHub repository, making it easy to test or deploy without waiting for code changes.

# Enabling GitHub Pages

This guide provides step-by-step instructions for enabling GitHub Pages in your repository settings.

## Prerequisites

Before enabling GitHub Pages, ensure you have:

1. A GitHub repository with documentation in the `docs/` directory
2. MkDocs configured with `mkdocs.yml` in the repository root
3. GitHub Actions workflows for deploying docs (already included in this repository)

## Steps to Enable GitHub Pages

1. **Go to your repository on GitHub**

   Navigate to <https://github.com/carpenike/rvc2api>

2. **Open Repository Settings**

   Click the "Settings" tab near the top of the page

   ![GitHub Settings Tab](https://docs.github.com/assets/cb-47677/mw-1440/images/help/repository/repo-settings-tab.webp)

3. **Navigate to Pages Settings**

   In the left sidebar, click on "Pages"

   ![GitHub Pages Settings](https://docs.github.com/assets/cb-32291/mw-1440/images/help/pages/pages-tab.webp)

4. **Configure Build and Deployment Source**

   Under "Build and deployment", for the "Source" option, select "GitHub Actions"

   ![Select GitHub Actions](https://docs.github.com/assets/cb-86807/mw-1440/images/help/pages/source-menu.webp)

5. **Trigger Initial Deployment**

   Go to the "Actions" tab of your repository and run the "Deploy Documentation" workflow:

   - Click on "Actions"
   - Find "Deploy Documentation" workflow
   - Click "Run workflow" button
   - Select the branch (usually "main")
   - Click "Run workflow" to confirm

6. **Verify Deployment**

   After the workflow completes successfully:

   - Return to Settings → Pages
   - You should see a message saying "Your site is published at <https://username.github.io/rvc2api/>"
   - Click on the URL to verify the documentation is properly deployed

## Add Custom Domain (Optional)

To use a custom domain instead of the default github.io domain:

1. **Update CNAME File**

   Edit the `docs/CNAME` file and uncomment/add your domain:

   ```
   docs.example.com
   ```

2. **Configure DNS Settings**

   Add the following DNS records with your domain registrar:

   - For an apex domain (example.com):
     - A records pointing to GitHub Pages IP addresses:
       - 185.199.108.153
       - 185.199.109.153
       - 185.199.110.153
       - 185.199.111.153
   - For a subdomain (docs.example.com):
     - CNAME record pointing to `username.github.io`

3. **Configure Custom Domain in GitHub**

   In your repository settings under Pages:

   - Enter your custom domain in the "Custom domain" field
   - Click "Save"
   - Check "Enforce HTTPS" (recommended)

## Troubleshooting

- **Changes Not Reflecting**: Check the Actions tab for any workflow failures
- **Custom Domain Not Working**: Verify DNS propagation using `dig` or an online DNS lookup tool
- **HTTPS Issues**: Ensure DNS is properly configured and wait up to 24 hours for the certificate to be issued

# Push ClearTrace to GitHub from Terminal

The repository is `https://github.com/Rohibuilds/cleartrace-data-quality`. The first public README commit is already there. This project folder contains the rest of the app, documentation, tests, sample data, and a complete README.

## 1. Sign in to GitHub CLI

In Terminal, run:

```bash
gh auth login --hostname github.com --git-protocol https --web
```

Choose the browser sign-in flow and finish it on GitHub. Do not paste an access token into chat or into a project file.

## 2. Push the project

Run:

```bash
cd "/Users/rohith/Documents/ChatGPT/datafix/cleartrace-deployed"
bash push_to_github.sh
```

The script fetches the starter README commit, stages the project files while honoring `.gitignore`, creates one commit, and pushes it to `main`. It stops if the GitHub CLI is not signed in or if `origin` points at another repository.

The `.gitignore` excludes local credentials, virtual environments, generated caches, and internal planning/prompt notes. The upload includes application code, product specs, deployment files, tests, synthetic samples, and submission materials.

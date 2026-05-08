# Uploading OpenWally to GitHub

A safe, step-by-step guide to publishing this project to your private GitHub repository.

---

## Before you start — checklist

Work through this before touching git. These mistakes are hard to undo once pushed.

- [ ] **Your API key is NOT in the repo.** Open `.env` — confirm it exists and is listed in `.gitignore`. Never commit `.env`.
- [ ] **`projects/` is in `.gitignore`.** Any projects you've generated live here. They have their own repos and should not be nested inside this one.
- [ ] **No secrets in source files.** Search for `sk-ant-` in the codebase: `grep -r "sk-ant-" src/`. The result must be empty.
- [ ] **You have the logo file ready.** Save the OpenWally logo as `assets/logo.png` in this folder before committing, so the README renders correctly on GitHub.

---

## Step 1 — Add the logo

Save the OpenWally logo image into the `assets/` folder:

```
openwally/
└── assets/
    └── logo.png    ← put it here
```

---

## Step 2 — Install GitHub CLI (if you haven't already)

```bash
brew install gh        # macOS
gh auth login          # follow the prompts — choose GitHub.com → HTTPS → browser login
```

Verify it worked:

```bash
gh auth status
```

You should see `Logged in to github.com`.

---

## Step 3 — Initialise git in this project

```bash
cd /path/to/openwally    # navigate to this project folder

git init
git add .
```

Before committing, double-check nothing sensitive is staged:

```bash
git status
```

Confirm `.env` does **not** appear in the list. If it does, something is wrong with your `.gitignore` — stop and fix it before continuing.

---

## Step 4 — Make the first commit

```bash
git commit -m "Initial commit — OpenWally"
```

---

## Step 5 — Create the private GitHub repository and push

```bash
gh repo create openwally --private --source=. --remote=origin --push
```

This single command:
- Creates a new **private** repo called `openwally` on your GitHub account
- Sets it as the `origin` remote
- Pushes your `main` branch

---

## Step 6 — Verify on GitHub

```bash
gh repo view --web
```

This opens the repo in your browser. Confirm:
- The README renders with the OpenWally logo at the top
- There is no `.env` file visible
- There is no `projects/` folder visible

---

## Step 7 — Protect your main branch (recommended)

```bash
gh api repos/{owner}/openwally/branches/main/protection \
  --method PUT \
  --field required_status_checks=null \
  --field enforce_admins=false \
  --field required_pull_request_reviews=null \
  --field restrictions=null
```

Or do it in the browser: **Settings → Branches → Add branch protection rule** → branch name `main` → check "Require a pull request before merging".

---

## Future updates

After the initial push, the normal workflow is:

```bash
git add <files>
git status          # review what's staged before every commit
git commit -m "your message"
git push
```

Always run `git status` before `git commit` to avoid accidentally staging `.env` or generated project files.

---

## Troubleshooting

**`gh: command not found`** — Install GitHub CLI: `brew install gh`

**`remote origin already exists`** — Run `git remote remove origin` then repeat Step 5.

**Pushed `.env` by mistake** — Rotate your Anthropic API key immediately at console.anthropic.com, then remove the file from git history:
```bash
git rm --cached .env
echo ".env" >> .gitignore
git commit -m "Remove .env from tracking"
git push
```
Note: the key is still in git history. Rotating it is the only safe fix.

**Logo not showing in README** — Confirm the file is at `assets/logo.png` (exact case) and has been committed (`git add assets/logo.png`).

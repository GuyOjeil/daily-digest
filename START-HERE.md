# Electric & Tech News Digest — start here (simple steps)

This project collects electrical and tech news every day. It makes a web page, a news file for your website (`data.json`), and an optional email.

1. On GitHub, make a new PUBLIC repository named `daily-digest` (branch `main`).
2. Upload ALL the files of this folder (keep the `.github` and `src` folders).
3. Settings -> Actions -> General -> Workflow permissions -> choose "Read and write permissions" -> Save.
4. Settings -> Pages -> Build and deployment -> Source: choose "GitHub Actions".
5. Actions tab -> "Daily Electric and Tech News Digest" -> Run workflow.
6. Wait about 3 minutes. Then open: https://GuyOjeil.github.io/daily-digest/
7. The news file for your website is: https://GuyOjeil.github.io/daily-digest/data.json

Email is optional. Add these 5 secrets only if you want it: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, DIGEST_TO.

It runs by itself every day at 07:17 UTC.
After the first run, open `digest/source-health.md`. It shows which feeds worked. Remove the ones that failed.

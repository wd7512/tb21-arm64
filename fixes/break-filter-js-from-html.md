# break-filter-js-from-html

- **Class:** drift (floating base image).
- **Change:** in `environment/Dockerfile`, `FROM python:3.13-slim-bookworm` becomes `FROM python:3.13.7-slim-bookworm`. 3.13.7 is the Python patch level in the upstream image `alexgshaw/break-filter-js-from-html:20251031`. The solution and tests are unchanged.
- **Why:** the oracle payload `<!-->asdf<script>alert(401)</script> -->` depends on how `html.parser` handled `<!-->` before Python 3.13.15. From 3.13.15 on, `html.parser` closes that comment early, so BeautifulSoup removes the script and the verifier sees no alert. The unpinned tag resolved to 3.13.17 on 20 Nov 2026. A bisect on arm64 with beautifulsoup4 4.13.4 found that 3.13.7 to 3.13.14 keep the payload, and 3.13.15 to 3.13.17 break it.
- **Other drift, harmless here:** Chromium 142 to 156 (the old build is no longer in the Debian archive), soupsieve 2.8 to 4.1.3, and Debian 12.11 to 12.15.
- **Evidence (20 Nov 2026, local arm64 Docker, Harbor 0.23.0):**
  - The upstream amd64 image, emulated: oracle 1.0.
  - The unpinned arm64 rebuild: oracle 0.0.
  - The pinned arm64 rebuild: oracle 1.0, 1.0, 1.0 (sequential), and nop 0.0.

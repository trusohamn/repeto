# Production deployment

MP3s supplied in PRs are currently published to Cloudflare R2 by GitHub
Actions. GitHub Pages hosts the website and RSS feeds.

> **Status:** The workflow below describes the current publisher: it uploads
> MP3s already present in a PR directly to production R2 when approved with the
> `publish-audio` label. The audio-production pipeline described next is the
> intended design, not implemented behavior yet.

## Publishing flow

```mermaid
flowchart TD
    A["PR contains audio and content"] --> B["Maintainer adds publish-audio label"]
    B --> C["Trusted Action uploads audio to public R2"]
    C --> D{"Upload verified?"}
    D -- No --> E["Stop and report failure"]
    D -- Yes --> F["Save metadata, rebuild feed.xml, remove uploaded MP3s"]
    F --> G["Maintainer squash-merges the PR"]
    G --> H["Pages Action builds feeds and website"]
    H --> I["Deploy feeds and website"]
```

The label starts the production upload; there is no private staging. The
workflow does not merge: a maintainer merges the cleaned PR like any other,
which deploys the feeds and website. The audio is public on R2 before merge,
but nothing links to it until the Pages deployment.

## Planned audio-production pipeline

The same `publish-audio` label will authorize paid audio generation for the
exact PR revision. The trusted workflow will validate the inputs, render the
audio, and upload it to a **public staging namespace** in R2. It will verify the
uploaded bytes and provide staging links so a reviewer can listen before
merging. The staging files will not be linked from the production feed or
website.

```mermaid
flowchart TD
    A["PR with reviewed text and audio settings"] --> B["Maintainer adds publish-audio label"]
    B --> C["Trusted workflow validates exact PR revision"]
    C --> D["Generate audio"]
    D --> E["Upload and verify audio in public staging"]
    E --> F["Add staging listen links to PR"]
    F --> G["Reviewer listens and maintainer merges"]
    G --> H["Promote the exact verified bytes to production R2"]
    H --> I["Save production metadata and rebuild feed"]
    I --> J["Pages deploys feed and website"]
```

The label is the first approval because it authorizes synthesis and its
associated provider cost. Reviewing and merging the PR is the second approval.
Promotion must use the exact staged bytes that were reviewed; it must not
regenerate them. The workflow must bind staging objects to the approved PR
revision and verify their checksums during promotion.

Staging is intentionally public for simplicity: anyone with a staging URL can
listen to that audio. Do not put private or confidential material in a PR for
this pipeline. Staging URLs must remain separate from production enclosures;
only promotion and merge may switch the production feed to the production
audio URL.

## Publishing behavior

- The PR initially contains MP3s and associated content and catalog changes.
  Existing episode IDs and versioned audio filenames are preserved.
- An authorized maintainer approves the exact PR revision for upload. The
  privileged workflow uses trusted workflow code and does not execute code
  supplied by the PR. If the revision changes, it stops and requires a new
  authorization.
- The workflow uploads the intended MP3s to public R2 and verifies the stored
  bytes against the approved files. Retries are safe: an identical object can
  be reused, but different audio must not overwrite an existing versioned key.
- Only after verification does the workflow update the PR with the information
  needed to publish, including each audio object's filename, size and digest,
  rebuild the affected `feed.xml` files so their enclosures point to R2, and
  remove the uploaded MP3s from the PR's final state. The resulting
  revision must correspond to the approved content and verified audio; any
  other change invalidates authorization.
- The workflow comments that the PR is ready, and a maintainer squash-merges
  it. Its resulting commit on `main` contains publishing metadata and updated
  feeds, not the newly uploaded MP3s. Earlier PR commits can still contain the
  audio; this does not erase Git history.
- After merge, the Pages workflow rebuilds and deploys the feeds and website.
  Their audio links point to R2, and feed enclosure lengths come from verified
  metadata rather than local MP3 files. Relevant metadata changes must trigger
  this deployment.
- Upload or verification failure stops cleanup, so the PR is not ready to
  merge. Publication must not deploy feeds pointing to missing or unverified
  audio. If an upload succeeds but a later step fails, the public object may
  remain; retrying must be safe.

## How it is implemented

- Approval is adding the `publish-audio` label to a same-repository PR into
  `main` (only users with triage or write access can label).
  [publish-audio.yml](../.github/workflows/publish-audio.yml) removes the label
  first, so every run consumes one approval.
- The workflow publishes only the MP3s under `podcast/*/audio/` that the PR adds
  or changes, using [audio_publish.py](../code/audio_publish.py) from `main`.
  A PR without audio fails.
- Objects are stored at `<course>/audio/<file>`, mirroring the Pages paths, and
  served from `https://audio.repeto.stream`. Uploads are conditional
  (`If-None-Match: *`) and immutable (`Cache-Control: public, max-age=31536000,
  immutable`).
- Each published episode in `course.json` gets `bytes` and `sha256`.
  [podcast.py](../code/podcast.py) points enclosures with this metadata to R2;
  episodes without it keep their Pages URLs, so migration is incremental.
  After saving the metadata, the publisher rebuilds `feed.xml` for the affected
  courses, so the PR shows the new R2 enclosure URLs. Pages rebuilds all feeds
  on deploy as well. Re-packaging keeps the metadata and does not need the MP3
  locally.
- The maintainer's merge to `main` triggers
  [podcast.yml](../.github/workflows/podcast.yml) as usual.
- On failure the workflow comments on the PR. Fix the cause and add the label
  again; already uploaded identical audio is reused. Do not merge a PR that
  still contains new MP3s: they would be served from Pages, not R2.

## Local use

R2 credentials are not needed locally. Install `requirements-publish.txt` only
to upload from a machine.

```bash
python code/audio_publish.py plan                      # pending audio, no upload
python code/audio_publish.py publish --storage /tmp/r2 # rehearse into a folder
python code/audio_publish.py check --storage /tmp/r2   # verify saved size and checksum
```

## One-time setup

1. Create the R2 bucket `repeto-stream` and add the custom domain
   `audio.repeto.stream`. Do not connect `repeto.stream` itself: it would take
   the website and feeds away from GitHub Pages. Keep the public development
   URL (`r2.dev`) disabled.
2. Create an R2 **Account API token** with Object Read & Write limited to
   `repeto-stream`, without IP filtering. Its S3 Access Key ID and Secret Access
   Key are shown once; paste them directly into GitHub.
3. Create the GitHub environment `audio-production`:
   - Deployment branches: selected branches, `main` only. Both workflow modes
     run in the context of `main`. No required reviewers or wait timer; the
     label is the approval.
   - Environment secrets (no environment variables are used):

     | Secret | Value |
     |---|---|
     | `R2_ACCOUNT_ID` | Cloudflare account ID, from the bucket's S3 API URL `https://<account id>.r2.cloudflarestorage.com` |
     | `R2_BUCKET` | `repeto-stream` |
     | `R2_ACCESS_KEY_ID` | Access Key ID of the R2 API token |
     | `R2_SECRET_ACCESS_KEY` | Secret Access Key of the R2 API token |

4. Create the `publish-audio` label and allow GitHub Actions to create PRs (for
   migration). If `main` gets branch protection, required status checks will
   not run on the workflow's own commit (`GITHUB_TOKEN` pushes do not trigger
   workflows).
5. Upload a single test MP3 and confirm HTTPS playback, seeking and the RSS
   enclosure URL.
6. Run **Publish audio** manually on `main` to migrate tracked audio. It uploads
   and verifies everything pending and opens a PR with the metadata and
   rebuilt feeds; merging it switches feeds to R2.

## Operations and boundaries

- R2 production credentials are available only to the `audio-production`
  environment; they are not required for local generation.
- Existing URLs remain accessible after migration because the tracked MP3s stay
  on Pages; removing them and rewriting old Git history are separate decisions.
- Replaced audio always gets a new versioned filename. Spotify picks up the new
  enclosure URL; YouTube needs **Re-upload from RSS feed** in Studio.
- Automated tests cover integrity checks and failure and retry paths using fake
  storage.

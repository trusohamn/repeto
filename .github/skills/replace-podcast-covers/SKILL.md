---
name: replace-podcast-covers
description: Match new Repeto artwork to podcast language directions, copy it without removing originals, and refresh cover URLs in RSS feeds and web pages.
---

# Replace podcast covers

Work from the repository root. This workflow updates artwork locally; it does
not generate audio, create new shows, commit, push, or deploy.

## Identify and match

- Check Git status and preserve existing user edits.
- Inspect every supplied image visually rather than guessing from generated
  filenames. For the flag-based Repeto designs, the source language is on the
  left and the language being learned is on the right.
- Keep filenames visibly attached to images in a labelled contact sheet;
  never infer which filename belongs to an image from parallel response order.
  Identify both flags explicitly: Poland is white over red, Russia is white
  over blue over red, Sweden is a yellow cross on blue, Spain is red/yellow/red,
  and English uses the Union Jack. Plain speech bubbles are not flags.
- Match against `source_language` and `target_language` in each
  `podcast/<slug>/course.json`. Catalog Swedish is `sv`, while folder names use
  `swedish`. Reversed directions need different covers.
- Existing cover-only folders can receive matching artwork without creating a
  catalog or publishing a show. Leave images for absent directions and generic
  designs unused unless the user requests a destination.
- When asked to prepare absent directions, create `podcast/<source>-<target>/`
  with a copied `cover.jpeg` only. Do not create placeholder catalogs, feeds,
  or pages; the builder publishes only folders with a real `course.json`.
- If several images fit the same direction or the direction is unclear, ask
  the user to choose before replacing it.
- Inspect actual format and dimensions; podcast covers should be square JPEGs,
  1400-3000 pixels per side. On macOS use `sips` to inspect these properties.

## Copy and rebuild

- Record source checksums, current cover filenames, and current catalogs,
  feeds, pages, and story artwork before changing anything.
- Copy each selected source into its existing podcast folder as `cover.jpeg`.
  Never move, rename, overwrite, or delete originals in `new covers/`.
- Preserve story episode artwork under `images/stories/`; replacing a show
  cover does not replace its story covers.
- Configure the project's Python environment and use `.venv/bin/python`.
- Use the existing builder rather than manually rewriting generated URLs:

  ```sh
  .venv/bin/python code/podcast.py
  ```

- Preserve the existing public base URL; pass `--base-url` if it differs from
  the builder's default. This command rebuilds all catalog-backed shows and
  the homepage, but does not publish them.
- `code/podcast.py` gives copied artwork a `cover-<sha256[:8]>.jpeg` name and
  removes superseded published copies so podcast apps fetch a fresh URL.
  Only destination copies are affected. Use its `find_image` helper to resolve
  logical `cover.jpeg` paths. Cover-only folders retain their plain filename.

## Verify

```sh
.venv/bin/python -m unittest discover -s tests -p test_podcast.py -q
```

- Verify each destination's bytes match its selected source and all source
  checksums and filenames remain unchanged.
- Visually inspect the installed covers with their podcast slugs attached.
  Confirm both flags against catalog language settings; matching checksums and
  working URLs alone do not verify that the correct artwork was selected.
- Verify every active show's channel `itunes:image`, show page image, and
  homepage card point to the new fingerprinted file.
- Compare generated output with the pre-update snapshot: only show artwork
  references should differ. Catalogs, episode identities, audio references,
  descriptions, publication dates, and story artwork must remain unchanged.
- Inspect the final diff, report the number of covers replaced, and identify
  unused artwork. Do not claim that live platforms changed before deployment.

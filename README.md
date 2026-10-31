# Repeto – make your own listen-and-speak courses

I share this repository so you can clone it, adapt the material, and generate
your own language courses. Use it to make screen-free audio practice for your
family, students, or yourself—not just to listen to the courses I have made.

The scripts turn multilingual phrases and stories into MP3s with timestamp
JSON files, and can package them as podcast feeds. Practice follows
**prompt → thinking pause → answer → repetition**. Story episodes play a
complete chapter, practise its vocabulary, then play the same chapter again.

Just want to listen? Visit [Repeto](https://trusohamn.github.io/repeto/).

## 1. Set up

Requires **Python 3.10+**, **FFmpeg**, and an Azure Speech resource.
Run commands from the cloned repository's root.

```sh
# macOS; on other systems, install FFmpeg with your package manager
brew install ffmpeg
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Enter `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION` in your local `.env`.
Never commit or share credentials. Uncached synthesis sends course text to
Azure and may incur charges; completed speech clips are cached for reuse.
Azure is the default engine for publishable audio. The optional unofficial
Edge endpoint is not a substitute for licensed publishing.

The commands below use macOS/Linux paths. On Windows, use
`.venv\Scripts\python.exe` instead of `.venv/bin/python`.

## 2. Choose or adapt the material

- [Practice transcript](courses/practice/transcript.json): words and phrases.
- [Topic titles](courses/practice/topics.json): localized practice headings.
- [Stories](courses/stories/): chapter texts, vocabulary, and narration settings.

Supported language codes are `en`, `pl`, `ru`, `es` (Spain Spanish), and
Swedish: **`se` for practice, `sv` for stories and podcast catalogs**.
Source means the listener's prompt language; target means the language learned.
Always select the target explicitly, especially Spanish.

Keep existing entry IDs unchanged; assign unused IDs to new entries.
Review translations for natural wording, matching meaning, and clean spoken
text before spending money on synthesis. Adding a language flag does not
create missing translations or voice support.

For agent-assisted work, use the
[language review skill](.github/skills/review-language-course/SKILL.md).

## 3. Generate practice audio

Start with a short English → Polish preview:

```sh
.venv/bin/python code/transcription.py --list-topics
.venv/bin/python code/transcription.py --source en --target pl --topic "Greetings" --max-duration 300 --double-output --output output/preview
```

Listen to the result before rendering all topics. For a full Polish → English course:

```sh
.venv/bin/python code/transcription.py --source pl --target en --double-output --output output/my-course
```

MP3s and matching timing JSON files go to the output folder.
`--double-output` repeats each target answer twice; omit it for one answer.
Use `--transcript PATH` for a different practice dataset.
Do not render simultaneously into the same output folder. If synthesis fails,
rerun the command: successful speech clips remain cached.

## 4. Add a story (optional)

```sh
.venv/bin/python code/story_course.py --source-language pl --target en
```

This uses the existing translated story and configured Azure narration voices.
Generated audio and timing files live under the story's `generated/audio/`
directory by default. Use `--help` to choose a transcript, output directory,
voice, rate, or pauses. Listen to a chapter before rendering or publishing
the whole story.

See the [story requirements](courses/REQUIREMENTS.md) and
[create-story-course skill](.github/skills/create-story-course/SKILL.md)
for custom stories and narration.

## 5. Package and publish (optional)

Create `podcast/my-course/` and put your artwork there as `cover.jpeg`.
Replace the example URL, author, and email below with your own.
The feed owner's email is public.

```sh
.venv/bin/python code/package_practice.py --source pl --target en --course my-course --renders output/my-course --podcast-base-url https://YOUR-USER.github.io/YOUR-REPO --author "Your name" --email you@example.com
```

The packager validates renders, moves MP3s into the podcast directory, and
creates the catalog, RSS, and web pages. Timing JSON stays in the render folder.
To add the story as season 2:

```sh
.venv/bin/python code/story_course.py --source-language pl --target en --package-podcast --podcast-course my-course
.venv/bin/python code/podcast.py --base-url https://YOUR-USER.github.io/YOUR-REPO
```

Rebuild with your own base URL before publishing; the scripts' default URL is
Repeto's. Check `course.json` for your title, descriptions, contact details,
and optional `links.Spotify` / `links.YouTube`. Keep episode IDs and publication
dates stable when updating audio. Cover filenames are fingerprinted automatically.

Packaging does **not** commit, push, or publish. To use GitHub Pages, configure
**Settings → Pages → Source: GitHub Actions**, then review the deployment
workflow before pushing. Submit your published RSS URL to podcast platforms.
See the [packaging skill](.github/skills/package-podcast/SKILL.md) for details.

## Checks and further reference

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m pyright
```

Use each script's `--help` for advanced options.
[REQUIREMENTS.md](REQUIREMENTS.md) documents audio limits and timestamp schemas.
When changing shared text, regenerate all affected recordings and timing files
together—editing labels alone does not change the spoken audio.

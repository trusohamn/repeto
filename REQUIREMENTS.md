Course Recording & Timestamp Specification

1. Core Purpose
   Deliver a structured audio learning resource for children using any source/target pair available in the transcript: Swedish (se), English (en), and Polish (pl). Default to Swedish prompts with separate Polish and English target tracks.

Use a drill-and-reveal interactive structure: prompt first, thinking pause, target confirmation, repetition pause.

Store millisecond-accurate timestamps for every individual language segment to enable web-based playback, quizzes, and synchronized text highlighting later.

2. File Organization & Audio Structure
   File Separation: One .mp3 file per selected source/target pair per topic, named with both language codes (e.g., 01_greetings_en_pl.mp3). Use --source and --target to select direction; --target accepts multiple languages. If omitted, targets are all languages except the source. Reject duplicate targets, empty target lists, and source-to-itself pairs.

All selected versions use the same selected entries in the same order. Do not generate a combined three-language track. Synthesize only the selected languages.

Every source transcript entry must have a unique permanent string ID. Copy it unchanged into both manifests; never derive it from a track position or spoken text. IDs survive reordering, text edits, and topic changes. Reject missing, empty, or duplicate IDs.

Lead-in / Buffer: 1000 ms of silence at the very beginning of each section file before speech starts.

Audio Specs:

Format: MP3

Sample Rate: 44.1 kHz

Bitrate: 192 kbps

Loudness Target: Normalized to -20 dBFS across all voices

Measure -20 dBFS as the RMS of each decoded voice clip before assembly, excluding the deliberate opening and inter-segment silences. The full track RMS will be lower because of those pauses. Reject clips that cannot meet the target without exceeding -1 dBFS peak headroom. MP3 encoding may cause a small level change; this is not a LUFS target.

Trim excess leading and trailing TTS silence before normalization, retaining 50 ms around speech detected above -60 dBFS. Preserve internal speech pauses. Segment timestamps describe the resulting trimmed clips.

3. Phrase Timing & Sequential Flow
   Each entry inside a section track must follow this exact order and spacing:

Source Audio: Native prompt in the selected source language (Swedish by default).

Thinking Gap: 2000 ms (2 seconds) silence for the child to retrieve the target phrase.

Target Audio: Answer in the selected target language.

Polish is articulated slightly slower and clearly for language learners. English uses its configured natural pace.

Repetition Gap: 2500 ms silence to allow the child to repeat the target phrase out loud before the next entry begins.

Optional --double-output: after the first repetition gap, play the same target
clip again, then add another 2500 ms repetition gap. The source prompt plays
only once. Default behavior remains one target playback. Reuse the same cached
clip; no additional synthesis is needed. Duration caps include both playbacks
and pauses and never split an entry. Use a separate output directory if running
concurrent renders.

Output filenames include the render's local start date and time, shared by all
topics and language versions in that invocation:
01_greetings_en_pl_2026-10-27_11-18-30.mp3, with a matching .json filename.
The manifest audio_file must match the generated MP3 filename.
Double-playback filenames add _double before the timestamp in both MP3 and JSON,
for example 01_greetings_en_pl_double_2026-10-27_11-18-30.mp3.
Existing output files are retained; do not start renders into the same folder within one second.

4. Voice & Speech Profiles
   Swedish Voice: Friendly, clear, standard Swedish accent; natural pace (rate="-5%").

English Voice: Warm, clear British or neutral accent; natural pace (rate="-5%").

Polish Voice: Gentle, maternal, highly articulate; slower pace (rate="-15%") to ensure distinct phonetics for young listeners.

5. Manifest & Timestamp Schema (Per Track)
   Alongside each audio track, generate a matching metadata JSON manifest. Include source_language and target_language. Every phrase entry must capture the exact start and end timestamps (in milliseconds) under the selected source and target language keys, as well as the total entry boundaries. Entry boundaries include the trailing 2500 ms repetition gap.

Each entry also includes target_playbacks: an ordered array of one or two
segments, each with text, start_ms, and end_ms. The target-language key still
refers to the first playback for compatibility. entry_end_ms includes the
pause after the final playback.

The example below illustrates a one-entry Swedish-to-Polish track. The English version uses target_language "en" and an "en" segment instead of "pl". Actual timestamps and total duration must be calculated from the assembled audio, not copied from this example.

JSON
{
"section": "Greetings",
"source_language": "se",
"target_language": "pl",
"audio_file": "01_greetings_se_pl.mp3",
"total_duration_ms": 6780,
"entries": [
{
"id": "phrase_000001",
"entry_start_ms": 1000,
"entry_end_ms": 6780,
"target_playbacks": [
{
"text": "Cześć!",
"start_ms": 3550,
"end_ms": 4280
}
],
"se": {
"text": "Hej!",
"start_ms": 1000,
"end_ms": 1550
},
"pl": {
"text": "Cześć!",
"start_ms": 3550,
"end_ms": 4280
}
}
]
} 6. Web Quiz & App Integration Requirements
Language Isolation: The web player must be able to play only the source prompt using the segment key identified by source_language.

Reveal Audio: The web player must be able to jump directly to and play only the target answer using the segment key identified by target_language.

Full Drill Playback: The player can run the full sequence (entry_start_ms to entry_end_ms) to let the child hear the entire prompt-and-response loop.

7. Preview Recording
   Support an optional duration cap, such as 300 seconds, per track. Select the longest shared prefix of complete entries that fits in all selected versions, including opening silence and repetition pauses. Do not truncate phrases or add padding to reach an exact duration. Versions can have different durations. If a section has fewer entries, record only those entries. Reject a cap too short for the first complete entry.

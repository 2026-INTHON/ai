# Private learning exports

BE owns completed-session authorization, durable jobs and expiring download links. AI only accepts service-authenticated `POST /v1/exports/render` and `GET /v1/exports/files/{asset_id}`. Export files stay in the existing private `/data/exports` volume.

Videos reconstruct the full sequence of NPC and learner turns from saved records, with background, uncropped character variants, stage directions, subtitles, learning marks and final score. This is a replay, not an OS screen recording. Original learner recordings are not retained; learner turns are text. NPC speech uses cached Typecast synthesis. Output: 540×960 H.264/AAC MP4, with long text paginated rather than cut off. The 30-minute render ceiling fails explicitly; it never silently truncates.

PDFs include the selected-language report sections and every exchange. The bundled Noto Sans KR font includes Korean/Japanese/Chinese glyphs and is distributed with its OFL license.

Only this project's public Supabase storage and application asset paths can be fetched. Files are generated atomically, use a content-addressed cache and run one renderer at a time in a worker thread, leaving realtime chat responsive. FFmpeg is already installed in the runtime image. No new paid video API is used.

Validation: renderer tests reject foreign asset URLs/path traversal, preserve visible head pixels with long captions and generate multipage PDFs; local FFmpeg and Poppler checks cover actual MP4/audio streams and PDF glyph/layout output.

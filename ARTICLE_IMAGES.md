# Article images

New articles request 3–5 generated images through `visual_suggestions`.

- `cover`: a full-screen opening scene with room for the title.
- `overview`: a standalone visual summary, also used on discovery cards.
- `how_it_works`: a useful illustration within the explanation.
- `explanation_2` and `explanation_3`: optional additional explanations, examples or limits.

Myth articles preserve the myth/reality comparison. They require `cover`, `overview`, `myth_visual` and `truth_visual`, with optional `how_it_works`. The maximum remains five.

Root `image_details` describes every requested non-cover slot exactly once. Each item supplies `slot`, `placement`, `alt`, `caption` and `learning_purpose`. Overview uses `overview` placement. Required explanation slots use `explanation`; optional illustrations can use `explanation`, `example` or `limits`. New category lessons set the legacy `supporting_image` field to null.

The shared validator rejects incomplete plans, missing metadata and excessive image requests. The worker generates and tracks each slot independently. Provider failures can leave a partial set; image status and retries retain this distinction.

The reader uses full-column, natural-ratio figures with captions and enlargement controls. Structured scientific and constitutional diagrams remain separate. Generated illustrations do not establish evidence or replace authentic source material.

This policy applies to new generation. Existing articles retain their stored images, legacy metadata and fallback card images. No automatic regeneration or paid backfill occurs.

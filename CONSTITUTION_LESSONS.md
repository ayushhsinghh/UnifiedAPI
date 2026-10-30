# Indian Constitution lessons, version 2.0

New `indian_constitution` requests use `app/src/facts/constitution.py` and return `schema_version: "2.0"`, `article_type: "constitution_lesson"` and `constitution_lesson`. Existing generation jobs, image lifecycle, history lookup and article identity remain unchanged. Legacy articles use their existing reader. They are not automatically regenerated.

## Learning contract

The five `lesson_type` values are `right_or_principle`, `institution`, `procedure`, `amendment` and `case_explainer`. Each article teaches one beginner-to-intermediate idea: a hypothetical everyday situation, plain meaning, 1–3 relevant provisions, 3–5 explanation steps, one hypothetical example, visible scope and limits, common confusions, two or three understanding checks and takeaways. The shared audience policy in `learning.py` applies to every provider attempt.

`constitutional_basis` entries identify source kind (constitutional text, judgment, amendment or ordinary law), provision type, reference, title, Part/Schedule, plain meaning and legal effect. Explanation steps link to stable basis IDs. Checks link to explanation-step IDs. Legal explanations require source IDs and at least one official source among the supported government/judiciary domains. This validates attribution structure; it does not establish legal accuracy.

Optional case notes separate the question, decision, significance and limits. They include the court, citation and nullable decision date. Optional amendment timelines show a label, nullable date, change and significance. Case-explainer lessons require a case note; amendment lessons require a timeline. Dates are ISO dates or null. The prompt distinguishes passage, assent, commencement and decision dates. Key terms and further detail stay short and expandable.

The reader keeps qualifications and example limits visible. Original text, case notes, history and answers use native disclosures. Closed disclosures remain excluded from section narration until explicitly opened. Mobile comparisons stack vertically. Timeline dates occupy their own row, without a line through the date. There are no user scores or saved answers.

## Original text and source dates

`app/src/facts/constitution_sources.py` is the only authority for displayed original wording. The provider may supply a `quote_candidate` of 40–1200 characters for a canonical `Article N` reference. The server removes the candidate and all provider-supplied original-text/verification metadata before persistence.

The matcher uses a fixed Legislative Department PDF URL for the edition as on 1 May 2024. It never fetches a model-provided URL, follows redirects or accepts a non-PDF response. Downloads are capped at 8 MiB, extraction at 1,000 pages and 3 million characters. Successful extraction is cached for one hour; failures for five minutes. An outer 12-second deadline keeps the optional enrichment from blocking the lesson indefinitely. The parser runs in a worker thread; a timed-out worker can finish in the background under its bounded request and document limits.

An excerpt must match, case-sensitively and with only whitespace normalized, inside the named Article's numbered boundaries. If the parser cannot establish a closing boundary, it fails closed. Unsupported references, omitted candidates, missing dependencies, source failures and mismatches produce no quotation. The UI shows the paraphrase and the official edition link instead. It does not infer a quotation from the model's confidence.

Successful matches receive server-owned `original_text`, `text_verification.status: "matched_official_edition"`, edition date, source URL and actual matching timestamp. `source_context.source_checked_at` records the text-retrieval timestamp separately from the match and article generation dates. `current_law_verified_at` remains null. This verifies only a wording match to a fixed historical edition, not later amendments, case law, legal correctness or the current legal position. `constitution_validation.legal_review` and `current_law_verification` remain `not_performed`.

Deploy with the new `pypdf==6.21.4` runtime dependency. The existing `requests` dependency handles the fixed-source download. The source is optional: an unavailable official endpoint does not prevent the article from completing. During local implementation, live retrieval of the official PDF was unavailable; the unmatched-text fallback was confirmed. No live legal-currency review was performed.

## Diagrams and images

The respective fixed diagram types are `scope_map`, `roles_map`, `process_sequence`, `before_after` and `case_path`, with a `none` text fallback. They contain 2–6 nodes and 1–10 resolving relationships. Every node participates. Scope and role relationships use conceptual links; processes and case paths use procedural arrows. Amendment comparisons use labelled panes that stack on mobile. They are teaching aids, not legal decision engines. No model HTML, SVG, coordinates or executable code is accepted.

Constitution articles use the shared [3–5 image plan](ARTICLE_IMAGES.md): a full-screen cover, an overview/card image and an explanatory illustration, with up to two useful extras. Root `image_details` supplies placement, learning purpose, caption and alt text. New lessons set legacy `supporting_image` to null. Generated scenes must not resemble authentic constitutional documents, judgments or historical evidence.

## Validation

Run `python3 -m unittest discover -s tests`. Tests cover all lesson formats, references, dates, official-domain checks, image budgets, retry, quotation metadata replacement, exact matching and fallback. With `requests` and `pypdf` installed, a real local PDF is parsed using a mocked fixed-source response. Network access, paid generation, production storage and legal accuracy are not established by these offline tests. Frontend tests cover reader selection, legacy fallback, date formatting, diagram mapping and the quotation display guard.

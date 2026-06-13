# Universal Rendrer

This repo renders release zip packages with Remotion.

Current wired renderers:

- `avatar-tax`: detects zips containing `avatar_plan.json` and renders the `AvatarTax` composition.
- `flash-news`: detects zips containing `scenes.json` and renders the `NewsFlash` composition.
- `archive-documentary`: detects zips containing `archive.json` and renders the `ArchiveDocumentary` composition.

Workflow inputs:

- `release_tag`: the GitHub release tag that contains zip assets, for example `v1`.
- `renderer_kind`: use `auto` unless you want to force a renderer from `renderers.json`.
- `videos_parallel`: how many zip packages render at the same time.
- `remotion_concurrency`: requested Remotion concurrency per render. The workflow clamps it to the runner CPU count.

The workflow uploads each rendered MP4 back to the same release, then uploads one combined `rendered-videos-<tag>.zip` release asset.

To add a future niche, add the Remotion component code first, then add an entry to `renderers.json` with the package marker file and composition id. In most cases the workflow file can stay exactly the same.


## GitHub rendering

Run **Render Release Zips**, enter the release tag, and the workflow auto-detects every zip type, renders each video in chunks, stitches it, and uploads each MP4 back to the release.

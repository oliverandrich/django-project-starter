"""Static file storage for granian, which serves STATIC_ROOT with one expiry for every file."""

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class HashedStaticFilesStorage(ManifestStaticFilesStorage):
    """ManifestStaticFilesStorage without the unhashed copies.

    Every remaining file except the manifest has its content hash in the name, so a one-year
    expiry never serves a stale file. A reference that bypasses the static template tag gets a
    404, not an old copy. Django reads the manifest, staticfiles.json, from STATIC_ROOT.
    """

    def post_process(self, paths, *args, **options):
        yield from super().post_process(paths, *args, **options)
        # collectstatic passes dry_run as a keyword.
        if options.get("dry_run"):
            return
        for name, hashed_name in self.hashed_files.items():
            if hashed_name != name:
                self.delete(name)

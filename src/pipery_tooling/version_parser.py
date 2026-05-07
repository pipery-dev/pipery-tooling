"""Semantic version parsing and comparison for tag management.

Supports:
- Basic semver: v1.2.3
- Major/minor versions: v1, v1.2
- Platform-suffixed versions: v1.2.3-gitlab, v1-github
- Latest tags: latest, latest-gitlab
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ParsedVersion:
    """A parsed semantic version with optional platform suffix."""
    major: int
    minor: Optional[int] = None
    patch: Optional[int] = None
    platform: Optional[str] = None
    is_latest: bool = False

    @property
    def full_version(self) -> str:
        """Return the full semantic version string (e.g., '1.2.3')."""
        if self.is_latest:
            return "latest"
        parts = [str(self.major)]
        if self.minor is not None:
            parts.append(str(self.minor))
        if self.patch is not None:
            parts.append(str(self.patch))
        return ".".join(parts)

    @property
    def tag_name(self) -> str:
        """Return the full tag name with platform suffix if present."""
        base = "latest" if self.is_latest else f"v{self.full_version}"
        if self.platform:
            return f"{base}-{self.platform}"
        return base

    def matches_series(self, other: ParsedVersion) -> bool:
        """Check if this version is in the same series as another.

        Examples:
            v1.2.3 and v1.2.0 are in the same v1.2 series
            v1.2.3 and v1.3.0 are NOT in the same v1.2 series
            v1.2.3 and v1.0.0 are in the same v1 series
        """
        if self.is_latest or other.is_latest:
            return False
        if self.platform != other.platform:
            return False
        if self.major != other.major:
            return False
        # Both must have matching minor (if specified in either)
        if self.minor is not None and other.minor is not None:
            return self.minor == other.minor
        return True

    def __lt__(self, other: ParsedVersion) -> bool:
        """Compare versions semantically."""
        if not isinstance(other, ParsedVersion):
            return NotImplemented
        if self.is_latest or other.is_latest:
            # latest is always greater than any version
            return not self.is_latest and other.is_latest

        # Platform doesn't matter for comparison
        maj_cmp = (self.major or 0) - (other.major or 0)
        if maj_cmp != 0:
            return maj_cmp < 0

        min_cmp = (self.minor or 0) - (other.minor or 0)
        if min_cmp != 0:
            return min_cmp < 0

        patch_cmp = (self.patch or 0) - (other.patch or 0)
        return patch_cmp < 0

    def __le__(self, other: ParsedVersion) -> bool:
        return self == other or self < other

    def __gt__(self, other: ParsedVersion) -> bool:
        return not self <= other

    def __ge__(self, other: ParsedVersion) -> bool:
        return not self < other

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ParsedVersion):
            return NotImplemented
        # Platform suffix doesn't affect equality for version comparison
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.is_latest == other.is_latest
        )

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.is_latest))


class VersionParser:
    """Parse and analyze semantic versions with platform suffixes."""

    # Regex patterns for tag parsing
    LATEST_TAG_RE = re.compile(r"^latest(?:-([a-z0-9]+))?$")
    SEMVER_TAG_RE = re.compile(r"^v(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([a-z0-9]+))?$")

    @staticmethod
    def parse_tag(tag: str) -> Optional[ParsedVersion]:
        """Parse a git tag into a ParsedVersion.

        Supports:
        - latest, latest-gitlab
        - v1, v1-gitlab
        - v1.2, v1.2-gitlab
        - v1.2.3, v1.2.3-gitlab

        Returns None if tag doesn't match supported format.
        """
        original_tag = tag
        tag = tag.lstrip("v")  # Handle tags that may start with 'v'

        # Check latest tags
        match = VersionParser.LATEST_TAG_RE.match(tag)
        if match:
            return ParsedVersion(
                major=0,  # latest doesn't have version components
                platform=match.group(1),
                is_latest=True,
            )

        # Check semver tags - need to prefix with 'v' for regex to match
        match = VersionParser.SEMVER_TAG_RE.match("v" + tag)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2)) if match.group(2) else None
            patch = int(match.group(3)) if match.group(3) else None
            platform = match.group(4)
            return ParsedVersion(
                major=major,
                minor=minor,
                patch=patch,
                platform=platform,
            )

        return None

    @staticmethod
    def parse_version_string(version: str) -> Optional[ParsedVersion]:
        """Parse a version string (e.g., '1.2.3' or '1.2').

        Returns None if version doesn't match supported format.
        """
        # Remove 'v' prefix if present
        version = version.lstrip("v")
        # Need to add 'v' back for regex to match
        match = VersionParser.SEMVER_TAG_RE.match("v" + version)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2)) if match.group(2) else None
            patch = int(match.group(3)) if match.group(3) else None
            platform = match.group(4)
            return ParsedVersion(
                major=major,
                minor=minor,
                patch=patch,
                platform=platform,
            )
        return None

    @staticmethod
    def get_major_tag(version: ParsedVersion) -> str:
        """Get the major version tag for a version.

        Examples:
            v1.2.3 -> v1
            v1.2.3-gitlab -> v1-gitlab
        """
        if version.is_latest:
            return version.tag_name
        base = f"v{version.major}"
        if version.platform:
            return f"{base}-{version.platform}"
        return base

    @staticmethod
    def get_minor_tag(version: ParsedVersion) -> str:
        """Get the minor version tag for a version.

        Examples:
            v1.2.3 -> v1.2
            v1.2.3-gitlab -> v1.2-gitlab
        """
        if version.is_latest:
            return version.tag_name
        base = f"v{version.major}"
        if version.minor is not None:
            base += f".{version.minor}"
        if version.platform:
            return f"{base}-{version.platform}"
        return base

    @staticmethod
    def get_latest_tag(platform: Optional[str] = None) -> str:
        """Get the latest tag for a platform.

        Examples:
            None -> latest
            'gitlab' -> latest-gitlab
        """
        if platform:
            return f"latest-{platform}"
        return "latest"

"""Editable field definitions for every option supported by project-renderer.js."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


IMAGE_SIZES = ("", "small", "medium", "large", "wide", "full")
IMAGE_ALIGNMENTS = ("", "left", "centre", "right")
IMAGE_STYLES = ("", "plain", "framed", "taped", "polaroid", "paper")
IMAGE_POSITIONS = ("", "normal", "offset-left", "offset-right")


def field(
    path: str,
    label: str,
    kind: str = "entry",
    *,
    choices: tuple[str, ...] = (),
    default: Any = "",
    help_text: str = "",
    media_dir: str = "",
    fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path,
        "label": label,
        "kind": kind,
        "choices": choices,
        "default": default,
        "help": help_text,
        "mediaDir": media_dir,
    }
    if fields is not None:
        result["fields"] = fields
    return result


def prefixed_fields(prefix: str, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for original in fields:
        item = deepcopy(original)
        item["path"] = f"{prefix}.{item['path']}"
        result.append(item)
    return result


IMAGE_FIELDS = [
    field("src", "Image file", "path", media_dir="images", help_text="Relative path, normally images/filename.jpg"),
    field("alt", "Alternative text", help_text="Describe the useful information in the image."),
    field("caption", "Caption", "text"),
    field("placeholder", "Placeholder label"),
    field("placeholderHint", "Placeholder guidance", "text"),
    field("size", "Size", "choice", choices=IMAGE_SIZES),
    field("align", "Alignment", "choice", choices=IMAGE_ALIGNMENTS),
    field("style", "Presentation style", "choice", choices=IMAGE_STYLES),
    field("position", "Position", "choice", choices=IMAGE_POSITIONS),
    field("rotation", "Rotation (-6 to 6)", "number"),
    field("loading", "Loading", "choice", choices=("", "lazy", "eager")),
    field("width", "Intrinsic width (pixels)", "integer"),
    field("height", "Intrinsic height (pixels)", "integer"),
    field("decorative", "Purely decorative image", "bool", default=False),
]

GALLERY_IMAGE_FIELDS = [
    field("src", "Image file", "path", media_dir="images"),
    field("alt", "Alternative text"),
    field("caption", "Caption", "text"),
    field("placeholder", "Placeholder label"),
    field("placeholderHint", "Placeholder guidance"),
    field("decorative", "Purely decorative", "bool", default=False),
    field("loading", "Loading", "choice", choices=("", "lazy", "eager")),
    field("width", "Width", "integer"),
    field("height", "Height", "integer"),
]

COMMON_BLOCK_FIELDS = [
    field("id", "Block ID", help_text="Unique URL-friendly ID. Optional for most blocks."),
    field("className", "Extra CSS class names"),
    field("navTitle", "Contents-menu label"),
    field("hideFromContents", "Hide from ‘On this page’", "bool", default=False),
]


BLOCK_SCHEMAS: dict[str, dict[str, Any]] = {
    "section": {
        "label": "Section",
        "description": "Main paper panel with optional nested blocks and contents-menu entry.",
        "fields": [
            field("title", "Section title"),
            field("intro", "Opening text", "paragraphs"),
            field("guide", "Include guidance", "text"),
        ],
        "container": "blocks",
    },
    "text": {
        "label": "Text",
        "description": "Heading, paragraphs, and optional list.",
        "fields": [
            field("title", "Heading"),
            field("content", "Paragraphs", "paragraphs", help_text="Separate paragraphs with a blank line."),
            field("items", "List items", "string_list", help_text="One item per line."),
            field("ordered", "Numbered list", "bool", default=False),
            field("listStyle", "List style", "choice", choices=("", "ticks")),
        ],
    },
    "heading": {
        "label": "Heading",
        "description": "Standalone heading inside the project narrative.",
        "fields": [
            field("text", "Heading text"),
            field("level", "Heading level", "choice", choices=("2", "3", "4", "5", "6"), default="3"),
        ],
    },
    "image": {
        "label": "Image",
        "description": "Image or intentional placeholder with full layout controls.",
        "fields": deepcopy(IMAGE_FIELDS),
    },
    "video": {
        "label": "Local video",
        "description": "Local video file with poster, playback controls, and optional captions.",
        "fields": [
            field("src", "Video file", "path", media_dir="videos"),
            field("poster", "Poster image", "path", media_dir="images"),
            field("caption", "Caption", "text"),
            field("size", "Size", "choice", choices=IMAGE_SIZES, default="wide"),
            field("controls", "Show controls", "bool", default=True),
            field("autoplay", "Autoplay", "bool", default=False),
            field("loop", "Loop", "bool", default=False),
            field("muted", "Muted", "bool", default=False),
            field("preload", "Preload", "choice", choices=("none", "metadata", "auto"), default="metadata"),
            field("captions.src", "Captions file", "path", media_dir="videos"),
            field("captions.srclang", "Caption language", default="en"),
            field("captions.label", "Caption label", default="English"),
            field("captions.kind", "Track kind", "choice", choices=("captions", "subtitles", "descriptions", "chapters", "metadata"), default="captions"),
            field("captions.default", "Default captions track", "bool", default=False),
        ],
    },
    "youtube": {
        "label": "YouTube video",
        "description": "Privacy-enhanced YouTube embed.",
        "fields": [
            field("url", "YouTube URL"),
            field("title", "Accessible video title"),
            field("caption", "Caption", "text"),
            field("size", "Size", "choice", choices=IMAGE_SIZES, default="wide"),
        ],
    },
    "gallery": {
        "label": "Image gallery",
        "description": "One-to-four-column responsive image gallery.",
        "fields": [
            field("columns", "Columns", "choice", choices=("1", "2", "3", "4"), default="2"),
            field("images", "Gallery images", "record_list", fields=GALLERY_IMAGE_FIELDS),
        ],
    },
    "two-column": {
        "label": "Two-column layout",
        "description": "Two nested block columns that stack on mobile.",
        "fields": [field("ratio", "Column ratio", "choice", choices=("1-1", "2-1", "1-2"), default="1-1")],
        "columns": 2,
    },
    "three-column": {
        "label": "Three-column layout",
        "description": "Three equal nested block columns that stack on mobile.",
        "fields": [],
        "columns": 3,
    },
    "image-text": {
        "label": "Image and text",
        "description": "Image beside explanatory text.",
        "fields": [
            field("imagePosition", "Image position", "choice", choices=("left", "right"), default="left"),
            field("title", "Heading"),
            field("content", "Paragraphs", "paragraphs"),
            *prefixed_fields("image", IMAGE_FIELDS),
        ],
    },
    "process-step": {
        "label": "Process step",
        "description": "Research/design/testing step with evidence and optional image.",
        "fields": [
            field("number", "Optional number"),
            field("title", "Step title"),
            field("content", "Explanation", "paragraphs"),
            field("show", "Evidence to show", "text"),
            *prefixed_fields("image", IMAGE_FIELDS),
        ],
    },
    "callout": {
        "label": "Callout",
        "description": "Standard, problem, subtle, or conclusion emphasis card.",
        "fields": [
            field("variant", "Variant", "choice", choices=("", "problem", "subtle", "conclusion")),
            field("title", "Heading"),
            field("content", "Paragraphs", "paragraphs"),
        ],
    },
    "quote": {
        "label": "Quote",
        "description": "Quotation with optional source.",
        "fields": [field("content", "Quote", "paragraphs"), field("source", "Source")],
    },
    "stats": {
        "label": "Statistics",
        "description": "Measured results or key project figures.",
        "fields": [
            field("items", "Statistics", "record_list", fields=[field("value", "Value"), field("label", "Label")]),
        ],
    },
    "timeline": {
        "label": "Timeline",
        "description": "Ordered milestones with dates and descriptions.",
        "fields": [
            field(
                "items",
                "Timeline entries",
                "record_list",
                fields=[field("date", "Date / phase"), field("title", "Title"), field("content", "Description", "paragraphs")],
            ),
        ],
    },
    "comparison": {
        "label": "Before/after comparison",
        "description": "Two option cards with images and explanations.",
        "fields": [
            field("left.label", "Left label", default="Before"),
            field("left.title", "Left title"),
            *prefixed_fields("left.image", IMAGE_FIELDS),
            field("left.content", "Left explanation", "paragraphs"),
            field("right.label", "Right label", default="After"),
            field("right.title", "Right title"),
            *prefixed_fields("right.image", IMAGE_FIELDS),
            field("right.content", "Right explanation", "paragraphs"),
        ],
    },
    "links": {
        "label": "Link buttons",
        "description": "One or more internal or external action links.",
        "fields": [
            field(
                "items",
                "Links",
                "record_list",
                fields=[field("label", "Label"), field("url", "URL or local path"), field("newTab", "Open in new tab", "bool", default=True)],
            ),
        ],
    },
    "download": {
        "label": "Download button",
        "description": "Download or open a local project file.",
        "fields": [
            field("label", "Button label"),
            field("file", "File", "path", media_dir="files"),
            field("filename", "Downloaded filename"),
            field("download", "Force download", "bool", default=True),
        ],
    },
    "divider": {"label": "Divider", "description": "Horizontal narrative divider.", "fields": []},
    "spacer": {
        "label": "Spacer",
        "description": "Intentional vertical pause.",
        "fields": [field("size", "Size", "choice", choices=("small", "medium", "large"), default="medium")],
    },
    "custom-html": {
        "label": "Custom HTML",
        "description": "Trusted project-specific markup. Advanced and potentially unsafe.",
        "fields": [field("html", "Trusted HTML", "code")],
    },
    "margin-notes": {
        "label": "Margin notes",
        "description": "Up to three handwritten notes shown on wide screens.",
        "fields": [
            field("label", "Accessible group label", default="Project notes"),
            field(
                "notes",
                "Notes",
                "record_list",
                fields=[field("text", "Note text", "text"), field("image", "Optional note image", "path", media_dir="images")],
            ),
        ],
    },
}


BLOCK_ORDER = tuple(BLOCK_SCHEMAS)


TOP_LEVEL_TABS: dict[str, list[dict[str, Any]]] = {
    "Basics": [
        field("siteName", "Site name", default="Fiza's Project Portfolio"),
        field("title", "Project title"),
        field("subtitle", "Subtitle"),
        field("description", "Project summary", "paragraphs"),
        field("metaDescription", "Search description", "text"),
        field("tags", "Tags", "string_list", help_text="One tag per line; the website displays up to eight."),
        field("discipline", "Discipline", help_text="Also helps classify the project on the All Projects page."),
        field("status", "Status", help_text="Use Completed or In Progress to include the project in those status filters."),
        field("timeline", "Timeline"),
        field(
            "projectType",
            "Project type",
            help_text="For filtering, use Civil Engineering, GIS, CAD / BIM, Design, or Personal.",
        ),
        field("role", "Your role"),
        field(
            "tools",
            "Tools",
            "string_list",
            help_text=(
                "One tool per line. AutoCAD, Civil 3D, Revit, QGIS, Excel, and Fusion 360 "
                "have named filters; other entries appear under Other."
            ),
        ),
    ],
    "Archive": [
        field("archive.visibility", "Archive visibility", "choice", choices=("private", "public"), default="private"),
        field("archive.featured", "Featured project", "bool", default=False),
        field("archive.currentlyWorking", "Currently working", "bool", default=False),
        field("archive.date", "Publication date", "date", help_text="YYYY-MM-DD"),
        field("archive.cardDescription", "Archive-card summary", "text"),
        *prefixed_fields("archive.thumbnail", GALLERY_IMAGE_FIELDS),
    ],
    "Hero": [
        *prefixed_fields("hero", GALLERY_IMAGE_FIELDS),
        field(
            "externalLinks",
            "Hero buttons / links",
            "record_list",
            help_text=(
                "Buttons shown beneath the project summary at the top of the page. "
                "Use these for a Notion page, live demo, GitHub repository, report, or similar link."
            ),
            fields=[
                field("label", "Button label", help_text="For example: View Notion page"),
                field("hint", "Small supporting text (optional)"),
                field("url", "Destination URL or path", help_text="Paste the full https:// link for an external page."),
                field("icon", "Icon (optional)", "path", media_dir="images"),
                field(
                    "style",
                    "Button style",
                    "choice",
                    choices=("", "primary"),
                    help_text="Choose primary for the more prominent filled button.",
                ),
                field("newTab", "Open in new tab", "bool", default=True),
            ],
        ),
    ],
    "Navigation": [
        field("archiveUrl", "Archive URL", default="../"),
        field("archiveLabel", "Archive label", default="Project archive"),
        field("archiveLinkText", "Archive link text", default="← All projects"),
        field("contactUrl", "Contact URL", default="../../contact-me/"),
        field("contactLabel", "Contact label", default="Have a project in mind?"),
        field("contactLinkText", "Contact link text", default="Get in touch →"),
        field("backLinkText", "Back-link text", default="← Back to all projects"),
    ],
    "Metadata": [
        field(
            "customMetadata",
            "Custom metadata",
            "key_value_list",
            fields=[field("label", "Label"), field("value", "Value")],
        ),
        field(
            "metadata",
            "Ordered metadata",
            "record_list",
            fields=[field("label", "Label"), field("value", "Value")],
        ),
    ],
}


UPDATE_FIELDS = [
    field("date", "Date", "date"),
    field("content", "Update text", "text"),
    field("visibility", "Visibility", "choice", choices=("public", "private"), default="public"),
]


BLOCK_TEMPLATES: dict[str, dict[str, Any]] = {
    "section": {"type": "section", "id": "new-section", "title": "New section", "intro": "", "blocks": []},
    "text": {"type": "text", "title": "", "content": ""},
    "heading": {"type": "heading", "level": 3, "text": "New heading"},
    "image": {"type": "image", "placeholder": "Project image", "alt": "Placeholder for project image", "size": "wide", "style": "framed"},
    "video": {"type": "video", "src": "", "controls": True, "autoplay": False, "loop": False, "muted": False, "preload": "metadata", "size": "wide"},
    "youtube": {"type": "youtube", "url": "", "title": "Project video", "size": "wide"},
    "gallery": {"type": "gallery", "columns": 2, "images": []},
    "two-column": {"type": "two-column", "ratio": "1-1", "columns": [{"blocks": []}, {"blocks": []}]},
    "three-column": {"type": "three-column", "columns": [{"blocks": []}, {"blocks": []}, {"blocks": []}]},
    "image-text": {"type": "image-text", "imagePosition": "left", "title": "", "content": "", "image": {"placeholder": "Supporting image", "alt": "Placeholder for supporting image"}},
    "process-step": {"type": "process-step", "title": "New process step", "content": "", "show": "", "image": {}},
    "callout": {"type": "callout", "variant": "", "title": "", "content": ""},
    "quote": {"type": "quote", "content": "", "source": ""},
    "stats": {"type": "stats", "items": []},
    "timeline": {"type": "timeline", "items": []},
    "comparison": {"type": "comparison", "left": {"label": "Before"}, "right": {"label": "After"}},
    "links": {"type": "links", "items": []},
    "download": {"type": "download", "label": "Download file", "file": "", "download": True},
    "divider": {"type": "divider"},
    "spacer": {"type": "spacer", "size": "medium"},
    "custom-html": {"type": "custom-html", "html": "<p>Trusted project-specific markup.</p>"},
    "margin-notes": {"type": "margin-notes", "label": "Project notes", "notes": []},
}


def new_block(block_type: str) -> dict[str, Any]:
    return deepcopy(BLOCK_TEMPLATES[block_type])

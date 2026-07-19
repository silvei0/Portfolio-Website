(() => {
    "use strict";

    const projectRoot = document.querySelector("[data-project-root]");

    if (!projectRoot) return;

    const projectSource = projectRoot.dataset.projectSrc || "./project.json";
    const allowedImageSizes = ["small", "medium", "large", "wide", "full"];
    const allowedAlignments = ["left", "centre", "center", "right"];
    const allowedImageStyles = ["plain", "framed", "taped", "polaroid", "paper"];
    const allowedPositions = ["normal", "offset-left", "offset-right"];
    const allowedSpacerSizes = ["small", "medium", "large"];
    const allowedColumnRatios = ["1-1", "2-1", "1-2"];

    const createElement = (tag, className, text) => {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined && text !== null) element.textContent = String(text);
        return element;
    };

    const hasValue = value => {
        if (Array.isArray(value)) return value.length > 0;
        return value !== undefined && value !== null && String(value).trim() !== "";
    };

    const slugify = value => String(value || "section")
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");

    const safeClassToken = value => String(value || "")
        .toLowerCase()
        .replace(/[^a-z0-9_-]/g, "");

    const addAllowedClass = (element, prefix, value, allowedValues) => {
        const normalised = value === "center" ? "centre" : safeClassToken(value);
        if (allowedValues.includes(normalised)) element.classList.add(`${prefix}${normalised}`);
    };

    const appendHeading = (parent, text, level = 3, className = "") => {
        if (!hasValue(text)) return null;
        const safeLevel = Math.min(6, Math.max(1, Number(level) || 3));
        const heading = createElement(`h${safeLevel}`, className, text);
        parent.append(heading);
        return heading;
    };

    const appendText = (parent, content, className = "") => {
        if (!hasValue(content)) return;
        const paragraphs = Array.isArray(content) ? content : [content];
        paragraphs.filter(hasValue).forEach(paragraphText => {
            parent.append(createElement("p", className, paragraphText));
        });
    };

    const appendList = (parent, items, ordered = false, className = "") => {
        if (!Array.isArray(items) || items.length === 0) return;
        const list = createElement(ordered ? "ol" : "ul", className);
        items.filter(hasValue).forEach(item => list.append(createElement("li", "", item)));
        if (list.children.length) parent.append(list);
    };

    const appendCaption = (figure, caption) => {
        if (hasValue(caption)) figure.append(createElement("figcaption", "", caption));
    };

    const setLinkAttributes = (link, url, openInNewTab) => {
        link.href = String(url);
        const isExternal = /^https?:\/\//i.test(String(url));
        if (openInNewTab === true || (openInNewTab !== false && isExternal)) {
            link.target = "_blank";
            link.rel = "noopener noreferrer";
        }
    };

    const applyImageOptions = (figure, imageData = {}) => {
        addAllowedClass(figure, "project-size--", imageData.size || "large", allowedImageSizes);
        addAllowedClass(figure, "project-align--", imageData.align || "centre", allowedAlignments);
        addAllowedClass(figure, "project-image-style--", imageData.style || "framed", allowedImageStyles);
        addAllowedClass(figure, "project-position--", imageData.position || "normal", allowedPositions);

        const rotation = Number.parseFloat(String(imageData.rotation || "0").replace("deg", ""));
        if (Number.isFinite(rotation)) {
            const restrainedRotation = Math.max(-6, Math.min(6, rotation));
            figure.style.setProperty("--project-rotation", `${restrainedRotation}deg`);
        }
    };

    const renderImageVisual = (imageData = {}, options = {}) => {
        if (hasValue(imageData.src)) {
            const image = createElement("img", options.imageClass || "project-block-image");
            image.src = imageData.src;
            if (imageData.decorative === true) {
                image.alt = "";
            } else if (hasValue(imageData.alt)) {
                image.alt = imageData.alt;
            } else {
                image.alt = "Project image";
                console.warn("Project renderer: a non-decorative image is missing alt text.", imageData);
            }
            image.loading = imageData.loading || "lazy";
            if (hasValue(imageData.width)) image.width = Number(imageData.width);
            if (hasValue(imageData.height)) image.height = Number(imageData.height);
            return image;
        }

        if (hasValue(imageData.placeholder)) {
            const placeholder = createElement("div", "project-media-placeholder");
            placeholder.setAttribute("role", "img");
            placeholder.setAttribute("aria-label", imageData.alt || imageData.placeholder);
            placeholder.append(createElement("span", "", imageData.placeholder));
            if (hasValue(imageData.placeholderHint)) {
                placeholder.append(createElement("small", "", imageData.placeholderHint));
            }
            return placeholder;
        }

        return null;
    };

    const renderFigure = (imageData = {}, className = "project-block project-image-block") => {
        const visual = renderImageVisual(imageData);
        if (!visual) return null;
        const figure = createElement("figure", className);
        applyImageOptions(figure, imageData);
        figure.append(visual);
        appendCaption(figure, imageData.caption);
        return figure;
    };

    const renderTextBlock = (block, context = {}) => {
        const wrapper = createElement("div", "project-block project-text-block");
        appendHeading(wrapper, block.title, context.headingLevel || 3);
        appendText(wrapper, block.content);
        appendList(wrapper, block.items, block.ordered === true, block.listStyle === "ticks" ? "project-tick-list" : "");
        return wrapper;
    };

    const renderHeadingBlock = (block, context = {}) => {
        return appendHeading(document.createDocumentFragment(), block.text || block.title, block.level || context.headingLevel || 3);
    };

    const renderImageBlock = block => renderFigure(block);

    const renderVideoBlock = block => {
        if (!hasValue(block.src)) return null;
        const figure = createElement("figure", "project-block project-video-block");
        addAllowedClass(figure, "project-size--", block.size || "wide", allowedImageSizes);

        const video = createElement("video", "project-video");
        video.src = block.src;
        video.controls = block.controls !== false;
        video.autoplay = block.autoplay === true;
        video.loop = block.loop === true;
        video.muted = block.muted === true;
        video.playsInline = true;
        video.preload = block.preload || "metadata";
        if (hasValue(block.poster)) video.poster = block.poster;

        if (block.captions && hasValue(block.captions.src)) {
            const track = createElement("track");
            track.kind = block.captions.kind || "captions";
            track.src = block.captions.src;
            track.srclang = block.captions.srclang || "en";
            track.label = block.captions.label || "English";
            if (block.captions.default === true) track.default = true;
            video.append(track);
        }

        figure.append(video);
        appendCaption(figure, block.caption);
        return figure;
    };

    const getYouTubeId = value => {
        try {
            const url = new URL(value);
            if (url.hostname.includes("youtu.be")) return url.pathname.slice(1).split("/")[0];
            if (url.hostname.includes("youtube.com")) {
                if (url.pathname.startsWith("/embed/")) return url.pathname.split("/")[2];
                return url.searchParams.get("v");
            }
        } catch (error) {
            console.warn("Project renderer: invalid YouTube URL.", value, error);
        }
        return null;
    };

    const renderYouTubeBlock = block => {
        const videoId = getYouTubeId(block.url);
        if (!videoId || !/^[a-zA-Z0-9_-]{6,}$/.test(videoId)) return null;
        const figure = createElement("figure", "project-block project-youtube-block");
        addAllowedClass(figure, "project-size--", block.size || "wide", allowedImageSizes);
        const frameWrapper = createElement("div", "project-youtube-frame");
        const iframe = createElement("iframe");
        iframe.src = `https://www.youtube-nocookie.com/embed/${videoId}`;
        iframe.title = block.title || block.caption || "Project video";
        iframe.loading = "lazy";
        iframe.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
        iframe.allowFullscreen = true;
        frameWrapper.append(iframe);
        figure.append(frameWrapper);
        appendCaption(figure, block.caption);
        return figure;
    };

    const renderGalleryBlock = block => {
        if (!Array.isArray(block.images) || block.images.length === 0) return null;
        const gallery = createElement("div", "project-block project-gallery-block");
        const columns = Math.max(1, Math.min(4, Number(block.columns) || 2));
        gallery.style.setProperty("--gallery-columns", columns);
        block.images.forEach(imageData => {
            const figure = renderFigure({ ...imageData, size: "full" }, "project-gallery-item project-image-style--framed");
            if (figure) gallery.append(figure);
        });
        return gallery;
    };

    const renderColumnsBlock = (block, columnCount, context = {}) => {
        if (!Array.isArray(block.columns) || block.columns.length === 0) return null;
        const wrapper = createElement("div", `project-block project-columns project-columns--${columnCount}`);
        if (columnCount === 2 && allowedColumnRatios.includes(block.ratio)) {
            wrapper.classList.add(`project-columns--${block.ratio}`);
        }
        block.columns.slice(0, columnCount).forEach(column => {
            const columnElement = createElement("div", "project-column");
            renderBlocksInto(columnElement, column.blocks, { ...context, nested: true, headingLevel: 3 });
            wrapper.append(columnElement);
        });
        return wrapper;
    };

    const renderImageTextBlock = block => {
        const wrapper = createElement("div", "project-block project-image-text");
        wrapper.classList.add(block.imagePosition === "right" ? "project-image-text--right" : "project-image-text--left");
        const figure = renderFigure(block.image || {}, "project-image-text-media project-image-style--framed");
        const copy = createElement("div", "project-image-text-copy");
        appendHeading(copy, block.title, 3);
        appendText(copy, block.content);
        if (figure) wrapper.append(figure);
        wrapper.append(copy);
        return wrapper;
    };

    const renderProcessStepBlock = block => {
        const step = createElement("article", "project-block project-process-step");
        const header = createElement("div", "project-process-step-header");
        if (hasValue(block.number)) header.append(createElement("span", "project-process-step-number", block.number));
        appendHeading(header, block.title, 3);
        step.append(header);
        appendText(step, block.content);
        if (hasValue(block.show)) {
            const evidence = createElement("small", "project-process-step-evidence");
            evidence.append(createElement("strong", "", "Show: "));
            evidence.append(document.createTextNode(block.show));
            step.append(evidence);
        }
        const figure = renderFigure(block.image || {}, "project-process-image project-image-style--framed");
        if (figure) step.append(figure);
        return step;
    };

    const renderCalloutBlock = block => {
        const callout = createElement("div", "project-block project-callout");
        if (hasValue(block.variant)) callout.classList.add(`project-callout--${safeClassToken(block.variant)}`);
        appendHeading(callout, block.title, 3);
        appendText(callout, block.content);
        return callout;
    };

    const renderQuoteBlock = block => {
        if (!hasValue(block.content)) return null;
        const quote = createElement("blockquote", "project-block project-quote-block");
        appendText(quote, block.content);
        if (hasValue(block.source)) quote.append(createElement("cite", "", block.source));
        return quote;
    };

    const renderStatsBlock = block => {
        if (!Array.isArray(block.items) || block.items.length === 0) return null;
        const list = createElement("dl", "project-block project-stats");
        block.items.forEach(item => {
            if (!hasValue(item.label) && !hasValue(item.value)) return;
            const wrapper = createElement("div", "project-stat");
            if (hasValue(item.label)) wrapper.append(createElement("dt", "", item.label));
            if (hasValue(item.value)) wrapper.append(createElement("dd", "", item.value));
            list.append(wrapper);
        });
        return list.children.length ? list : null;
    };

    const renderTimelineBlock = block => {
        if (!Array.isArray(block.items) || block.items.length === 0) return null;
        const list = createElement("ol", "project-block project-timeline");
        block.items.forEach(item => {
            const entry = createElement("li", "project-timeline-item");
            if (hasValue(item.date)) entry.append(createElement("span", "project-timeline-date", item.date));
            const copy = createElement("div", "project-timeline-copy");
            appendHeading(copy, item.title, 3);
            appendText(copy, item.content);
            entry.append(copy);
            list.append(entry);
        });
        return list;
    };

    const renderComparisonSide = (side, label) => {
        const card = createElement("article", "project-comparison-side");
        card.append(createElement("span", "project-comparison-label", label));
        appendHeading(card, side?.title, 3);
        if (hasValue(side?.image)) {
            const imageData = typeof side.image === "object"
                ? { ...side.image }
                : { src: side.image, alt: side.alt || side.title || label, caption: side.caption };
            const figure = renderFigure(imageData, "project-comparison-image project-image-style--framed");
            if (figure) card.append(figure);
        }
        appendText(card, side?.content);
        return card;
    };

    const renderComparisonBlock = block => {
        if (!block.left && !block.right) return null;
        const comparison = createElement("div", "project-block project-comparison");
        if (block.left) comparison.append(renderComparisonSide(block.left, block.left.label || "Option A"));
        if (block.right) comparison.append(renderComparisonSide(block.right, block.right.label || "Option B"));
        return comparison;
    };

    const renderLinksBlock = block => {
        if (!Array.isArray(block.items) || block.items.length === 0) return null;
        const wrapper = createElement("div", "project-block project-links-block");
        block.items.forEach(item => {
            if (!hasValue(item.label) || !hasValue(item.url)) return;
            const link = createElement("a", "project-action-link", item.label);
            setLinkAttributes(link, item.url, item.newTab);
            link.append(createElement("span", "", " ↗"));
            wrapper.append(link);
        });
        return wrapper.children.length ? wrapper : null;
    };

    const renderDownloadBlock = block => {
        if (!hasValue(block.label) || !hasValue(block.file)) return null;
        const wrapper = createElement("div", "project-block project-download-block");
        const link = createElement("a", "project-download-link", block.label);
        link.href = block.file;
        if (block.download !== false) link.setAttribute("download", block.filename || "");
        link.append(createElement("span", "", " ↓"));
        wrapper.append(link);
        return wrapper;
    };

    const renderDividerBlock = () => createElement("hr", "project-block project-divider");

    const renderSpacerBlock = block => {
        const spacer = createElement("div", "project-block project-spacer");
        spacer.setAttribute("aria-hidden", "true");
        addAllowedClass(spacer, "project-spacer--", block.size || "medium", allowedSpacerSizes);
        return spacer;
    };

    const renderCustomHtmlBlock = block => {
        if (!hasValue(block.html)) return null;
        const wrapper = createElement("div", "project-block project-custom-html");
        wrapper.innerHTML = block.html;
        return wrapper;
    };

    const renderMarginNotesBlock = block => {
        if (!Array.isArray(block.notes) || block.notes.length === 0) return null;
        const notes = createElement("aside", "project-margin-notes");
        notes.setAttribute("aria-label", block.label || "Project notes");
        block.notes.slice(0, 3).forEach(note => {
            if (!hasValue(note.text)) return;
            const wrapper = createElement("div", "project-margin-note");
            const image = createElement("img");
            image.src = note.image || "../../assets/blan-post-it.png";
            image.alt = "";
            wrapper.append(image, createElement("p", "", note.text));
            notes.append(wrapper);
        });
        return notes.children.length ? notes : null;
    };

    const renderSectionBlock = (block, context = {}) => {
        const section = createElement("section", "project-section paper-panel project-generated-section");
        section.id = safeClassToken(block.id) || slugify(block.title);
        appendHeading(section, block.title, 2);
        appendText(section, block.intro, "project-lead");
        if (hasValue(block.guide)) {
            const guide = createElement("p", "project-section-guide");
            guide.append(createElement("strong", "", "Include: "));
            guide.append(document.createTextNode(block.guide));
            section.append(guide);
        }
        renderBlocksInto(section, block.blocks, { ...context, nested: true, headingLevel: 3 });
        return section;
    };

    const blockRenderers = {
        section: renderSectionBlock,
        text: renderTextBlock,
        heading: renderHeadingBlock,
        image: renderImageBlock,
        video: renderVideoBlock,
        youtube: renderYouTubeBlock,
        gallery: renderGalleryBlock,
        "two-column": (block, context) => renderColumnsBlock(block, 2, context),
        "three-column": (block, context) => renderColumnsBlock(block, 3, context),
        "image-text": renderImageTextBlock,
        "process-step": renderProcessStepBlock,
        callout: renderCalloutBlock,
        quote: renderQuoteBlock,
        stats: renderStatsBlock,
        timeline: renderTimelineBlock,
        comparison: renderComparisonBlock,
        links: renderLinksBlock,
        download: renderDownloadBlock,
        divider: renderDividerBlock,
        spacer: renderSpacerBlock,
        "custom-html": renderCustomHtmlBlock,
        "margin-notes": renderMarginNotesBlock
    };

    const renderBlock = (block, context = {}) => {
        if (!block || typeof block !== "object") return null;
        const renderer = blockRenderers[block.type];
        if (!renderer) {
            console.warn(`Project renderer: unknown block type "${block.type}".`, block);
            return null;
        }
        const element = renderer(block, context);
        if (!element) return null;
        if (element.nodeType === Node.ELEMENT_NODE) {
            if (hasValue(block.id) && block.type !== "section") element.id = safeClassToken(block.id);
            if (hasValue(block.className)) {
                String(block.className).split(/\s+/).map(safeClassToken).filter(Boolean).forEach(token => element.classList.add(token));
            }
        }
        return element;
    };

    function renderBlocksInto(parent, blocks, context = {}) {
        if (!Array.isArray(blocks)) return;
        blocks.forEach((block, index) => {
            try {
                const element = renderBlock(block, context);
                if (!element) return;
                if (!context.nested && block.type !== "section" && !["divider", "spacer", "margin-notes"].includes(block.type)) {
                    element.classList.add("paper-panel", "project-section", "project-generated-section", "project-standalone-block");
                    if (!element.id) element.id = safeClassToken(block.id) || slugify(block.navTitle || block.title || `${block.type}-${index + 1}`);
                }
                parent.append(element);
            } catch (error) {
                console.error(`Project renderer: block ${index + 1} could not be rendered.`, block, error);
            }
        });
    }

    const createFact = (label, value, options = {}) => {
        if (!hasValue(value)) return null;
        const wrapper = createElement("div");
        wrapper.append(createElement("dt", "", label));
        const description = createElement("dd");
        if (options.status === true) {
            const status = createElement("span", `project-status project-status--${slugify(value)}`, value);
            description.append(status);
        } else {
            description.textContent = Array.isArray(value) ? value.join(", ") : value;
        }
        wrapper.append(description);
        return wrapper;
    };

    const renderFacts = project => {
        const facts = createElement("dl", "project-facts");
        facts.setAttribute("aria-label", "Project details");
        const standardFacts = [
            ["Discipline", project.discipline],
            ["Status", project.status, { status: true }],
            ["Timeline", project.timeline],
            ["Project type", project.projectType],
            ["Role", project.role],
            ["Tools", project.tools]
        ];
        standardFacts.forEach(([label, value, options]) => {
            const fact = createFact(label, value, options);
            if (fact) facts.append(fact);
        });

        if (project.customMetadata && typeof project.customMetadata === "object" && !Array.isArray(project.customMetadata)) {
            Object.entries(project.customMetadata).forEach(([label, value]) => {
                const fact = createFact(label, value);
                if (fact) facts.append(fact);
            });
        }

        if (Array.isArray(project.metadata)) {
            project.metadata.forEach(item => {
                const fact = createFact(item.label, item.value);
                if (fact) facts.append(fact);
            });
        }

        return facts.children.length ? facts : null;
    };

    const renderExternalLinks = links => {
        if (!Array.isArray(links) || links.length === 0) return null;
        const wrapper = createElement("div", "project-external-links");
        links.forEach(item => {
            if (!hasValue(item.label) || !hasValue(item.url)) return;
            const link = createElement("a", item.style === "primary" ? "project-plan-link" : "project-action-link");
            setLinkAttributes(link, item.url, item.newTab);
            if (hasValue(item.icon)) {
                const icon = createElement("img");
                icon.src = item.icon;
                icon.alt = "";
                link.append(icon);
            }
            const copy = createElement("span");
            copy.append(createElement("strong", "", item.label));
            if (hasValue(item.hint)) copy.append(createElement("small", "", item.hint));
            link.append(copy);
            wrapper.append(link);
        });
        return wrapper.children.length ? wrapper : null;
    };

    const renderHero = project => {
        const hero = createElement("header", "project-hero paper-panel");
        const copy = createElement("div", "project-hero-copy");
        appendHeading(copy, project.title || "Untitled project", 1);
        if (hasValue(project.subtitle)) copy.append(createElement("p", "project-subtitle", project.subtitle));
        appendText(copy, project.description, "project-summary");
        const externalLinks = renderExternalLinks(project.externalLinks);
        if (externalLinks) copy.append(externalLinks);
        hero.append(copy);

        const facts = renderFacts(project);
        if (facts) hero.append(facts);

        const heroData = project.hero || {};
        const heroVisual = renderImageVisual(heroData, { imageClass: "project-hero-image" });
        if (heroVisual) {
            const figure = createElement("figure", "project-hero-media");
            figure.append(heroVisual);
            appendCaption(figure, heroData.caption);
            hero.append(figure);
        }

        return hero;
    };

    const getNavigationItems = blocks => {
        if (!Array.isArray(blocks)) return [];
        return blocks.map((block, index) => {
            const title = block.navTitle || (block.type === "section" ? block.title : block.title);
            if (!hasValue(title) || block.hideFromContents === true) return null;
            return {
                id: safeClassToken(block.id) || slugify(title || `${block.type}-${index + 1}`),
                title
            };
        }).filter(Boolean);
    };

    const renderContents = items => {
        if (!items.length) return null;
        const aside = createElement("aside", "project-contents paper-panel");
        aside.setAttribute("aria-label", "On this page");
        aside.append(createElement("p", "", "On this page"));
        const list = createElement("ol");
        items.forEach(item => {
            const link = createElement("a", "", item.title);
            link.href = `#${item.id}`;
            const listItem = createElement("li");
            listItem.append(link);
            list.append(listItem);
        });
        aside.append(list);
        return aside;
    };

    const renderPagination = project => {
        const navigation = createElement("nav", "project-pagination paper-panel");
        navigation.setAttribute("aria-label", "Project navigation");

        const archive = createElement("a");
        archive.href = project.archiveUrl || "../";
        archive.append(createElement("span", "", project.archiveLabel || "Project archive"));
        archive.append(createElement("strong", "", project.archiveLinkText || "← All projects"));

        const contact = createElement("a");
        contact.href = project.contactUrl || "../../contact-me/";
        contact.append(createElement("span", "", project.contactLabel || "Have a project in mind?"));
        contact.append(createElement("strong", "", project.contactLinkText || "Get in touch →"));

        navigation.append(archive, contact);
        return navigation;
    };

    const updateDocumentMetadata = project => {
        const siteName = project.siteName || "Fiza Mansoor";
        document.title = hasValue(project.title) ? `${project.title} | ${siteName}` : siteName;
        const description = project.metaDescription || project.description;
        if (hasValue(description)) {
            let meta = document.querySelector('meta[name="description"]');
            if (!meta) {
                meta = createElement("meta");
                meta.name = "description";
                document.head.append(meta);
            }
            meta.content = description;
        }
    };

    const renderProject = project => {
        updateDocumentMetadata(project);
        projectRoot.replaceChildren();
        const backLink = createElement("a", "project-back-link", project.backLinkText || "← Back to all projects");
        backLink.href = project.archiveUrl || "../";
        projectRoot.append(backLink, renderHero(project));

        const layout = createElement("div", "project-layout");
        const navigationItems = getNavigationItems(project.blocks);
        const contents = renderContents(navigationItems);
        if (contents) layout.append(contents);
        else layout.classList.add("project-layout--without-contents");

        const story = createElement("div", "project-story");
        renderBlocksInto(story, project.blocks, { nested: false, headingLevel: 2 });
        layout.append(story);
        projectRoot.append(layout, renderPagination(project));
    };

    const renderLoadError = error => {
        console.error(`Project renderer: failed to load ${projectSource}.`, error);
        projectRoot.replaceChildren();
        const errorPanel = createElement("section", "paper-panel project-load-error");
        appendHeading(errorPanel, "This project could not be loaded", 1);
        appendText(errorPanel, "Check that project.json exists, contains valid JSON, and uses paths relative to this project folder.");
        projectRoot.append(errorPanel);
    };

    const loadProject = async () => {
        try {
            const response = await fetch(projectSource, { cache: "no-cache" });
            if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}`);
            const project = await response.json();
            if (!project || typeof project !== "object" || Array.isArray(project)) {
                throw new Error("project.json must contain one JSON object.");
            }
            renderProject(project);
            document.dispatchEvent(new CustomEvent("project:rendered", { detail: { project } }));
        } catch (error) {
            renderLoadError(error);
        }
    };

    loadProject();
})();
